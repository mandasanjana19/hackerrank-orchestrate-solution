"""Step 2 sanity test: does the evidence index contain every (evidence_id, resource_id) cited in sample_output.csv,
and is that observation linked to the right person?   Run: python code/evaluation/check_index.py"""
import csv, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auditor.config import DATASET
from auditor.data import Data
from auditor.evidence import build_index
from auditor.identity import resolve

d = Data(); ix = build_index(d.evidence_files)
reqs = {r["case_id"]: r for r in csv.DictReader(open(DATASET / "sample_deletion_requests.csv", encoding="utf-8"))}
tot = found = linked = 0
miss = Counter(); misses = []
for row in csv.DictReader(open(DATASET / "sample_output.csv", encoding="utf-8")):
    r = reqs[row["case_id"]]
    keys = resolve(d, r["email"], r["audit_at"]).all_keys()
    for s in json.loads(row["steps_json"]):
        if not s["evidence_id"]:
            continue
        tot += 1
        hits = [o for o in ix.by_resource.get(s["resource_id"], []) if o.file_id == s["evidence_id"]]
        if hits:
            found += 1
            if any(o.idents & keys for o in hits):
                linked += 1
        else:
            ext = d.evidence_files[s["evidence_id"]]["file_path"].rsplit(".", 1)[-1]
            miss[ext] += 1
            misses.append((row["case_id"], s["evidence_id"], s["resource_id"], s["operation"], ext))
print(f"cited evidence steps: {tot} | resource found in cited file: {found} | also linked to user: {linked}")
print("missing by file type:", dict(miss))
for m in misses[:15]: print("  ", m)
