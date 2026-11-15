#!/usr/bin/env python3
"""Offline grader validation (no API calls).

Checks that, for every task: the gold answer scores 100%, an empty answer scores 0%,
and EACH single-field corruption of the gold answer is caught (no false pass), while
harmless formatting variants of the gold answer are still accepted (no false fail).
"""
import copy, json, os, sys
from grader import grade_task, extract_json

ROOT = os.path.dirname(os.path.abspath(__file__))
tasks = json.load(open(os.path.join(ROOT, "tasks", "tasks.json")))["tasks"]


def wrap(obj, style="fence"):
    s = json.dumps(obj)
    return {"fence": f"Some reasoning.\n```json\n{s}\n```",
            "bare": f"Some reasoning. Final: {s}",
            "plainfence": f"Reasoning\n```\n{s}\n```".replace("```\n{", "```json\n{")}[style]


def corrupt(kind, val):
    if kind in ("enum", "exact_str"):
        return str(val) + "x"
    if kind == "int":
        return val + 1
    if kind == "bool":
        return not val
    if kind in ("int_set", "str_set"):
        return list(val)[:-1] if len(val) > 1 else list(val) + (["zz"] if kind == "str_set" else [999])
    if kind == "list_exact":
        c = list(val)
        c[0], c[-1] = c[-1], c[0]
        return c
    if kind == "datetime":
        return "2000-01-01 00:00"


fails = 0
for t in tasks:
    exp, match = t["expected"], t["match"]
    for style in ("fence", "bare"):
        if not grade_task(t, wrap(exp, style))["passed"]:
            print(f"FAIL {t['id']}: gold rejected ({style})"); fails += 1
    if grade_task(t, "no json here")["passed"]:
        print(f"FAIL {t['id']}: garbage accepted"); fails += 1
    for f in exp:
        bad = copy.deepcopy(exp)
        bad[f] = corrupt(match[f], exp[f])
        g = grade_task(t, wrap(bad))
        if g["passed"] or g["fields"][f]:
            print(f"FAIL {t['id']}.{f}: corrupted value accepted"); fails += 1

# formatting-tolerance checks (no false fails)
t8 = next(t for t in tasks if t["id"] == "T08")
for variant in ("2026-11-06T11:30", "2026-11-06 11:30:00", "2026-11-06 11:30 EAT", "2026-11-06T11:30:00+03:00"):
    bad = dict(t8["expected"], commissioner_deadline=variant)
    if not grade_task(t8, wrap(bad))["fields"]["commissioner_deadline"]:
        print("FAIL: datetime variant rejected:", variant); fails += 1
t9 = next(t for t in tasks if t["id"] == "T09")
s = {k: str(v).lower() for k, v in t9["expected"].items()}      # "true"/"false" strings
if not grade_task(t9, wrap(s))["passed"]:
    print("FAIL: string booleans rejected"); fails += 1
t1 = next(t for t in tasks if t["id"] == "T01")
if not grade_task(t1, wrap({"buggy_lines": ["5"], "callback_resultcode_json_type": "Integer"}))["passed"]:
    print("FAIL: numeric-string line numbers / case rejected"); fails += 1
if grade_task(t1, wrap({"buggy_lines": [5, 6], "callback_resultcode_json_type": "integer"}))["passed"]:
    print("FAIL: extra line accepted"); fails += 1
t7 = next(t for t in tasks if t["id"] == "T07")
wrong_case = dict(t7["expected"], password=t7["expected"]["password"].lower())
if grade_task(t7, wrap(wrong_case))["fields"]["password"]:
    print("FAIL: Base64 compared case-insensitively"); fails += 1

print(f"{len(tasks)} tasks checked; {'ALL OK' if not fails else str(fails) + ' FAILURES'}")
sys.exit(1 if fails else 0)
