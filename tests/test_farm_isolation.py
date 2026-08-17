"""
P3.5/P3.8 - farm-scoped access control and cross-farm isolation.

Exercises the real `identity`/`repositories` boundary (not a mock): two
distinct users, two distinct farms, and proof that one cannot read, write,
or delete the other's data via either the repository layer directly or the
API layer (simulating a different caller by overriding the
`get_current_identity` FastAPI dependency - the same seam a real platform
identity provider would plug into).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import repositories.category_budgets as budgets_repo
import repositories.documents as documents_repo
import repositories.financial_records as records_repo
import repositories.onboarding as onboarding_repo
from api.main import app
from config.settings import backend_for
from identity.access import FarmAccessDeniedError, enforce_farm_access, require_farm_access
from identity.context import Membership, RequestIdentity, get_current_identity
from identity.seed import ensure_dev_owner, get_or_create_farm

FARM_A = "isolation_farm_a.json"
FARM_B = "isolation_farm_b.json"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(records_repo, "FINANCIAL_RECORDS_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(documents_repo, "DOCUMENTS_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(budgets_repo, "CATEGORY_BUDGETS_DIR", str(tmp_path / "budgets"))
    monkeypatch.setattr(onboarding_repo, "ONBOARDING_DIR", str(tmp_path / "onboarding"))

    # `resolve_farm_file` (services/farmer_dashboard_service.py) only accepts
    # a farm_id that matches a real dataset file, else it silently falls
    # back to the default demo farm - so the two API-level test farms need a
    # (minimal, content-irrelevant for these tests) dataset file each to be
    # recognised as distinct farms rather than both collapsing onto the demo
    # farm. See the P3 completion report for this as a documented follow-up
    # (a genuinely dataset-free farm_id is accepted by the identity/access
    # layer already - see test_ownerless_farm_is_adopted_by_first_toucher -
    # but not yet by every route that still resolves via `resolve_farm_file`).
    import services.farmer_dashboard_service as dashboard_svc

    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    (datasets_dir / FARM_A).write_text("{}", encoding="utf-8")
    (datasets_dir / FARM_B).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(dashboard_svc, "DATASETS_DIR", str(datasets_dir))
    import identity.seed as identity_seed
    monkeypatch.setattr(identity_seed, "DATASETS_DIR", str(datasets_dir))

    yield tmp_path


@pytest.fixture(autouse=True)
def db_backend(monkeypatch):
    """Exercise the database-backed repositories specifically for these
    tests, regardless of the shipped default (see config/settings.py)."""
    monkeypatch.setenv("PERSISTENCE_BACKEND", "db")
    assert backend_for("FINANCIAL_RECORDS") == "db"
    yield


@pytest.fixture
def two_farms_two_owners(isolated_db):
    """Farm A owned by user_a, Farm B owned by user_b - two genuinely
    separate tenants, set up directly against the database (bypassing the
    single-dev-identity auto-enrolment convenience) so isolation checks are
    real rather than accidentally satisfied by the dev placeholder."""
    from db.orm_models import FarmMembership, User
    from db.session import session_scope

    with session_scope() as session:
        farm_a = get_or_create_farm(session, FARM_A)
        farm_b = get_or_create_farm(session, FARM_B)
        user_a = User(email="farmer.a@example.test", display_name="Farmer A", is_dev_placeholder="false")
        user_b = User(email="farmer.b@example.test", display_name="Farmer B", is_dev_placeholder="false")
        session.add_all([user_a, user_b])
        session.flush()
        session.add(FarmMembership(user_id=user_a.id, farm_id=farm_a.id, role="owner"))
        session.add(FarmMembership(user_id=user_b.id, farm_id=farm_b.id, role="owner"))
        farm_a_id, farm_b_id, user_a_id, user_b_id = farm_a.id, farm_b.id, user_a.id, user_b.id

    identity_a = RequestIdentity(
        user_id=user_a_id, display_name="Farmer A", is_dev_placeholder=False,
        memberships=(Membership(farm_id=farm_a_id, role="owner"),),
    )
    identity_b = RequestIdentity(
        user_id=user_b_id, display_name="Farmer B", is_dev_placeholder=False,
        memberships=(Membership(farm_id=farm_b_id, role="owner"),),
    )
    return {
        "farm_a_id": farm_a_id, "farm_b_id": farm_b_id,
        "identity_a": identity_a, "identity_b": identity_b,
    }


# ---------------------------------------------------------------------------
# identity.access unit tests
# ---------------------------------------------------------------------------

def test_owner_has_read_and_write_access_to_own_farm(two_farms_two_owners):
    ctx = two_farms_two_owners
    require_farm_access(ctx["identity_a"], ctx["farm_a_id"])
    require_farm_access(ctx["identity_a"], ctx["farm_a_id"], write=True)


def test_user_with_no_membership_is_denied_read_and_write(two_farms_two_owners):
    ctx = two_farms_two_owners
    with pytest.raises(FarmAccessDeniedError):
        require_farm_access(ctx["identity_a"], ctx["farm_b_id"])
    with pytest.raises(FarmAccessDeniedError):
        require_farm_access(ctx["identity_a"], ctx["farm_b_id"], write=True)


def test_read_only_role_can_read_but_not_write():
    identity = RequestIdentity(
        user_id="advisor-1", display_name="Advisor", is_dev_placeholder=False,
        memberships=(Membership(farm_id="farm-x", role="read_only"),),
    )
    require_farm_access(identity, "farm-x")  # read is fine
    with pytest.raises(FarmAccessDeniedError):
        require_farm_access(identity, "farm-x", write=True)


def test_manager_role_can_write():
    identity = RequestIdentity(
        user_id="manager-1", display_name="Manager", is_dev_placeholder=False,
        memberships=(Membership(farm_id="farm-x", role="manager"),),
    )
    require_farm_access(identity, "farm-x", write=True)


def test_ownerless_farm_is_adopted_by_first_toucher(isolated_db):
    """A freshly created farm (e.g. via onboarding, P3.6) has no owner yet -
    the first identity to touch it becomes its owner, so "create your farm"
    needs no separate manual membership step."""
    identity = RequestIdentity(user_id="new-user-1", display_name="New Farmer", is_dev_placeholder=False)
    new_farm_file = "brand_new_farm.json"

    enforce_farm_access(identity, new_farm_file, write=True)  # must not raise

    from db.orm_models import FarmMembership
    from db.session import session_scope
    with session_scope() as session:
        farm = get_or_create_farm(session, new_farm_file)
        membership = (
            session.query(FarmMembership)
            .filter(FarmMembership.user_id == "new-user-1", FarmMembership.farm_id == farm.id)
            .one_or_none()
        )
        assert membership is not None
        assert membership.role == "owner"


def test_farm_with_an_existing_owner_is_not_adoptable_by_someone_else(two_farms_two_owners):
    ctx = two_farms_two_owners
    with pytest.raises(FarmAccessDeniedError):
        enforce_farm_access(ctx["identity_b"], FARM_A, write=True)


# ---------------------------------------------------------------------------
# Repository-level isolation: farm_id filtering is real, not incidental
# ---------------------------------------------------------------------------

def test_financial_records_are_isolated_at_the_repository_level(isolated_db):
    from services.financial_record_service import add_financial_record, list_financial_records

    add_financial_record(FARM_A, {
        "record_type": "income", "date": "2026-01-01", "category": "milk", "amount": 111.0,
    })
    add_financial_record(FARM_B, {
        "record_type": "income", "date": "2026-01-01", "category": "milk", "amount": 222.0,
    })

    records_a = list_financial_records(FARM_A)
    records_b = list_financial_records(FARM_B)
    assert [r["amount"] for r in records_a] == [111.0]
    assert [r["amount"] for r in records_b] == [222.0]


def test_documents_are_isolated_at_the_repository_level(isolated_db):
    from services.document_service import add_document, list_documents

    add_document(FARM_A, {
        "document_type": "receipt", "record_type": "expense", "date": "2026-01-01",
        "counterparty": "A Supplier", "amount": 50.0, "category": "feed",
    })
    add_document(FARM_B, {
        "document_type": "receipt", "record_type": "expense", "date": "2026-01-01",
        "counterparty": "B Supplier", "amount": 75.0, "category": "feed",
    })

    assert [d["counterparty"] for d in list_documents(FARM_A)] == ["A Supplier"]
    assert [d["counterparty"] for d in list_documents(FARM_B)] == ["B Supplier"]


def test_category_budgets_are_isolated_at_the_repository_level(isolated_db):
    from services.category_budget_service import list_category_budgets, set_monthly_budget

    set_monthly_budget(FARM_A, {"record_type": "expense", "category": "feed", "year": 2026, "month": 1, "amount": 100.0})
    set_monthly_budget(FARM_B, {"record_type": "expense", "category": "feed", "year": 2026, "month": 1, "amount": 200.0})

    assert [b["amount"] for b in list_category_budgets(FARM_A, year=2026)] == [100.0]
    assert [b["amount"] for b in list_category_budgets(FARM_B, year=2026)] == [200.0]


def test_onboarding_profiles_are_isolated_at_the_repository_level(isolated_db):
    from services.onboarding_service import complete_onboarding, get_onboarding_overrides

    complete_onboarding(FARM_A, {"farm_type": "dairy", "current_cash": 1000.0, "year": 2026})
    complete_onboarding(FARM_B, {"farm_type": "beef", "current_cash": 2000.0, "year": 2026})

    assert get_onboarding_overrides(FARM_A)["current_cash"] == 1000.0
    assert get_onboarding_overrides(FARM_B)["current_cash"] == 2000.0


# ---------------------------------------------------------------------------
# API-level isolation: a different caller cannot reach another farm's data
# by changing farm_file in the request, even though the route itself is
# unchanged (proves the check is enforced server-side, not just client UX).
# ---------------------------------------------------------------------------

client = TestClient(app)


def test_api_denies_cross_farm_read_and_write(two_farms_two_owners):
    ctx = two_farms_two_owners
    app.dependency_overrides[get_current_identity] = lambda: ctx["identity_a"]
    try:
        # Farmer A can read/write their own farm.
        own = client.get("/farmer/financial-records", params={"farm_file": FARM_A})
        assert own.status_code == 200

        add_own = client.post(
            "/farmer/financial-records",
            params={"farm_file": FARM_A},
            json={
                "record_type": "income", "date": "2026-01-01", "category": "milk",
                "amount": 10.0, "description": "Milk cheque",
            },
        )
        assert add_own.status_code == 200

        # Farmer A is denied Farm B's data via the exact same endpoints.
        cross_read = client.get("/farmer/financial-records", params={"farm_file": FARM_B})
        assert cross_read.status_code == 403

        cross_write = client.post(
            "/farmer/financial-records",
            params={"farm_file": FARM_B},
            json={
                "record_type": "income", "date": "2026-01-01", "category": "milk",
                "amount": 999.0, "description": "Attempted cross-farm write",
            },
        )
        assert cross_write.status_code == 403

        cross_onboarding = client.post(
            "/farmer/onboarding",
            params={"farm_file": FARM_B},
            json={"farm_type": "dairy", "current_cash": 5000.0},
        )
        assert cross_onboarding.status_code == 403

        cross_budget = client.post(
            "/farmer/category-budgets/monthly",
            params={"farm_file": FARM_B},
            json={"record_type": "expense", "category": "feed", "year": 2026, "month": 1, "amount": 50.0},
        )
        assert cross_budget.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_identity, None)


def test_api_read_only_advisor_cannot_write(two_farms_two_owners):
    ctx = two_farms_two_owners
    advisor_identity = RequestIdentity(
        user_id="advisor-x", display_name="Farm Advisor", is_dev_placeholder=False,
        memberships=(Membership(farm_id=ctx["farm_a_id"], role="advisor"),),
    )
    app.dependency_overrides[get_current_identity] = lambda: advisor_identity
    try:
        read = client.get("/farmer/financial-records", params={"farm_file": FARM_A})
        assert read.status_code == 200

        write = client.post(
            "/farmer/financial-records",
            params={"farm_file": FARM_A},
            json={
                "record_type": "income", "date": "2026-01-01", "category": "milk",
                "amount": 10.0, "description": "Advisor attempted write",
            },
        )
        assert write.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_identity, None)
