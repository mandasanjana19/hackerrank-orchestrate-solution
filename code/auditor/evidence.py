"""Step 2: turn every machine-readable evidence file into a flat list of Observations.

One Observation = "file X shows resource R (in system S, table/collection T) with these fields at time t".
Formats handled: .sql (SQLite), .json (nested), .txt (handover), .log (5 different layouts).
PDFs and PNGs are listed in `Index.unparsed` and handled later (step 8).
"""
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATASET

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")
USER_RE = re.compile(r"\buser_\d+\b")
KV_RE = re.compile(r'(\w+)=("([^"]*)"|\S+)')
TS_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")

# resource-id prefix -> owning system (the prefix is the most reliable signal in every format)
PREFIX_SYSTEM = {
    "account": "account_service", "search": "search_service", "analytics": "analytics_platform",
    "support": "support_platform", "export": "export_service", "data_flow": "integration_service",
    "backup": "backup_service", "audit_record": "security_service",
}


def system_of(resource_id: str) -> str | None:
    m = re.match(r"([a-z_]+?)_\d+$", resource_id or "")
    return PREFIX_SYSTEM.get(m.group(1)) if m else None


@dataclass
class Obs:
    file_id: str
    fmt: str                 # sql | json | txt | log
    source: str              # table name, collection, or log event name
    resource_id: str
    system: str | None
    observed_at: str | None
    fields: dict = field(default_factory=dict)
    idents: set = field(default_factory=set)   # lower-cased emails / hashes / user_ids / phones


def _flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(d, list):
        out[prefix[:-1]] = json.dumps(d)
    else:
        out[prefix[:-1]] = d
    return out


def _idents(flat: dict) -> set:
    ids = set()
    for k, v in flat.items():
        if v is None or v == "":
            continue
        s = str(v)
        ids.update(e.lower() for e in EMAIL_RE.findall(s))
        ids.update(HASH_RE.findall(s.lower()))
        ids.update(USER_RE.findall(s.lower()))
        if "phone" in k.lower():
            ids.add(s.lower())
    return ids


class Index:
    def __init__(self):
        self.obs: list[Obs] = []
        self.unparsed: list[str] = []          # file_ids we could not read yet
        self.by_resource: dict[str, list[Obs]] = {}
        self.snapshot_scope: dict[str, dict] = {}   # file_id -> {origin_system: captured_at}

    def add(self, o: Obs):
        self.obs.append(o)
        self.by_resource.setdefault(o.resource_id, []).append(o)


# ---------------------------------------------------------------- SQL
def _parse_sql(idx, fid, path, cap):
    text = Path(path).read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:")
    con.executescript(text)
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    for t in tables:
        rows = [dict(r) for r in con.execute(f'select * from "{t}"')]
        if t == "snapshot_scope":
            idx.snapshot_scope[fid] = {r["origin_system"]: r["captured_at"] for r in rows}
            continue
        for r in rows:
            if "record_json" in r:
                rec = json.loads(r.pop("record_json"))
                r = {**r, **_flatten(rec)}
            rid = r.get("resource_id")
            if not rid:
                continue
            obs_at = r.get("updated_at") or cap
            idx.add(Obs(fid, "sql", t, rid, r.get("origin_system") or system_of(rid), obs_at, r, _idents(r)))
    con.close()


# ---------------------------------------------------------------- JSON
def _walk_json(idx, fid, node, ctx, cap):
    if isinstance(node, dict):
        ctx = dict(ctx)
        for k in ("captured_at", "recorded_at", "observed_at"):
            if isinstance(node.get(k), str):
                ctx["time"] = node[k]
        if "data_store" in node:
            ctx["system"] = node["data_store"]
        if "collection" in node and isinstance(node["collection"], str):
            ctx["collection"] = node["collection"]
        if "resource_id" in node and isinstance(node["resource_id"], str):
            flat = _flatten(node)
            sysname = node.get("system") or ctx.get("system") or system_of(node["resource_id"])
            idx.add(Obs(fid, "json", ctx.get("collection", "json"), node["resource_id"], sysname,
                        flat.get("observed_at") or flat.get("recorded_at") or ctx.get("time") or cap,
                        flat, _idents(flat)))
            return
        for k, v in node.items():
            sub = dict(ctx)
            if k in ("service_exports",):
                pass
            _walk_json(idx, fid, v, sub, cap)
    elif isinstance(node, list):
        for v in node:
            _walk_json(idx, fid, v, ctx, cap)


