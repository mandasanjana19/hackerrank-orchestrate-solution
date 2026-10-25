"""Step 3b: what is the real state of each resource at audit_at?

Reported workflow statuses and activity results are only claims; the state comes from the newest evidence
observation captured at or before audit_at. Tags returned per resource:
  PRESENT / ABSENT            account, search, export, support attachment, marketing
  IDENTIFIABLE / ANONYMIZED   analytics profile (REDACTED for support message / tombstone)
  ACTIVE / DISABLED           data flow (sync, connector)
  ACTIVE / BLOCKED            backup restore path
  RETAINED                    security audit record, legal hold
"""
from dataclasses import dataclass

DIRECT = ("email", "phone", "email_hash", "full_name", "name", "owner_email", "owner_phone",
          "requester_email", "requester_name", "requester_phone", "customer_email", "matched_value",
          "subject:customer_email")
ATTRIB = DIRECT + ("customer_reference", "user_id")      # analytics is "attributable" through the user reference too
TRUE = {"true", "1", "yes", "active"}


def _t(v):
    return str(v).strip().lower() if v is not None else ""


def _any(f, keys):
    return any(f.get(k) not in (None, "", "null") for k in keys)


def prefix_of(rid: str) -> str:
    return rid.rsplit("_", 1)[0]


def category(rid, observations=()):
    """Data category (deletion_rules.csv) of a resource, from its id prefix refined by what the evidence says."""
    p = prefix_of(rid)
    fields = [o.fields for o in observations]
    visual_attachment = any(o.fmt == "visual" and "attachment" in o.source.lower() for o in observations)
    if p == "analytics":
        if any("email_opt_in" in f or str(f.get("event", "")).startswith("contact_") for f in fields):
            return "MARKETING_PROFILE"
        return "ANALYTICS_PROFILE"
    if p == "marketing":
        return "MARKETING_PROFILE"
    if p == "support":
        if visual_attachment:                       # e.g. delivery_correction_attachment.pdf
            return "SUPPORT_ATTACHMENT"
        for f in fields:
            ev = str(f.get("event", ""))
            if f.get("record_type") == "SUPPORT_ATTACHMENT" or "attachment" in ev or ev in ("deletion_marker_check", "contact_query_completed"):
                return "SUPPORT_ATTACHMENT"
        return "SUPPORT_MESSAGE"
    return {"account": "USER_PROFILE", "search": "SEARCH_INDEX_ENTRY", "export": "USER_EXPORT",
            "data_flow": "DATA_FLOW", "backup": "BACKUP_ARCHIVE", "audit_record": "SECURITY_AUDIT_LOG",
            "tombstone": "ACCOUNT_TOMBSTONE", "legal_hold": "LEGAL_HOLD_RECORD",
            "cache": "CACHE_ENTRY", "email_delivery": "EMAIL_DELIVERY_LOG"}.get(p, "OTHER")


def obs_state(o, cat):
    f = o.fields
    res = _t(f.get("result"))
    if cat == "USER_PROFILE":
        if res == "not_found" or _t(f.get("status_code")) == "404" or _t(f.get("rows")) == "0" or _t(f.get("http_status")) == "404":
            return "ABSENT"
        return "PRESENT"
    if cat in ("SEARCH_INDEX_ENTRY", "USER_EXPORT"):
        if res in ("miss", "not_found") or _t(f.get("download_available")) in ("false", "0") or _t(f.get("result")) == "miss":
            return "ABSENT"
        return "PRESENT"
    if cat in ("ANALYTICS_PROFILE", "MARKETING_PROFILE"):
        if res in ("identifiable", "anonymized"):
            return res.upper()
        if cat == "MARKETING_PROFILE":
            return "PRESENT" if _t(f.get("rows")) != "0" else "ABSENT"
        if _t(f.get("direct_identifiers")) == "1" or _any(f, ATTRIB):
            return "IDENTIFIABLE"
        return "ANONYMIZED"
    if cat == "SUPPORT_MESSAGE":
        if res in ("identifiable", "redacted"):
            return res.upper()
        txt = " ".join(str(v) for v in f.values() if v and str(v) != "null")
        return "IDENTIFIABLE" if (_any(f, DIRECT) or "@" in txt) else "REDACTED"
    if cat == "SUPPORT_ATTACHMENT":
        if _t(f.get("marker_found")) == "false" or _t(f.get("rows")) == "1" or res in ("found", "identifiable") or "pii_scan" in str(f.get("event")):
            return "PRESENT"
        return "ABSENT" if res in ("not_found",) or _t(f.get("rows")) == "0" else "PRESENT"
    if cat == "ACCOUNT_TOMBSTONE":
        return "IDENTIFIABLE" if _any(f, DIRECT) else "REDACTED"      # the stable user reference may stay
    if cat == "DATA_FLOW":
        return "ACTIVE" if (_t(f.get("enabled")) in TRUE or res == "active") else "DISABLED"
    if cat == "BACKUP_ARCHIVE":
        if _t(f.get("deletion_block")) in TRUE or res == "blocked":
            return "BLOCKED"
        can = _t(f.get("restore_allowed")) in TRUE or _t(f.get("eligible")) in TRUE or res == "active"
        return "ACTIVE" if can else "BLOCKED"
    return "RETAINED"


BAD = {"PRESENT", "IDENTIFIABLE", "ACTIVE"}


@dataclass
class ResState:
    resource_id: str
    system: str | None
    category: str
    state: str
    evidence_id: str | None
    seen: bool               # False = never observed (absence inferred from a covering snapshot)
    retention_until: str | None = None

    @property
    def compliant(self):
        return self.state not in BAD


def _when(o, files):
    return files[o.file_id]["captured_at"] if o.fmt == "sql" else (o.observed_at or files[o.file_id]["captured_at"])


def resource_state(rid, audit_at, index, files):
    allobs = index.by_resource.get(rid, [])
    cat = category(rid, allobs)
    # usable evidence: the FILE must already exist at audit time, the observation inside it too,
    # and "*_started" log lines are queries without a result, so they say nothing about state
    obs = [o for o in allobs
           if files[o.file_id]["captured_at"] <= audit_at and _when(o, files) <= audit_at
           and not str(o.fields.get("event", "")).endswith("_started")]
    if obs:
        newest = max(_when(o, files) for o in obs)
        latest = [o for o in obs if _when(o, files) == newest]
        states = [(obs_state(o, cat), o) for o in latest]
        bad = [x for x in states if x[0] in BAD]
        st, o = (bad or states)[0]
        ret = next((x.fields.get("retention_until") for x in obs if x.fields.get("retention_until")), None)
        return ResState(rid, o.system, cat, st, o.file_id, True, ret)
    if cat in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"):
        # retained records persist: a later-exported file may still prove the record existed at audit time
        early = [o for o in allobs if _when(o, files) <= audit_at]
        if early:
            o = min(early, key=lambda x: files[x.file_id]["captured_at"])
            ret = next((x.fields.get("retention_until") for x in allobs if x.fields.get("retention_until")), None)
            return ResState(rid, o.system, cat, "RETAINED", o.file_id, True, ret)
    inferable = cat in ("USER_PROFILE", "SEARCH_INDEX_ENTRY", "USER_EXPORT")
    return ResState(rid, None, cat, "ABSENT" if inferable else "UNKNOWN", None, False)
