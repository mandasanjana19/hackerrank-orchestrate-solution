"""Step 1: resolve ALL identifiers (current + historical) of the person behind a request email."""
from dataclasses import dataclass, field


@dataclass
class Identity:
    user_id: str | None
    emails: set = field(default_factory=set)
    phones: set = field(default_factory=set)
    hashes: set = field(default_factory=set)
    names: set = field(default_factory=set)

    def all_keys(self):
        keys = {self.user_id} | self.emails | self.phones | self.hashes
        return {k.lower() for k in keys if k}


def resolve(data, email: str, audit_at: str) -> Identity:
    email = email.strip().lower()
    row = data.by_email.get(email)
    user_id = row["user_id"] if row else None
    # request email may be an OLD address: find the user through the audit log
    if not user_id:
        for a in data.audit_log:
            if a["field_name"] == "email" and a["old_value"].lower() == email:
                user_id = a["user_id"]
                break
    ident = Identity(user_id)
    ident.emails.add(email)
    if not user_id:
        return ident
    cur = data.by_user.get(user_id)
    if cur:
        ident.emails.add(cur["email"].lower()); ident.phones.add(cur["phone"])
        ident.hashes.add(cur["email_hash"]); ident.names.add(cur["name"])
    for a in data.audit_by_user[user_id]:       # every value this user ever had
        for v in (a["old_value"], a["new_value"]):
            if not v:
                continue
            {"email": ident.emails, "phone": ident.phones, "email_hash": ident.hashes}[a["field_name"]].add(v.lower() if a["field_name"] != "phone" else v)
    return ident