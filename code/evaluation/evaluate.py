"""Scores predictions against sample_output.csv.
Run:  python code/main.py --sample && python code/evaluation/evaluate.py [pred.csv] [expected.csv]
Metrics: case-level status accuracy, row exact match, step-level P/R/F1, field-level accuracy, sequence accuracy."""
import csv, json, sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
args = [a for a in sys.argv[1:] if not a.startswith("-")]
pred_p = Path(args[0]) if args else HERE / "sample_pred.csv"
exp_p = Path(args[1]) if len(args) > 1 else HERE.parents[1] / "dataset" / "sample_output.csv"
load = lambda p: {r["case_id"]: r for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}
P, E = load(pred_p), load(exp_p)
KEY = lambda s: (s["phase"], s["system_id"], s["resource_id"], s["operation"])
FIELDS = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")
canon = lambda steps: [tuple(s[f] for f in FIELDS) for s in steps]

def lcs(a, b):
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            dp[i + 1][j + 1] = dp[i][j] + 1 if a[i] == b[j] else max(dp[i][j + 1], dp[i + 1][j])
    return dp[-1][-1]

n = status_ok = row_ok = seq_ok = 0
tp = fp = fn = 0
fld_tot, fld_ok = Counter(), Counter()
lcs_sum = lcs_den = 0
bad_cases = []
for cid, e in E.items():
    n += 1
    p = P.get(cid)
    if not p:
        bad_cases.append((cid, "MISSING")); continue
    es, ps = json.loads(e["steps_json"]), json.loads(p["steps_json"])
    status_ok += p["deletion_status"] == e["deletion_status"]
    row_ok += p["deletion_status"] == e["deletion_status"] and canon(es) == canon(ps)
    ek, pk = [KEY(s) for s in es], [KEY(s) for s in ps]
    seq_ok += ek == pk
    tp += len(set(ek) & set(pk)); fp += len(set(pk) - set(ek)); fn += len(set(ek) - set(pk))
    em = {KEY(s): s for s in es}
    for s in ps:
        if KEY(s) in em:
            for f in ("state", "evidence_id"):
                fld_tot[f] += 1; fld_ok[f] += s[f] == em[KEY(s)][f]
    lcs_sum += lcs(ek, pk); lcs_den += max(len(ek), len(pk), 1)
    if p["deletion_status"] != e["deletion_status"] or ek != pk:
        bad_cases.append((cid, e["deletion_status"], p["deletion_status"], sorted(set(ek) - set(pk))[:3], sorted(set(pk) - set(ek))[:3]))
prec = tp / (tp + fp) if tp + fp else 0; rec = tp / (tp + fn) if tp + fn else 0
print(f"cases: {n}")
print(f"case status accuracy : {status_ok}/{n} = {status_ok/n:.1%}")
print(f"row exact match      : {row_ok}/{n} = {row_ok/n:.1%}")
print(f"sequence exact match : {seq_ok}/{n} = {seq_ok/n:.1%}   (LCS ratio {lcs_sum/lcs_den:.1%})")
print(f"step P/R/F1          : {prec:.1%} / {rec:.1%} / {2*prec*rec/(prec+rec) if prec+rec else 0:.1%}")
for f in ("state", "evidence_id"):
    print(f"field accuracy {f:11s}: {fld_ok[f]}/{fld_tot[f]} = {fld_ok[f]/max(fld_tot[f],1):.1%}")
if "-v" in sys.argv:
    for b in bad_cases: print(b)
