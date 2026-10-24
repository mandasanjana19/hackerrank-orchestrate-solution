"""Loads the CSV tables once and exposes simple lookups."""
import csv
from collections import defaultdict
from .config import DATASET


def _read(name):
    with open(DATASET / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Data:
    def __init__(self):
        self.requests = _read("deletion_requests.csv")
        self.identities = _read("user_identities.csv")
        self.audit_log = _read("user_audit_log.csv")
        self.activity = _read("system_activity.csv")
        self.rules = _read("deletion_rules.csv")
        self.evidence_files = {r["file_id"]: r for r in _read("evidence_files.csv")}
        self.by_email = {r["email"].lower(): r for r in self.identities}
        self.by_user = {r["user_id"]: r for r in self.identities}
        self.audit_by_user = defaultdict(list)
        for a in self.audit_log:
            self.audit_by_user[a["user_id"]].append(a)
        self.activity_by_resource = defaultdict(list)
        for a in self.activity:
            self.activity_by_resource[a["resource_id"]].append(a)