"""Agent core data types — Tool system.

References:
- Sakura: app/agent/tools/registry.py — Tool(DataClass), ToolRegistry, ToolExecutionResult
- OpenPet: lib.rs — RuntimeState, ActionPayload, EventType

Design:
- Tool is a data class describing what a tool can do
- ToolRegistry manages registration and dispatch
- ToolResult standardizes execution outcomes
- PermissionLevel controls confirmation UX
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Protocol


class PermissionLevel(IntEnum):
    """Risk tier for tool execution confirmation.

    References Sakura's three-tier permission model.
    """
    SAFE = 0       # No confirmation needed (e.g., view todos)
    NOTIFY = 1     # Brief bubble notification (e.g., add todo, open website)
    CONFIRM = 2    # User must explicitly approve (e.g., delete file)
    BLOCK = 3      # Always blocked unless user explicitly allows


@dataclass
class ToolMeta:
    """Metadata describing a tool to both the system and LLM."""
    name: str                          # Unique ID: "todo_manager"
    display_name: str                  # Human-readable: "📋 待办管理"
    description: str                   # What it does, shown to LLM
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema for params
    permission: PermissionLevel = PermissionLevel.NOTIFY
    icon: str = "🔧"                   # Emoji for menus
    tags: list[str] = field(default_factory=list)  # For grouping: ["productivity", "system"]


@dataclass
class ToolResult:
    """Standardized result from tool execution.

    Used by the pet to decide animation (happy/sad) and bubble message.
    """
    success: bool
    message: str                       # Short bubble message: "已添加待办 ✓"
    data: Any = None                   # Structured data for further processing
    error: str | None = None           # Error detail if success=False
    pet_reaction: str = "happy"        # "happy" | "sad" | "working" | "idle"


class ToolHandler(Protocol):
    """Callable that executes a tool and returns a ToolResult."""
    async def __call__(self, params: dict[str, Any]) -> ToolResult: ...


@dataclass
class Tool:
    """A registered tool that the agent can call.

    Combines metadata with its execution handler.
    """
    meta: ToolMeta
    handler: ToolHandler

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def description(self) -> str:
        return self.meta.description

    def to_openai_function(self) -> dict[str, Any]:
        """Export as OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.meta.name,
                "description": self.meta.description,
                "parameters": self.meta.parameters,
            },
        }
