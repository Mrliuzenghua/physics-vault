"""Shared runtime primitives for the Physics Vault MCP entrypoint.

This package deliberately contains only infrastructure.  Tool handlers and
database schema ownership remain in their existing domain modules.
"""

from .audit import build_task_action_context
from .database import DatabaseRuntime
from .payloads import clean_args, tool_error
from .services import MCPServiceFactory

__all__ = [
    "DatabaseRuntime",
    "MCPServiceFactory",
    "build_task_action_context",
    "clean_args",
    "tool_error",
]
