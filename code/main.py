"""Entry point: python3 code/main.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from auditor.data import Data
from auditor.identity import resolve


def main():
    d = Data()
    print(f"loaded {len(d.requests)} requests, {len(d.identities)} users, {len(d.activity)} activity rows")
    unresolved = 0
    multi = 0
    for r in d.requests:
        ident = resolve(d, r["email"], r["audit_at"])
        if not ident.user_id: unresolved += 1
        if len(ident.emails) > 1: multi += 1
    print(f"identity check: unresolved={unresolved}, users with historical emails={multi}")


if __name__ == "__main__":
    main()