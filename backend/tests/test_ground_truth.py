"""
Unit and integration tests for ground truth dataset validation.
"""

from fastapi.testclient import TestClient


def test_validate_ground_truth_valid_dataset(client: TestClient):
    """Test validation of a well-formed dataset passes quality gates."""
    payload = {
        "dataset_name": "vault_finance_bench_v1",
        "items": [
            {
                "id": "sample-1",
                "prompt": "What is the net asset value of the portfolio?",
                "reference_answer": "The net asset value of the portfolio is $1.2M.",
                "context": "According to the Q3 financial report, the portfolio net asset value is $1.2M.",
            },
            {
                "id": "sample-2",
                "prompt": "Explain the offline isolation boundary for VAULT.",
                "reference_answer": "VAULT operates in an offline perimeter without external API calls.",
                "context": "VAULT is an offline perimeter system that disallows external cloud API calls.",
            },
        ],
        "check_duplicates": True,
        "check_grounding": True,
    }

    response = client.post("/api/ground-truth/validate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["dataset_name"] == "vault_finance_bench_v1"
    assert data["total_samples"] == 2
    assert data["valid_samples"] == 2
    assert data["invalid_samples"] == 0
    assert data["is_valid"] is True
    assert data["statistics"]["duplicate_prompts_detected"] == 0


def test_validate_ground_truth_missing_fields_and_length(client: TestClient):
    """Samples with empty prompts or answers fail validation."""
    payload = {
        "dataset_name": "broken_dataset",
        "items": [
            {
                "prompt": "",
                "reference_answer": "Answer with missing prompt.",
            },
            {
                "prompt": "A prompt with empty answer",
                "reference_answer": "",
            },
            {
                "prompt": "ab",  # Below min length (3)
                "reference_answer": "Valid answer",
            },
        ],
    }

    response = client.post("/api/ground-truth/validate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["is_valid"] is False
    assert data["invalid_samples"] == 3
    assert len(data["issues"]) >= 3


def test_validate_ground_truth_detects_duplicates(client: TestClient):
    """Detects duplicate prompts and emits warnings."""
    payload = {
        "dataset_name": "duplicate_bench",
        "items": [
            {
                "prompt": "How does offline inference work in VAULT?",
                "reference_answer": "It runs locally on host hardware.",
            },
            {
                "prompt": "How does offline inference work in VAULT?",  # Duplicate
                "reference_answer": "It uses local models without external network.",
            },
        ],
        "check_duplicates": True,
    }

    response = client.post("/api/ground-truth/validate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["statistics"]["duplicate_prompts_detected"] == 1
    duplicate_issues = [i for i in data["issues"] if i["issue_type"] == "duplicate"]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0]["severity"] == "warning"


def test_validate_ground_truth_grounding_warning(client: TestClient):
    """Flags answers that have no lexical overlap with provided context chunk."""
    payload = {
        "dataset_name": "grounding_test",
        "items": [
            {
                "prompt": "What color is the sky in the scene?",
                "reference_answer": "The elephant walked across the savanna yesterday evening.",  # Completely unrelated to context
                "context": "The sky above the mountain was bright azure blue without clouds.",
            }
        ],
        "check_grounding": True,
    }

    response = client.post("/api/ground-truth/validate", json=payload)
    assert response.status_code == 200
    data = response.json()

    grounding_issues = [i for i in data["issues"] if i["issue_type"] == "low_grounding"]
    assert len(grounding_issues) == 1
    assert "hallucination" in grounding_issues[0]["message"].lower()
