"""LLM client — OpenAI-compatible API (DeepSeek, Ollama, OpenAI, etc.)

References:
- DeepSeek API: https://platform.deepseek.com/api-docs (OpenAI-compatible)
- KillClawd: completion-style with short prompts, fast timeout, envCtx() injection
- Sakura: native OpenAI tool_calls, structured JSON output

Design:
- Single OpenAIClient for all OpenAI-compatible providers
- Two modes: completion (fast, for simple classify) and chat (for tool calling)
- Prompt engineering for Chinese intent classification
- Graceful timeout and error handling
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("hachicat.llm")


# ======================================================================
# Data types
# ======================================================================

@dataclass
class LLMConfig:
    """LLM backend configuration."""
    provider: str = "deepseek"          # deepseek | ollama | openai | custom
    model: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""                   # Required for cloud APIs
    temperature: float = 0.1
    max_tokens: int = 512
    timeout_seconds: float = 60.0
    enabled: bool = True


@dataclass
class LLMResponse:
    """Structured LLM response."""
    text: str
    tool_calls: list[dict[str, Any]] | None = None
    tokens_used: int = 0
    model: str = ""
    latency_ms: float = 0.0
    success: bool = True
    error: str = ""


# ======================================================================
# Intent classification prompt
# ======================================================================

FORCE_TODO_PROMPT = """现在时间是 {current_datetime}（{weekday}）。用户选中了一段文字并选择了"添加待办"，你必须从中提取所有的待办事项。

## 需要识别的内容类型
- 任务、作业、截止日期 → 待办
- 会议邀请、日程安排 → 待办（提取会议主题+时间）
- 购物清单、提醒事项 → 待办
- 任何"需要在某个时间做某事"的文字 → 待办
- 腾讯会议/zoom/teams等会议链接 → 待办（提取会议主题作为标题，时间作为due_date）

## 示例
选中"王庆华邀请您参加腾讯会议，会议时间：2026/06/25 22:46-23:46" → title:"参加腾讯会议-王庆华"，due_date:"2026-06-25 22:46"
选中"记得买牛奶和面包" → title:"买牛奶和面包"

## 任务
- 仔细阅读全文，识别出所有独立的任务项
- 不同截止日期的任务 → 分开提取为多条
- 同一截止日期的同类任务 → 可以合并
- 每条标题 ≤20字，简洁准确
- 原文保存到 description

## 时间提取
- 先理解语义，判断哪个时间才是真正的截止时间
- 忽略背景描述中提到的时间，只关注任务本身的截止时间
- 暗示词："之前"、"前"、"ddl"、"截止"、"交"、"提交"、"发送"、"完成"
- 格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM，没有就不填
- 现在是 {current_datetime}，"明天"={tomorrow}，"后天"={day_after_tomorrow}

## 输出
多条输出数组，单条输出对象：
{{"todos":[{{"title":"任务1","due_date":"日期","description":"原文"}},{{"title":"任务2","due_date":"日期","description":"原文"}}]}}"""

INTENT_SYSTEM_PROMPT = """你是一个智能桌面助手。现在时间是 {current_datetime}（{weekday}）。用户选中了一段文字并触发了你，你需要判断这段文字应该怎么处理。

## 时间识别规则（重要）
- 先理解语义再提取时间，不要看到数字就当作截止时间
- 截止时间是"事情需要在什么时候之前完成"，忽略背景信息中提到的时间
- "明天"={tomorrow}，"后天"={day_after_tomorrow}，"下周X"=下周对应日期
- "6月9日"→未过就是今年，已过就是明年
- 有具体时间点用 YYYY-MM-DD HH:MM，只有日期用 YYYY-MM-DD
- 没有明确截止时间就不要填 due_date

## 可用工具

1. todo_manager — 待办事项
   参数: {{"action":"add", "title":"简短标题(≤20字)", "due_date":"YYYY-MM-DD 或 YYYY-MM-DD HH:MM(可选)", "description":"详细描述(可选)"}}
   例: 用户选中 "明天下午3点前交报告" → {{"tool":"todo_manager","params":{{"action":"add","title":"交报告","due_date":"{tomorrow} 15:00","description":"明天下午3点前交报告"}}}}
   例: 用户选中 "下周一把PPT改好发给我" → {{"tool":"todo_manager","params":{{"action":"add","title":"改好PPT发给同事","due_date":"2026-06-30","description":"下周一把PPT改好发给我"}}}}

2. note_manager — 保存笔记
   参数: {{"action":"add", "content":"原文", "title":"简短概括(≤20字)"}}

3. browser_opener — 打开网页
   参数: {{"url":"完整网址"}}

