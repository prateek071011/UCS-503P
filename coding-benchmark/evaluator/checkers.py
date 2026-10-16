#!/usr/bin/env python3
"""
checkers.py - output checkers for stdin/stdout benchmark tasks.

DESIGN PRINCIPLE
----------------
A false positive is worse than a false negative.

* `exact` is the DEFAULT and is applied whenever no checker is declared.
* A non-exact checker is used ONLY when a problem explicitly declares one.
* Any uncertainty (unknown type, missing validator, crashing validator,
  truncated output) resolves to a FAILING status - never to PASS.
* `special` / `optimization` judges NEVER compare against the reference
  output; they independently validate the candidate against the problem's
  constraints. If no validator exists, the result is `checker_missing`,
  and the strict (exact) verdict is retained.

CHECKER SPEC FORMAT
-------------------
A spec is a dict. It may live either

  (a) inline in dataset.jsonl on the problem record:
        {"problem_id": "...", ..., "checker": {"type": "exact"}}

  (b) or in a sidecar JSON file mapping problem_id -> spec
      (keeps the 1,500-problem dataset byte-for-byte unchanged):
        {
          "apps_0123": {"type": "float", "abs_tol": 1e-6, "rel_tol": 1e-6,
                        "evidence": "quoted tolerance sentence from statement"},
          "apps_0456": {"type": "special", "validator": "perm_sum",
                        "params": {...}}
        }
      Inline specs win over sidecar specs.

Supported types
---------------
exact         normalized exact string comparison (DEFAULT, unchanged behavior)
tokens        whitespace-insensitive, ORDER-PRESERVING token comparison.
              Opt-in only. Does NOT sort, does NOT ignore missing tokens.
float         token-wise comparison; numeric tokens compared with
              abs(a-b) <= abs_tol + rel_tol*abs(b). Non-numeric tokens must
              match exactly. Token counts must match. Requires an explicit
              abs_tol and/or rel_tol - no tolerance is ever invented.
special       problem-specific validator decides validity from the test INPUT
              and the candidate OUTPUT. Reference output is NOT used as the
              criterion.
optimization  validator reports feasibility + objective value; candidate must
              be feasible AND match the reference objective (a feasible but
              suboptimal answer FAILS).

VALIDATOR MODULES (for special / optimization)
----------------------------------------------
Put a Python file in the `validators/` directory next to this file, e.g.
`validators/perm_sum.py`, and reference it with {"validator": "perm_sum"}.

For `special`, the module must define:

    def check(test_input: str, candidate_output: str, params: dict) -> tuple[bool, str]
        # return (is_valid, human_readable_reason)

For `optimization`, the module must define:

    def objective(test_input: str, output: str, params: dict) -> float | None
        # return the objective value, or None if the output is INFEASIBLE

    # optional; defaults to "min"
    SENSE = "min"   # or "max"

The optimization checker computes the reference objective from the expected
output using the same function, so the reference must itself be feasible.
"""

import importlib.util
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
VALIDATOR_DIR = os.path.join(HERE, "validators")

# Verdict codes returned by run_checker()
V_PASS = "pass"
V_MISMATCH = "output_mismatch"     # exact/tokens/float disagreement
V_INVALID = "wrong_answer"         # judge says candidate is genuinely invalid
V_CHECKER_ERROR = "checker_error"  # checker unusable / crashed / unsafe
V_CHECKER_MISSING = "checker_missing"  # declared judge has no validator

DEFAULT_SPEC = {"type": "exact"}
KNOWN_TYPES = {"exact", "tokens", "float", "special", "optimization"}


# --------------------------------------------------------------------------
# normalization (conservative - identical to the original evaluator)
# --------------------------------------------------------------------------

def norm(s):
    """CRLF->LF, strip trailing spaces per line, drop trailing blank lines.

    This is the ONLY normalization applied globally. Anything more
    aggressive must be opt-in via a checker type.
    """
    lines = s.replace("\r\n", "\n").split("\n")
    lines = [ln.rstrip() for ln in lines]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def exact_equal(candidate, expected):
    return norm(candidate) == norm(expected)


