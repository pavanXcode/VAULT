"""
Trainer Worker Adapter for Model Lead (Rohit) Tiny Aya LoRA Training and Hardening.
Supports:
1. Subprocess CLI execution for local GPU/CPU model runs.
2. Controlled remote/LAN worker dispatch.
3. Truthful fallback with explicit [MOCK] / not_tested reporting when GPU weights are pending.
Strict invariant: status=succeeded is emitted ONLY when actual checkpoint artifacts exist.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional
from backend.config import get_settings
from backend.integrations.base_runner import BaseToolRunner, ToolRunResult

logger = logging.getLogger("vault.trainer")
settings = get_settings()


def compute_hash(data: Any) -> str:
    """Computes a SHA-256 digest of arbitrary serialized data."""
    if isinstance(data, (dict, list)):
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    elif isinstance(data, bytes):
        return hashlib.sha256(data).hexdigest()
    else:
        return hashlib.sha256(str(data).encode("utf-8")).hexdigest()


def compute_file_sha256(file_path: Path) -> str:
    """Computes SHA-256 digest of a physical file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class TrainerWorkerRunner(BaseToolRunner):
    @property
    def tool_name(self) -> str:
        return "train_adapter"

    def validate_inputs(
        self,
        parameters: Dict[str, Any],
        input_reference: Optional[str] = None,
    ) -> None:
        dataset = parameters.get("dataset") or input_reference
        if not dataset:
            raise ValueError(
                "Training adapter requires a dataset path or manifest reference (pass via 'dataset' or 'input_reference')."
            )

        model_target = parameters.get("model", "tiny-aya-global")
        allowed_models = {
            "tiny-aya-global",
            "tiny-aya-lora-m1",
            "tiny-aya-gated-m2",
            "tiny-aya-safetune-m3",
            "cohereforai/aya-23-8b",
            "mock-aya-dev",
        }
        if model_target.lower() not in allowed_models and not model_target.startswith(("hf:", "local:")):
            raise ValueError(
                f"Unknown model target '{model_target}'. Allowed: {sorted(list(allowed_models))}"
            )

    def execute(
        self,
        job_id: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        output_dir: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolRunResult:
        if self.is_cancelled_or_terminated(output_dir, cancel_event):
            return ToolRunResult(
                tool_name=self.tool_name,
                success=False,
                status="cancelled",
                stage="train",
                errors=["Job was cancelled or terminated before training worker dispatch."],
            )

        config_hash = compute_hash(parameters)
        dataset_ref = parameters.get("dataset") or input_reference or "synthetic_default"
        model_name = parameters.get("model", "tiny-aya-global")
        stage = parameters.get("stage", "train")

        training_out = output_dir / "checkpoints"
        training_out.mkdir(parents=True, exist_ok=True)

        # Check if real training execution is requested and script exists
        workspace_root = Path(__file__).resolve().parent.parent.parent
        explicit_script = parameters.get("training_script")
        execute_real = bool(parameters.get("execute_real") or parameters.get("mode") == "real" or explicit_script)

        real_script_path = None
        if execute_real:
            script_candidates = [
                Path(explicit_script) if explicit_script else None,
                workspace_root / "vault_ml" / "train.py",
                workspace_root / "scripts" / "train_adapter.py",
            ]
            for candidate in script_candidates:
                if candidate and candidate.is_file():
                    real_script_path = candidate
                    break

        # ---------------------------------------------------------
        # Case A: Real Model Lead Training Script Found & Requested
        # ---------------------------------------------------------
        if real_script_path:
            logger.info(f"Executing real training script: {real_script_path}")
            config_file = output_dir / "training_config.json"
            config_file.write_text(json.dumps(parameters, indent=2), encoding="utf-8")

            # Support vault_ml CLI argument structure
            if "vault_ml" in str(real_script_path):
                variant = "M1" if "m1" in str(model_name).lower() else "M2" if "m2" in str(model_name).lower() else "smoke"
                cmd = [
                    sys.executable,
                    "-m",
                    "vault_ml.train",
                    "--variant",
                    parameters.get("variant", variant),
                    "--steps",
                    str(parameters.get("steps", 2)),
                    "--output-root",
                    str(training_out),
                ]
            else:
                cmd = [
                    sys.executable,
                    str(real_script_path),
                    "--config",
                    str(config_file),
                    "--output-dir",
                    str(training_out),
                    "--job-id",
                    job_id,
                ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(workspace_root),
            )

            stdout_lines = []
            stderr_lines = []

            # Poll for process completion with cooperative cancellation
            while process.poll() is None:
                if self.is_cancelled_or_terminated(output_dir, cancel_event):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return ToolRunResult(
                        tool_name=self.tool_name,
                        success=False,
                        status="cancelled",
                        stage=stage,
                        config_hash=config_hash,
                        errors=["Training subprocess terminated upon cancellation request."],
                    )
                cancel_event.wait(0.5) if cancel_event else None

            out, err = process.communicate()
            if out:
                stdout_lines.append(out)
            if err:
                stderr_lines.append(err)

            if process.returncode != 0:
                return ToolRunResult(
                    tool_name=self.tool_name,
                    success=False,
                    status="failed",
                    stage=stage,
                    config_hash=config_hash,
                    errors=[f"Training subprocess exited with non-zero code {process.returncode}: {err}"],
                    stdout="\n".join(stdout_lines),
                    stderr="\n".join(stderr_lines),
                )

            # Strict Invariant: Checkpoint MUST physically exist
            expected_adapter = training_out / "adapter_model.safetensors"
            if not expected_adapter.exists():
                found_adapters = list(training_out.rglob("adapter_model.safetensors"))
                if found_adapters:
                    expected_adapter = found_adapters[0]

            if not expected_adapter.exists():
                return ToolRunResult(
                    tool_name=self.tool_name,
                    success=False,
                    status="failed",
                    stage=stage,
                    config_hash=config_hash,
                    errors=[
                        f"CRITICAL: Training worker completed but output checkpoint '{expected_adapter.name}' was NOT found on disk. "
                        "Status marked failed per zero-fabrication safety rule."
                    ],
                    stdout="\n".join(stdout_lines),
                    stderr="\n".join(stderr_lines),
                )

            ckpt_hash = compute_file_sha256(expected_adapter)
            manifest = {
                "model_id": f"aya-{job_id}",
                "model_name": model_name,
                "stage": stage,
                "dataset_manifest_hash": compute_hash(dataset_ref),
                "config_hash": config_hash,
                "checkpoint_hash": ckpt_hash,
                "checkpoint_path": str(expected_adapter.relative_to(output_dir)),
                "evaluation_refs": [],
                "is_mock": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            manifest_file = output_dir / "model_run.json"
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            return ToolRunResult(
                tool_name=self.tool_name,
                success=True,
                status="succeeded",
                stage=stage,
                config_hash=config_hash,
                output_reference=str(manifest_file),
                output_artifact_ids=[ckpt_hash],
                summary=manifest,
                metrics={"checkpoint_bytes": expected_adapter.stat().st_size},
                worker_id="rohit-gpu-worker",
                is_mock=False,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
            )

        # ---------------------------------------------------------
        # Case B: Pending Model Lead Work -> Honest [MOCK] Status
        # ---------------------------------------------------------
        logger.info(
            "No active training script found on disk. Generating honest [MOCK] model_run manifest."
        )

        mock_manifest = {
            "model_id": f"mock-{model_name}-{job_id[:8]}",
            "model_name": model_name,
            "stage": stage,
            "dataset_manifest_hash": compute_hash(dataset_ref),
            "config_hash": config_hash,
            "checkpoint_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # Placeholder
            "checkpoint_path": None,
            "evaluation_refs": [],
            "metrics": {
                "train_loss_last": None,
                "domain_accuracy": None,
                "safety_compliance": None,
            },
            "is_mock": True,
            "status": "not_tested",
            "notice": (
                "[MOCK] Awaiting Model Lead (Rohit) Tiny Aya LoRA weights and GPU worker environment. "
                "No weights were trained. Checkpoint status is not_tested."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        manifest_file = output_dir / "model_run.json"
        manifest_file.write_text(json.dumps(mock_manifest, indent=2), encoding="utf-8")

        # In Playbook section 4: "Mock workers are allowed only during early UI prototyping,
        # visibly marked mock; they must not reach release state as if trained."
        # Status is truthful: 'not_tested', success=True (manifest generated, but not trained).
        return ToolRunResult(
            tool_name=self.tool_name,
            success=True,
            status="not_tested",
            stage=stage,
            config_hash=config_hash,
            output_reference=str(manifest_file),
            output_artifact_ids=[mock_manifest["checkpoint_hash"]],
            summary=mock_manifest,
            metrics={"status": "not_tested"},
            worker_id="pawan-mock-adapter",
            is_mock=True,
            stdout="[MOCK] Trainer worker adapter executed successfully. Checkpoint status: not_tested (awaiting Rohit GPU weights).",
        )
