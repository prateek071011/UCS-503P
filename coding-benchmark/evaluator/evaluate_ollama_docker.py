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



def _norm(s):
    """Normalize stdout for comparison: strip trailing spaces per line,
    drop trailing blank lines."""
    lines = s.replace("\r\n", "\n").split("\n")
    lines = [ln.rstrip() for ln in lines]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _worker_main():
    """Run one problem's tests against one candidate solution.

    stdin : {"task_type","code","tests"}
    stdout: {"status","tests_total","tests_passed","error_type",
             "error_message","first_failing_test"}
    """
    sys.set_int_max_str_digits(1000000)
    job = json.load(sys.stdin)
    code, tests, task_type = job["code"], job["tests"], job["task_type"]

    out = {
        "status": "pass",
        "tests_total": len(tests),
        "tests_passed": 0,
        "error_type": None,
        "error_message": None,
        "first_failing_test": None,
    }


    try:
        compiled = compile(code, "<candidate>", "exec")
    except SyntaxError as e:
        out.update(status="syntax_error", error_type="SyntaxError",
                   error_message=str(e)[:400], first_failing_test=0)
        print(json.dumps(out))
        return

    if task_type == "function":
        # exec the module body once, then run each assertion in that namespace
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
                       error_message=str(e)[:400], first_failing_test=0)
            print(json.dumps(out))
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
                           error_message=str(e)[:400], first_failing_test=i)
                print(json.dumps(out))
                return
            except BaseException as e:
                sys.stdout, sys.stderr = real_out, real_err
                out.update(status="runtime_error", error_type=type(e).__name__,
                           error_message=str(e)[:400], first_failing_test=i)
                print(json.dumps(out))
                return

    else:  # stdin_stdout
        for i, t in enumerate(tests):
            buf = io.StringIO()
            real_in, real_out, real_err = sys.stdin, sys.stdout, sys.stderr
            sys.stdin = io.StringIO(t["input"])
            sys.stdout, sys.stderr = buf, io.StringIO()
            g = {"__name__": "__main__"}  # stdin programs need main to run
            try:
                exec(compiled, g)
                sys.stdin, sys.stdout, sys.stderr = real_in, real_out, real_err
            except SystemExit:
                sys.stdin, sys.stdout, sys.stderr = real_in, real_out, real_err
            except BaseException as e:
                sys.stdin, sys.stdout, sys.stderr = real_in, real_out, real_err
                out.update(status="runtime_error", error_type=type(e).__name__,
                           error_message=str(e)[:400], first_failing_test=i)
                print(json.dumps(out))
                return
            if _norm(buf.getvalue()) != _norm(t["expected"]):
                out.update(status="wrong_answer", error_type="OutputMismatch",
                           error_message=("expected=%r got=%r" %
                                          (_norm(t["expected"])[:150],
                                           _norm(buf.getvalue())[:150])),
                           first_failing_test=i)
                print(json.dumps(out))
                return
            out["tests_passed"] += 1

    print(json.dumps(out))


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
# code extraction
# --------------------------------------------------------------------------

FENCE_RE = re.compile(r"```[ \t]*(?:python|py|python3)?[ \t]*\r?\n(.*?)```",
                      re.DOTALL | re.IGNORECASE)
CODE_START_RE = re.compile(r"^\s*(import |from |def |class |if |for |while |"
                           r"with |try:|@|#!|print\()", re.MULTILINE)


def extract_code(text):
    """Pull the Python source out of a model response."""
    if not text:
        return ""
    blocks = FENCE_RE.findall(text)
    if blocks:
        # prefer the first block that compiles; else the longest one
        for b in blocks:
            try:
                compile(b, "<x>", "exec")
                return b.strip("\n")
            except SyntaxError:
                continue
        return max(blocks, key=len).strip("\n")

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
        # drop a trailing prose tail if it breaks compilation
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
# execution driver
# --------------------------------------------------------------------------

