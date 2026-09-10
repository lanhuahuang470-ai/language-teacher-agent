"""Additive schema migration; does not rewrite or delete historical business rows."""

from sqlalchemy import select, text

from language_tutor.db.engine import get_engine
from language_tutor.db.models import Base, SchemaMigration


def migrate():
    """Create new tables and apply additive migrations under a PG advisory lock."""
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
        # 002: 给 errors 表加 resolved 列（旧表没有这列时才加）
        resolved_done = connection.execute(
            select(SchemaMigration.version).where(SchemaMigration.version == "002_error_resolved")
        ).scalar_one_or_none()
        if resolved_done is None:
            from sqlalchemy import inspect as sa_inspect

            inspector = sa_inspect(connection)
            if "errors" in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns("errors")]
                if "resolved" not in columns:
                    connection.execute(
                        text(
                            "ALTER TABLE errors ADD COLUMN resolved BOOLEAN NOT NULL DEFAULT FALSE"
                        )
                    )
            connection.execute(
                SchemaMigration.__table__.insert().values(version="002_error_resolved")
            )
