"""Glue: requests -> identities -> resources -> states -> plan -> rows."""
import csv
import json
from .assign import assign_resources
from .config import DATASET
from .data import Data
from .evidence import build_index
from .identity import resolve
from .linker import build_ownership, resources_of
from .plan import build_steps
from .state import resource_state, prefix_of


def _read(name):
    with open(DATASET / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Auditor:
    def __init__(self):
        self.data = Data()
        self.index = build_index(self.data.evidence_files)
        self.own = build_ownership(self.data, self.index)
        self.samples = _read("sample_deletion_requests.csv")
        self.pool = self.samples + self.data.requests        # pooled: elimination needs every case
        self.ids = {q["case_id"]: resolve(self.data, q["email"], q["audit_at"]) for q in self.pool}
        self.assigned = assign_resources(self.data, self.own, self.pool, self.ids)
        self.non_deletion = {a["resource_id"] for a in self.data.activity if a["event_type"] == "CLASSIFY_REQUEST"}
        self._cover = {}

    def covering(self, prefix, audit_at):
        """Latest evidence file captured <= audit_at that contains records of this resource family."""
        key = prefix
        if key not in self._cover:
            files = {}
            for o in self.index.obs:
                if prefix_of(o.resource_id) == prefix:
                    files[o.file_id] = self.data.evidence_files[o.file_id]["captured_at"]
            self._cover[key] = sorted(files.items(), key=lambda x: x[1])
        best = None
        for fid, cap in self._cover[key]:
            if cap <= audit_at:
                best = fid
        return best

    def audit(self, q):
        resources, _ = self.assigned[q["case_id"]]
        if resources & self.non_deletion:
            return "NOT_APPLICABLE", []
        states = [resource_state(r, q["audit_at"], self.index, self.data.evidence_files) for r in sorted(resources)]
        return build_steps(states, q["audit_at"], self.covering)

    def run(self, requests):
        rows = []
        for q in sorted(requests, key=lambda r: r["case_id"]):
            status, steps = self.audit(q)
            rows.append({"case_id": q["case_id"], "deletion_status": status,
                         "steps_json": json.dumps(steps, separators=(",", ":"))})
        return rows


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        w.writeheader()
        w.writerows(rows)
