"""
CuratorKIT integration runner for dataset curation, deduplication, and quality gates.
"""

from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from backend.config import get_settings
from backend.integrations.base_runner import BaseToolRunner, ToolRunResult

settings = get_settings()


class CuratorRunner(BaseToolRunner):
    @property
    def tool_name(self) -> str:
        return "curatorkit"

    def validate_inputs(
        self,
        parameters: Dict[str, Any],
        input_reference: Optional[str] = None,
    ) -> None:
        dataset = parameters.get("dataset") or input_reference
        if not dataset:
            raise ValueError(
                "CuratorKIT requires a dataset path (pass via 'dataset' parameter or 'input_reference')."
            )

        # Path validation and directory restriction if local path
        if isinstance(dataset, str) and not dataset.startswith(("http://", "https://")):
            p = Path(dataset)
            if p.suffix and not p.exists():
                # Allow relative paths inside data directory
                resolved = (settings.resolved_upload_path.parent / dataset).resolve()
                if not resolved.exists() and not p.resolve().exists():
                    raise ValueError(f"CuratorKIT dataset path not found: {dataset}")

        # Check allowed generation tasks if specified
        gen_task = parameters.get("generation_task")
        allowed_tasks = {"qa", "preference", "grpo", "multiturn", "evol", "cot", "adversarial_preference", None}
        if gen_task not in allowed_tasks:
            raise ValueError(
                f"Invalid generation_task '{gen_task}'. Must be one of {sorted(list(allowed_tasks))}"
            )

    def execute(
        self,
        job_id: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        output_dir: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolRunResult:
        try:
            from curatorkit.curator import Curator, CuratorConfig
        except ImportError as err:
            return ToolRunResult(
                tool_name=self.tool_name,
                success=False,
                errors=[f"CuratorKIT is not installed: {err}"],
            )

        dataset = parameters.get("dataset") or input_reference
        curation_out = output_dir / "curated"
        curation_out.mkdir(parents=True, exist_ok=True)

        min_tokens = parameters.get("min_tokens", 10)
        max_tokens = parameters.get("max_tokens", 2048)
        format_type = parameters.get("format", "auto")
        max_samples = parameters.get("max_samples")

        generation_task = parameters.get("generation_task")
        llm_model = parameters.get("llm_model")
        llm_api_base = parameters.get("llm_api_base")

        if self.is_cancelled_or_terminated(output_dir, cancel_event):
            return ToolRunResult(
                tool_name=self.tool_name,
                success=False,
                errors=["Job was cancelled or timed out before execution started."],
            )

        try:
            config = CuratorConfig(
                dataset=dataset,
                output_dir=str(curation_out),
                min_tokens=min_tokens,
                max_tokens=max_tokens,
                format=format_type,
                max_samples=max_samples,
                generation_task=generation_task,
                llm_model=llm_model,
                llm_api_base=llm_api_base,
            )

            curator = Curator(config)
            res = curator.run()

            # Guard against modifying results after cancellation/timeout
            if self.is_cancelled_or_terminated(output_dir, cancel_event):
                return ToolRunResult(
                    tool_name=self.tool_name,
                    success=False,
                    errors=["Job was cancelled or timed out during execution."],
                )

            passed_count = len(res.passed) if res.passed is not None else 0
            rejected_count = len(res.rejected) if res.rejected is not None else 0
            total_samples = passed_count + rejected_count
            pass_rate = round(passed_count / total_samples, 4) if total_samples > 0 else 1.0

            summary = {
                "dataset": str(dataset),
                "total_samples": total_samples,
                "passed_samples": passed_count,
                "rejected_samples": rejected_count,
                "stage_counts": res.stage_counts,
                "output_dir": str(res.output_dir),
            }

            metrics = {
                "pass_rate": pass_rate,
                "wall_clock_seconds": round(getattr(res, "wall_clock_seconds", 0.0), 3),
            }

            return ToolRunResult(
                tool_name=self.tool_name,
                success=True,
                output_reference=str(res.output_dir),
                summary=summary,
                metrics=metrics,
                errors=[],
            )
        except Exception as exc:
            return ToolRunResult(
                tool_name=self.tool_name,
                success=False,
                output_reference=str(curation_out),
                summary={"dataset": str(dataset)},
                metrics={},
                errors=[str(exc)],
            )