# --------------------------------------------------------------------------
# spec resolution
# --------------------------------------------------------------------------

def resolve_spec(rec, sidecar=None):
    """Return the checker spec for a problem record.

    Priority: inline rec["checker"] > sidecar[problem_id] > exact default.
    A spec that is not a dict, or has no/unknown type, is returned as-is so
    the caller can surface a checker_error rather than silently defaulting.
    """
    spec = None
    if isinstance(rec, dict) and isinstance(rec.get("checker"), dict):
        spec = rec["checker"]
    elif sidecar:
        spec = sidecar.get(rec.get("problem_id"))
    if spec is None:
        return dict(DEFAULT_SPEC)
    if not isinstance(spec, dict):
        return {"type": "__invalid__", "raw": repr(spec)[:120]}
    if "type" not in spec:
        return {"type": "__invalid__", "raw": "spec has no 'type'"}
    return spec


def load_sidecar(path):
    if not path:
        return {}
    import json
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("checker sidecar must be a JSON object mapping problem_id -> spec")
    # ignore audit/metadata blocks that are not specs
    return {k: v for k, v in data.items() if not k.startswith("_")}


# --------------------------------------------------------------------------
# float comparison
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _as_float(tok):
    if _NUM_RE.match(tok):
        try:
            return float(tok)
        except ValueError:
            return None
    # allow inf/nan only if explicitly written
    low = tok.lower()
    if low in ("inf", "-inf", "+inf", "infinity", "-infinity"):
        try:
            return float(low)
        except ValueError:
            return None
    return None


def float_equal(candidate, expected, abs_tol, rel_tol):
    """Token-wise numeric comparison.

    Rules (deliberately strict):
      * token counts must match exactly
      * a non-numeric token must match its counterpart exactly
      * a numeric token passes if abs(a-b) <= abs_tol + rel_tol*abs(b)
      * NaN never compares equal
    """
    ct, et = norm(candidate).split(), norm(expected).split()
    if len(ct) != len(et):
        return False, "token count %d != expected %d" % (len(ct), len(et))
    for i, (a, b) in enumerate(zip(ct, et)):
        if a == b:
            continue
        fa, fb = _as_float(a), _as_float(b)
        if fa is None or fb is None:
            return False, "token %d differs: %r != %r" % (i, a[:40], b[:40])
        if math.isnan(fa) or math.isnan(fb):
            return False, "token %d is NaN" % i
        if math.isinf(fa) or math.isinf(fb):
            if fa != fb:
                return False, "token %d inf mismatch" % i
            continue
        if abs(fa - fb) > abs_tol + rel_tol * abs(fb):
            return False, ("token %d outside tolerance: %r vs %r (diff=%g)"
                           % (i, a, b, abs(fa - fb)))
    return True, "within tolerance"


def tokens_equal(candidate, expected):
    """Order-preserving token comparison. Does NOT sort."""
    ct, et = norm(candidate).split(), norm(expected).split()
    if ct == et:
        return True, "tokens match in order"
    if len(ct) != len(et):
        return False, "token count %d != expected %d" % (len(ct), len(et))
    for i, (a, b) in enumerate(zip(ct, et)):
        if a != b:
            return False, "token %d differs: %r != %r" % (i, a[:40], b[:40])
    return False, "tokens differ"


# --------------------------------------------------------------------------
# validator loading
# --------------------------------------------------------------------------

_VALIDATOR_CACHE = {}


