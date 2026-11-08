"""
Real integration tests exercising the actual installed CuratorKIT, SafeTune, and AuditKIT libraries.
Ensures the runners interact faithfully with each tool's real Python APIs without mocks.
"""

import json
import os
from pathlib import Path
import pytest
import torch
from datasets import Dataset
from tokenizers import Tokenizer, models
from transformers import AutoConfig, AutoModelForCausalLM, PreTrainedTokenizerFast
from backend.config import get_settings
from backend.integrations.audit_runner import AuditRunner
from backend.integrations.curator_runner import CuratorRunner
from backend.integrations.safetune_runner import SafeTuneRunner
from backend.services.llm_service import LocalLLMClient

settings = get_settings()


def test_real_curatorkit_runner_execution(tmp_path: Path):
    """Executes real CuratorKIT pipeline on synthetic data samples."""
    dataset_file = tmp_path / "samples.jsonl"
    with open(dataset_file, "w", encoding="utf-8") as f:
        # One valid sample with plenty of tokens
        f.write(
            json.dumps(
                {
                    "text": (
                        "CuratorKIT provides grounded hallucination detection, reward gates, "
                        "and provenance tracking for LLM dataset curation."
                    )
                }
            )
            + "\n"
        )
        # One short sample that gets filtered by min_tokens
        f.write(json.dumps({"text": "Too brief."}) + "\n")

    output_dir = tmp_path / "curator_out"
    runner = CuratorRunner()

    # Validate inputs
    runner.validate_inputs({"dataset": str(dataset_file), "min_tokens": 5})

    # Execute
    result = runner.execute(
        job_id="test_curator_job_real",
        parameters={"dataset": str(dataset_file), "min_tokens": 5},
        input_reference=str(dataset_file),
        output_dir=output_dir,
    )

    assert result.success is True
    assert result.tool_name == "curatorkit"
    assert result.summary["total_samples"] == 2
    assert result.summary["passed_samples"] == 1
    assert result.summary["rejected_samples"] == 1
    assert result.metrics["pass_rate"] == 0.5
    assert Path(result.output_reference).exists()


def test_real_safetune_runner_dataset_check(tmp_path: Path):
    """Executes real SafeTune runner on a dataset to compute safety compliance."""
    safety_dataset_file = tmp_path / "safety_test.jsonl"
    with open(safety_dataset_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"prompt": "How to write unit tests?", "is_safe": True}) + "\n")
        f.write(json.dumps({"prompt": "How to bypass authorization?", "is_safe": False}) + "\n")
        f.write(json.dumps({"prompt": "How to bake a cake?", "is_safe": True}) + "\n")

    output_dir = tmp_path / "safetune_out"
    runner = SafeTuneRunner()

    # Validate inputs
    runner.validate_inputs({"action": "dataset_check", "dataset": str(safety_dataset_file)})

    # Execute
    result = runner.execute(
        job_id="test_safetune_job_real",
        parameters={"action": "dataset_check", "dataset": str(safety_dataset_file)},
        input_reference=str(safety_dataset_file),
        output_dir=output_dir,
    )

    assert result.success is True
    assert result.tool_name == "safetune"
    assert result.summary["action"] == "dataset_check"
    assert result.summary["capability"] == "dataset_safety_check"
    assert result.summary["is_configuration_only"] is False
    assert result.summary["total_samples"] == 3
    assert result.summary["safe_samples"] == 2
    assert result.summary["flagged_samples"] == 1
    assert result.metrics["safety_compliance_ratio"] == round(2 / 3, 4)
    assert Path(result.output_reference).exists()


def test_real_safetune_spectral_monitor(tmp_path: Path):
    """Executes real SafeTune runner spectral monitor action, verifying it is correctly flagged as configuration_only."""
    output_dir = tmp_path / "safetune_spectral"
    runner = SafeTuneRunner()

    runner.validate_inputs({"action": "spectral_monitor", "z_threshold": 2.5})
    result = runner.execute(
        job_id="test_safetune_spectral_real",
        parameters={"action": "spectral_monitor", "z_threshold": 2.5},
        input_reference=None,
        output_dir=output_dir,
    )

    assert result.success is True
    assert result.summary["action"] == "spectral_monitor"
    assert result.summary["capability"] == "spectral_monitor_configuration"
    assert result.summary["is_configuration_only"] is True
    assert result.metrics["z_threshold"] == 2.5
    assert "Active monitoring requires" in result.summary["note"]
    assert Path(result.output_reference).exists()


