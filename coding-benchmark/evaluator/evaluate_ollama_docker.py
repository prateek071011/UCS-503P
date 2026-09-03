#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests


def extract_code(text):
    m = re.search(r"```(?:python|py)?\s*(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    return text.strip()


def docker_run(image, script_path, stdin_text=None, timeout=30,
               memory="512m", cpus="1", pids="128"):
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,size=64m",
        "--memory", memory,
        "--cpus", cpus,
        "--pids-limit", pids,
        "--security-opt", "no-new-privileges:true",
        "-v", f"{script_path}:/sandbox/{Path(script_path).name}:ro",
        image,
        "/sandbox/" + Path(script_path).name,
    ]

    started = time.perf_counter()
    try:
        p = subprocess.run(
            cmd,
            input=stdin_text,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
            "timed_out": False,
            "docker_time_seconds": time.perf_counter() - started,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": -1,
            "stdout": e.stdout or "",
            "stderr": (e.stderr or "") + "\nTIMEOUT",
            "timed_out": True,
            "docker_time_seconds": time.perf_counter() - started,
        }


def clean_function_candidate(code):
    """Remove obvious model-added top-level print/assert example calls."""
    lines = code.splitlines()
    kept = []
    for line in lines:
        stripped = line.strip()
        if not line.startswith((" ", "\t")) and re.match(r"^(print|assert)\s*\(", stripped):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def normalize_output(s):
    return "\n".join(line.rstrip() for line in s.strip().splitlines()).strip()


def evaluate_function(candidate, tests, image, timeout, memory, cpus, pids):
    # MBPP-style tests are normally a list of assert statements.
    if isinstance(tests, list):
        harness = candidate + "\n\n" + "\n".join(str(x) for x in tests) + "\n"
    else:
        # Some datasets store a complete harness, e.g. HumanEval+:
        # check(candidate). Bind the generated function as candidate.
        harness = candidate + "\n\n" + str(tests) + "\n"

        if re.search(r"\bcheck\s*\(\s*candidate\s*\)", str(tests)):
            names = re.findall(
                r"^\s*def\s+([A-Za-z_]\w*)\s*\(",
                candidate,
                re.M,
            )
            if names:
                harness = candidate + f"\n\ncandidate = {names[0]}\n" + str(tests) + "\n"

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "test.py")
        Path(path).write_text(harness, encoding="utf-8")

        result = docker_run(
            image, path, timeout=timeout,
            memory=memory, cpus=cpus, pids=pids
        )

    result["tests_total"] = len(tests) if isinstance(tests, list) else 1
    result["tests_passed"] = (
        result["tests_total"] if result["returncode"] == 0 else 0
    )
    return result


def evaluate_stdin_stdout(candidate, tests, image, timeout, memory, cpus, pids):
    passed = 0
    total = len(tests) if isinstance(tests, list) else 0
    last_result = None

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "candidate.py")
        Path(path).write_text(candidate, encoding="utf-8")

        for test in tests:
            inp = str(test.get("input", ""))
            expected = normalize_output(str(test.get("expected", "")))

            result = docker_run(
                image, path, stdin_text=inp, timeout=timeout,
                memory=memory, cpus=cpus, pids=pids
            )
            last_result = result

            if result["returncode"] == 0 and not result["timed_out"]:
                actual = normalize_output(result["stdout"])
                if actual == expected:
                    passed += 1
                else:
                    result["output_mismatch"] = True
                    break
            else:
                break

    if last_result is None:
        last_result = {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "docker_time_seconds": 0,
        }

    last_result["tests_total"] = total
    last_result["tests_passed"] = passed
    return last_result


def call_ollama(model, prompt, host):
    url = host.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }

    started = time.perf_counter()
    r = requests.post(url, json=payload, timeout=300)
    r.raise_for_status()
    data = r.json()
    wall = time.perf_counter() - started

    data["_wall_time_seconds"] = wall
    return data


