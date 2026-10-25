"""Checks the FULL output.csv (all 518 requests) against the submission rules and flags risky rows.
There are no answers for these requests, so this checks validity and confidence, not correctness.
Run:  python code/main.py && python code/evaluation/validate_output.py"""
import csv, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auditor.config import DATASET, OP_ORDER, PHASE_ORDER, OUTPUT
from auditor.pipeline import Auditor

a = Auditor()
rows = list(csv.DictReader(open(OUTPUT, newline="", encoding="utf-8")))
req_ids = [r["case_id"] for r in a.data.requests]
problems, risky = [], []
if [r["case_id"] for r in rows] != sorted(req_ids):
    problems.append("case_id list is not exactly the sorted deletion_requests list")
valid_ids = set(a.data.evidence_files) | {x["activity_id"] for x in a.data.activity} | {x["audit_id"] for x in a.data.audit_log}
for r in rows:
    cid, st = r["case_id"], json.loads(r["steps_json"])
    if r["deletion_status"] not in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
        problems.append(f"{cid}: bad status")
    if r["deletion_status"] == "NOT_APPLICABLE" and st:
        problems.append(f"{cid}: NOT_APPLICABLE must have []")
    if [s["step_no"] for s in st] != list(range(1, len(st) + 1)):
        problems.append(f"{cid}: step numbers not consecutive")
    order = [(PHASE_ORDER[s["phase"]], OP_ORDER[s["operation"]], s["system_id"], s["resource_id"]) for s in st]
    if order != sorted(order):
        problems.append(f"{cid}: steps not in required order")
    for s in st:
        e = s["evidence_id"]
        if s["phase"] == "FINDING" and e not in valid_ids:
            problems.append(f"{cid}: finding cites unknown evidence '{e}'")
        if s["phase"] == "REMEDIATION" and e:
            problems.append(f"{cid}: remediation must have empty evidence_id")
        if s["phase"] == "VERIFICATION":
            if r["deletion_status"] == "COMPLETE" and e not in valid_ids:
                problems.append(f"{cid}: COMPLETE verification without valid evidence")
            if r["deletion_status"] == "INCOMPLETE" and e:
                problems.append(f"{cid}: future verification must have empty evidence_id")
    link = a.assigned[cid][1]
    if r["deletion_status"] != "NOT_APPLICABLE" and (not st or link != "unique"):
        risky.append((cid, r["deletion_status"], f"account link={link}", f"{len(st)} steps"))
print(f"rows: {len(rows)} | statuses: {dict(Counter(r['deletion_status'] for r in rows))}")
print(f"rule violations: {len(problems)}")
for p in problems[:25]: print("  ", p)
print(f"low-confidence rows (empty steps or account not uniquely identified): {len(risky)}")
for x in risky[:15]: print("  ", x)
