# Evaluation report

Ground truth exists only for the 32 cases in `dataset/sample_output.csv`; the 518 real requests have hidden answers.
Metrics below are measured on the samples (`python code/main.py --sample && python code/evaluation/evaluate.py -v`).
Matching rules were tuned on sample cases 21-32, so sample scores are optimistic for the hidden set.

## Final scores (32 sample cases)

| Metric | Result |
|---|---|
| Case accuracy (status) | 32/32 = 100.0% |
| Row accuracy (status + every step identical) | 19/32 = 59.4% |
| Sequence accuracy (same ordered list of phase/system/resource/operation) | 20/32 = 62.5% (LCS overlap 93.0%) |
| Step precision / recall / F1 | 95.9% / 96.4% / 96.1% |
| Field accuracy `state` | 186/186 = 100.0% |
| Field accuracy `evidence_id` | 185/186 = 99.5% |

## Progress and improvements

| Version | Status | Row exact | Step F1 | Change that produced it |
|---|---|---|---|---|
| Step 3 state logic | 28/32 | - | - (finding recall 37/41) | first state-at-`audit_at` rules |
| Step 4 first run | 29/32 | - | ~91% | rule-driven step builder |
| + usable-evidence rule | 30/32 | 46.9% | 92.7% | only files that exist at `audit_at` count; `*_started` log lines ignored (fixed wrong evidence ids and a false finding) |
| + `reported_at` timing + matching | 30/32 | 56.2% | 94.8% | account event expected ~1h before `reported_at`; one-to-one matching removes impossible assignments |
| + OCR/PDF reader, backup `eligible` flag | 32/32 | 56.2% | 94.6% | PDF-only record found; backup restore path detected from `eligible=true` |
| + attachment classification | 32/32 | 59.4% | 96.1% | PDF/PNG named *attachment* -> delete instead of redact |

## Failures found (remaining)

| Cases | Failure | Cause |
|---|---|---|
| 11, 17, 23, 28, 29 | wrong or extra account verification | two requests with near-identical timing; account cannot be told apart |
| 25-28 | analytics record swapped between neighbours | worker actions of different requests minutes apart |
| 3, 4 | missing `analytics_9406`, `account_004`, `analytics_901` | hand-made cases; no identifier or link anywhere in the evidence |
| 18, 20 | missing retained `audit_record_*` | ids appear in no input file, so they cannot be derived |

On the full 518 requests (`validate_output.py`): 0 rule violations; 106 rows flagged low-confidence (account not uniquely identified).

## Additional evaluation cases (written by us) - `code/evaluation/custom_cases.py`

All four pass (`python code/evaluation/custom_cases.py`).

1. **Clean deletion** - account absent, analytics anonymized, audit record retained -> `COMPLETE`; verification-only steps, each citing evidence; audit record stays PRESENT.
2. **Ghost data and recreation** - replica still holds the account, a sync flow is active, a backup can restore, a support message exposes PII -> `INCOMPLETE`; asserts exact phase/operation order (findings, then disable/block/delete/redact, then verifications) and empty evidence on remediation and future verification.
3. **Expired retention** - a retained audit record past its retention date is no longer protected -> finding + delete + verify absent.
4. **Absence by covering snapshot** - a deleted account never observed in any file is verified absent by citing the newest covering snapshot.

## Other checks

- `validate_output.py`: sorted case ids, valid statuses, consecutive `step_no`, required ordering, valid evidence ids, empty evidence on remediation and future verification, evidence on every COMPLETE verification.
- No hardcoded case ids or answers; the timing signature and offsets are derived from the dataset structure, not per-case.
