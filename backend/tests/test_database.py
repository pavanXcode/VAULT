"""
Unit tests for database session, connection health, dialect handling, and ORM models.
"""

from sqlalchemy.orm import Session
from backend.database import check_db_connection, get_engine_args
from backend.models.document import Document
from backend.models.experiment import Experiment
from backend.models.ground_truth import GroundTruthValidation


def test_get_engine_args_sqlite():
    """Verify engine arguments for SQLite dialect."""
    args = get_engine_args("sqlite:///./vault.db")
    assert "connect_args" in args
    assert args["connect_args"]["check_same_thread"] is False


def test_get_engine_args_postgresql():
    """Verify engine arguments for PostgreSQL dialect."""
    args = get_engine_args("postgresql://user:pass@localhost:5432/vault")
    assert "pool_size" in args
    assert args["pool_size"] == 10
    assert args["pool_pre_ping"] is True


def test_database_connection_check():
    """Verify that active database connection returns True."""
    assert check_db_connection() is True


def test_document_model_crud(db_session: Session):
    """Verify Document model insert, query, and dictionary serialization."""
    doc = Document(
        filename="test_manual.txt",
        stored_filename="uuid_test_manual.txt",
        file_path="/data/uploads/uuid_test_manual.txt",
        file_size=1024,
        content_type="text/plain",
        checksum_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        status="uploaded",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    assert doc.id is not None
    queried = db_session.query(Document).filter(Document.id == doc.id).first()
    assert queried is not None
    assert queried.filename == "test_manual.txt"
    assert queried.file_size == 1024

    d_dict = queried.to_dict()
    assert d_dict["id"] == doc.id
    assert d_dict["checksum_sha256"] == doc.checksum_sha256


def test_experiment_model_crud(db_session: Session):
    """Verify Experiment model insert, query, and JSON parameter parsing."""
    exp = Experiment(
        name="Unit Test Experiment",
        description="Testing model behavior",
        tool_type="curatorkit",
        status="created",
        parameters='{"learning_rate": 0.0001, "batch_size": 16}',
        results='{"loss": 0.12}',
    )
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)

    assert exp.id is not None
    params = exp.get_parameters_dict()
    assert params["learning_rate"] == 0.0001
    results = exp.get_results_dict()
    assert results["loss"] == 0.12


def test_ground_truth_validation_model(db_session: Session):
    """Verify GroundTruthValidation model insert and issue retrieval."""
    val = GroundTruthValidation(
        dataset_name="db_test_bench",
        total_samples=10,
        valid_samples=9,
        invalid_samples=1,
        is_valid=False,
        issues='[{"item_index": 2, "field": "prompt", "message": "Missing"}]',
        statistics='{"accuracy": 0.9}',
    )
    db_session.add(val)
    db_session.commit()
    db_session.refresh(val)

    assert val.id is not None
    issues = val.get_issues_list()
    assert len(issues) == 1
    assert issues[0]["item_index"] == 2