## 规则
- 输出纯JSON，tool 只能用 todo_manager / note_manager / browser_opener / none
- todo 的 title 是AI总结的简短标题，≤20字
- **description 必须包含用户选中的原文字段**（这是最重要的，方便用户回溯原文）
- 日期时间必须准确转换
{{"tool":"工具名","params":{{...}},"confidence":0.85,"reason":"简短理由"}}"""


# ======================================================================
# OpenAI-compatible Client
# ======================================================================

class OpenAIClient:
    """Generic OpenAI-compatible API client.

    Works with: DeepSeek, Ollama (/v1), OpenAI, Groq, and any
    other provider that supports /v1/chat/completions endpoint.
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._client = httpx.Client(
            timeout=config.timeout_seconds,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}",
            },
        )

    def _url(self, path: str) -> str:
        """Build a full API URL, handling /v1 prefix smartly."""
        base = self._config.api_base.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}{path}"
        return f"{base}/v1{path}"

    @property
    def is_available(self) -> bool:
        """Quick check if the API is reachable."""
        try:
            r = self._client.get(
                self._url("/models"),
                timeout=5.0,
            )
            return r.status_code < 500
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Fetch available model IDs from the API.

        Returns a sorted list of model id strings, or empty list on failure.
        """
        import logging
        logger = logging.getLogger("hachicat")
        try:
            url = self._url("/models")
            r = self._client.get(url, timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                raw = data.get("data", [])
                models = [m.get("id", "") for m in raw if m.get("id")]
                logger.debug("Fetched %d models from %s", len(models), url)
                return sorted(models)
            logger.warning("Model list failed (%d): %s", r.status_code, r.text[:200])
            return []
        except Exception as e:
            logger.error("list_models error: %s", e)
            return []

    def chat(self, messages: list[dict[str, str]], **kwargs) -> LLMResponse:
        """Chat completion — used for intent classification and tool calling.

        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."}
            **kwargs: Override model, temperature, max_tokens

        Returns:
            LLMResponse with the assistant's text response
        """
        model = kwargs.get("model", self._config.model)
        temperature = kwargs.get("temperature", self._config.temperature)
        max_tokens = kwargs.get("max_tokens", self._config.max_tokens)
        response_format = kwargs.get("response_format", None)  # {"type": "json_object"}

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format

        t0 = time.monotonic()

        try:
            r = self._client.post(
                self._url("/chat/completions"),
                json=payload,
            )

            if r.status_code == 401:
                return LLMResponse(
                    text="", success=False,
                    error="API key 无效，请检查 settings.json 中的 api_key",
                    latency_ms=(time.monotonic() - t0) * 1000,
                )
            if r.status_code == 429:
                return LLMResponse(
                    text="", success=False,
                    error="API 请求过于频繁，请稍后再试",
                    latency_ms=(time.monotonic() - t0) * 1000,
                )

            r.raise_for_status()
            data = r.json()

            choice = data["choices"][0]
            content = choice["message"].get("content", "") or ""
            usage = data.get("usage", {})

            latency = (time.monotonic() - t0) * 1000
            logger.debug(
                "LLM chat: model=%s tokens=%s latency=%.0fms",
                data.get("model", model),
                usage.get("total_tokens", "?"),
                latency,
            )

            return LLMResponse(
                text=content.strip(),
                tokens_used=usage.get("total_tokens", 0),
                model=data.get("model", model),
                latency_ms=latency,
                success=True,
            )

        except httpx.TimeoutException:
            return LLMResponse(
                text="", success=False,
                error=f"LLM 请求超时 ({self._config.timeout_seconds}s)",
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as e:
            logger.warning("LLM chat failed: %s", e)
            return LLMResponse(
                text="", success=False,
                error=str(e),
                latency_ms=(time.monotonic() - t0) * 1000,
            )

    def classify_intent(self, user_input: str, extra_context: str = "") -> LLMResponse:
        """Classify user input into a tool intent.

        Injects current date/time so the model can calculate deadlines.
        """
        from datetime import datetime, date, timedelta
        now = datetime.now()
        today = now.date()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)

        prompt = INTENT_SYSTEM_PROMPT.format(
            current_datetime=now.strftime("%Y-%m-%d %H:%M"),
            weekday=weekdays[today.weekday()],
            tomorrow=tomorrow.isoformat(),
            day_after_tomorrow=day_after.isoformat(),
        )

        messages = [
            {"role": "system", "content": prompt},
        ]

        if extra_context:
            messages.append({
                "role": "system",
                "content": f"当前上下文: {extra_context}",
            })

        messages.append({"role": "user", "content": user_input})

        # Try JSON mode (DeepSeek, OpenAI support this)
        response = self.chat(
            messages,
            temperature=0.05,
            max_tokens=256,
            response_format={"type": "json_object"},
        )

        if not response.success:
            # Retry without JSON mode
            logger.debug("JSON mode failed, retrying without")
            response = self.chat(messages, temperature=0.05, max_tokens=256)

        if not response.success or not response.text:
            return response

        # Parse JSON from response
        text = response.text.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]

        try:
            parsed = json.loads(text)
            logger.info(
                "LLM intent: %s (confidence=%.2f, reason=%s)",
                parsed.get("tool", "none"),
                parsed.get("confidence", 0),
                parsed.get("reason", ""),
            )
            response.text = json.dumps(parsed, ensure_ascii=False)
            return response
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON: %.100s", text)
            response.text = json.dumps({"tool": "none", "params": {}, "confidence": 0})
            return response

    def force_todo(self, user_input: str) -> LLMResponse:
        """User explicitly chose 'add todo' — always summarize as a todo."""
        from datetime import datetime, timedelta
        now = datetime.now()
        today = now.date()
        weekdays = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"]
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)

        prompt = FORCE_TODO_PROMPT.format(
            current_datetime=now.strftime("%Y-%m-%d %H:%M"),
            weekday=weekdays[today.weekday()],
            tomorrow=tomorrow.isoformat(),
            day_after_tomorrow=day_after.isoformat(),
        )

        resp = self.chat(
            [{"role": "system", "content": prompt}, {"role": "user", "content": user_input}],
            temperature=0.1, max_tokens=512,
        )
        if not resp.success or not resp.text:
            resp.text = '{"tool":"todo_manager","params":{"action":"add","title":"'+user_input[:30]+'","description":"'+user_input+'"}}'
            return resp

        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("\n",1)[-1].rsplit("\n```",1)[0] if "```" in text else text
        s, e = text.find("{"), text.rfind("}")+1
        if s >= 0 and e > s:
            resp.text = text[s:e]
        return resp

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()


# ======================================================================
# Ollama-specific client (local)
# ======================================================================

class OllamaClient:
    """Ollama local LLM client — uses /api/generate for completions.

    Simpler than the OpenAI-compatible path because Ollama's
    /v1/chat/completions support varies by version.
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._client = httpx.Client(timeout=config.timeout_seconds)

    @property
    def is_available(self) -> bool:
        try:
            r = self._client.get(f"{self._config.api_base}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    def detect_models(self) -> list[str]:
        try:
            r = self._client.get(f"{self._config.api_base}/api/tags")
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    def classify_intent(self, user_input: str, extra_context: str = "") -> LLMResponse:
        """Classify intent using Ollama completion API."""
        from datetime import datetime, date, timedelta
        now = datetime.now()
        today = now.date()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)

        sys_prompt = INTENT_SYSTEM_PROMPT.format(
            current_datetime=now.strftime("%Y-%m-%d %H:%M"),
            weekday=weekdays[today.weekday()],
            tomorrow=tomorrow.isoformat(),
            day_after_tomorrow=day_after.isoformat(),
        )

        prompt = f"""{sys_prompt}

{extra_context if extra_context else ""}
用户输入: "{user_input}"

请输出严格的JSON（不要markdown代码块）:"""

        t0 = time.monotonic()
        try:
            r = self._client.post(
                f"{self._config.api_base}/api/generate",
                json={
                    "model": self._config.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 200,
                        "temperature": 0.05,
                        "top_p": 0.9,
                    },
                },
            )
            r.raise_for_status()
            data = r.json()
            text = data.get("response", "").strip()

            # Parse JSON
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]

            parsed = json.loads(text)
            latency = (time.monotonic() - t0) * 1000
            logger.info("Ollama intent: %s (%.0fms)", parsed.get("tool"), latency)
            return LLMResponse(
                text=json.dumps(parsed, ensure_ascii=False),
                tokens_used=data.get("eval_count", 0),
                model=self._config.model,
                latency_ms=latency,
                success=True,
            )
        except Exception as e:
            logger.warning("Ollama classify failed: %s", e)
            return LLMResponse(text="", success=False, error=str(e))

    def close(self) -> None:
        self._client.close()


# ======================================================================
# Factory
# ======================================================================

def create_llm_client(config: LLMConfig | None = None):
    """Create the appropriate LLM client based on provider.

    Returns:
        OpenAIClient or OllamaClient, or None if unavailable/disabled
    """
    if config is None or not config.enabled:
        logger.info("LLM disabled")
        return None

    if config.provider == "ollama":
        client = OllamaClient(config)
        if client.is_available:
            models = client.detect_models()
            if models:
                # Auto-select best model
                prefs = ["qwen3", "qwen", "llama3.2", "phi3", "gemma3", "mistral"]
                for pref in prefs:
                    for m in models:
                        if pref in m:
                            config.model = m
                            break
                    if config.model != "qwen3:latest":
                        break
                logger.info("Ollama ready: %s", config.model)
                return client
        logger.warning("Ollama not available")
        client.close()
        return None

    # Cloud APIs (DeepSeek, OpenAI, etc.)
    if config.api_key:
        logger.info("LLM ready: %s/%s", config.provider, config.model)
        return OpenAIClient(config)

    logger.warning("No API key configured for %s", config.provider)
    return None
