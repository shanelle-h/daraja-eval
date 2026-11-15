"""Deterministic grader for the Daraja/Kenya-DPA eval.

No LLM is used for grading. Every task asks the model to END with one JSON object;
this module extracts it and compares each field to the expected value using a
per-field match type. See README "Scoring logic".
"""
import json
import re

FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(text):
    """Return the LAST JSON object in the response (fenced block preferred), or None."""
    if not text:
        return None
    for m in reversed(FENCE.findall(text)):
        try:
            return json.loads(m)
        except json.JSONDecodeError:
            continue
    # fallback: scan for the last balanced {...} that parses
    ends = [i for i, c in enumerate(text) if c == "}"]
    for end in reversed(ends):
        depth = 0
        for start in range(end, -1, -1):
            if text[start] == "}":
                depth += 1
            elif text[start] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:end + 1])
                    except json.JSONDecodeError:
                        break
    return None


def _s(x):
    return str(x).strip().strip('"').strip("'")


def _bool(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, str) and x.strip().lower() in ("true", "false"):
        return x.strip().lower() == "true"
    return None


def _int(x):
    try:
        if isinstance(x, bool):
            return None
        return int(str(x).strip())
    except (ValueError, TypeError):
        return None


DT = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})")


def check_field(kind, expected, got):
    """True if `got` matches `expected` under match type `kind`."""
    if got is None:
        return False
    if kind == "enum":                       # case-insensitive exact string
        return _s(got).lower() == _s(expected).lower()
    if kind == "exact_str":                  # case-sensitive exact string
        return _s(got) == _s(expected)
    if kind == "int":
        return _int(got) == expected
    if kind == "bool":
        return _bool(got) is expected
    if kind == "int_set":
        if not isinstance(got, list):
            return False
        vals = [_int(v) for v in got]
        return None not in vals and set(vals) == set(expected) and len(vals) == len(set(vals))
    if kind == "str_set":
        if not isinstance(got, list):
            return False
        vals = [_s(v).lower() for v in got]
        return set(vals) == {e.lower() for e in expected} and len(vals) == len(set(vals))
    if kind == "list_exact":                 # ordered, case-sensitive
        return isinstance(got, list) and [_s(v) for v in got] == [_s(e) for e in expected]
    if kind == "datetime":                   # tolerate T separator, seconds, tz suffix
        m1, m2 = DT.search(_s(got)), DT.search(_s(expected))
        return bool(m1 and m2 and m1.groups() == m2.groups())
    raise ValueError(f"unknown match type {kind}")


def grade_task(task, response_text):
    """Return {parse_ok, fields:{name:bool}, score (0..1), passed (all fields right)}."""
    obj = extract_json(response_text)
    exp, match = task["expected"], task["match"]
    if not isinstance(obj, dict):
        return {"parse_ok": False, "fields": {k: False for k in exp}, "score": 0.0, "passed": False}
    fields = {k: check_field(match[k], exp[k], obj.get(k)) for k in exp}
    score = sum(fields.values()) / len(fields)
    return {"parse_ok": True, "fields": fields, "score": score, "passed": all(fields.values())}
