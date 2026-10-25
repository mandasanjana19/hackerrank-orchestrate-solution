"""Step 2b: which resources belong to which person?

A resource keeps its owner forever, so ownership is learned from ANY observation (any date) that carried an
identifier of that resource, plus the LINK_RESOURCE_IDENTITY activity rows. Deleted/anonymized observations carry
no identifiers, which is why we need this graph instead of matching each observation on its own.
"""
import re
from .evidence import EMAIL_RE, USER_RE


def build_ownership(data, index) -> dict:
    own: dict[str, set] = {}
    for o in index.obs:
        if o.idents:
            own.setdefault(o.resource_id, set()).update(o.idents)
    for a in data.activity:
        if a["event_type"] == "LINK_RESOURCE_IDENTITY":
            ids = {x.lower() for x in EMAIL_RE.findall(a["details"]) + USER_RE.findall(a["details"])}
            own.setdefault(a["resource_id"], set()).update(ids)
    return own


def resources_of(identity, ownership) -> set:
    keys = identity.all_keys()
    return {rid for rid, ids in ownership.items() if ids & keys}