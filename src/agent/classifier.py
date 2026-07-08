"""Two-level intent classifier: rules first, LLM as fallback.

References:
- Sakura: uses native OpenAI tool_calls for intent (single-level LLM)
  — we add a rule layer before LLM for speed and offline capability
- KillClawd: completion-format prompting with few-shot examples,
  environment context injection

Design:
- Level 1 (RuleEngine): regex + keyword matching, zero latency, works offline
- Level 2 (LLMFallback): sends to LLM for fuzzy intent classification
- Returns structured Intent with tool_name + params + confidence
"""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntentRule:
    """A rule for matching user input to a tool intent."""
    pattern: str                      # Regex pattern (or simple keyword)
    tool_name: str                    # Tool to invoke
    confidence: float = 0.85          # Base confidence for rule match
    param_map: dict[str, str] | None = None  # Regex group -> param name
    description: str = ""


@dataclass
class Intent:
    """Classified user intent."""
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source: str = "rule"            # "rule" | "llm"
    needs_confirmation: bool = False
    raw_input: str = ""


# --- Built-in intent rules (MVP) ---

BUILTIN_RULES: list[IntentRule] = [
    # URL detection
    IntentRule(
        pattern=r"^(https?://|www\.)[^\s]+$",
        tool_name="browser_opener",
        confidence=0.95,
        param_map={"0": "url"},
        description="打开网页",
    ),
    # TODO patterns
    IntentRule(
        pattern=r"^(TODO|待办|任务|记得|别忘了)[:：\s]*(.+)",
        tool_name="todo_manager",
        confidence=0.90,
        param_map={"2": "title"},
        description="添加待办",
    ),
    # Search patterns
    IntentRule(
        pattern=r"^(搜索|查找|搜一下|帮我搜)[:：\s]*(.+)",
        tool_name="browser_opener",
        confidence=0.90,
        param_map={"2": "query"},
        description="搜索",
    ),
    # Reminder patterns
    IntentRule(
        pattern=r"(\d+)\s*(分钟|小时|天|周)?\s*(后|之后|以后)\s*(提醒|叫我|通知)",
        tool_name="quick_reminder",
        confidence=0.82,
        description="设置提醒",
    ),
    # Music patterns
    IntentRule(
        pattern=r"^(播放|听|放|来首|音乐|听歌)",
        tool_name="music_controller",
        confidence=0.80,
        description="播放音乐",
    ),
]

# Open/launch patterns
APP_LAUNCH_RULE = IntentRule(
    pattern=r"^(打开|启动|运行|launch)\s+(.+)",
    tool_name="app_launcher",
    confidence=0.85,
    param_map={"2": "app_name"},
    description="打开应用",
)
BUILTIN_RULES.append(APP_LAUNCH_RULE)


class RuleEngine:
    """Fast regex + keyword intent matching.

    Runs before LLM to handle common patterns instantly.
    """

    def __init__(self, rules: list[IntentRule] | None = None):
        self._rules = rules or BUILTIN_RULES
        self._compiled: list[tuple[re.Pattern, IntentRule]] = [
            (re.compile(r.pattern, re.IGNORECASE), r) for r in self._rules
        ]

    def classify(self, text: str) -> Intent | None:
        """Try to match input against rules. Returns None if no match."""
        if not text or not text.strip():
            return None

        text = text.strip()

        for pattern, rule in self._compiled:
            match = pattern.match(text)
            if match:
                params: dict[str, Any] = {}
                if rule.param_map:
                    for group_name, param_name in rule.param_map.items():
                        try:
                            idx = int(group_name)
                            value = match.group(idx)
                        except (ValueError, IndexError):
                            value = match.group(group_name)
                        if value:
                            params[param_name] = value.strip()

                return Intent(
                    tool_name=rule.tool_name,
                    params=params,
                    confidence=rule.confidence,
                    source="rule",
                    raw_input=text,
                )

        return None

    def add_rule(self, rule: IntentRule) -> None:
        """Add a new rule at runtime."""
        self._rules.append(rule)
        self._compiled.append((re.compile(rule.pattern, re.IGNORECASE), rule))

    def remove_rule(self, description: str) -> bool:
        """Remove rules by description."""
        initial_count = len(self._rules)
        self._rules = [r for r in self._rules if r.description != description]
        self._compiled = [
            (p, r) for p, r in self._compiled if r.description != description
        ]
        return len(self._rules) < initial_count


class IntentClassifier:
    """Two-level intent classification.

    Level 1: RuleEngine (fast, offline, 0ms)
    Level 2: LLM fallback (DeepSeek / Ollama / OpenAI)
    """

    def __init__(self, rules: list[IntentRule] | None = None):
        self._rule_engine = RuleEngine(rules)
        self._llm_client = None  # Any client with classify_intent(user_input) → LLMResponse

    def classify(self, text: str, extra_context: str = "") -> Intent | None:
        """Classify user input synchronously.

        First tries rules. If no match, tries LLM.
        """
        # Level 1: Rule matching (instant)
        intent = self._rule_engine.classify(text)
        if intent and intent.confidence >= 0.85:
            return intent

        # Level 2: LLM fallback
        if self._llm_client:
            try:
                import json
                response = self._llm_client.classify_intent(text, extra_context)
                if response.success and response.text:
                    data = json.loads(response.text)
                    tool_name = data.get("tool", "none")
                    if tool_name and tool_name != "none":
                        return Intent(
                            tool_name=tool_name,
                            params=data.get("params", {}),
                            confidence=data.get("confidence", 0.7),
                            source="llm",
                            raw_input=text,
                        )
            except Exception:
                pass  # LLM failed, fall through

        # No match from either level — return low-confidence rule result or None
        return intent

    def set_llm_client(self, client) -> None:
        """Inject LLM client (OpenAIClient, OllamaClient, etc.)."""
        self._llm_client = client