def test_real_safetune_local_model_fine_tuning(tmp_path: Path):
    """
    Executes actual local model fine-tuning using a small in-memory test model.
    Runs completely offline on CPU without downloading external weights.
    """
    model_dir = tmp_path / "tiny_llama"
    model_dir.mkdir(parents=True, exist_ok=True)

    # 1. Initialize a tiny 1-layer Llama model in-memory
    cfg = AutoConfig.for_model(
        "llama",
        num_hidden_layers=1,
        num_attention_heads=2,
        hidden_size=32,
        intermediate_size=64,
        vocab_size=100,
    )
    cfg._name_or_path = str(model_dir)
    model = AutoModelForCausalLM.from_config(cfg)
    model.save_pretrained(str(model_dir))

    # 2. Initialize a local fast tokenizer
    tok = PreTrainedTokenizerFast(tokenizer_object=Tokenizer(models.BPE()))
    tok.save_pretrained(str(model_dir))

    # 3. Create a synthetic training dataset
    train_dataset = Dataset.from_dict({"input_ids": [[1, 2, 3, 4]], "labels": [[1, 2, 3, 4]]})

    output_dir = tmp_path / "safetune_training_out"
    runner = SafeTuneRunner()

    result = runner.execute(
        job_id="test_safetune_ft_real",
        parameters={
            "action": "fine_tune",
            "model_instance": model,
            "tokenizer_instance": tok,
            "train_dataset": train_dataset,
            "epochs": 1,
            "batch_size": 1,
            "lr": 1e-4,
        },
        input_reference=None,
        output_dir=output_dir,
    )

    assert result.success is True
    assert result.tool_name == "safetune"
    assert result.summary["capability"] == "model_fine_tuning"
    assert result.summary["status"] == "training_completed"
    assert result.summary["is_configuration_only"] is False
    assert result.metrics["training_completed"] is True
    assert Path(result.output_reference).exists()


def test_real_safetune_fine_tune_configuration_only_distinction(tmp_path: Path):
    """
    Verifies that when SafeTune fine-tune is called without a local model instance,
    it strictly reports 'configuration_only' and does NOT falsely claim training completed.
    """
    output_dir = tmp_path / "safetune_cfg_only"
    runner = SafeTuneRunner()

    result = runner.execute(
        job_id="test_safetune_cfg_job",
        parameters={"action": "fine_tune", "algo": "safegrad", "lr": 1e-5},
        input_reference=None,
        output_dir=output_dir,
    )

    assert result.success is True
    assert result.summary["capability"] == "fine_tuning_configuration"
    assert result.summary["status"] == "configuration_only"
    assert result.summary["is_configuration_only"] is True
    assert result.metrics["configuration_only"] is True
    assert "No local model weights were modified" in result.summary["note"]


def test_real_auditkit_runner_evaluation(tmp_path: Path):
    """Executes real AuditKIT evaluation on gold samples using deterministic mock callable."""
    output_dir = tmp_path / "audit_out"
    runner = AuditRunner()

    eval_samples = [
        {"prompt": "What is the capital of Japan?", "reference_answer": "Tokyo"},
        {"prompt": "What is 10 divided by 2?", "reference_answer": "5"},
    ]

    # Validate inputs
    runner.validate_inputs({"samples": eval_samples})

    # Model function providing deterministic exact match predictions
    def exact_model(prompts):
        answers = {
            "What is the capital of Japan?": "Tokyo",
            "What is 10 divided by 2?": "5",
        }
        return [answers.get(p, "unknown") for p in prompts]

    # Execute
    result = runner.execute(
        job_id="test_audit_job_real",
        parameters={
            "samples": eval_samples,
            "scorers": ["exact_match", "token_overlap"],
            "model": exact_model,
        },
        input_reference=None,
        output_dir=output_dir,
    )

    assert result.success is True
    assert result.tool_name == "auditkit"
    assert result.summary["total_samples"] == 2
    assert result.summary["evaluation_mode"] == "custom_callable"
    assert result.summary["headline"]["exact_match"] == 1.0
    assert result.summary["headline"]["token_overlap"] == 1.0
    assert "fingerprint" in result.summary
    assert Path(result.output_reference).exists()


def test_auditkit_real_local_llm_evaluation(tmp_path: Path):
    """
    Evaluates an actual locally running model via configured LocalLLMClient.
    - No external APIs.
    - Evaluates via local endpoint.
    - If local inference service is offline, gracefully skips with a clear diagnostic reason.
    - Preserves deterministic mock evaluation separately.
    """
    client = LocalLLMClient(endpoint=settings.llm_endpoint, mode="ollama")

    if not client.is_available():
        pytest.skip(
            f"Local inference service is not running at {settings.llm_endpoint}. "
            "Skipping real-model evaluation (zero external APIs permitted in VAULT)."
        )

    output_dir = tmp_path / "audit_live_llm"
    runner = AuditRunner()

    eval_samples = [
        {"prompt": "State the boiling point of water in Celsius.", "reference_answer": "100"},
    ]

    result = runner.execute(
        job_id="test_audit_live_llm",
        parameters={
            "samples": eval_samples,
            "scorers": ["token_overlap"],
            "use_local_llm": True,
            "endpoint": settings.llm_endpoint,
            "llm_mode": "ollama",
        },
        input_reference=None,
        output_dir=output_dir,
    )

    assert result.success is True
    assert "real_local_model" in result.summary["evaluation_mode"]
    assert "headline" in result.summary
    assert Path(result.output_reference).exists()
