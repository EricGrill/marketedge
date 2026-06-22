from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from src.state import SCHEMA_VERSION


def test_alembic_upgrade_creates_state_and_audit_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "migrated.db"
    monkeypatch.setenv("MARKETEDGE_DB_PATH", str(db_path))

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)

    assert "positions" in inspector.get_table_names()
    assert "schema_migrations" in inspector.get_table_names()
    assert "audit_events" in inspector.get_table_names()
    assert "alembic_version" in inspector.get_table_names()

    with engine.connect() as connection:
        versions = connection.exec_driver_sql(
            "select version from schema_migrations"
        ).fetchall()

    assert [row[0] for row in versions] == [SCHEMA_VERSION]
