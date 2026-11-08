"""
Tool registry for managing and discovering VAULT tool runners.
Supports dynamic registration and mock runner overrides for testing.
"""

from typing import Dict, List, Optional
from backend.integrations.base_runner import BaseToolRunner


class ToolRegistry:
    def __init__(self):
        self._runners: Dict[str, BaseToolRunner] = {}

    def register(self, name: str, runner: BaseToolRunner) -> None:
        """Registers a runner instance under the specified name."""
        self._runners[name.lower().strip()] = runner

    def get(self, name: str) -> Optional[BaseToolRunner]:
        """Retrieves a runner by name, or None if not found."""
        return self._runners.get(name.lower().strip())

    def list_tools(self) -> List[str]:
        """Returns sorted list of registered tool names."""
        return sorted(self._runners.keys())

    def clear(self) -> None:
        """Clears registered runners."""
        self._runners.clear()


registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Returns the global ToolRegistry singleton."""
    return registry
