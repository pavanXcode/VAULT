"""
Unit and integration tests for document management and upload endpoints.
"""

import hashlib
import io
from fastapi.testclient import TestClient


def test_list_documents_initially_empty(client: TestClient):
    """Ensure document listing works cleanly when empty."""
    response = client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_upload_document_success(client: TestClient):
    """Test successful multipart upload, SHA-256 checksum calculation, and database persistence."""
    content = b"sample dataset row 1\nsample dataset row 2\nsample dataset row 3\n"
    expected_checksum = hashlib.sha256(content).hexdigest()

    file_tuple = ("eval_dataset.txt", io.BytesIO(content), "text/plain")
    response = client.post("/api/documents/upload", files={"file": file_tuple})

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "document" in data

    doc = data["document"]
    assert doc["filename"] == "eval_dataset.txt"
    assert doc["file_size"] == len(content)
    assert doc["checksum_sha256"] == expected_checksum
    assert doc["status"] == "uploaded"
    assert doc["id"] is not None


def test_upload_duplicate_deduplication(client: TestClient):
    """Uploading the exact same content returns the existing document rather than duplicating storage."""
    content = b"unique content for deduplication test"
    file_tuple_1 = ("doc1.txt", io.BytesIO(content), "text/plain")
    resp1 = client.post("/api/documents/upload", files={"file": file_tuple_1})
    assert resp1.status_code == 201
    doc1 = resp1.json()["document"]

    file_tuple_2 = ("doc2.txt", io.BytesIO(content), "text/plain")
    resp2 = client.post("/api/documents/upload", files={"file": file_tuple_2})
    assert resp2.status_code == 201
    doc2 = resp2.json()["document"]

    # Must match the same ID and checksum
    assert doc1["id"] == doc2["id"]
    assert doc1["checksum_sha256"] == doc2["checksum_sha256"]
    assert "deduplicated" in resp2.json()["message"]


def test_list_documents_after_upload(client: TestClient):
    """List documents endpoint accurately reflects uploaded files."""
    content = b"test row data for listing"
    client.post(
        "/api/documents/upload",
        files={"file": ("list_test.txt", io.BytesIO(content), "text/plain")},
    )

    response = client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    filenames = [item["filename"] for item in data["items"]]
    assert "list_test.txt" in filenames
