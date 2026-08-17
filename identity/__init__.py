"""
Identity and farm-access boundary (P3.5).

This standalone prototype does not implement its own login, password, or
session system - `context.py`'s `DevIdentityProvider` is an explicitly
marked placeholder that stands in for a real signed-in user. What IS real
here, and fully enforced/tested, is everything downstream of "who is this":
the `users` / `farms` / `farm_memberships` schema, role model, and the
`access.require_farm_access` check every farm-scoped repository call goes
through.

When this prototype is wired into the main FarmBiddy platform, only
`context.py` needs to change (swap `DevIdentityProvider` for a provider that
verifies the platform's own session/JWT and maps it to a `RequestIdentity`)
- no repository, service, or route body has to change, because they only
ever depend on the `RequestIdentity`/`require_farm_access` contract, never
on how the identity was established.
"""
