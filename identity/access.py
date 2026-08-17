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
