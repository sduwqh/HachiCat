"""Quick system tools: browser opener, music controller, app launcher.

References:
- Sakura: builtin_tools.py — open_url, open_local_folder
- Design doc section 7.2: simple tools that need minimal state
- Uses Python stdlib where possible (webbrowser, subprocess)
"""

import logging
import subprocess
import webbrowser
from typing import Any

from src.agent.base import Tool, ToolMeta, ToolResult, PermissionLevel

logger = logging.getLogger("hachicat.tools.quick")


# ======================================================================
# Browser Opener
# ======================================================================

def create_browser_tool() -> Tool:
    """Create browser opener tool — open URLs and search."""

    meta = ToolMeta(
        name="browser_opener",
        display_name="🌐 打开网页",
        description="在浏览器中打开网页或搜索关键词",
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要打开的网页URL",
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词 (如果没有URL)",
                },
            },
        },
        permission=PermissionLevel.NOTIFY,
        icon="🌐",
        tags=["system"],
    )

    async def handler(params: dict[str, Any]) -> ToolResult:
        url = params.get("url", "")
        query = params.get("query", "")

        try:
            if url:
                # Auto-add https:// if missing
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                webbrowser.open(url)
                return ToolResult(
                    success=True,
                    message=f"已在浏览器中打开 🌐\n{url}",
                    pet_reaction="happy",
                )

            elif query:
                import urllib.parse
                engine_urls = {
                    "bing": "https://www.bing.com/search?q=",
                    "google": "https://www.google.com/search?q=",
                    "baidu": "https://www.baidu.com/s?wd=",
                    "duckduckgo": "https://duckduckgo.com/?q=",
                }
                engine = params.get("engine", "bing")
                base = engine_urls.get(engine, engine_urls["bing"])
                search_url = base + urllib.parse.quote(query)
                webbrowser.open(search_url)
                return ToolResult(
                    success=True,
                    message=f"正在搜索 🔍\n{query}",
                    pet_reaction="happy",
                )

            else:
                return ToolResult(
                    success=False,
                    message="需要提供URL或搜索关键词",
                    pet_reaction="sad",
                )

        except Exception as e:
            logger.exception("Browser tool error")
            return ToolResult(
                success=False, message=f"打开浏览器失败: {e}",
                error=str(e), pet_reaction="sad",
            )

    return Tool(meta=meta, handler=handler)


# ======================================================================
# Music Controller
# ======================================================================

def create_music_tool() -> Tool:
    """Create music controller tool — media key simulation."""

    meta = ToolMeta(
        name="music_controller",
        display_name="🎵 音乐控制",
        description="控制音乐播放: 播放/暂停、下一首、上一首、调节音量",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play_pause", "next", "previous", "volume_up", "volume_down", "mute"],
                    "description": "控制动作",
                },
            },
            "required": ["action"],
        },
        permission=PermissionLevel.SAFE,
        icon="🎵",
        tags=["system"],
    )

    # Windows virtual key codes for media keys
    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT = 0xB0
    VK_MEDIA_PREV = 0xB1
    VK_VOLUME_UP = 0xAF
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_MUTE = 0xAD

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    ACTION_MAP: dict[str, tuple[int, str]] = {
        "play_pause": (VK_MEDIA_PLAY_PAUSE, "播放/暂停"),
        "next": (VK_MEDIA_NEXT, "下一首"),
        "previous": (VK_MEDIA_PREV, "上一首"),
        "volume_up": (VK_VOLUME_UP, "音量+"),
        "volume_down": (VK_VOLUME_DOWN, "音量-"),
        "mute": (VK_VOLUME_MUTE, "静音"),
    }

    async def handler(params: dict[str, Any]) -> ToolResult:
        action = params.get("action", "play_pause")
        vk_code, label = ACTION_MAP.get(action, (VK_MEDIA_PLAY_PAUSE, "播放/暂停"))

        try:
            import ctypes
            # Send media key
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

            return ToolResult(
                success=True,
                message=f"音乐控制 🎵\n{label}",
                pet_reaction="happy",
            )
        except Exception as e:
            # Fallback: try via keyboard library if available
            try:
                import pyautogui
                key_map = {
                    "play_pause": "playpause",
                    "next": "nexttrack",
                    "previous": "prevtrack",
                    "volume_up": "volumeup",
                    "volume_down": "volumedown",
                    "mute": "volumemute",
                }
                pyautogui.press(key_map.get(action, "playpause"))
                return ToolResult(
                    success=True,
                    message=f"音乐控制 🎵\n{label}",
                    pet_reaction="happy",
                )
            except Exception:
                logger.exception("Music tool fallback error")
                return ToolResult(
                    success=False, message=f"音乐控制失败: {e}",
                    error=str(e), pet_reaction="sad",
                )

    return Tool(meta=meta, handler=handler)


# ======================================================================
# App Launcher
# ======================================================================

def create_app_launcher_tool() -> Tool:
    """Create app launcher tool — open applications by name."""

    meta = ToolMeta(
        name="app_launcher",
        display_name="🚀 启动应用",
        description="打开电脑上的应用程序",
        parameters={
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "应用名称或可执行文件路径",
                },
            },
            "required": ["app_name"],
        },
        permission=PermissionLevel.NOTIFY,
        icon="🚀",
        tags=["system"],
    )

    # Known Windows app name → command mapping
    APP_MAP: dict[str, str] = {
        "notepad": "notepad.exe",
        "记事本": "notepad.exe",
        "calculator": "calc.exe",
        "计算器": "calc.exe",
        "cmd": "cmd.exe",
        "terminal": "wt.exe",
        "终端": "wt.exe",
        "explorer": "explorer.exe",
        "资源管理器": "explorer.exe",
        "paint": "mspaint.exe",
        "画图": "mspaint.exe",
        "task manager": "taskmgr.exe",
        "任务管理器": "taskmgr.exe",
        "snipping": "snippingtool.exe",
        "截图工具": "snippingtool.exe",
        "spotify": "spotify.exe",
        "vscode": "code",
        "code": "code",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "firefox": "firefox.exe",
    }

    async def handler(params: dict[str, Any]) -> ToolResult:
        app_name = params.get("app_name", "").strip().lower()

        if not app_name:
            return ToolResult(
                success=False, message="需要提供应用名称",
                pet_reaction="sad",
            )

        # Only allow known apps — prevents command injection from LLM output.
        command = APP_MAP.get(app_name)
        if command is None:
            return ToolResult(
                success=False,
                message=f"未知应用: {app_name}\n仅支持常见应用（记事本、计算器等）",
                pet_reaction="sad",
            )

        try:
            # shell=False + list form: no shell interpretation of the command
            subprocess.Popen([command])
            return ToolResult(
                success=True,
                message=f"正在启动 🚀\n{app_name}",
                pet_reaction="happy",
            )
        except Exception as e:
            logger.exception("App launcher error")
            return ToolResult(
                success=False,
                message=f"启动失败: {app_name}",
                error=str(e), pet_reaction="sad",
            )

    return Tool(meta=meta, handler=handler)