# ---------------------------------------------------------------- TXT (pipe table)
def _parse_txt(idx, fid, path, cap):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("- ") or "|" not in line:
            continue
        parts = [p.strip() for p in line[2:].split("|")]
        if len(parts) < 6:
            continue
        ts, system, rid, rtype, result, subject = parts[:6]
        f = {"result": result, "record_type": rtype, "subject_reference": subject}
        idx.add(Obs(fid, "txt", "handover", rid, system, ts, f, _idents(f)))


# ---------------------------------------------------------------- LOG
SUBJECT_KEYS = ("lookup_key", "match_key", "subject_key", "scan_key", "correlation_key", "subject_ref",
                "matched_value", "email", "customer_email", "owner_email", "subject_reference",
                "customer_reference", "requester_email")


def _parse_line(raw):
    """Return (timestamp, event, kv-dict) for any of the log layouts."""
    line = raw.rstrip("\n")
    m = TS_RE.match(line)
    ts = m.group(0) if m else None
    body = line[len(ts):].strip() if ts else line
    kv = {}
    if body.startswith("{"):                                   # ts {json}
        try:
            kv = {k: v for k, v in json.loads(body).items()}
        except Exception:
            pass
    else:
        body = body.replace('\\"', '"')
        body = re.sub(r'message="', "", body)
        if body.endswith('"') and body.count('"') % 2 == 1:
            body = body[:-1]
        for k, v, q in KV_RE.findall(body):
            kv[k] = q if v.startswith('"') else v
    event = kv.get("event")
    if not event:
        m1 = re.search(r"\]\s+(\w+):", body)                    # [LEVEL] [svc] [trace] event:
        if m1:
            event = m1.group(1)
        elif " | " in body or body.startswith("|"):                                     # ts | LEVEL | svc | trace | event | ...
            p = [x.strip() for x in body.lstrip("| ").split(" | ")]
            event = p[3] if len(p) > 3 else None
            if len(p) > 2:
                kv.setdefault("trace_id", p[2])
        m2 = re.search(r"\[(tr-\d+|[a-z]+-\d+)\]", body)
        if m2:
            kv.setdefault("trace_id", m2.group(1))
    if "trace_id" not in kv and "requestId" in kv:
        kv["trace_id"] = kv["requestId"]
    if "trace_id" not in kv:                                    # syslog: ... node-1 svc tr-123 - -
        m3 = re.search(r"\b(tr-\d+)\b", body)
        if m3:
            kv["trace_id"] = m3.group(1)
    return ts, event, kv


def _parse_log(idx, fid, path, cap):
    trace_subjects = {}
    pending = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        ts, event, kv = _parse_line(raw)
        if not kv and not event:
            continue
        tr = kv.get("trace_id")
        subj = {k: kv[k] for k in SUBJECT_KEYS if kv.get(k) not in (None, "", "null")}
        if tr and subj:
            trace_subjects.setdefault(tr, {}).update(subj)
        # structured "record_lookup" style lines carry system/resource_id/result directly
        rid = kv.get("resource_id")
        if rid:
            pending.append((tr, ts, event, kv, subj, rid))
    for tr, ts, event, kv, subj, rid in pending:
        merged = {**trace_subjects.get(tr, {}), **subj}
        f = {**kv, **{f"subject:{k}": v for k, v in merged.items()}}
        f["event"] = event
        ids = _idents({k: v for k, v in f.items() if k != "resource_id"})
        idx.add(Obs(fid, "log", event or "log", rid, kv.get("system") or system_of(rid), ts or cap, f, ids))


# ---------------------------------------------------------------- public
def build_index(files: dict) -> Index:
    """files = Data.evidence_files (file_id -> manifest row)."""
    idx = Index()
    for fid, row in files.items():
        path = DATASET / row["file_path"]
        cap = row["captured_at"]
        ext = path.suffix.lower()
        if ext == ".sql":
            _parse_sql(idx, fid, path, cap)
        elif ext == ".json":
            _walk_json(idx, fid, json.loads(path.read_text(encoding="utf-8")), {}, cap)
        elif ext == ".txt":
            _parse_txt(idx, fid, path, cap)
        elif ext == ".log":
            _parse_log(idx, fid, path, cap)
        else:
            idx.unparsed.append(fid)
    return idx
