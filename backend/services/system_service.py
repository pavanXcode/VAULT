"""
System inspection and resource monitoring service for VAULT.
"""

from datetime import datetime, timezone
import importlib.metadata
import platform
import sys
from typing import Any, Dict
import psutil
from backend.config import get_settings
from backend.database import check_db_connection
from backend.schemas.common import HealthResponse, SystemInfoResponse

settings = get_settings()


def get_installed_tool_version(package_name: str) -> Dict[str, Any]:
    """Inspects if a VAULT kit is installed and returns version and metadata."""
    try:
        ver = importlib.metadata.version(package_name)
        return {"installed": True, "version": ver, "status": "available"}
    except importlib.metadata.PackageNotFoundError:
        return {"installed": False, "version": None, "status": "not_installed"}
    except Exception as exc:
        return {"installed": False, "error": str(exc), "status": "error"}


def get_health_status() -> HealthResponse:
    """Returns current health status of the backend and core dependencies."""
    db_connected = check_db_connection()
    status = "ok" if db_connected else "degraded"

    return HealthResponse(
        status=status,
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        offline_mode=settings.offline_mode,
        database_connected=db_connected,
        timestamp=datetime.now(timezone.utc),
    )


def get_system_info() -> SystemInfoResponse:
    """Returns comprehensive system metrics, environment state, and tool availability."""
    db_connected = check_db_connection()

    # Hardware & OS metrics
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(".")
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # VAULT ecosystem tools detection
    vault_tools = {
        "CuratorKIT": get_installed_tool_version("curatorkit"),
        "SafeTune": get_installed_tool_version("safetune"),
        "AuditKIT": get_installed_tool_version("auditkit"),
    }

    # Safe local LLM config preview (no secrets)
    llm_config = {
        "mode": settings.llm_mode,
        "model": settings.llm_model,
        "endpoint": settings.llm_endpoint,
        "offline_enforced": settings.offline_mode,
    }

    db_type = "sqlite" if settings.is_sqlite else ("postgresql" if settings.is_postgres else "other")

    return SystemInfoResponse(
        platform=platform.platform(),
        os_name=platform.system(),
        os_version=platform.release(),
        python_version=sys.version.split()[0],
        cpu_count=psutil.cpu_count(logical=True) or 1,
        cpu_percent=cpu_percent,
        memory_total_gb=round(mem.total / (1024**3), 2),
        memory_available_gb=round(mem.available / (1024**3), 2),
        memory_used_percent=mem.percent,
        disk_total_gb=round(disk.total / (1024**3), 2),
        disk_free_gb=round(disk.free / (1024**3), 2),
        disk_used_percent=disk.percent,
        offline_mode=settings.offline_mode,
        database_type=db_type,
        database_connected=db_connected,
        vault_tools=vault_tools,
        llm_config=llm_config,
    )
