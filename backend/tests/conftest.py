"""
Pytest configuration and shared fixtures for VAULT Backend tests.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.config import Settings, get_settings
from backend.database import Base, get_db, install_ground_truth_triggers
from backend.main import app
from backend.services.tool_execution_service import ToolExecutionService

# Shared in-memory SQLite engine for tests
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
ToolExecutionService.session_factory = TestingSessionLocal


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """Create all tables and database triggers in test database once per session."""
    Base.metadata.create_all(bind=test_engine)
    install_ground_truth_triggers(test_engine)
    yield
    with ToolExecutionService._lock:
        for ev in ToolExecutionService._active_cancel_events.values():
            ev.set()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Provides an isolated database session per test function with cleanup."""
    session = TestingSessionLocal()
    yield session
    session.close()
    with ToolExecutionService._lock:
        for ev in ToolExecutionService._active_cancel_events.values():
            ev.set()
    with test_engine.begin() as conn:
        conn.execute(text("DROP TRIGGER IF EXISTS trg_prevent_ground_truth_delete"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    install_ground_truth_triggers(test_engine)


@pytest.fixture(scope="function")
def test_settings(tmp_path: Path):
    """Provides test-specific settings with isolated upload directory."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        app_name="VAULT Test Backend",
        environment="testing",
        debug=True,
        offline_mode=True,
        database_url="sqlite:///:memory:",
        upload_dir=str(upload_dir),
        llm_mode="mock",
        llm_endpoint="http://127.0.0.1:11434",
    )
    return settings


@pytest.fixture(scope="function")
def client(db_session, test_settings):
    """Provides a FastAPI TestClient with overridden get_db and get_settings."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_settings():
        return test_settings

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
