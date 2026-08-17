"""
Farm provisioning helpers shared by the JSON->DB migration script and by the
DB-backed repositories' "farm_file string -> Farm row" resolution.

`slug_for_farm_file` is the one place that turns a legacy `farm_file`
(e.g. "multi_sector_farm.json") into the stable `Farm.slug` key
(e.g. "multi_sector_farm") every first-class Farm row is looked up by.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from config.paths import DATASETS_DIR
from db.orm_models import Farm, FarmMembership
from identity.context import get_or_create_dev_user


def slug_for_farm_file(farm_file: str) -> str:
    return os.path.splitext(os.path.basename(farm_file))[0]


def get_or_create_farm(
    session: Session,
    farm_file: str,
    *,
    name: str | None = None,
    sectors: list[str] | None = None,
    settings: dict | None = None,
    dataset_file: str | None = None,
) -> Farm:
    """Look up a Farm by its slug, creating one on first use.

    Auto-provisioning here (rather than requiring an explicit "create farm"
    step first) keeps every existing test/API caller that already passes an
    arbitrary `farm_file` string working unchanged during the P3 migration -
    see `repositories/*` for where this is called from.

    A newly-created row's `dataset_file` defaults to `farm_file` itself when
    a matching read-only sample dataset actually exists on disk (so
    `DevIdentityProvider`'s "auto-enrol the sample farm" convenience - see
    `identity/context.py` - recognises it), unless the caller explicitly
    overrides it (e.g. the migration script already knows the answer).
    """
    slug = slug_for_farm_file(farm_file)
    farm = session.query(Farm).filter(Farm.slug == slug).one_or_none()
    if farm is None:
        if dataset_file is None and os.path.exists(os.path.join(DATASETS_DIR, farm_file)):
            dataset_file = farm_file
        farm = Farm(
            slug=slug,
            name=name or slug.replace("_", " ").title(),
            sectors=sectors or [],
            settings=settings or {},
            dataset_file=dataset_file,
        )
        session.add(farm)
        session.flush()
    return farm


def ensure_dev_owner(session: Session, farm: Farm) -> FarmMembership:
    """Grant the seeded development identity 'owner' on `farm`, if it does
    not already have a membership there. Used by the migration script (so
    the prototype's one operator can see the farms it just migrated) and by
    tests that need a farm the dev identity can access."""
    user = get_or_create_dev_user(session)
    membership = (
        session.query(FarmMembership)
        .filter(FarmMembership.user_id == user.id, FarmMembership.farm_id == farm.id)
        .one_or_none()
    )
    if membership is None:
        membership = FarmMembership(user_id=user.id, farm_id=farm.id, role="owner")
        session.add(membership)
        session.flush()
    return membership
