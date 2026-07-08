"""Smart reminder engine — urgency-based todo reminders + wellness nudges.

Reminder frequency adapts to deadline proximity:
- URGENT  (<1 day):         every 20-40 min
- SOON    (1-3 days):       every 1-2 hours
- LATER   (3+ days/no DDL): every 3-5 hours
- Wellness:                 every 50-70 min
"""

import json
import logging
import random
import time
from datetime import datetime, date
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from src.memory.database import Database

logger = logging.getLogger("hachicat.reminder")

REMINDER_PROMPT = """根据用户待办列表，选出最该提醒的一项，生成一句简洁提醒。

待办：
{todo_list}

要求：简洁自然，≤20字，有截止日期要提。格式："记得xxx"/"别忘了xxx"
输出纯JSON：{{"index":数字,"reminder":"文字"}}"""

WELLNESS_REMINDERS = [
    "记得喝水哦 💧",
    "站起来活动一下吧 🧘",
    "休息一下眼睛，看看远处 👀",
    "伸个懒腰，放松肩膀",
    "该起来走走了 🚶",
]

# Urgency → (min_seconds, max_seconds)
DEFAULT_URGENCY_INTERVALS: dict[str, tuple[int, int]] = {
    "urgent": (20 * 60, 40 * 60),       # 20-40 min
    "soon":   (60 * 60, 120 * 60),      # 1-2 hours
    "later":  (180 * 60, 300 * 60),     # 3-5 hours
}
DEFAULT_WELLNESS_INTERVAL = (50 * 60, 70 * 60)  # 50-70 min


def _days_until(due_str: str) -> int | None:
    """Parse a due date string and return days until deadline, or None."""
    if not due_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
        try:
            d = datetime.strptime(due_str.strip()[:10], fmt.split(" ")[0])
            return (d.date() - date.today()).days
        except (ValueError, TypeError):
            continue
    return None


class ReminderEngine(QObject):
    """Periodic reminder engine with smart urgency-based scheduling."""

    reminder_ready = Signal(str)

    def __init__(
        self,
        db: Database,
        llm_client=None,
        urgency_intervals: dict[str, tuple[int, int]] | None = None,
        wellness_interval: tuple[int, int] | None = None,
        enabled: bool = True,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._db = db
        self._llm = llm_client
        self._urgent_int = urgency_intervals or DEFAULT_URGENCY_INTERVALS
        self._wellness_int = wellness_interval or DEFAULT_WELLNESS_INTERVAL
        self._enabled = enabled
        self._last_todo_time = 0.0
        self._last_wellness_time = 0.0
        self._wellness_index = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setSingleShot(True)

        if enabled:
            QTimer.singleShot(120_000, self._schedule_next)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self._schedule_next()
        else:
            self._timer.stop()

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _schedule_next(self) -> None:
        if not self._enabled:
            return

        now = time.time()

        # Determine next check time based on urgency of pending todos
        try:
            todos = self._db.fetch_all(
                "SELECT * FROM todos WHERE status='pending' ORDER BY priority DESC"
            )
        except Exception:
            todos = []

        min_wait = self._calc_min_wait(todos, now)
        # Random jitter: ±5 to ±30 minutes (±300 to ±1800 seconds)
        jitter = random.randint(-1800, 1800)
        base = max(60, min_wait + jitter)
        seconds = random.randint(base, int(base * 1.3))
        self._timer.start(seconds * 1000)

    def _calc_min_wait(self, todos: list[dict], now: float) -> int:
        """Calculate minimum wait based on most urgent todo + wellness timer."""
        # Base: wellness interval
        wellness_elapsed = now - self._last_wellness_time
        wellness_due = max(0, self._wellness_int[0] - int(wellness_elapsed))

        if not todos:
            return max(wellness_due, 3600)  # No todos: check hourly

        # Find the most urgent todo
        min_days = None
        for t in todos:
            d = _days_until(t.get("due_date", ""))
            if d is not None and (min_days is None or d < min_days):
                min_days = d

        # Map urgency → interval
        if min_days is not None and min_days <= 0:
            urgency = "urgent"
        elif min_days is not None and min_days <= 3:
            urgency = "soon"
        else:
            urgency = "later"

        interval = self._urgent_int[urgency]
        todo_wait = interval[0]

        # Return the shorter of wellness vs todo
        return min(wellness_due, todo_wait) if wellness_due > 0 else todo_wait

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        if not self._enabled:
            self._schedule_next()
            return

        now = time.time()

        # Wellness check
        wellness_elapsed = now - self._last_wellness_time
        wellness_target = random.randint(*self._wellness_int)
        if wellness_elapsed >= wellness_target:
            msg = WELLNESS_REMINDERS[self._wellness_index % len(WELLNESS_REMINDERS)]
            self._wellness_index += 1
            self._last_wellness_time = now
            self._emit(msg)
            self._schedule_next()
            return

        # Todo check
        try:
            todos = self._db.fetch_all(
                "SELECT * FROM todos WHERE status='pending' ORDER BY priority DESC"
            )
        except Exception:
            self._schedule_next()
            return

        if not todos:
            self._schedule_next()
            return

        # Pick most urgent
        todos_sorted = sorted(
            todos,
            key=lambda t: (_days_until(t.get("due_date", "")) or 999, -(t.get("priority", 0))),
        )

        if self._llm and len(todos_sorted) > 1:
            reminder = self._llm_pick(todos_sorted)
        else:
            reminder = self._simple(todos_sorted[0])

        if reminder:
            self._last_todo_time = now
            self._emit(reminder)

        self._schedule_next()

    # ------------------------------------------------------------------
    # Reminder generation
    # ------------------------------------------------------------------

    def _simple(self, todo: dict) -> str:
        title = todo["title"]
        due = todo.get("due_date", "")
        days = _days_until(due)
        if days is not None and days <= 0:
            return f"别忘了{title}，今天截止！"
        if days is not None and days == 1:
            return f"别忘了{title}，明天截止"
        if due:
            return f"记得{title}，{due}截止"
        return f"记得{title}"

    def _llm_pick(self, todos: list[dict]) -> str | None:
        lines = []
        for i, t in enumerate(todos, 1):
            parts = [f"{i}. {t['title']}"]
            d = _days_until(t.get("due_date", ""))
            if d is not None and d <= 0:
                parts.append("(今天截止!!)")
            elif d is not None and d <= 3:
                parts.append(f"({d}天后截止)")
            elif t.get("due_date"):
                parts.append(f"(截止: {t['due_date']})")
            lines.append(" ".join(parts))

        prompt = REMINDER_PROMPT.format(todo_list="\n".join(lines))

        try:
            if hasattr(self._llm, 'chat'):
                resp = self._llm.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.8, max_tokens=100,
                )
            elif hasattr(self._llm, 'complete'):
                resp = self._llm.complete(prompt)
            else:
                return None

            if not resp.success or not resp.text:
                return None

            text = resp.text.strip()
            s, e = text.find("{"), text.rfind("}") + 1
            if s >= 0 and e > s:
                data = json.loads(text[s:e])
                r = data.get("reminder", "")
                if r:
                    logger.info("LLM reminder #%d: %s", data.get("index", 1), r)
                    return r
        except Exception as ex:
            logger.warning("LLM reminder failed: %s", ex)

        return None

    def _emit(self, text: str) -> None:
        logger.info("Reminder: %s", text)
        self.reminder_ready.emit(text)
