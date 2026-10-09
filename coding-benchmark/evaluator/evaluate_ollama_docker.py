#!/usr/bin/env python3
"""
sage_evaluator - evaluate a local Ollama model against the coding benchmark.

Usage
-----
  # smoke test
  python evaluator.py --model qwen2.5-coder:7b --limit 20

  # full run (resumes automatically if interrupted)
  python evaluator.py --model qwen2.5-coder:7b

  # re-judge ALREADY GENERATED solutions with the checker system
  # (no model calls at all; writes a NEW file, never touches the old one)
  python evaluator.py --rescore results.jsonl --output results_validated.jsonl \
                      --model qwen2.5-coder:7b --checkers checker_specs.json

  # scan the dataset for problems that may need a checker (report only)
  python evaluator.py --scan-checkers --out-specs checker_specs.generated.json

Layout
------
  dataset.jsonl   input  (1 problem per line)
  evaluator.py    this file
  checkers.py     checker implementations
  validators/     optional problem-specific special/optimization judges
  results.jsonl   output (1 result per line, appended incrementally)

Scoring
-------
Every result carries TWO verdicts:

  strict_pass     normalized exact match against the reference output.
                  This is the ORIGINAL metric (Qwen 7B = 40.4%).
  validated_pass  the checker verdict. Identical to strict_pass for every
                  problem using the default `exact` checker, so the two
                  numbers only diverge where a checker was explicitly
                  declared.

Notes
-----
* Generated code is executed in a separate, killable subprocess with a hard
  timeout. Nothing is exec'd inside this process.
* Function tasks: `__name__` is "__solution__" so a model's
  `if __name__ == "__main__":` block does not run and block on input().
  Stray print() output is captured and discarded.
* stdin tasks: `__name__` is "__main__", stdin/stdout are real
  TextIOWrapper objects so `sys.stdin.buffer` / `sys.stdout.buffer` work.
* Resume is on by default: problem_ids already present in the output file
  for the same model are skipped.
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATASET = os.path.join(HERE, "dataset.jsonl")
DEFAULT_OUTPUT = os.path.join(HERE, "results.jsonl")
OLLAMA_URL = "http://localhost:11434/api/generate"

# marker so candidate stdout can never be mistaken for the worker's result
SENTINEL = "@@SAGE_RESULT@@"
# how much captured stdout the worker ships back for checker use
OUT_CAP = 200000
# how much output is embedded in the result JSON (kept small on purpose)
RESULT_OUT_CAP = 400

sys.path.insert(0, HERE)
import checkers  # noqa: E402


# --------------------------------------------------------------------------
# sandbox worker  (this file re-invoked as: python evaluator.py --_worker)
# --------------------------------------------------------------------------

def _norm(s):
    """Kept for backward compatibility; delegates to checkers.norm()."""
    return checkers.norm(s)


def _make_streams(input_text):
    """Build stdin/stdout objects that behave like the real ones.

    Using TextIOWrapper over BytesIO (instead of StringIO) means
    `sys.stdin.buffer.read()` and `sys.stdout.buffer.write()` work - a very
    common idiom in competitive-programming solutions. With StringIO those
    raise AttributeError and get misreported as the model's runtime error.
    """
    in_bytes = io.BytesIO(input_text.encode("utf-8"))
    stdin = io.TextIOWrapper(in_bytes, encoding="utf-8", newline=None)
    out_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(out_bytes, encoding="utf-8", newline="",
                              write_through=True)
    return stdin, stdout, out_bytes


def _drain(stdout, out_bytes):
    try:
        stdout.flush()
    except Exception:  # noqa: BLE001
        pass
    try:
        return out_bytes.getvalue().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def _worker_main():
    """Run one problem's tests against one candidate solution.

    stdin : {"task_type","code","tests","stop_on_mismatch","out_cap"}
    stdout: SENTINEL + json result (last such line wins)
    """
    sys.set_int_max_str_digits(1000000)
    job = json.load(sys.stdin)
    code, tests, task_type = job["code"], job["tests"], job["task_type"]
    stop_on_mismatch = job.get("stop_on_mismatch", True)
    out_cap = int(job.get("out_cap", OUT_CAP))

    out = {
        "status": "pass",
        "tests_total": len(tests),
        "tests_passed": 0,
        "error_type": None,
        "error_message": None,
        "first_failing_test": None,
        "per_test": [],          # only populated for stdin tasks
        "all_strict_pass": True,
    }

    def emit():
        print(SENTINEL + json.dumps(out))

    # 1. compile once - catches syntax errors before anything runs
    try:
        compiled = compile(code, "<candidate>", "exec")
    except SyntaxError as e:
        out.update(status="syntax_error", error_type="SyntaxError",
                   error_message=str(e)[:400], first_failing_test=0,
                   all_strict_pass=False)
        emit()
        return

    # ---------------- function tasks (behavior unchanged) ----------------
    if task_type == "function":
        g = {"__name__": "__solution__"}
        buf = io.StringIO()
        real_out, real_err = sys.stdout, sys.stderr
        sys.stdout = buf  # swallow stray print()
        sys.stderr = buf
        try:
            exec(compiled, g)
        except BaseException as e:
            sys.stdout, sys.stderr = real_out, real_err
            out.update(status="runtime_error", error_type=type(e).__name__,
                       error_message=str(e)[:400], first_failing_test=0,
                       all_strict_pass=False)
            emit()
            return
        sys.stdout, sys.stderr = real_out, real_err

        for i, t in enumerate(tests):
            buf = io.StringIO()
            sys.stdout, sys.stderr = buf, buf
            try:
                exec(compile(t, "<test>", "exec"), g)
                sys.stdout, sys.stderr = real_out, real_err
                out["tests_passed"] += 1
            except AssertionError as e:
                sys.stdout, sys.stderr = real_out, real_err
                out.update(status="wrong_answer", error_type="AssertionError",
                           error_message=str(e)[:400], first_failing_test=i,
                           all_strict_pass=False)
                emit()
                return
            except BaseException as e:
                sys.stdout, sys.stderr = real_out, real_err
                out.update(status="runtime_error", error_type=type(e).__name__,
                           error_message=str(e)[:400], first_failing_test=i,
                           all_strict_pass=False)
                emit()
                return
        emit()
        return

    # ---------------- stdin/stdout tasks ----------------
    for i, t in enumerate(tests):
        real_in, real_out, real_err = sys.stdin, sys.stdout, sys.stderr
        stdin_obj, stdout_obj, out_bytes = _make_streams(t["input"])
        sys.stdin, sys.stdout, sys.stderr = stdin_obj, stdout_obj, io.StringIO()
        g = {"__name__": "__main__"}  # stdin programs need main to run
        crashed = None
        try:
            exec(compiled, g)
        except SystemExit:
            pass
        except BaseException as e:
            crashed = e
        produced = _drain(stdout_obj, out_bytes)
        sys.stdin, sys.stdout, sys.stderr = real_in, real_out, real_err

        if crashed is not None:
            out.update(status="runtime_error", error_type=type(crashed).__name__,
                       error_message=str(crashed)[:400], first_failing_test=i,
                       all_strict_pass=False)
            emit()
            return

        # strict verdict computed here on the FULL output (no truncation)
        strict_ok = checkers.exact_equal(produced, t["expected"])
        if not strict_ok:
            out["all_strict_pass"] = False
            if out["first_failing_test"] is None:
                out["first_failing_test"] = i

        clipped = produced[:out_cap]
        out["per_test"].append({
            "strict": strict_ok,
            "out": clipped,
            "truncated": len(produced) > out_cap,
        })

        if strict_ok:
            out["tests_passed"] += 1
        elif stop_on_mismatch:
            # exact-checker problems keep the original fail-fast behavior
            out.update(status="output_mismatch", error_type="OutputMismatch",
                       error_message=("expected=%r got=%r"
                                      % (checkers.norm(t["expected"])[:150],
                                         checkers.norm(produced)[:150])))
            emit()
            return

    if not out["all_strict_pass"]:
        out["status"] = "output_mismatch"
        out["error_type"] = "OutputMismatch"
    emit()


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

FUNC_INSTR = (
    "You are an expert Python programmer.\n\n"
    "Solve the following problem.\n\n"
    "{prompt}\n\n"
    "Respond with ONE Python code block containing the complete solution "
    "(including any imports and the required function definition).\n"
    "Do not include tests, example usage, or explanation."
)

IO_INSTR = (
    "You are an expert Python programmer.\n\n"
    "Solve the following competitive-programming problem.\n\n"
    "{prompt}\n\n"
    "Write a COMPLETE Python program that reads from standard input and "
    "writes the answer to standard output.\n"
    "Respond with ONE Python code block only. "
    "Do not include tests, example usage, or explanation."
)


def build_prompt(rec):
    tmpl = FUNC_INSTR if rec["task_type"] == "function" else IO_INSTR
    return tmpl.format(prompt=rec["prompt"])


def ollama_generate(model, prompt, temperature, num_predict, num_ctx,
                    seed, timeout, retries=2):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "seed": seed,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=data,
                headers={"Content-Type": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
            body["_wall_s"] = round(time.time() - t0, 3)
            return body, None
        except Exception as e:  # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, str(e)[:200])
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    return None, last


# --------------------------------------------------------------------------
# code extraction  (logic unchanged except: prefer explicitly tagged python
# blocks, so a stray ```text example block cannot win just because it happens
# to be valid Python. Falls back to the original behavior.)
# --------------------------------------------------------------------------

FENCE_ANY_RE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)```",
                          re.DOTALL)
CODE_START_RE = re.compile(r"^\s*(import |from |def |class |if |for |while |"
                           r"with |try:|@|#!|print\()", re.MULTILINE)


def extract_code(text):
    """Pull the Python source out of a model response."""
    if not text:
        return ""
    tagged, untagged = [], []
    for lang, body in FENCE_ANY_RE.findall(text):
        if lang.lower() in ("python", "py", "python3"):
            tagged.append(body)
        elif lang == "":
            untagged.append(body)
    for group in (tagged, untagged):
        if not group:
            continue
        for b in group:
            try:
                compile(b, "<x>", "exec")
                return b.strip("\n")
            except SyntaxError:
                continue
        return max(group, key=len).strip("\n")

    # unfenced: maybe the whole response is code
    try:
        compile(text, "<x>", "exec")
        return text.strip("\n")
    except SyntaxError:
        pass
    # salvage from the first code-looking line
    m = CODE_START_RE.search(text)
    if m:
        cand = text[m.start():]
        lines = cand.split("\n")
        while lines:
            snippet = "\n".join(lines)
            try:
                compile(snippet, "<x>", "exec")
                return snippet.strip("\n")
            except SyntaxError:
                lines.pop()
    return ""


# --------------------------------------------------------------------------
# execution + checking
# --------------------------------------------------------------------------

def _parse_worker_output(stdout_text):
    for line in reversed((stdout_text or "").split("\n")):
        if line.startswith(SENTINEL):
            try:
                return json.loads(line[len(SENTINEL):])
            except Exception:  # noqa: BLE001
                return None
    return None


def run_candidate(code, rec, timeout, spec):
    """Execute the candidate and apply the problem's checker.

    Returns a result dict with strict_pass / validated_pass and a status.
    """
    ctype = spec.get("type", "exact")
    stop_on_mismatch = (ctype == "exact")
    job = {"task_type": rec["task_type"], "code": code, "tests": rec["tests"],
           "stop_on_mismatch": stop_on_mismatch, "out_cap": OUT_CAP}
    base = {"tests_total": len(rec["tests"]), "tests_passed": 0,
            "error_type": None, "error_message": None,
            "first_failing_test": None,
            "checker": {"type": ctype, "verdict": None, "detail": None}}
    try:
        p = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--_worker"],
            input=json.dumps(job), capture_output=True, text=True,
            timeout=timeout)
    except subprocess.TimeoutExpired:
        base.update(status="timeout", error_type="Timeout",
                    error_message="exceeded %ss" % timeout,
                    strict_pass=False, validated_pass=False)
        return base

    w = _parse_worker_output(p.stdout)
    if w is None:
        base.update(status="runtime_error", error_type="WorkerCrash",
                    error_message=((p.stderr or "")[-300:] or "no worker output"),
                    strict_pass=False, validated_pass=False)
        return base

    strict_pass = bool(w.get("all_strict_pass"))
    res = {
        "tests_total": w.get("tests_total", len(rec["tests"])),
        "tests_passed": w.get("tests_passed", 0),
        "error_type": w.get("error_type"),
        "error_message": w.get("error_message"),
        "first_failing_test": w.get("first_failing_test"),
        "strict_pass": strict_pass,
        "checker": {"type": ctype, "verdict": None, "detail": None},
    }

    # hard failures are never checker-recoverable
    if w["status"] in ("syntax_error", "runtime_error"):
        res.update(status=w["status"], strict_pass=False, validated_pass=False)
        return res

    # function tasks: assertions are the judge; no output checker applies
    if rec["task_type"] == "function":
        res.update(status=w["status"], validated_pass=(w["status"] == "pass"))
        res["checker"] = {"type": "assertions", "verdict": w["status"],
                          "detail": None}
        return res

    # stdin tasks -------------------------------------------------------
    if strict_pass:
        res.update(status="pass", validated_pass=True)
        res["checker"].update(verdict="pass", detail="strict exact match")
        return res

    if ctype == "exact":
        res.update(status="output_mismatch", validated_pass=False)
        res["checker"].update(verdict="output_mismatch", detail="exact mismatch")
        _attach_io(res, rec, w)
        return res

    # non-exact checker: judge each test independently
    per = w.get("per_test") or []
    worst = None
    detail = None
    idx = None
    npass = 0
    for i, t in enumerate(rec["tests"]):
        if i >= len(per):
            worst, detail, idx = checkers.V_CHECKER_ERROR, "missing captured output", i
            break
        try:
            verdict, why = checkers.run_checker(
                spec, t["input"], per[i]["out"], t["expected"],
                truncated=per[i].get("truncated", False))
        except Exception as e:  # noqa: BLE001
            verdict, why = checkers.V_CHECKER_ERROR, "%s: %s" % (type(e).__name__, str(e)[:200])
        if verdict == checkers.V_PASS:
            npass += 1
            continue
        worst, detail, idx = verdict, why, i
        break

    res["tests_passed"] = npass
    if worst is None:
        res.update(status="pass", validated_pass=True, first_failing_test=None)
        res["checker"].update(verdict="pass",
                              detail="validated by %s checker" % ctype)
        return res

    res.update(status=worst, validated_pass=False, first_failing_test=idx)
    res["checker"].update(verdict=worst, detail=detail)
    _attach_io(res, rec, w)
    return res


def _attach_io(res, rec, w):
    """Attach small clipped candidate/expected output for debugging."""
    i = res.get("first_failing_test")
    per = w.get("per_test") or []
    if i is None or i >= len(per):
        return
    res["candidate_output"] = checkers.norm(per[i].get("out", ""))[:RESULT_OUT_CAP]
    if res["checker"]["type"] in ("exact", "tokens", "float"):
        res["expected_output"] = checkers.norm(rec["tests"][i]["expected"])[:RESULT_OUT_CAP]


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def _vpass(r):
    """validated_pass with backward compatibility for pre-checker rows."""
    res = r["results"]
    if "validated_pass" in res:
        return bool(res["validated_pass"])
    return bool(res.get("passed"))


def _spass(r):
    """strict_pass with backward compatibility (old rows: passed == strict)."""
    res = r["results"]
    if "strict_pass" in res:
        return bool(res["strict_pass"])
    return bool(res.get("passed"))


def summarize(rows, model, title="RESULTS"):
    n = len(rows)
    if not n:
        print("no results yet")
        return {}
    strict = sum(1 for r in rows if _spass(r))
    valid = sum(1 for r in rows if _vpass(r))
    status = Counter(r["results"]["status"] for r in rows)
    ctypes = Counter((r["results"].get("checker") or {}).get("type", "exact")
                     for r in rows if r["task_type"] == "stdin_stdout")

    by_src = defaultdict(lambda: [0, 0, 0])
    by_diff = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        for bucket, key in ((by_src, r["source"]),
                            (by_diff, str(r["human_difficulty"]))):
            b = bucket[key]
            b[2] += 1
            b[0] += 1 if _spass(r) else 0
            b[1] += 1 if _vpass(r) else 0

    gen_t = [r["run_meta"]["generation_time_s"] for r in rows
             if r["run_meta"].get("generation_time_s")]
    tot_tok = sum(r["run_meta"].get("total_tokens") or 0 for r in rows)

    def c(k):
        return status.get(k, 0)

    print("\n" + "=" * 68)
    print("%s | MODEL: %s" % (title, model))
    print("=" * 68)
    print("problems evaluated        : %d" % n)
    print("strict pass@1 (reference) : %d/%d  (%.1f%%)" % (strict, n, 100.0 * strict / n))
    print("validated pass@1 (checker): %d/%d  (%.1f%%)" % (valid, n, 100.0 * valid / n))
    print("difference                : %+d problems" % (valid - strict))
    print("\nfailure / status breakdown")
    for k in ("pass", "wrong_answer", "output_mismatch", "runtime_error",
              "syntax_error", "timeout", "no_code", "generation_error",
              "checker_error", "checker_missing"):
        if status.get(k):
            print("  %-18s %5d  (%.1f%%)" % (k, status[k], 100.0 * status[k] / n))
    other = set(status) - {"pass", "wrong_answer", "output_mismatch",
                           "runtime_error", "syntax_error", "timeout",
                           "no_code", "generation_error", "checker_error",
                           "checker_missing"}
    for k in sorted(other):
        print("  %-18s %5d" % (k, status[k]))

    print("\nchecker usage (stdin/stdout problems)")
    for k in sorted(ctypes):
        print("  %-18s %5d" % (k, ctypes[k]))

    print("\nby source            strict        validated")
    for k in sorted(by_src):
        s, v, t = by_src[k]
        print("  %-16s %4d/%-4d(%5.1f%%) %4d/%-4d(%5.1f%%)"
              % (k, s, t, 100.0 * s / t, v, t, 100.0 * v / t))
    print("\nby difficulty        strict        validated")
    for k in sorted(by_diff):
        s, v, t = by_diff[k]
        print("  %-16s %4d/%-4d(%5.1f%%) %4d/%-4d(%5.1f%%)"
              % (k, s, t, 100.0 * s / t, v, t, 100.0 * v / t))
    if gen_t:
        print("\ngeneration time    : avg %.1fs  total %.1f min"
              % (sum(gen_t) / len(gen_t), sum(gen_t) / 60.0))
    print("tokens generated   : %d" % tot_tok)
    print("=" * 68)

    return {
        "model": model,
        "problems_evaluated": n,
        "strict_passed": strict,
        "strict_pass_rate": round(strict / n, 4),
        "validated_passed": valid,
        "validated_pass_rate": round(valid / n, 4),
        "status_counts": dict(status),
        "checker_type_counts": dict(ctypes),
        "n_exact_checks": ctypes.get("exact", 0),
        "n_float_checks": ctypes.get("float", 0),
        "n_token_checks": ctypes.get("tokens", 0),
        "n_special_checks": ctypes.get("special", 0),
        "n_optimization_checks": ctypes.get("optimization", 0),
        "n_checker_missing": c("checker_missing"),
        "n_checker_error": c("checker_error"),
        "n_runtime_error": c("runtime_error"),
        "n_syntax_error": c("syntax_error"),
        "n_timeout": c("timeout"),
        "n_no_code": c("no_code"),
        "n_generation_error": c("generation_error"),
        "by_source": {k: {"strict_passed": v[0], "validated_passed": v[1],
                          "total": v[2],
                          "strict_pass_rate": round(v[0] / v[2], 4),
                          "validated_pass_rate": round(v[1] / v[2], 4)}
                      for k, v in by_src.items()},
        "by_difficulty": {k: {"strict_passed": v[0], "validated_passed": v[1],
                              "total": v[2],
                              "strict_pass_rate": round(v[0] / v[2], 4),
                              "validated_pass_rate": round(v[1] / v[2], 4)}
                          for k, v in by_diff.items()},
        "total_tokens_generated": tot_tok,
        "avg_generation_time_s": round(sum(gen_t) / len(gen_t), 2) if gen_t else None,
    }


# --------------------------------------------------------------------------
# dataset / spec helpers
# --------------------------------------------------------------------------

def load_dataset(path, sources=None):
    problems = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                problems.append(json.loads(line))
    if sources:
        problems = [p for p in problems if p["source"] in sources]
    return problems


def scan_checkers(problems, out_path):
    """Report which problems MIGHT need a checker. Changes no verdicts.

    * float specs are emitted ONLY when the statement states a tolerance
      explicitly (the matching sentence is recorded as evidence).
    * multi-valid-output phrasing is recorded as a REVIEW FLAG only. No
      special judge is invented, and nothing is auto-applied.
    """
    specs = {}
    flags = []
    n_tol = n_multi = 0
    for p in problems:
        if p["task_type"] != "stdin_stdout":
            continue
        prompt = p.get("prompt", "")
        exp, evidence = checkers.detect_tolerance(prompt)
        if exp is not None:
            tol = 10.0 ** (-exp)
            specs[p["problem_id"]] = {
                "type": "float", "abs_tol": tol, "rel_tol": tol,
                "evidence": evidence[:300],
            }
            n_tol += 1
        phrase = checkers.detect_multi_output(prompt)
        if phrase:
            n_multi += 1
            flags.append({"problem_id": p["problem_id"], "source": p["source"],
                          "phrase": phrase,
                          "status": "NEEDS_SPECIAL_JUDGE_REVIEW"})
    doc = {
        "_README": (
            "Generated by --scan-checkers. REVIEW BEFORE USE. "
            "float entries were derived from an explicitly stated tolerance "
            "in the problem statement (see 'evidence'). Entries under "
            "_needs_review are NOT applied: they are candidates that may "
            "require a hand-written special judge in validators/. "
            "Pass this file with --checkers to activate the float specs."),
        "_needs_review": flags,
    }
    doc.update(specs)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    print("scanned %d stdin/stdout problems" % sum(
        1 for p in problems if p["task_type"] == "stdin_stdout"))
    print("  explicit float tolerance found : %d  (float specs written)" % n_tol)
    print("  multi-valid-output phrasing    : %d  (flagged for review only)" % n_multi)
    print("wrote %s" % out_path)
    return doc


# --------------------------------------------------------------------------
# rescore: re-judge stored solutions without calling the model
# --------------------------------------------------------------------------

def rescore(args, sidecar):
    problems = {p["problem_id"]: p for p in load_dataset(args.dataset, args.sources)}
    src_path = args.rescore
    if os.path.abspath(src_path) == os.path.abspath(args.output):
        print("ERROR: --output must differ from --rescore (never overwrite history)")
        return 2
    rows = []
    with open(src_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    rows = [r for r in rows
            if r["run_meta"]["model"] == args.model and r["problem_id"] in problems]
    if args.limit:
        rows = rows[:args.limit]
    print("rescoring %d stored results from %s" % (len(rows), src_path))
    print("output    : %s  (source file is NOT modified)\n" % args.output)

    out_rows = []
    changed = []
    with open(args.output, "w", encoding="utf-8") as fout:
        for i, old in enumerate(rows, 1):
            pid = old["problem_id"]
            rec = problems.get(pid)
            oldres = old["results"]
            if rec is None:
                continue
            code = oldres.get("extracted_code") or ""
            spec = checkers.resolve_spec(rec, sidecar)
            if oldres["status"] in ("generation_error", "no_code") or not code.strip():
                res = dict(oldres)
                res.setdefault("strict_pass", False)
                res["validated_pass"] = False
                res["checker"] = {"type": spec.get("type", "exact"),
                                  "verdict": "not_run", "detail": oldres["status"]}
            else:
                res = run_candidate(code, rec, args.timeout, spec)
                res["extracted_code"] = code
                res["passed"] = res["validated_pass"]
            row = dict(old)
            row["results"] = res
            meta = dict(old.get("run_meta") or {})
            meta["rescored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            meta["rescore_source"] = os.path.basename(src_path)
            row["run_meta"] = meta
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            out_rows.append(row)
            if bool(oldres.get("passed")) != bool(res.get("validated_pass")):
                changed.append((pid, oldres["status"], res["status"]))
            if i % 100 == 0:
                print("  %d/%d" % (i, len(rows)), flush=True)

    print("\nverdict changes vs stored results: %d" % len(changed))
    for pid, a, b in changed[:40]:
        print("   %-38s %-16s -> %s" % (pid, a, b))
    if len(changed) > 40:
        print("   ... %d more" % (len(changed) - 40))
    s = summarize(out_rows, args.model, title="RESCORED")
    if args.summary_out and s:
        json.dump(s, open(args.summary_out, "w", encoding="utf-8"), indent=2)
        print("summary written to %s" % args.summary_out)
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Evaluate an Ollama model on the coding benchmark.")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--limit", type=int, default=None,
                    help="evaluate at most N problems")
    ap.add_argument("--sources", nargs="*", default=None,
                    choices=["mbpp", "humaneval_plus", "apps", "codecontests"])
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="seconds allowed for executing a candidate solution")
    ap.add_argument("--gen-timeout", type=float, default=600.0,
                    help="seconds allowed for one Ollama generation")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--num-predict", type=int, default=1024)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--checkers", default=None,
                    help="JSON sidecar mapping problem_id -> checker spec")
    ap.add_argument("--rescore", default=None,
                    help="re-judge stored results from this file (no model calls)")
    ap.add_argument("--scan-checkers", action="store_true",
                    help="report problems that may need a checker; writes specs")
    ap.add_argument("--out-specs", default=os.path.join(HERE, "checker_specs.generated.json"))
    ap.add_argument("--no-resume", action="store_true",
                    help="ignore existing results and start over")
    ap.add_argument("--keep-response", action="store_true",
                    help="store the full raw model response in results.jsonl")
    ap.add_argument("--summary-out", default=None,
                    help="also write the summary as JSON to this path")
    ap.add_argument("--report", action="store_true",
                    help="only re-print the summary of an existing results file")
    ap.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args._worker:
        _worker_main()
        return

    try:
        sidecar = checkers.load_sidecar(args.checkers)
    except Exception as e:  # noqa: BLE001
        print("ERROR loading --checkers: %s" % e)
        sys.exit(2)
    if args.checkers:
        print("loaded %d checker specs from %s" % (len(sidecar), args.checkers))

    # ---- scan mode
    if args.scan_checkers:
        scan_checkers(load_dataset(args.dataset, args.sources), args.out_specs)
        return

    # ---- rescore mode
    if args.rescore:
        sys.exit(rescore(args, sidecar))

    # ---- report-only mode
    if args.report:
        rows = [json.loads(l) for l in open(args.output, encoding="utf-8") if l.strip()]
        rows = [r for r in rows if r["run_meta"]["model"] == args.model]
        summarize(rows, args.model)
        return

    problems = load_dataset(args.dataset, args.sources)

    # ---- resume
    done = set()
    existing = []
    if os.path.exists(args.output) and not args.no_resume:
        with open(args.output, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                existing.append(r)
                if r["run_meta"]["model"] == args.model:
                    done.add(r["problem_id"])
    elif args.no_resume and os.path.exists(args.output):
        os.remove(args.output)

    todo = [p for p in problems if p["problem_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]

    print("model     : %s" % args.model)
    print("dataset   : %s (%d problems after filters)" % (args.dataset, len(problems)))
    print("already   : %d done for this model" % len(done))
    print("to run    : %d" % len(todo))
    print("output    : %s\n" % args.output)

    session_rows = []
    t_start = time.time()
    fout = open(args.output, "a", encoding="utf-8")
    try:
        for i, rec in enumerate(todo, 1):
            prompt = build_prompt(rec)
            spec = checkers.resolve_spec(rec, sidecar)

            body, err = ollama_generate(
                args.model, prompt, args.temperature, args.num_predict,
                args.num_ctx, args.seed, args.gen_timeout)

            if body is None:
                res = {"status": "generation_error", "passed": False,
                       "strict_pass": False, "validated_pass": False,
                       "tests_total": len(rec["tests"]), "tests_passed": 0,
                       "error_type": "OllamaError", "error_message": err,
                       "first_failing_test": None, "extracted_code": "",
                       "checker": {"type": spec.get("type", "exact"),
                                   "verdict": "not_run", "detail": None}}
                meta = {"model": args.model, "generation_time_s": None,
                        "prompt_tokens": None, "completion_tokens": None,
                        "total_tokens": None, "execution_time_s": None}
            else:
                text = body.get("response", "")
                code = extract_code(text)
                gen_s = round(body.get("total_duration", 0) / 1e9, 3) or body["_wall_s"]

                if not code.strip():
                    res = {"status": "no_code", "tests_total": len(rec["tests"]),
                           "tests_passed": 0, "error_type": "NoCodeExtracted",
                           "error_message": text[:300], "first_failing_test": None,
                           "strict_pass": False, "validated_pass": False,
                           "checker": {"type": spec.get("type", "exact"),
                                       "verdict": "not_run", "detail": None}}
                    exec_s = 0.0
                else:
                    t0 = time.time()
                    res = run_candidate(code, rec, args.timeout, spec)
                    exec_s = round(time.time() - t0, 3)

                res["passed"] = bool(res.get("validated_pass"))
                res["extracted_code"] = code
                if args.keep_response:
                    res["raw_response"] = text

                pt = body.get("prompt_eval_count")
                ct = body.get("eval_count")
                meta = {
                    "model": args.model,
                    "generation_time_s": gen_s,
                    "execution_time_s": exec_s,
                    "prompt_tokens": pt,
                    "completion_tokens": ct,
                    "total_tokens": (pt or 0) + (ct or 0),
                    "tokens_per_s": (round(ct / (body.get("eval_duration", 1) / 1e9), 1)
                                     if ct and body.get("eval_duration") else None),
                }

            meta.update({
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "temperature": args.temperature,
                "seed": args.seed,
                "num_predict": args.num_predict,
                "num_ctx": args.num_ctx,
                "exec_timeout_s": args.timeout,
                "checker_specs": os.path.basename(args.checkers) if args.checkers else None,
            })

            row = {
                "problem_id": rec["problem_id"],
                "source": rec["source"],
                "task_type": rec["task_type"],
                "human_difficulty": rec["human_difficulty"],
                "results": res,
                "run_meta": meta,
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            os.fsync(fout.fileno())
            session_rows.append(row)

            npass = sum(1 for r in session_rows if r["results"].get("validated_pass"))
            elapsed = time.time() - t_start
            eta = (elapsed / i) * (len(todo) - i)
            print("[%4d/%d] %-28s %-16s pass=%d/%d (%.1f%%)  %.1fs  eta %.0fm"
                  % (i, len(todo), rec["problem_id"], res["status"], npass, i,
                     100.0 * npass / i, meta.get("generation_time_s") or 0, eta / 60),
                  flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted - results so far are saved; rerun the same command to resume")
    finally:
        fout.close()

    all_rows = [r for r in existing if r["run_meta"]["model"] == args.model] + session_rows
    s = summarize(all_rows, args.model)
    if args.summary_out and s:
        json.dump(s, open(args.summary_out, "w", encoding="utf-8"), indent=2)
        print("summary written to %s" % args.summary_out)


if __name__ == "__main__":
    main()
