"""TODO Manager tool with SQLite persistence.

References:
- Sakura: app/agent/builtin_tools.py — add_todo, list_todos, complete_todo
  with SQLite backend, priority, due_date, status fields
- Design doc section 7.2: full TODO CRUD spec

Operations: add, list, complete, delete
Permission: SAFE for list, NOTIFY for add/complete, CONFIRM for delete
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent.base import Tool, ToolMeta, ToolResult, PermissionLevel
from src.memory.database import Database

logger = logging.getLogger("hachicat.tools.todo")


class TodoManager:
    """Backend for TODO CRUD operations backed by SQLite."""

    def __init__(self, db: Database):
        self._db = db

    def add(self, title: str, description: str = "",
            priority: int = 0, due_date: str = "",
            source: str = "manual", tags: list[str] | None = None) -> dict[str, Any]:
        """Add a new TODO item. Returns the created row."""
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        row_id = self._db.insert(
            """INSERT INTO todos (title, description, priority, due_date, source, tags)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, description, priority, due_date, source, tags_json),
        )
        logger.info("Added TODO #%d: %s", row_id, title)
        return self._db.fetch_one("SELECT * FROM todos WHERE id = ?", (row_id,)) or {"id": row_id}

    def list(self, status: str = "pending", limit: int = 10) -> list[dict[str, Any]]:
        """List TODO items by status."""
        rows = self._db.fetch_all(
            "SELECT * FROM todos WHERE status = ? ORDER BY priority DESC, created_at DESC LIMIT ?",
            (status, limit),
        )
        return rows

    def complete(self, todo_id: int) -> dict[str, Any] | None:
        """Mark a TODO as done."""
        self._db.update(
            "UPDATE todos SET status = 'done', completed_at = datetime('now','localtime') WHERE id = ?",
            (todo_id,),
        )
        return self._db.fetch_one("SELECT * FROM todos WHERE id = ?", (todo_id,))

    def delete(self, todo_id: int) -> bool:
        """Delete a TODO item."""
        rowcount = self._db.update("DELETE FROM todos WHERE id = ?", (todo_id,))
        return rowcount > 0

    def find_by_title(self, title: str) -> list[dict[str, Any]]:
        """Fuzzy-find TODO by title."""
        return self._db.fetch_all(
            "SELECT * FROM todos WHERE title LIKE ? AND status = 'pending'",
            (f"%{title}%",),
        )


# --- Tool factory ---

