"""Tool registry — manages tool registration, lookup, and dispatch.

References:
- Sakura: app/agent/tools/registry.py — ToolRegistry with prepare_or_execute()
  + describe_openai_tools() for LLM function-calling schema generation
- Sakura: app/agent/tools/permission_policy.py — risk-based confirmation

Design:
- Flat registry: name -> Tool mapping
- Filter by tag, permission level, enabled status
- Export OpenAI-compatible function schemas
"""

import logging
from typing import Any

from src.agent.base import Tool, ToolMeta, ToolResult, PermissionLevel

logger = logging.getLogger("hachicat.agent")


class ToolRegistry:
    """Central registry for all tools available to the agent."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ValueError on duplicate name."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (permission=%s)", tool.name, tool.meta.permission.name)

    def unregister(self, name: str) -> None:
        """Remove a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> list[ToolMeta]:
        """List metadata for all registered tools."""
        return [t.meta for t in self._tools.values()]

    def list_by_tag(self, tag: str) -> list[ToolMeta]:
        """List tools matching a tag."""
        return [t.meta for t in self._tools.values() if tag in t.meta.tags]

    def list_by_permission(self, max_level: PermissionLevel) -> list[ToolMeta]:
        """List tools at or below a permission level."""
        return [t.meta for t in self._tools.values() if t.meta.permission <= max_level]

    async def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """Execute a tool by name. Returns error result if tool not found."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                message=f"未知工具: {name}",
                error=f"Tool '{name}' not registered",
                pet_reaction="sad",
            )

        try:
            logger.info("Executing tool: %s with params: %s", name, params)
            result = await tool.handler(params)
            logger.info("Tool %s result: success=%s", name, result.success)
            return result
        except Exception as e:
            logger.exception("Tool %s failed with exception", name)
            return ToolResult(
                success=False,
                message=f"执行失败: {name}",
                error=str(e),
                pet_reaction="sad",
            )

    def to_openai_functions(self, enabled_tools: set[str] | None = None) -> list[dict[str, Any]]:
        """Export all (or filtered) tools as OpenAI function-calling schemas."""
        tools = self._tools.values()
        if enabled_tools is not None:
            tools = [t for t in tools if t.name in enabled_tools]
        return [t.to_openai_function() for t in tools]

    def tool_names(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
