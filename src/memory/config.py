"""Configuration management with Pydantic models.

References:
- DyberPet: res/role/PETNAME/pet_conf.json + settings.json — JSON config per pet
- Sakura: app/config/ — YAML config with runtime token resolution
- OpenPet: Rust AppState with TOML config

We use JSON for user-editable config with Pydantic for type safety.
"""

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field


# --- Data Models ---

class PetConfig(BaseModel):
    """Pet appearance and behavior configuration."""
    name: str = "小樱"
    skin: str = "HaChiCat"
    size: float = Field(default=1.0, ge=0.05, le=5.0)
    opacity: float = Field(default=1.0, ge=0.1, le=1.0)
    auto_sleep: bool = True
    sleep_timeout_seconds: int = Field(default=300, ge=30)
    start_position: str = "bottom_right"
    search_engine: str = "bing"  # bing | google | baidu | duckduckgo
    snap_to_taskbar: bool = True  # 拖到任务栏附近自动吸附
    skin_sizes: dict[str, float] = {}  # per-skin size memory
    todo_bg: str = ""       # Path to todo viewer background image
    note_bg: str = ""       # Path to note viewer background image


class HotkeyConfig(BaseModel):
    """Keyboard shortcut configuration."""
    add_todo: str = "ctrl+shift+t"
    music_control: str = "ctrl+shift+m"
    open_website: str = "ctrl+shift+w"
    quick_search: str = "ctrl+shift+s"
    quick_reminder: str = "ctrl+shift+r"
    general_agent: str = "ctrl+shift+a"
    toggle_pet: str = "ctrl+shift+p"


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = "deepseek"  # deepseek | ollama | openai | custom
    model: str = "deepseek-chat"
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""  # Set your API key here or in settings.json
    enabled: bool = True
    max_tokens: int = 512
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    timeout_seconds: int = 30
    cached_models: list[str] = []


class ToolToggle(BaseModel):
    """Per-tool enable/disable toggle."""
    enabled: bool = True


class ToolsConfig(BaseModel):
    """Which tools are enabled."""
    todo_manager: ToolToggle = Field(default_factory=ToolToggle)
    music_controller: ToolToggle = Field(default_factory=ToolToggle)
    browser_opener: ToolToggle = Field(default_factory=ToolToggle)
    quick_reminder: ToolToggle = Field(default_factory=ToolToggle)
    app_launcher: ToolToggle = Field(default_factory=ToolToggle)
    clipboard_processor: ToolToggle = Field(
        default_factory=lambda: ToolToggle(enabled=False)
    )


class ReminderConfig(BaseModel):
    """Reminder frequency configuration (in minutes)."""
    urgent_interval: int = Field(default=30, ge=10, le=120)     # <1 day DDL
    soon_interval: int = Field(default=90, ge=30, le=360)       # 1-3 days DDL
    later_interval: int = Field(default=240, ge=60, le=720)     # 3+ days or no DDL
    wellness_interval: int = Field(default=60, ge=30, le=240)   # Health nudges
    enabled: bool = True


class PrivacyConfig(BaseModel):
    """Privacy-sensitive settings."""
    clipboard_monitor: bool = False
    history_retention_days: int = Field(default=30, ge=1)
    telemetry: bool = False


class Settings(BaseModel):
    """Root configuration model."""
    pet: PetConfig = Field(default_factory=PetConfig)
    hotkeys: HotkeyConfig = Field(default_factory=HotkeyConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)


# --- Config Manager ---

class ConfigManager:
    """Loads and saves Settings to a JSON file.

    Merges user overrides onto built-in defaults.
    """

    DEFAULT_SETTINGS = Settings()

    def __init__(self, config_path: Path):
        self._path = config_path
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        """Get current settings (lazy-loaded)."""
        if self._settings is None:
            self._settings = self.load()
        return self._settings

    def load(self) -> Settings:
        """Load settings from disk, falling back to defaults."""
        if not self._path.exists():
            self._settings = Settings()
            return self._settings

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            # Merge user data onto defaults (shallow dict merge per section)
            merged: dict[str, Any] = {}
            for field_name, default_value in self.DEFAULT_SETTINGS.model_dump().items():
                user_value = data.get(field_name)
                if user_value is not None and isinstance(default_value, dict):
                    merged[field_name] = {**default_value, **user_value}
                elif user_value is not None:
                    merged[field_name] = user_value
                else:
                    merged[field_name] = default_value
            self._settings = Settings(**merged)
            return self._settings
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            # Corrupted config — log and fall back to defaults
            import logging
            logging.getLogger("hachicat").warning(
                "Failed to load config from %s: %s. Using defaults.", self._path, e
            )
            self._settings = Settings()
            return self._settings

    def save(self, settings: Settings | None = None) -> None:
        """Save current (or provided) settings to disk."""
        if settings is not None:
            self._settings = settings

        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = self._settings.model_dump() if self._settings else self.DEFAULT_SETTINGS.model_dump()
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def reset(self) -> Settings:
        """Reset to factory defaults."""
        self._settings = Settings()
        self.save()
        return self._settings
