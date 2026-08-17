"""
Loan storage.

Unlike the other domains, there is no legacy JSON store for loans - the
read-only canonical dataset has always been the only source (embedded
`loans` array, see `datasets/multi_sector_farm.json`), and farmers have
never been able to edit it. `JsonLoanRepository.load()` therefore always
returns `None` - an explicit "no database rows recorded" sentinel, distinct
from an empty list - so `services/multi_sector_farm.py` knows to keep using
the dataset-embedded loans exactly as before P3 whenever the loans domain's
backend flag is "json" (the default rollback state) or a farm simply has no
DB loan rows yet.
"""

from __future__ import annotations

from typing import Optional, Protocol

from config.settings import backend_for


class LoanRepository(Protocol):
    def load(self, farm_file: str) -> Optional[list[dict]]:
        """`None` = no DB rows for this farm; caller should fall back to the
        dataset-embedded loans. `[]` = this farm has DB loan rows and
        genuinely has zero loans - a real, distinct state."""

    def save(self, farm_file: str, loans: list[dict]) -> None: ...


class JsonLoanRepository:
    def load(self, farm_file: str) -> Optional[list[dict]]:
        return None

    def save(self, farm_file: str, loans: list[dict]) -> None:
        raise NotImplementedError(
            "Loans have no legacy JSON store - switch PERSISTENCE_BACKEND_LOANS=db to record loans.",
        )


class DbLoanRepository:
    def load(self, farm_file: str) -> Optional[list[dict]]:
        from db.orm_models import Loan as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm
        from repositories._convert import to_float

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            rows = session.query(ORM).filter(ORM.farm_id == farm.id).all()
            if not rows:
                return None
            return [
                {
                    "id": row.id,
                    "lender": row.lender,
                    "principal": to_float(row.principal),
                    "monthly_repayment": to_float(row.monthly_repayment),
                    "rate": row.rate,
                    "maturity": row.maturity,
                    "source": row.source,
                }
                for row in rows
            ]

    def save(self, farm_file: str, loans: list[dict]) -> None:
        from db.orm_models import Loan as ORM
        from db.session import session_scope
        from identity.seed import get_or_create_farm

        with session_scope() as session:
            farm = get_or_create_farm(session, farm_file)
            session.query(ORM).filter(ORM.farm_id == farm.id).delete()
            for loan in loans:
                session.add(ORM(
                    farm_id=farm.id,
                    lender=loan["lender"],
                    principal=loan["principal"],
                    monthly_repayment=loan["monthly_repayment"],
                    rate=loan.get("rate"),
                    maturity=loan.get("maturity"),
                    source=loan.get("source", "dataset_import"),
                ))


def get_repository() -> LoanRepository:
    if backend_for("LOANS") == "db":
        return DbLoanRepository()
    return JsonLoanRepository()
