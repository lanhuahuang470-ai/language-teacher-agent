"""Additive schema migration; does not rewrite or delete historical business rows."""

from sqlalchemy import select, text

from language_tutor.db.engine import get_engine
from language_tutor.db.models import Base, SchemaMigration


def migrate():
    engine = get_engine()
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(724061901)"))
        Base.metadata.create_all(connection)
        existing = connection.execute(
            select(SchemaMigration.version).where(SchemaMigration.version == "001_assessment_index")
        ).scalar_one_or_none()
        if existing is None:
            connection.execute(
                SchemaMigration.__table__.insert().values(version="001_assessment_index")
            )
