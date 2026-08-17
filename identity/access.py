"""
Farm-scoped access control (P3.5).

`require_farm_access` is the one gate every farm-owned repository/service
call goes through once a request has a `RequestIdentity` and a target
`farm_id`. It is deliberately simple - membership exists or it doesn't,
write access is `owner`/`manager` or it isn't - matching the brief's "do not
create complex per-button permissions yet".
"""

from __future__ import annotations

from db.orm_models import WRITE_ROLES
from identity.context import RequestIdentity


class FarmAccessDeniedError(PermissionError):
    """No membership (or insufficient role) for the target farm. Mapped to
    HTTP 403 by the handler registered in `api/main.py`."""


def require_farm_access(identity: RequestIdentity, farm_id: str, *, write: bool = False) -> None:
    role = identity.role_for(farm_id)
    if role is None:
        raise FarmAccessDeniedError(
            f"'{identity.display_name}' has no membership on this farm.",
        )
    if write and role not in WRITE_ROLES:
        raise FarmAccessDeniedError(
            f"Role '{role}' can view but not change this farm's data (requires {', '.join(WRITE_ROLES)}).",
        )


def enforce_farm_access(identity: RequestIdentity, farm_file: str, *, write: bool = False) -> None:
    """API-route convenience: resolve `farm_file` (the legacy string every
    farmer-facing endpoint already accepts) to its `Farm.id` and check
    `identity` against it. Raises `FarmAccessDeniedError` (mapped to HTTP
    403 in `api/main.py`) if the identity has no membership, or an
    insufficient role for a write.

    An "ownerless" farm (freshly created - e.g. by Simple Farm Setup for a
    brand new farm, see P3.6 - or otherwise recorded with no membership yet)
    is automatically adopted by whichever identity is the first to touch it,
    exactly as creating a resource makes you its owner in most systems. This
    is what lets onboarding create a first-class farm with no pre-existing
    dataset without a separate manual "create membership" step, while a farm
    that already has an owner stays fully protected against a different
    identity - real isolation, not a bypass.

    Applied to the domains this P3 phase gave real farm-scoped repositories
    (financial records, documents, category budgets, onboarding) - see the
    P3 completion report for why the remaining, still JSON/dataset-only,
    read-heavy aggregate endpoints are a documented fast-follow rather than
    part of this pass.
    """
    from db.orm_models import FarmMembership
    from db.session import session_scope
    from identity.seed import get_or_create_farm

    with session_scope() as session:
        farm = get_or_create_farm(session, farm_file)
        has_any_membership = (
            session.query(FarmMembership).filter(FarmMembership.farm_id == farm.id).first() is not None
        )
        if not has_any_membership:
            session.add(FarmMembership(user_id=identity.user_id, farm_id=farm.id, role="owner"))
            return
        farm_id = farm.id
    require_farm_access(identity, farm_id, write=write)
