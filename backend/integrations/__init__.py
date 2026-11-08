"""
Tool integrations package for VAULT.
"""

from backend.integrations.audit_runner import AuditRunner
from backend.integrations.base_runner import BaseToolRunner, ToolRunResult
from backend.integrations.curator_runner import CuratorRunner
from backend.integrations.safetune_runner import SafeTuneRunner
from backend.integrations.tool_registry import ToolRegistry, get_tool_registry

# Register default tool runners
_default_registry = get_tool_registry()
_default_registry.register("curatorkit", CuratorRunner())
_default_registry.register("safetune", SafeTuneRunner())
_default_registry.register("auditkit", AuditRunner())

__all__ = [
    "BaseToolRunner",
    "ToolRunResult",
    "ToolRegistry",
    "get_tool_registry",
    "CuratorRunner",
    "SafeTuneRunner",
    "AuditRunner",
]
