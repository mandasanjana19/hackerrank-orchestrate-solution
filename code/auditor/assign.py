"""Step 3a: build each case's resource set.

1. identifier-linked resources (emails / hashes / user_id seen in evidence)      -> linker.py
2. the ACCOUNT of the person, when it left no identifier behind (deleted rows):
   the deletion worker's DELETE_RECORD on account_service happens 24*k-1 hours after the request (k=1..3) and its
   reported_result mirrors the workflow's reported_status. Candidates owned by other people are dropped and
   the leftovers are resolved by elimination across ALL cases (one account event serves one case).
3. other policy actions of the same request (ANONYMIZE / REDACT / DELETE / BLOCK / DISABLE) are executed by the worker
   in the ~3 hours after that account event -> unambiguous candidates in that window are added.
"""
from datetime import datetime
from .linker import resources_of

RESULT_OF_STATUS = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}
POLICY_EVENTS = {"DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "BLOCK_RESTORE", "DISABLE_DATA_FLOW"}
_P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def _hours(a, b):
    return (_P(a) - _P(b)).total_seconds() / 3600


def assign_resources(data, ownership, requests, identities, tol=0.4, window_h=3.2, resolve_ties=False):
    """requests: list of request dicts (samples + real, pooled for elimination). identities: case_id -> Identity."""
    acc_events = [a for a in data.activity if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
    mine = {q["case_id"]: resources_of(identities[q["case_id"]], ownership) for q in requests}

    cand = {}
    for q in requests:
        cid = q["case_id"]
        have = {r for r in mine[cid] if r.startswith("account_")}
        if have:
            cand[cid] = set(have)
            continue
        c = set()
        for a in acc_events:
            if a["reported_result"] != RESULT_OF_STATUS.get(q["reported_status"]):
                continue
            if q.get("reported_at"):             # the worker acts ~1h before the workflow reports its status
                if abs(_hours(a["event_time"], q["reported_at"]) + 1) > tol:
                    continue
            else:
                h = _hours(a["event_time"], q["requested_at"])
                if not any(abs(h - (24 * k - 1)) <= tol for k in (1, 2, 3)):
                    continue
            rid = a["resource_id"]
            if ownership.get(rid) and rid not in mine[cid]:
                continue                      # belongs to another identified person
            c.add(rid)
        cand[cid] = c
    _prune_by_matching(cand)
    # still ambiguous? prefer the account event whose worker burst also touches resources already linked to this case
    ev_time = {a["resource_id"]: a["event_time"] for a in acc_events}
    for q in requests:
        cid = q["case_id"]
        if len(cand[cid]) <= 1:
            continue
        evs = [a["event_time"] for r in mine[cid] if not r.startswith("account_")
               for a in data.activity_by_resource.get(r, []) if a["event_type"] in POLICY_EVENTS | {"RETAIN_RECORD", "CHECK_DATA_FLOW"}]
        score = {r: sum(-0.5 <= _hours(t, ev_time[r]) <= window_h for t in evs) for r in cand[cid] if r in ev_time}
        if score and max(score.values()) > 0:
            top = [r for r, v in score.items() if v == max(score.values())]
            if len(top) < len(cand[cid]):
                cand[cid] = set(top)
    _prune_by_matching(cand)

    # symmetric leftovers: take the event whose timing is closest to the "1h before the report" signature,
    # then remove it from every other case (one account event serves one request)
    def off(q, r):
        return abs(_hours(ev_time[r], q["reported_at"]) + 1) if q.get("reported_at") and r in ev_time else 9
    for q in (sorted(requests, key=lambda x: x["case_id"]) if resolve_ties else []):
        cid = q["case_id"]
        if len(cand[cid]) > 1:
            best = min(sorted(cand[cid]), key=lambda r: off(q, r))
            cand[cid] = {best}
            for o, t in cand.items():
                if o != cid and best in t and len(t) > 1:
                    t.discard(best)

    # naming-convention fallback seen in the small hand-made accounts: user_07 <-> account_007
    for q in requests:
        cid = q["case_id"]
        if not cand[cid]:
            uid = identities[cid].user_id or ""
            if uid.startswith("user_") and uid[5:].isdigit():
                rid = f"account_{int(uid[5:]):03d}"
                if data.activity_by_resource.get(rid):
                    cand[cid] = {rid}

    # each policy action goes to the claimant case whose own account event most closely precedes it
    anchor_time = {}
    for cid, accs in cand.items():
        if len(accs) == 1:
            ev = next((a for a in acc_events if a["resource_id"] == next(iter(accs))), None)
            if ev:
                anchor_time[cid] = ev["event_time"]
    extra = {q["case_id"]: set() for q in requests}
    for a in data.activity:
        if a["event_type"] not in POLICY_EVENTS or a["target_system"] == "account_service":
            continue
        rid = a["resource_id"]
        claim = []
        for cid, T in anchor_time.items():
            h = _hours(a["event_time"], T)
            if -0.5 <= h <= window_h and not (ownership.get(rid) and rid not in mine[cid]):
                claim.append((h if h >= 0 else 99 + abs(h), cid))
        if claim:
            extra[min(claim)[1]].add(rid)

    result = {}
    for q in requests:
        cid = q["case_id"]
        accs = cand[cid]
        status = "unique" if len(accs) == 1 else ("none" if not accs else "ambiguous")
        result[cid] = (set(mine[cid]) | accs | extra[cid], status)
    return result


def _max_matching(cases, edges, banned_res=frozenset()):
    """Augmenting-path bipartite matching. edges: case -> iterable of resources. Returns {resource: case}."""
    match = {}

    def try_case(c, seen):
        for r in edges[c]:
            if r in seen or r in banned_res:
                continue
            seen.add(r)
            if r not in match or try_case(match[r], seen):
                match[r] = c
                return True
        return False

    for c in cases:
        try_case(c, set())
    return match


def _prune_by_matching(cand):
    """Every account DELETE event serves exactly one request, so an edge (case, resource) that no complete
    matching can contain is impossible and is dropped. Works one connected component at a time."""
    # components of the case<->resource graph
    comp_of, comps = {}, []
    for c in cand:
        if c in comp_of or not cand[c]:
            continue
        stack, members = [c], []
        comp_of[c] = len(comps)
        while stack:
            x = stack.pop(); members.append(x)
            for r in cand[x]:
                for y in cand:
                    if y not in comp_of and r in cand[y]:
                        comp_of[y] = len(comps); stack.append(y)
        comps.append(members)
    for members in comps:
        amb = [c for c in members if len(cand[c]) > 1]
        if not amb:
            continue
        base = len(_max_matching(members, cand))
        for c in amb:
            for r in sorted(cand[c]):
                rest = [m for m in members if m != c]
                m = _max_matching(rest, cand, banned_res={r})
                if len(m) + 1 < base:            # forcing c->r loses a match somewhere else: impossible edge
                    cand[c].discard(r)