def load_validator(name):
    """Import validators/<name>.py. Returns (module, error_string)."""
    if not name or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name)):
        return None, "invalid validator name %r" % (name,)
    if name in _VALIDATOR_CACHE:
        return _VALIDATOR_CACHE[name]
    path = os.path.join(VALIDATOR_DIR, name + ".py")
    if not os.path.isfile(path):
        res = (None, "validator module not found: %s" % path)
        _VALIDATOR_CACHE[name] = res
        return res
    try:
        spec = importlib.util.spec_from_file_location("validator_" + name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = (mod, None)
    except Exception as e:  # noqa: BLE001
        res = (None, "validator import failed: %s: %s" % (type(e).__name__, e))
    _VALIDATOR_CACHE[name] = res
    return res


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------

def run_checker(spec, test_input, candidate_output, expected_output,
                truncated=False):
    """Judge one test case.

    Returns (verdict, detail) where verdict is one of the V_* constants.
    Never returns V_PASS on uncertainty.
    """
    ctype = spec.get("type")

    # ---- exact (default) -------------------------------------------------
    if ctype == "exact":
        if exact_equal(candidate_output, expected_output):
            return V_PASS, "exact match"
        return V_MISMATCH, "exact mismatch"

    # An exact match is sufficient under EVERY checker type: if the candidate
    # reproduced the reference byte-for-byte (after conservative
    # normalization) it is correct regardless of the judge. Checking this
    # first also means truncation cannot affect the common case.
    if not truncated and exact_equal(candidate_output, expected_output):
        return V_PASS, "exact match"

    if truncated:
        # We only have a prefix of the real output - judging it could produce
        # a false positive. Refuse.
        return V_CHECKER_ERROR, "candidate output truncated; cannot judge safely"

    # ---- tokens ----------------------------------------------------------
    if ctype == "tokens":
        ok, why = tokens_equal(candidate_output, expected_output)
        return (V_PASS if ok else V_MISMATCH), why

    # ---- float -----------------------------------------------------------
    if ctype == "float":
        abs_tol = spec.get("abs_tol")
        rel_tol = spec.get("rel_tol")
        if abs_tol is None and rel_tol is None:
            return V_CHECKER_ERROR, "float checker declared without abs_tol/rel_tol"
        try:
            abs_tol = float(abs_tol or 0.0)
            rel_tol = float(rel_tol or 0.0)
        except (TypeError, ValueError):
            return V_CHECKER_ERROR, "non-numeric tolerance in checker spec"
        if abs_tol < 0 or rel_tol < 0:
            return V_CHECKER_ERROR, "negative tolerance in checker spec"
        ok, why = float_equal(candidate_output, expected_output, abs_tol, rel_tol)
        return (V_PASS if ok else V_MISMATCH), why

    # ---- special ---------------------------------------------------------
    if ctype == "special":
        mod, err = load_validator(spec.get("validator"))
        if mod is None:
            return V_CHECKER_MISSING, err
        fn = getattr(mod, "check", None)
        if not callable(fn):
            return V_CHECKER_MISSING, "validator has no callable check()"
        try:
            res = fn(test_input, candidate_output, dict(spec.get("params") or {}))
        except Exception as e:  # noqa: BLE001
            return V_CHECKER_ERROR, "validator raised %s: %s" % (type(e).__name__, str(e)[:200])
        ok, why = _unpack_bool(res)
        if ok is None:
            return V_CHECKER_ERROR, "validator returned malformed result: %r" % (res,)
        return (V_PASS if ok else V_INVALID), why

    # ---- optimization ----------------------------------------------------
    if ctype == "optimization":
        mod, err = load_validator(spec.get("validator"))
        if mod is None:
            return V_CHECKER_MISSING, err
        fn = getattr(mod, "objective", None)
        if not callable(fn):
            return V_CHECKER_MISSING, "validator has no callable objective()"
        params = dict(spec.get("params") or {})
        sense = str(spec.get("sense", getattr(mod, "SENSE", "min"))).lower()
        if sense not in ("min", "max"):
            return V_CHECKER_ERROR, "invalid sense %r" % sense
        try:
            cand_obj = fn(test_input, candidate_output, params)
        except Exception as e:  # noqa: BLE001
            return V_CHECKER_ERROR, "objective() raised on candidate: %s: %s" % (
                type(e).__name__, str(e)[:200])
        if cand_obj is None:
            return V_INVALID, "candidate output is infeasible"
        # reference objective: from spec, else computed from expected output
        if "reference_objective" in spec:
            ref_obj = spec["reference_objective"]
        else:
            try:
                ref_obj = fn(test_input, expected_output, params)
            except Exception as e:  # noqa: BLE001
                return V_CHECKER_ERROR, "objective() raised on reference: %s: %s" % (
                    type(e).__name__, str(e)[:200])
            if ref_obj is None:
                return V_CHECKER_ERROR, "reference output judged infeasible - validator is wrong"
        try:
            cand_obj = float(cand_obj)
            ref_obj = float(ref_obj)
        except (TypeError, ValueError):
            return V_CHECKER_ERROR, "objective values are not numeric"
        tol = float(spec.get("objective_tol", 0.0))
        if abs(cand_obj - ref_obj) <= tol:
            return V_PASS, "feasible and optimal (obj=%g)" % cand_obj
        # strictly better than the reference means the reference was not
        # optimal -> the benchmark data is suspect, do not silently pass
        better = (cand_obj < ref_obj - tol) if sense == "min" else (cand_obj > ref_obj + tol)
        if better:
            return V_CHECKER_ERROR, (
                "candidate objective %g beats reference %g (%s) - reference "
                "may not be optimal; refusing to judge" % (cand_obj, ref_obj, sense))
        return V_INVALID, "feasible but suboptimal: obj=%g vs optimal %g" % (cand_obj, ref_obj)

    # ---- unknown ---------------------------------------------------------
    return V_CHECKER_ERROR, "unknown checker type %r" % (ctype,)


def _unpack_bool(res):
    """Accept True/False or (bool, reason)."""
    if isinstance(res, bool):
        return res, ""
    if isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], bool):
        return res[0], str(res[1])[:200]
    return None, ""


