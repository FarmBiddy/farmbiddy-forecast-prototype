"""
Relational schema for P3.

Designed around the domain (see `docs/` audit notes in the P3 completion
report), not a mechanical mirror of the legacy JSON files:

    User --< FarmMembership >-- Farm --< FinancialRecord
                                      |-< Document
                                      |-< CategoryBudget
                                      |-< Loan
                                      `-- OnboardingProfile (1:1)

Every mutable farm-owned table carries a NOT NULL `farm_id` foreign key -
ownership lives in the schema, not in a globally-selected JSON filename.
Money fields use `Numeric`, never floating point, so authoritative amounts
are stored exactly as entered rather than as an approximate binary fraction.
"""

from __future__ import annotations

import uuid
from datetime import date as date_, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


MONEY = Numeric(12, 2)


class User(Base):
    """A FarmBiddy user.

    In this standalone prototype the only row is the seeded development
    identity (see `identity/dev_provider.py`) - there is no login form, no
    password, no session. `is_dev_placeholder` marks that fact explicitly so
    it is never mistaken for a real account once this application is wired
    to the main FarmBiddy platform's authentication.
    """

    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=True)
    display_name = Column(String(120), nullable=False)
    is_dev_placeholder = Column(String(5), nullable=False, default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    memberships = relationship("FarmMembership", back_populates="user", cascade="all, delete-orphan")


class Farm(Base):
    """A farm. `slug` is the stable, human-meaningful lookup key that
    corresponds to today's `farm_file` (e.g. "multi_sector_farm" for
    "multi_sector_farm.json") so existing API callers that pass a `farm_file`
    string keep working unchanged during the P3 migration; `id` is the real
    foreign-key target every owned table uses internally.
    """

    __tablename__ = "farms"

    id = Column(String(32), primary_key=True, default=_uuid)
    slug = Column(String(120), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    sectors = Column(JSON, nullable=False, default=list)
    settings = Column(JSON, nullable=False, default=dict)
    dataset_file = Column(
        String(255), nullable=True,
        doc="Read-only canonical dataset backing this farm's historical actuals/forecast inputs, if any.",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    memberships = relationship("FarmMembership", back_populates="farm", cascade="all, delete-orphan")
    financial_records = relationship("FinancialRecord", back_populates="farm", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="farm", cascade="all, delete-orphan")
    category_budgets = relationship("CategoryBudget", back_populates="farm", cascade="all, delete-orphan")
    loans = relationship("Loan", back_populates="farm", cascade="all, delete-orphan")
    onboarding_profile = relationship(
        "OnboardingProfile", back_populates="farm", uselist=False, cascade="all, delete-orphan",
    )


MEMBERSHIP_ROLES = ("owner", "manager", "advisor", "accountant", "read_only")
# Roles allowed to create/edit/delete a farm's financial data. Advisors,
# accountants and read_only members can see everything but not mutate it -
# "do not create complex per-button permissions yet" from the P3 brief, just
# this one read/write split.
WRITE_ROLES = ("owner", "manager")


class FarmMembership(Base):
    """One user's relationship to one farm. This - not any request-supplied
    farm_file/farm_id alone - is the sole source of truth for "can this
    identity see/change this farm's data"."""

    __tablename__ = "farm_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "farm_id", name="uq_membership_user_farm"),
        CheckConstraint(f"role IN {MEMBERSHIP_ROLES!r}", name="ck_membership_role"),
    )

    id = Column(String(32), primary_key=True, default=_uuid)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(32), ForeignKey("farms.id"), nullable=False)
    role = Column(String(20), nullable=False, default="owner")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="memberships")
    farm = relationship("Farm", back_populates="memberships")


class FinancialRecord(Base):
    """Manual/document-originated income or expense (P0.2/P1.2)."""

    __tablename__ = "financial_records"
    __table_args__ = (
        CheckConstraint("record_type IN ('income', 'expense')", name="ck_financial_record_type"),
        UniqueConstraint("origin_document_id", name="uq_financial_record_origin_document"),
    )

    id = Column(String(32), primary_key=True, default=_uuid)
    farm_id = Column(String(32), ForeignKey("farms.id"), nullable=False, index=True)
    record_type = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    category = Column(String(50), nullable=False)
    amount = Column(MONEY, nullable=False)
    description = Column(Text, nullable=True, default="")
    counterparty = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    sector = Column(String(20), nullable=True)
    origin = Column(String(20), nullable=False, default="manual")
    origin_document_id = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    farm = relationship("Farm", back_populates="financial_records")


