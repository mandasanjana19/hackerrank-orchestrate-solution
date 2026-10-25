"""Custom evaluation cases written by us (the task asks for >= 3 beyond the samples).
They feed hand-made resource states straight into the step builder, so they test the rules, not the data.
Run:  python code/evaluation/custom_cases.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auditor.plan import build_steps
from auditor.state import ResState

AUDIT = "2026-09-15T12:00:00Z"
cover = lambda prefix, at: "evidence_cover"          # file used to prove "not present in snapshot"
R = lambda rid, cat, state, ev, ret=None: ResState(rid, None, cat, state, ev, True, ret)


def ops(steps):
    return [(s["phase"][:4], s["resource_id"], s["operation"], s["evidence_id"]) for s in steps]


def case_a_clean_deletion():
    """Everything compliant -> COMPLETE; only VERIFICATION steps, all citing evidence; audit record stays PRESENT."""
    st, steps = build_steps([R("account_1", "USER_PROFILE", "ABSENT", "evidence_01"),
                             R("analytics_2", "ANALYTICS_PROFILE", "ANONYMIZED", "evidence_02"),
                             R("audit_record_3", "SECURITY_AUDIT_LOG", "RETAINED", "evidence_03", "2027-01-01T00:00:00Z")], AUDIT, cover)
    assert st == "COMPLETE" and all(s["phase"] == "VERIFICATION" and s["evidence_id"] for s in steps), ops(steps)
    assert [s["operation"] for s in steps] == ["VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_ANONYMIZED"]


def case_b_ghost_data_and_recreation():
    """Replica still holds the account, a sync flow is active, a backup can restore -> INCOMPLETE with ordered phases."""
    st, steps = build_steps([R("backup_9", "BACKUP_ARCHIVE", "ACTIVE", "evidence_09"),
                             R("account_1", "USER_PROFILE", "PRESENT", "evidence_54"),
                             R("data_flow_5", "DATA_FLOW", "ACTIVE", "evidence_05"),
                             R("support_7", "SUPPORT_MESSAGE", "IDENTIFIABLE", "evidence_07")], AUDIT, cover)
    assert st == "INCOMPLETE"
    got = [(s["phase"][:4], s["operation"]) for s in steps]
    assert got == [("FIND", "REPORT_REMAINING_RECORD"), ("FIND", "REPORT_EXPOSED_PII"), ("FIND", "REPORT_ACTIVE_DATA_FLOW"),
                   ("FIND", "REPORT_RESTORE_RISK"), ("REME", "DISABLE_DATA_FLOW"), ("REME", "BLOCK_RESTORE"),
                   ("REME", "DELETE_RECORD"), ("REME", "REDACT_RECORD"), ("VERI", "VERIFY_RECORD_ABSENT"),
                   ("VERI", "VERIFY_RECORD_REDACTED"), ("VERI", "VERIFY_DATA_FLOW_DISABLED"), ("VERI", "VERIFY_RESTORE_BLOCKED")], got
    assert all(s["evidence_id"] == "" for s in steps if s["phase"] != "FINDING")


def case_c_expired_retention_must_be_deleted():
    """A retained audit record whose retention period has ended is no longer protected -> it must be deleted."""
    st, steps = build_steps([R("audit_record_3", "SECURITY_AUDIT_LOG", "RETAINED", "evidence_03", "2026-01-01T00:00:00Z")], AUDIT, cover)
    assert st == "INCOMPLETE" and [s["operation"] for s in steps] == ["REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT"], ops(steps)


def case_d_absence_is_proved_by_covering_snapshot():
    """A deleted account never seen in any file is verified absent by citing the covering snapshot."""
    st, steps = build_steps([ResState("account_4", None, "USER_PROFILE", "ABSENT", None, False)], AUDIT, cover)
    assert st == "COMPLETE" and steps[0]["evidence_id"] == "evidence_cover"


if __name__ == "__main__":
    for fn in (case_a_clean_deletion, case_b_ghost_data_and_recreation, case_c_expired_retention_must_be_deleted,
               case_d_absence_is_proved_by_covering_snapshot):
        fn(); print("PASS", fn.__name__)
