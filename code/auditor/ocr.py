"""Step 5b: read the PDF and PNG evidence (screenshots of admin consoles, statements, registers).

PDFs are text PDFs  -> pypdf.   PNGs are screenshots -> Tesseract OCR (needs the `tesseract` program installed).
If either tool is missing the files are simply skipped (listed in Index.unparsed) and everything else still runs.
Each resource id found in the text becomes an Obs whose identifiers come from the SAME LINE (OCR is noisy and
screens often list several customers); a screen that shows exactly one customer lends that customer to all its ids.
"""
import re
from pathlib import Path

from .evidence import EMAIL_RE, HASH_RE, USER_RE, Obs, system_of

RID_RE = re.compile(r"\b(account|search|analytics|support|export|data_flow|backup|audit_record|tombstone|legal_hold)[_ ](\d{2,5})\b", re.I)
GONE = re.compile(r"no results|not found|deleted|0 results|removed|purged|blocked|disabled|paused", re.I)


def _text_of(path: Path) -> str | None:
    try:
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path))
    except Exception:
        return None


def parse_visual(idx, fid, path, cap):
    text = _text_of(Path(path))
    if text is None:
        idx.unparsed.append(fid)
        return
    doc_emails = {e.lower() for e in EMAIL_RE.findall(text)}
    doc_users = {u.lower() for u in USER_RE.findall(text.lower())}
    single = (doc_emails | doc_users) if len(doc_emails) <= 1 and len(doc_users) <= 1 else set()
    seen = set()
    for line in text.splitlines():
        for m in RID_RE.finditer(line):
            rid = f"{m.group(1).lower()}_{m.group(2)}"
            ids = {e.lower() for e in EMAIL_RE.findall(line)} | {u.lower() for u in USER_RE.findall(line.lower())}
            ids |= {h for h in HASH_RE.findall(line.lower())}
            f = {"line": line.strip(), "event": "visual_capture"}
            if ids or single:
                f["email"] = next(iter(sorted(ids or single)))
            if GONE.search(line):
                f["result"] = "not_found"
            if (rid, tuple(sorted(ids))) in seen:
                continue
            seen.add((rid, tuple(sorted(ids))))
            idx.add(Obs(fid, "visual", Path(path).name, rid, system_of(rid), cap, f, ids | (single if not ids else set())))
