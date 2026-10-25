# Ghost Data Still Exists - deletion audit agent

Deterministic, evidence-driven auditor. For each request in `dataset/deletion_requests.csv` it decides
`COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE` and writes the ordered findings / remediation / verification steps to `output.csv`.
It uses **no language-model calls**: every decision is a rule applied to evidence, so runs are repeatable, free and fast
(~seconds for all 518 requests). OCR (Tesseract) is the only external tool and is optional.

## Setup (Windows PowerShell; macOS/Linux: use `python3` and `source .venv/bin/activate`)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r code/requirements.txt
winget install UB-Mannheim.TesseractOCR      # optional: reads the PNG screenshots; add C:\Program Files\Tesseract-OCR to PATH
```
PDFs are read without Tesseract. If Tesseract is missing, PNGs are skipped and everything else still runs.

## Run

```powershell
python code/main.py                       # writes ./output.csv for dataset/deletion_requests.csv
python code/main.py --sample              # writes code/evaluation/sample_pred.csv for the 32 sample cases
python code/evaluation/evaluate.py -v     # scores the sample run against dataset/sample_output.csv
python code/evaluation/custom_cases.py    # our own rule tests
python code/evaluation/validate_output.py # rule checks + low-confidence report on the full output.csv
```

## How it works (code/auditor)

| Module | Job |
|---|---|
| `data.py`, `config.py` | load the CSV tables; operation / phase ordering from `problem_statement.md` |
| `identity.py` | request email -> user, plus every historical email, phone and email hash (old addresses resolve through `user_audit_log.csv`) |
| `evidence.py` | parses SQL snapshots (SQLite), JSON, the TXT handover and five log layouts into flat observations; joins log lines by `trace_id` |
| `ocr.py` | PDFs (pypdf) and screenshots (Tesseract) -> observations, linked to a person by identifiers on the same line |
| `linker.py` | resource -> owner identifiers learned from any observation (deleted records carry no identifiers themselves) |
| `assign.py` | picks each request's resources: identifier links, then the deletion worker's timing signature (account event ~1h before `reported_at`, result mirrors reported status), one-to-one matching across all requests, then the worker's follow-up policy actions |
| `state.py` | real state at `audit_at` from the newest usable evidence (file and record must exist at audit time; replicas that still hold data win; reported statuses are never trusted) |
| `plan.py` | applies `deletion_rules.csv` treatments, builds findings -> remediation -> verification in the required order |
| `pipeline.py` | glue; `NOT_APPLICABLE` when the intake system classified the request as non-deletion |

Absence is proved by citing the newest snapshot that covers that system and does not contain the record.
Retained records (security audit log, legal hold) are checked as PRESENT; a retention period that has ended turns them into deletions.

## Known limitations

- Account assignment relies on timing patterns of the deletion worker; ~100 of 518 requests have two near-identical candidates (`validate_output.py` lists them).
- Some retained audit records appear in no evidence file and cannot be derived.
- Screenshot OCR is noisy; ids are linked per line.
- `NOT_APPLICABLE` currently comes from the intake classification only, not from reading the request text.
