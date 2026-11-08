"""
Database configuration and session management for VAULT.
Supports SQLite for local offline development and PostgreSQL through environment configuration.
"""

import logging
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.config import get_settings

logger = logging.getLogger("vault.database")
settings = get_settings()


def get_engine_args(database_url: str) -> dict:
    """Returns engine arguments tailored for the target database dialect."""
    args = {"echo": settings.db_echo}
    if database_url.startswith("sqlite"):
        args["connect_args"] = {"check_same_thread": False}
        # If SQLite file path has parent directory, create it
        if "///" in database_url:
            path_part = database_url.split("///")[-1]
            if path_part and not path_part.startswith(":memory:"):
                db_path = Path(path_part)
                if db_path.parent and str(db_path.parent) != ".":
                    db_path.parent.mkdir(parents=True, exist_ok=True)
    elif database_url.startswith("postgresql"):
        args["pool_size"] = 10
        args["max_overflow"] = 20
        args["pool_pre_ping"] = True
    return args


engine = create_engine(settings.database_url, **get_engine_args(settings.database_url))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing an isolated database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sync_sqlite_columns() -> None:
    """Adds missing columns to SQLite tables if created under an earlier schema version."""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info(ground_truth_validations)")).fetchall()
            existing_cols = {row[1] for row in res}
            if existing_cols:
                cols_to_add = [
                    ("verdict_hash", "VARCHAR(64)"),
                    ("rule_engine_version", "VARCHAR(50) DEFAULT 'vijay_rule_engine_v1.0'"),
                    ("run_sequence", "INTEGER DEFAULT 1"),
                    ("conflict_detected", "BOOLEAN DEFAULT 0"),
                    ("conflict_details", "TEXT"),
                ]
                for col_name, col_def in cols_to_add:
                    if col_name not in existing_cols:
                        conn.execute(text(f"ALTER TABLE ground_truth_validations ADD COLUMN {col_name} {col_def}"))
                        logger.info(f"Added column '{col_name}' to ground_truth_validations")
        except Exception as exc:
            logger.warning(f"SQLite schema sync note: {exc}")


def install_ground_truth_triggers(target_engine=None) -> None:
    """
    Installs database-level triggers to enforce immutability of ground-truth verdicts.
    Guarantees that direct SQL UPDATE and DELETE statements (outside ORM lifecycle,
    such as raw SQL execution, bulk updates, and raw DBAPI calls) are intercepted
    and rejected by the database engine itself.
    """
    eng = target_engine or engine
    dialect = eng.dialect.name
    with eng.begin() as conn:
        if dialect == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_prevent_ground_truth_update
                    BEFORE UPDATE ON ground_truth_validations
                    BEGIN
                        SELECT RAISE(ABORT, 'IMMUTABILITY VIOLATION: ground_truth_validations records are immutable and cannot be updated.');
                    END;
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_prevent_ground_truth_delete
                    BEFORE DELETE ON ground_truth_validations
                    BEGIN
                        SELECT RAISE(ABORT, 'IMMUTABILITY VIOLATION: ground_truth_validations records are immutable and cannot be deleted.');
                    END;
                    """
                )
            )
            logger.info("Installed SQLite immutability triggers on ground_truth_validations")

        elif dialect == "postgresql":
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION prevent_ground_truth_mutation()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        RAISE EXCEPTION 'IMMUTABILITY VIOLATION: ground_truth_validations records are immutable and cannot be updated or deleted.';
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'trg_prevent_ground_truth_mutation'
                        ) THEN
                            CREATE TRIGGER trg_prevent_ground_truth_mutation
                            BEFORE UPDATE OR DELETE ON ground_truth_validations
                            FOR EACH ROW EXECUTE FUNCTION prevent_ground_truth_mutation();
                        END IF;
                    END $$;
                    """
                )
            )
            logger.info("Installed PostgreSQL immutability trigger function on ground_truth_validations")


def init_db() -> None:
    """Initializes tables in the configured database."""
    # Import all models before create_all to register metadata
    from backend import models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
        _sync_sqlite_columns()
        install_ground_truth_triggers(engine)
        logger.info("Database initialized successfully", extra={"database_url": settings.database_url})
    except Exception as exc:
        logger.error(f"Failed to initialize database: {exc}", exc_info=True)
        raise


def check_db_connection() -> bool:
    """Pings the database to verify active connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Database health check failed: {exc}")
        return False