class Document(Base):
    """Invoice/receipt metadata (P1.2), independent of the FinancialRecord
    it may create - see `services/document_service.py` for the lifecycle."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("document_type IN ('invoice', 'receipt')", name="ck_document_type"),
        CheckConstraint("record_type IN ('income', 'expense')", name="ck_document_record_type"),
        CheckConstraint("payment_status IN ('unpaid', 'paid')", name="ck_document_payment_status"),
        CheckConstraint(
            "review_status IN ('confirmed', 'pending_review', 'rejected')", name="ck_document_review_status",
        ),
        UniqueConstraint("farm_id", "source", "provider_reference", name="uq_document_provider_reference"),
    )

    id = Column(String(32), primary_key=True, default=_uuid)
    farm_id = Column(String(32), ForeignKey("farms.id"), nullable=False, index=True)
    document_type = Column(String(10), nullable=False)
    record_type = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    counterparty = Column(String(120), nullable=False)
    amount = Column(MONEY, nullable=False)
    category = Column(String(50), nullable=False)
    payment_status = Column(String(10), nullable=False)
    payment_date = Column(Date, nullable=True)
    reference = Column(String(100), nullable=True)
    attachment_reference = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    sector = Column(String(20), nullable=True)
    source = Column(String(20), nullable=False, default="manual")
    provider_reference = Column(String(200), nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    review_status = Column(String(20), nullable=False, default="confirmed")
    linked_financial_record_id = Column(String(32), nullable=True)
    possible_duplicate_manual_record_id = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    farm = relationship("Farm", back_populates="documents")


class CategoryBudget(Base):
    """One category/month budget slot (P0.3). Upsert key is
    (farm_id, sector, record_type, category, year, month) - enforced here as
    a real unique constraint, not just application-level discipline."""

    __tablename__ = "category_budgets"
    __table_args__ = (
        CheckConstraint("record_type IN ('income', 'expense')", name="ck_category_budget_record_type"),
        UniqueConstraint(
            "farm_id", "sector", "record_type", "category", "year", "month",
            name="uq_category_budget_slot",
        ),
    )

    id = Column(String(32), primary_key=True, default=_uuid)
    farm_id = Column(String(32), ForeignKey("farms.id"), nullable=False, index=True)
    sector = Column(String(20), nullable=True)
    record_type = Column(String(10), nullable=False)
    category = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    amount = Column(MONEY, nullable=False)
    source = Column(String(20), nullable=False, default="monthly")
    annual_total = Column(MONEY, nullable=True)
    allocation_rule = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    farm = relationship("Farm", back_populates="category_budgets")


class Loan(Base):
    """One lender/loan line. Historically embedded read-only inside the
    canonical sample dataset's `loans` array; first-class and farm-owned
    here so a real, newly-onboarded farm can eventually record its own
    loans the same way (see `services/loans_service.py`)."""

    __tablename__ = "loans"

    id = Column(String(32), primary_key=True, default=_uuid)
    farm_id = Column(String(32), ForeignKey("farms.id"), nullable=False, index=True)
    lender = Column(String(120), nullable=False)
    principal = Column(MONEY, nullable=False)
    monthly_repayment = Column(MONEY, nullable=False)
    rate = Column(Float, nullable=True)
    maturity = Column(String(7), nullable=True, doc="YYYY-MM")
    source = Column(String(20), nullable=False, default="dataset_import")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    farm = relationship("Farm", back_populates="loans")


class OnboardingProfile(Base):
    """Simple Farmer Onboarding overrides (P1.3) - one row per farm."""

    __tablename__ = "onboarding_profiles"

    farm_id = Column(String(32), ForeignKey("farms.id"), primary_key=True)
    farm_type = Column(String(20), nullable=True)
    current_cash = Column(MONEY, nullable=True)
    loans = Column(JSON, nullable=False, default=list)
    loan_repayments_annual = Column(MONEY, nullable=False, default=0)
    year = Column(Integer, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    farm = relationship("Farm", back_populates="onboarding_profile")
