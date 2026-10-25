# Usage report - final full-dataset run

**Command:** `python code/main.py` (all 518 requests in `dataset/deletion_requests.csv`).

## Models

| Item | Value |
|---|---|
| Model providers / model names | none - the solution makes **no language-model or vision-model calls** |
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Average tokens per request | 0 |
| Estimated total cost | USD 0.00 |
| Estimated cost per request | USD 0.00 |

Per-model totals: not applicable (no models). Overall totals are as above.

## Non-model tools used

- Tesseract OCR (local, free, open source) reads the 11 PNG screenshots; `pypdf` reads the 4 PDFs. Both run locally, with no API cost.
- Wall-clock time for the full 518-request run, including OCR: about 35 seconds on the development machine (about 0.07 s per request).

## Why no model

Every decision is a rule over structured evidence (identifier matching, timing signature of the deletion worker, snapshot state at `audit_at`, `deletion_rules.csv` treatments), so a model would add cost and non-determinism without evidence to reason over. A model could later be added for free-text request classification (`NOT_APPLICABLE` from request wording) and for noisy screenshots; if so, this report must be regenerated with provider, model, calls, tokens and cost.