def create_todo_tool(db: Database) -> Tool:
    """Create the TODO manager tool with SQLite backend."""
    manager = TodoManager(db)

    meta = ToolMeta(
        name="todo_manager",
        display_name="📋 待办管理",
        description="管理待办事项: 添加、查看、完成、删除待办",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "complete", "delete"],
                    "description": "操作类型",
                },
                "title": {
                    "type": "string",
                    "description": "待办标题 (add 操作需要)",
                },
                "description": {
                    "type": "string",
                    "description": "待办详细描述",
                },
                "priority": {
                    "type": "integer",
                    "enum": [0, 1, 2],
                    "description": "优先级: 0=低, 1=中, 2=高",
                },
                "due_date": {
                    "type": "string",
                    "description": "截止日期 (ISO 8601 格式)",
                },
                "todo_id": {
                    "type": "integer",
                    "description": "待办ID (complete/delete 操作需要)",
                },
            },
            "required": ["action"],
        },
        permission=PermissionLevel.NOTIFY,
        icon="📋",
        tags=["productivity"],
    )

    async def handler(params: dict[str, Any]) -> ToolResult:
        action = params.get("action", "list")

        try:
            if action == "add":
                # Accept flexible param names from LLM: title, content, text, name, task
                title = (
                    params.get("title") or
                    params.get("content") or
                    params.get("text") or
                    params.get("name") or
                    params.get("task") or
                    ""
                ).strip()
                if not title:
                    return ToolResult(
                        success=False, message="待办标题不能为空，请提供具体内容",
                        pet_reaction="sad",
                    )
                desc = params.get("description", "") or params.get("desc", "")
                priority = params.get("priority", 0)
                due_date = params.get("due_date", "") or params.get("deadline", "") or params.get("date", "")
                source = params.get("source", "hotkey")
                tags = params.get("tags")

                result = manager.add(title, desc, priority, due_date, source, tags)
                # Calculate time until deadline
                due_msg = ""
                if due_date:
                    from datetime import datetime
                    try:
                        # Try with time, then date-only
                        has_time = False
                        try:
                            d = datetime.strptime(due_date.strip(), "%Y-%m-%d %H:%M")
                            has_time = True
                        except ValueError:
                            d = datetime.strptime(due_date.strip(), "%Y-%m-%d")

                        now = datetime.now()
                        delta = d - now
                        total_hours = delta.total_seconds() / 3600

                        if total_hours < 0:
                            due_msg = f"\n⏰ {due_date}（已过期）"
                        elif has_time and total_hours < 24:
                            if total_hours < 1:
                                due_msg = f"\n⏰ {due_date}（不到1小时！）"
                            else:
                                due_msg = f"\n⏰ {due_date}（还有{int(total_hours)}小时）"
                        else:
                            days = int(total_hours / 24)
                            if days == 0:
                                due_msg = f"\n⏰ {due_date}（今天截止！）"
                            elif days == 1:
                                due_msg = f"\n⏰ {due_date}（明天截止）"
                            else:
                                due_msg = f"\n⏰ {due_date}（还有{days}天）"
                    except (ValueError, TypeError):
                        due_msg = f"\n⏰ {due_date}"
                return ToolResult(
                    success=True,
                    message=f"已添加待办 ✓\n📌 {title}{due_msg}",
                    data=result,
                    pet_reaction="happy",
                )

            elif action == "list":
                items = manager.list(limit=5)
                if not items:
                    return ToolResult(
                        success=True, message="当前没有待办事项 🎉",
                        data=[], pet_reaction="happy",
                    )
                lines = [f"📋 待办 ({len(items)}):"]
                for i, item in enumerate(items):
                    check = "☐" if item["status"] == "pending" else "☑"
                    lines.append(f"  {check} [{item['id']}] {item['title']}")
                return ToolResult(
                    success=True, message="\n".join(lines),
                    data=items, pet_reaction="happy",
                )

            elif action == "complete":
                todo_id = params.get("todo_id")
                if not todo_id:
                    return ToolResult(
                        success=False, message="需要提供待办ID",
                        pet_reaction="sad",
                    )
                item = manager.complete(int(todo_id))
                if item:
                    return ToolResult(
                        success=True, message=f"已完成 ✓\n✅ {item['title']}",
                        data=item, pet_reaction="happy",
                    )
                return ToolResult(
                    success=False, message=f"未找到待办 #{todo_id}",
                    pet_reaction="sad",
                )

            elif action == "delete":
                todo_id = params.get("todo_id")
                if not todo_id:
                    return ToolResult(
                        success=False, message="需要提供待办ID",
                        pet_reaction="sad",
                    )
                deleted = manager.delete(int(todo_id))
                if deleted:
                    return ToolResult(
                        success=True, message=f"已删除待办 #{todo_id} 🗑️",
                        pet_reaction="happy",
                    )
                return ToolResult(
                    success=False, message=f"未找到待办 #{todo_id}",
                    pet_reaction="sad",
                )

            else:
                return ToolResult(
                    success=False, message=f"未知操作: {action}",
                    pet_reaction="sad",
                )

        except Exception as e:
            logger.exception("TODO tool error")
            return ToolResult(
                success=False, message=f"待办操作失败: {e}",
                error=str(e), pet_reaction="sad",
            )

    return Tool(meta=meta, handler=handler)
