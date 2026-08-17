"""
`RequestIdentity` resolution.

`DevIdentityProvider` is the only provider implemented today, and it is
explicitly a prototype stand-in (see package docstring). It resolves to one
fixed, seeded "Development User" row and whatever `FarmMembership` rows
already exist for it - it never fabricates access to a farm the user has no
membership row for, so isolation logic exercised against it is real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from config.settings import IDENTITY_PROVIDER
from db.orm_models import Farm, FarmMembership, User

DEV_USER_EMAIL = "dev@farmbiddy.local"


@dataclass(frozen=True)
class Membership:
    farm_id: str
    role: str


@dataclass(frozen=True)
class RequestIdentity:
    """Everything a route/service/repository needs to know about "who is
    calling" - deliberately independent of *how* that was established
    (dev placeholder today, real platform-issued session/JWT claims later)."""

    user_id: str
    display_name: str
    is_dev_placeholder: bool
    memberships: tuple[Membership, ...] = field(default_factory=tuple)

    def role_for(self, farm_id: str) -> str | None:
        for membership in self.memberships:
            if membership.farm_id == farm_id:
                return membership.role
        return None

    def has_access(self, farm_id: str) -> bool:
        return self.role_for(farm_id) is not None


class IdentityProvider(Protocol):
    def resolve(self, session: Session) -> RequestIdentity: ...


def get_or_create_dev_user(session: Session) -> User:
    user = session.query(User).filter(User.email == DEV_USER_EMAIL).one_or_none()
    if user is None:
        user = User(email=DEV_USER_EMAIL, display_name="Development User", is_dev_placeholder="true")
        session.add(user)
        session.flush()
    return user


def _auto_enroll_dataset_farms(session: Session, user: User) -> None:
    """Prototype-only convenience: there is exactly one human operator
    behind `DevIdentityProvider`, so it is automatically an `owner` of every
    farm backed by a read-only sample dataset (`Farm.dataset_file` set) -
    matching "if a user belongs to one farm: enter it automatically" for
    today's single-farm demo experience without any manual setup step.

    Farms with no `dataset_file` (created via onboarding, or created
    directly in isolation tests) are deliberately NOT auto-enrolled here,
    so cross-farm access denial for them is real, not bypassed.
    """
    dataset_farms = session.query(Farm).filter(Farm.dataset_file.isnot(None)).all()
    if not dataset_farms:
        return
    existing_farm_ids = {
        m.farm_id for m in session.query(FarmMembership).filter(FarmMembership.user_id == user.id).all()
    }
    for farm in dataset_farms:
        if farm.id not in existing_farm_ids:
            session.add(FarmMembership(user_id=user.id, farm_id=farm.id, role="owner"))
    session.flush()


class DevIdentityProvider:
    """PROTOTYPE ONLY - see module docstring.

    Swapping this out for a real platform-backed provider (e.g. one that
    verifies a JWT/session cookie issued by the main FarmBiddy platform and
    loads that user's real `FarmMembership` rows) is the entire migration
    path to real authentication: no repository, service, or API route body
    needs to change, because they depend only on `RequestIdentity`.
    """

    def resolve(self, session: Session) -> RequestIdentity:
        user = get_or_create_dev_user(session)
        _auto_enroll_dataset_farms(session, user)
        memberships = session.query(FarmMembership).filter(FarmMembership.user_id == user.id).all()
        return RequestIdentity(
            user_id=user.id,
            display_name=user.display_name,
            is_dev_placeholder=True,
            memberships=tuple(Membership(farm_id=m.farm_id, role=m.role) for m in memberships),
        )


_PROVIDERS: dict[str, IdentityProvider] = {"dev": DevIdentityProvider()}


def get_identity_provider() -> IdentityProvider:
    return _PROVIDERS.get(IDENTITY_PROVIDER, _PROVIDERS["dev"])


def get_current_identity() -> RequestIdentity:
    """FastAPI dependency: the one place routes ask "who is calling?".

    Change `IDENTITY_PROVIDER` (config/settings.py) to change the answer
    without touching any route or service.

    Deliberately opens its own short-lived, immediately-committed session
    (rather than depending on a request-scoped session shared with the rest
    of the route) so identity resolution never holds a transaction open
    while the route body goes on to make its own repository calls -
    SQLite only allows one writer at a time, and a long-lived request-scoped
    session here would otherwise deadlock against them.
    """
    from db.session import session_scope

    with session_scope() as session:
        return get_identity_provider().resolve(session)