def load_done(output):
    done = set()
    if not os.path.exists(output):
        return done
    with open(output, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if obj.get("problem_id") is not None:
                    done.add(obj["problem_id"])
            except Exception:
                pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--ollama-host", default="http://localhost:11434")
    ap.add_argument("--docker-image", default="benchmark-python")
    ap.add_argument("--docker-timeout", type=int, default=30)
    ap.add_argument("--memory", default="512m")
    ap.add_argument("--cpus", default="1")
    ap.add_argument("--pids", default="128")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--start-at", type=int, default=0)
    args = ap.parse_args()

    done = load_done(args.output)
    processed_this_run = 0

    with open(args.dataset, "r", encoding="utf-8") as df, \
         open(args.output, "a", encoding="utf-8") as out:

        for index, line in enumerate(df):
            if index < args.start_at:
                continue
            if args.limit is not None and processed_this_run >= args.limit:
                break

            problem = json.loads(line)
            pid = problem["problem_id"]

            if pid in done:
                continue

            prompt = problem["prompt"]
            model_started = time.perf_counter()

            base = {
                "problem_id": pid,
                "source": problem.get("source"),
                "task_type": problem.get("task_type"),
                "model": args.model,
                "status": "evaluated",
            }

            try:
                response = call_ollama(args.model, prompt, args.ollama_host)
                raw = response.get("response", "")
                candidate = extract_code(raw)
                if problem.get("task_type") == "function":
                    candidate = clean_function_candidate(candidate)

                base.update({
                    "raw_response": raw,
                    "candidate_code": candidate,
                    "prompt_eval_count": response.get("prompt_eval_count"),
                    "eval_count": response.get("eval_count"),
                    "total_tokens": (
                        (response.get("prompt_eval_count") or 0)
                        + (response.get("eval_count") or 0)
                    ),
                    "prompt_eval_duration_ns": response.get("prompt_eval_duration"),
                    "eval_duration_ns": response.get("eval_duration"),
                    "total_duration_ns": response.get("total_duration"),
                    "ollama_host_wall_time_seconds": response.get("_wall_time_seconds"),
                })

                try:
                    compile(candidate, "<candidate>", "exec")
                    syntax_ok = True
                except SyntaxError as e:
                    syntax_ok = False
                    base.update({
                        "syntax_ok": False,
                        "passed": False,
                        "failure_type": "syntax_error",
                        "error": str(e),
                    })
                    base["generation_tokens_per_second"] = (
                        (base["eval_count"] or 0)
                        / ((base["eval_duration_ns"] or 1) / 1e9)
                    )
                    out.write(json.dumps(base, ensure_ascii=False) + "\n")
                    out.flush()
                    os.fsync(out.fileno())
                    done.add(pid)
                    processed_this_run += 1
                    continue

                base["syntax_ok"] = syntax_ok

                if problem.get("task_type") == "function":
                    result = evaluate_function(
                        candidate, problem.get("tests", []),
                        args.docker_image, args.docker_timeout,
                        args.memory, args.cpus, args.pids
                    )
                else:
                    result = evaluate_stdin_stdout(
                        candidate, problem.get("tests", []),
                        args.docker_image, args.docker_timeout,
                        args.memory, args.cpus, args.pids
                    )

                base.update({
                    "passed": result["returncode"] == 0
                    and not result.get("timed_out", False)
                    and result.get("tests_passed", 0) == result.get("tests_total", 0),
                    "tests_total": result.get("tests_total"),
                    "tests_passed": result.get("tests_passed"),
                    "docker": result,
                })

                if base["passed"]:
                    base["failure_type"] = None
                elif result.get("timed_out"):
                    base["failure_type"] = "timeout"
                elif result.get("output_mismatch"):
                    base["failure_type"] = "wrong_output"
                elif result.get("returncode") != 0:
                    # AssertionError means the candidate executed but failed a benchmark test.
                    if re.search(r"\bAssertionError\b", result.get("stderr", "")):
                        base["failure_type"] = "wrong_answer"
                    else:
                        base["failure_type"] = "runtime_error"
                else:
                    base["failure_type"] = "wrong_answer"

                base["generation_tokens_per_second"] = (
                    (base["eval_count"] or 0)
                    / ((base["eval_duration_ns"] or 1) / 1e9)
                )

            except Exception as e:
                base.update({
                    "passed": False,
                    "failure_type": "evaluator_error",
                    "error": repr(e),
                })

            out.write(json.dumps(base, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())

            done.add(pid)
            processed_this_run += 1

            print(
                f"[{index + 1}] {pid}: "
                f"{'PASS' if base.get('passed') else 'FAIL'} "
                f"({base.get('failure_type')})",
                flush=True,
            )


if __name__ == "__main__":
    main()
