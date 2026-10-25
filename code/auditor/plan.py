"""Step 4: apply deletion_rules.csv and build the ordered steps_json for one case."""
from .config import OP_ORDER, PHASE_ORDER, STATE_FOR_OP
from .state import prefix_of

SYSTEM_OF_PREFIX = {"account": "account_service", "search": "search_service", "analytics": "analytics_platform",
                    "support": "support_platform", "export": "export_service", "data_flow": "integration_service",
                    "backup": "backup_service", "audit_record": "security_service", "tombstone": "identity_service",
                    "legal_hold": "legal_service", "marketing": "marketing_platform"}

# category -> (rule action, finding op, remediation op, verification op)   [from deletion_rules.csv]
TREATMENT = {
    "USER_PROFILE": ("DELETE", "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "SEARCH_INDEX_ENTRY": ("DELETE", "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "USER_EXPORT": ("DELETE", "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "MARKETING_PROFILE": ("DELETE", "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "SUPPORT_ATTACHMENT": ("DELETE", "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"),
    "SUPPORT_MESSAGE": ("REDACT", "REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"),
    "ACCOUNT_TOMBSTONE": ("REDACT", "REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED"),
    "ANALYTICS_PROFILE": ("ANONYMIZE", "REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED"),
    "DATA_FLOW": ("DISABLE", "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED"),
    "BACKUP_ARCHIVE": ("RETAIN+BLOCK", "REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED"),
    "SECURITY_AUDIT_LOG": ("RETAIN", None, None, "VERIFY_RECORD_PRESENT"),
    "LEGAL_HOLD_RECORD": ("RETAIN", None, None, "VERIFY_RECORD_PRESENT"),
}


def system_of(rid, st):
    return st.system if st.system and prefix_of(rid) != "tombstone" else SYSTEM_OF_PREFIX.get(prefix_of(rid), st.system)


def _step(phase, st, op, evidence):
    rid = st.resource_id
    return {"phase": phase, "system_id": SYSTEM_OF_PREFIX.get(prefix_of(rid), st.system), "resource_id": rid,
            "operation": op, "state": STATE_FOR_OP[op], "evidence_id": evidence or ""}


def build_steps(states, audit_at, covering):
    """states: list[ResState]. covering(prefix, audit_at) -> file_id used to prove a record absent from a snapshot."""
    findings, remed, verif = [], [], []
    dirty = False
    for st in states:
        t = TREATMENT.get(st.category)
        if not t:
            continue
        _, f_op, r_op, v_op = t
        if st.category == "SECURITY_AUDIT_LOG" and st.retention_until and st.retention_until < audit_at:
            f_op, r_op, v_op = "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"   # retention period over
            st.state = "PRESENT"
        if st.state == "UNKNOWN":
            continue
        bad = not st.compliant
        ev = st.evidence_id or covering(prefix_of(st.resource_id), audit_at)
        if bad and f_op:
            dirty = True
            findings.append(_step("FINDING", st, f_op, st.evidence_id))
            remed.append(_step("REMEDIATION", st, r_op, ""))
        verif.append((st, v_op, ev))
    status = "INCOMPLETE" if dirty else "COMPLETE"
    vsteps = [_step("VERIFICATION", st, op, ev if status == "COMPLETE" else "") for st, op, ev in verif]
    steps = findings + remed + vsteps
    steps.sort(key=lambda s: (PHASE_ORDER[s["phase"]], OP_ORDER[s["operation"]], s["system_id"], s["resource_id"]))
    for i, s in enumerate(steps, 1):
        s["step_no"] = i
    return status, steps
