"""
Base runner interface and standardized result contract for VAULT tool runners.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional


@dataclass
class ToolRunResult:
    """Standardized output contract returned by every tool runner."""

    tool_name: str
    success: bool
    output_reference: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    stdout: Optional[str] = None
    stderr: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "output_reference": self.output_reference,
            "summary": self.summary,
            "metrics": self.metrics,
            "errors": self.errors,
        }


class BaseToolRunner(ABC):
    """Abstract base class for all tool runners."""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Name of the tool handled by this runner."""
        pass

    @abstractmethod
    def validate_inputs(
        self,
        parameters: Dict[str, Any],
        input_reference: Optional[str] = None,
    ) -> None:
        """
        Validates arguments and input references before execution starts.
        Raises ValueError if validation fails.
        """
        pass

    @abstractmethod
    def execute(
        self,
        job_id: str,
        parameters: Dict[str, Any],
        input_reference: Optional[str],
        output_dir: Path,
        cancel_event: Optional[threading.Event] = None,
    ) -> ToolRunResult:
        """
        Executes the tool workflow, generating output artifacts in output_dir.
        Must respect cancel_event if checked during execution.
        """
        pass

    @staticmethod
    def is_cancelled_or_terminated(
        output_dir: Path, cancel_event: Optional[threading.Event] = None
    ) -> bool:
        """Checks cooperative cancellation event and output directory termination sentinel."""
        if cancel_event and cancel_event.is_set():
            return True
        if output_dir and (output_dir / ".execution_terminated").exists():
            return True
        return False

    @staticmethod
    def resolve_safe_path(path_str: str, allowed_roots: Optional[List[Path]] = None) -> Path:
        """
        Enforces path safety by resolving path and verifying it resides within allowed roots.
        Prevents directory traversal attacks.
        """
        target = Path(path_str).resolve()
        if allowed_roots:
            is_allowed = any(
                target == root.resolve() or root.resolve() in target.parents
                for root in allowed_roots
            )
            if not is_allowed:
                raise ValueError(
                    f"Access denied: path '{target}' is outside approved directories."
                )
        return target