def run_candidate(code, rec, timeout):
    job = {"task_type": rec["task_type"], "code": code, "tests": rec["tests"]}
    try:
        p = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--_worker"],
            input=json.dumps(job), capture_output=True, text=True,
            timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "tests_total": len(rec["tests"]),
                "tests_passed": 0, "error_type": "Timeout",
                "error_message": "exceeded %ss" % timeout,
                "first_failing_test": None}
    line = (p.stdout or "").strip().split("\n")[-1] if p.stdout else ""
    try:
        return json.loads(line)
    except Exception:  # worker crashed hard (segfault, MemoryError, ...)
        return {"status": "runtime_error", "tests_total": len(rec["tests"]),
                "tests_passed": 0, "error_type": "WorkerCrash",
                "error_message": ((p.stderr or "")[-300:] or "no output"),
                "first_failing_test": None}


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def summarize(rows, model):
    n = len(rows)
    if not n:
        print("no results yet")
        return {}
    passed = sum(1 for r in rows if r["results"]["passed"])
    status = Counter(r["results"]["status"] for r in rows)
    by_src = defaultdict(lambda: [0, 0])
    by_diff = defaultdict(lambda: [0, 0])
    for r in rows:
        s = by_src[r["source"]]
        s[1] += 1
        s[0] += 1 if r["results"]["passed"] else 0
        d = by_diff[str(r["human_difficulty"])]
        d[1] += 1
        d[0] += 1 if r["results"]["passed"] else 0

    gen_t = [r["run_meta"]["generation_time_s"] for r in rows
             if r["run_meta"].get("generation_time_s")]
    tot_tok = sum(r["run_meta"].get("total_tokens") or 0 for r in rows)

    print("\n" + "=" * 62)
    print("MODEL: %s" % model)
    print("=" * 62)
    print("problems evaluated : %d" % n)
    print("pass@1             : %d/%d  (%.1f%%)" % (passed, n, 100.0 * passed / n))
    print("\nstatus breakdown")
    for k, v in status.most_common():
        print("  %-16s %5d  (%.1f%%)" % (k, v, 100.0 * v / n))
    print("\nby source")
    for k in sorted(by_src):
        p, t = by_src[k]
        print("  %-16s %4d/%-4d  (%.1f%%)" % (k, p, t, 100.0 * p / t))
    print("\nby difficulty")
    for k in sorted(by_diff):
        p, t = by_diff[k]
        print("  %-16s %4d/%-4d  (%.1f%%)" % (k, p, t, 100.0 * p / t))
    if gen_t:
        print("\ngeneration time    : avg %.1fs  total %.1f min"
              % (sum(gen_t) / len(gen_t), sum(gen_t) / 60.0))
    print("tokens generated   : %d" % tot_tok)
    print("=" * 62)

    return {
        "model": model,
        "problems_evaluated": n,
        "passed": passed,
        "pass_rate": round(passed / n, 4),
        "status_counts": dict(status),
        "by_source": {k: {"passed": v[0], "total": v[1],
                          "pass_rate": round(v[0] / v[1], 4)}
                      for k, v in by_src.items()},
        "by_difficulty": {k: {"passed": v[0], "total": v[1],
                              "pass_rate": round(v[0] / v[1], 4)}
                          for k, v in by_diff.items()},
        "total_tokens_generated": tot_tok,
        "avg_generation_time_s": round(sum(gen_t) / len(gen_t), 2) if gen_t else None,
    }


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

    # ---- report-only mode
    if args.report:
        rows = [json.loads(l) for l in open(args.output, encoding="utf-8") if l.strip()]
        rows = [r for r in rows if r["run_meta"]["model"] == args.model]
        summarize(rows, args.model)
        return

    # ---- load dataset
    problems = []
    with open(args.dataset, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                problems.append(json.loads(line))
    if args.sources:
        problems = [p for p in problems if p["source"] in args.sources]

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

            body, err = ollama_generate(
                args.model, prompt, args.temperature, args.num_predict,
                args.num_ctx, args.seed, args.gen_timeout)

            if body is None:
                res = {"status": "generation_error", "passed": False,
                       "tests_total": len(rec["tests"]), "tests_passed": 0,
                       "error_type": "OllamaError", "error_message": err,
                       "first_failing_test": None, "extracted_code": ""}
                meta = {"model": args.model, "generation_time_s": None,
                        "prompt_tokens": None, "completion_tokens": None,
                        "total_tokens": None, "execution_time_s": None}
            else:
                text = body.get("response", "")
                code = extract_code(text)
                gen_s = round(body.get("total_duration", 0) / 1e9, 3) or body["_wall_s"]

                if not code.strip():
                    exec_res = {"status": "no_code", "tests_total": len(rec["tests"]),
                                "tests_passed": 0, "error_type": "NoCodeExtracted",
                                "error_message": text[:300], "first_failing_test": None}
                    exec_s = 0.0
                else:
                    t0 = time.time()
                    exec_res = run_candidate(code, rec, args.timeout)
                    exec_s = round(time.time() - t0, 3)

                res = dict(exec_res)
                res["passed"] = res["status"] == "pass"
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

            npass = sum(1 for r in session_rows if r["results"]["passed"])
            elapsed = time.time() - t_start
            rate = elapsed / i
            eta = rate * (len(todo) - i)
            print("[%4d/%d] %-28s %-15s pass=%d/%d (%.1f%%)  %.1fs  eta %.0fm"
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
