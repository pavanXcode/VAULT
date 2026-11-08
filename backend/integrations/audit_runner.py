"""
AuditKIT integration runner for benchmark evaluation, dataset quality metrics, and model assessment.
"""

import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from backend.config import get_settings
from backend.integrations.base_runner import BaseToolRunner, ToolRunResult

settings = get_settings()


class AuditRunner(BaseToolRunner):
    @property
    def tool_name(self) -> str:
        return "auditkit"

    def validate_inputs(
        self,
        parameters: Dict[str, Any],
        input_reference: Optional[str] = None,
    ) -> None:
        dataset = parameters.get("dataset") or parameters.get("csv") or input_reference or parameters.get("samples")
        if not dataset:
            raise ValueError(
                "AuditKIT requires a dataset (pass via 'dataset', 'csv', 'samples', or 'input_reference')."
            )

        if isinstance(dataset, str) and not dataset.startswith(("http://", "https://")):
            p = Path(dataset)
            if p.suffix and not p.exists():
                resolved = (settings.resolved_upload_path.parent / dataset).resolve()
                if not resolved.exists() and not p.resolve().exists():
                    raise ValueError(f"AuditKIT dataset file not found: {dataset}")

    def execute(
        self,
        job_id: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        output_dir: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolRunResult:
        try:
            import auditkit as ak
        except ImportError as err:
            return ToolRunResult(
                tool_name=self.tool_name,
                success=False,
                errors=[f"AuditKIT is not installed: {err}"],
            )

        audit_out = output_dir / "audit"
        audit_out.mkdir(parents=True, exist_ok=True)

        if self.is_cancelled_or_terminated(output_dir, cancel_event):
            return ToolRunResult(
                tool_name=self.tool_name,
                success=False,
                errors=["Job was cancelled or timed out before execution started."],
            )

        dataset_ref = (
            parameters.get("dataset")
            or parameters.get("csv")
            or input_reference
            or parameters.get("samples")
        )

        scorers = parameters.get("scorers", ["exact_match"])
        input_col = parameters.get("input_col", "prompt")
        target_col = parameters.get("target_col", "reference_answer")
        max_samples = parameters.get("limit")

        try:
            # 1. Resolve dataset
            samples: List[ak.Sample] = []
            if isinstance(dataset_ref, list):
                for item in dataset_ref:
                    if isinstance(item, dict):
                        inp = item.get("prompt") or item.get("input") or ""
                        tgt = item.get("reference_answer") or item.get("target") or item.get("answer") or ""
                        samples.append(ak.Sample(input=str(inp), target=str(tgt)))
                    elif isinstance(item, ak.Sample):
                        samples.append(item)
            elif isinstance(dataset_ref, str) and Path(dataset_ref).exists():
                p = Path(dataset_ref)
                if p.suffix == ".csv":
                    loaded = ak.load_csv(str(p), input_col=input_col, target_col=target_col)
                    samples = list(loaded)
                elif p.suffix == ".jsonl":
                    loaded = ak.load_jsonl(str(p), input_col=input_col, target_col=target_col)
                    samples = list(loaded)
                else:
                    loaded = ak.load_dataset(str(p))
                    samples = list(loaded)
            else:
                # Built-in or registered scenario
                scenario = ak._to_scenario(dataset_ref)
                samples = list(scenario)

            if max_samples and max_samples > 0:
                samples = samples[:max_samples]

            if not samples:
                raise ValueError("No valid evaluation samples found in the provided dataset.")

            if self.is_cancelled_or_terminated(output_dir, cancel_event):
                return ToolRunResult(
                    tool_name=self.tool_name,
                    success=False,
                    errors=["Job was cancelled or timed out before evaluation."],
                )

            # 2. Resolve evaluation model (distinguish real local model vs deterministic mock)
            model_spec = parameters.get("model")
            evaluation_mode = "deterministic_mock"

            if callable(model_spec):
                model_fn = model_spec
                evaluation_mode = "custom_callable"
            elif isinstance(model_spec, str) and model_spec.startswith("hf:"):
                model_fn = ak.AutoModel.resolve(model_spec)
                evaluation_mode = "hf_model"
            elif model_spec in ("local_llm", "local_model", "real_model") or parameters.get("use_local_llm"):
                from backend.services.llm_service import LocalLLMClient
                from backend.schemas.llm import LLMGenerateRequest

                client = LocalLLMClient(
                    endpoint=parameters.get("endpoint"),
                    mode=parameters.get("llm_mode"),
                )
                evaluation_mode = f"real_local_model ({client.mode} at {client.endpoint})"

                def _local_llm_callable(prompts: List[str]) -> List[str]:
                    completions = []
                    for prompt in prompts:
                        if self.is_cancelled_or_terminated(output_dir, cancel_event):
                            raise InterruptedError("Evaluation cancelled during inference.")
                        req = LLMGenerateRequest(
                            prompt=prompt,
                            max_tokens=parameters.get("max_tokens", 128),
                            model=parameters.get("model_name"),
                        )
                        res = client.generate_sync(req)
                        completions.append(res.content)
                    return completions

                model_fn = _local_llm_callable
            else:
                evaluation_mode = "deterministic_mock"

                def model_fn(prompts: List[str]) -> List[str]:
                    return [f"Predicted completion for: {p.strip()}" for p in prompts]

            # 3. Execute evaluation
            result = ak.evaluate(
                dataset=samples,
                model=model_fn,
                scorers=scorers,
            )

            if self.is_cancelled_or_terminated(output_dir, cancel_event):
                return ToolRunResult(
                    tool_name=self.tool_name,
                    success=False,
                    errors=["Job was cancelled or timed out before writing report."],
                )

            # 4. Save structured report
            report_data = {
                "headline": result.headline,
                "fingerprint": result.fingerprint,
                "total_samples": len(samples),
                "scorers": scorers,
                "evaluation_mode": evaluation_mode,
                "summary": result.summary() if hasattr(result, "summary") else {},
            }

            report_file = audit_out / "audit_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2)

            return ToolRunResult(
                tool_name=self.tool_name,
                success=True,
                output_reference=str(report_file),
                summary={
                    "total_samples": len(samples),
                    "fingerprint": result.fingerprint,
                    "scorers": scorers,
                    "headline": result.headline,
                    "evaluation_mode": evaluation_mode,
                },
                metrics=result.headline,
                errors=[],
            )

        except Exception as exc:
            return ToolRunResult(
                tool_name=self.tool_name,
                success=False,
                output_reference=str(audit_out),
                summary={"dataset": str(dataset_ref)},
                metrics={},
                errors=[str(exc)],
            )