# --------------------------------------------------------------------------
# multi-valid-output phrase detection  (FLAGGING ONLY - never changes verdicts)
# --------------------------------------------------------------------------

MULTI_OUTPUT_PATTERNS = [
    r"\bprint any\b", r"\boutput any\b", r"\bany valid\b", r"\bany of them\b",
    r"\bany permutation\b", r"\bany arrangement\b", r"\bany such\b",
    r"\bany answer\b", r"\bany one of\b", r"\bany solution\b",
    r"\bmultiple answers\b", r"\bmultiple solutions\b",
    r"\bif (?:there are )?(?:several|multiple|many)\b",
    r"\bif multiple\b", r"\byou may print any\b", r"\bany correct answer\b",
]
_MULTI_RE = re.compile("|".join(MULTI_OUTPUT_PATTERNS), re.IGNORECASE)

# explicit tolerance statements, e.g. "absolute or relative error ... 10^-6"
TOLERANCE_PATTERNS = [
    r"(?:absolute|relative)(?:\s+or\s+relative)?\s+error[^.]{0,80}?"
    r"(?:10\s*[\^\-–]{1,2}\s*\{?-?\s*(\d+)\}?|1e-?(\d+)|0\.(0+)1)",
    r"error[^.]{0,40}?(?:not exceed|less than|at most|does not exceed)[^.]{0,40}?"
    r"(?:10\s*[\^\-–]{1,2}\s*\{?-?\s*(\d+)\}?|1e-?(\d+))",
]
_TOL_RES = [re.compile(p, re.IGNORECASE) for p in TOLERANCE_PATTERNS]


def detect_multi_output(prompt):
    """Return the matched phrase, or None. FLAGGING ONLY."""
    m = _MULTI_RE.search(prompt or "")
    return m.group(0) if m else None


def detect_tolerance(prompt):
    """Extract an EXPLICITLY STATED tolerance from the problem statement.

    Returns (exponent, evidence_sentence) or (None, None). Never guesses:
    if the statement does not state a tolerance, nothing is returned.
    """
    text = prompt or ""
    for rx in _TOL_RES:
        m = rx.search(text)
        if not m:
            continue
        digits = [g for g in m.groups() if g]
        if not digits:
            continue
        d = digits[0]
        try:
            exp = len(d) if d.startswith("0") else int(d)
        except ValueError:
            continue
        if not (1 <= exp <= 15):
            continue
        start = max(0, m.start() - 60)
        return exp, text[start:m.end() + 20].replace("\n", " ").strip()
    return None, None
