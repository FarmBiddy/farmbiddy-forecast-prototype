"""Relational persistence layer (P3).

`db.session` owns the SQLAlchemy engine/session; `db.orm_models` defines the
schema. Nothing outside `repositories/` should import SQLAlchemy directly -
that is the "clean persistence boundary" the P3 audit called for.
"""
