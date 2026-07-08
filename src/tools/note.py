"""Note/知识库 tool — save text snippets for later reference."""

import logging
from typing import Any

from src.agent.base import Tool, ToolMeta, ToolResult, PermissionLevel
from src.memory.database import Database

logger = logging.getLogger("hachicat.tools.note")


def create_note_tool(db: Database) -> Tool:
    meta = ToolMeta(
        name="note_manager",
        display_name="📝 笔记",
        description="保存文本片段、知识点、参考资料",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "delete"],
                    "description": "操作类型",
                },
                "content": {
                    "type": "string",
                    "description": "笔记内容 (add 操作需要)",
                },
                "title": {
                    "type": "string",
                    "description": "笔记标题（可选，LLM自动生成摘要）",
                },
                "note_id": {
                    "type": "integer",
                    "description": "笔记ID (delete 操作需要)",
                },
            },
            "required": ["action"],
        },
        permission=PermissionLevel.SAFE,
        icon="📝",
        tags=["knowledge"],
    )

    async def handler(params: dict[str, Any]) -> ToolResult:
        action = params.get("action", "add")

        try:
            if action == "add":
                content = (
                    params.get("content") or
                    params.get("text") or
                    params.get("body") or
                    ""
                ).strip()
                if not content:
                    return ToolResult(success=False, message="笔记内容不能为空", pet_reaction="sad")

                title = (params.get("title") or params.get("summary") or "").strip()
                if not title and len(content) > 30:
                    title = content[:30] + "…"
                elif not title:
                    title = content

                db.insert(
                    "INSERT INTO notes (title, content, source) VALUES (?, ?, ?)",
                    (title, content, "selection"),
                )
                return ToolResult(
                    success=True,
                    message=f"已保存笔记 📝\n{title}",
                    pet_reaction="happy",
                )

            elif action == "list":
                notes = db.fetch_all(
                    "SELECT id, title, created_at FROM notes ORDER BY created_at DESC LIMIT 10"
                )
                if not notes:
                    return ToolResult(success=True, message="暂无笔记", data=[], pet_reaction="happy")
                lines = [f"📝 笔记 ({len(notes)}):"]
                for n in notes:
                    lines.append(f"  [{n['id']}] {n['title']}")
                return ToolResult(success=True, message="\n".join(lines), data=notes, pet_reaction="happy")

            elif action == "delete":
                nid = params.get("note_id")
                if not nid:
                    return ToolResult(success=False, message="需要提供笔记ID", pet_reaction="sad")
                db.update("DELETE FROM notes WHERE id=?", (int(nid),))
                return ToolResult(success=True, message=f"已删除笔记 #{nid}", pet_reaction="happy")

            else:
                return ToolResult(success=False, message=f"未知操作: {action}", pet_reaction="sad")

        except Exception as e:
            logger.exception("Note tool error")
            return ToolResult(success=False, message=f"笔记操作失败: {e}", pet_reaction="sad")

    return Tool(meta=meta, handler=handler)
