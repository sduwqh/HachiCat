"""HaChiCat — Desktop pet agent with LLM-powered intent classification."""

import sys
import json
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QPoint, Signal
from PySide6.QtWidgets import QApplication, QInputDialog

from src.utils.logger import setup_logger
from src.utils.theme import app_window_style, form_field_style, button_style
from src.utils.markdown import md_to_html
from src.memory.config import ConfigManager
from src.memory.database import Database
from src.pet.animator import FrameAnimator, SpriteConfig, AnimationState
from src.pet.window import PetWindow
from src.pet.tray import SystemTray
from src.pet.bubble import BubbleType
from src.pet.settings_dialog import SettingsDialog
from src.pet.popup_menu import PopupMenu
from src.agent.registry import ToolRegistry
from src.agent.classifier import IntentClassifier, Intent
from src.agent.llm import LLMConfig, create_llm_client
from src.input.hotkey_manager import GlobalHotkeyManager
from src.tools.todo import create_todo_tool
from src.tools.quick_tools import create_browser_tool, create_music_tool, create_app_launcher_tool
from src.tools.note import create_note_tool
from src.tools.todo_viewer import TodoViewer
from src.tools.note_viewer import NoteViewer
from src.tools.music_panel import MusicPanel
from src.tools.image_viewer import ImageViewer, get_clipboard_image
from src.tools.gallery import GalleryBrowser
from src.agent.reminder import ReminderEngine


# --- Paths ---

def get_app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    return get_app_dir() / "data"


def get_assets_dir() -> Path:
    return get_app_dir() / "assets"


# ======================================================================
# Agent Pipeline
# ======================================================================

class AgentPipeline(QObject):
    """Orchestrates: trigger → classify → dispatch → feedback."""

    task_started = Signal()
    task_done = Signal(bool, str)
    input_requested = Signal(str)
    translation_ready = Signal(str)  # Show translation result

    def __init__(
        self,
        classifier: IntentClassifier,
        registry: ToolRegistry,
        db: Database | None = None,
        config=None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._classifier = classifier
        self._registry = registry
        self._db = db
        self._config = config

    _selected_text: str = ""

    def handle_popup_action(self, action: str, text: str = "") -> None:
        """Popup menu action selected."""
        self._selected_text = text.strip()
        if not self._selected_text:
            self.task_done.emit(False, "未检测到选中文字")
            return

        if action == "search":
            self._do_search(self._selected_text)
        elif action == "note":
            self._do_note(self._selected_text)
        elif action == "todo":
            self._do_todo(self._selected_text)
        elif action == "translate":
            self._do_translate(self._selected_text)

    def _do_search(self, text: str) -> None:
        if text.startswith(("http://", "https://", "www.")):
            self._execute("browser_opener", {"url": text})
        else:
            engine = self._config.settings.pet.search_engine if self._config else "bing"
            self._execute("browser_opener", {"query": text, "engine": engine})

    def _do_note(self, text: str) -> None:
        self._execute("note_manager", {"action": "add", "content": text,
                       "title": text[:30] + ("…" if len(text) > 30 else "")})

    def _do_todo(self, text: str) -> None:
        """User explicitly chose 'add todo' — LLM extraction in background."""
        if self._classifier._llm_client and hasattr(self._classifier._llm_client, 'force_todo'):
            self.task_started.emit()
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            import threading
            def _run():
                import json, logging
                try:
                    resp = self._classifier._llm_client.force_todo(text)
                    data = json.loads(resp.text)
                    items = data.get("todos", [data.get("params", data)])
                    if isinstance(items, dict):
                        items = [items]
                    count = 0
                    titles = []
                    for item in items:
                        if isinstance(item, dict) and item.get("title"):
                            self._execute_silent("todo_manager", {
                                "action": "add",
                                "title": item["title"],
                                "due_date": item.get("due_date", ""),
                                "description": item.get("description", text[:500]),
                            })
                            titles.append(item["title"])
                            count += 1
                    if count == 0:
                        self.task_done.emit(False, "未能识别待办")
                    elif count == 1:
                        self.task_done.emit(True, f"已添加待办 ✓\n📌 {titles[0]}")
                    else:
                        self.task_done.emit(True, f"已添加{count}条待办 ✓\n📌 {titles[0]} 等")
                except Exception:
                    self.task_done.emit(False, "未能识别待办")
            threading.Thread(target=_run, daemon=True).start()
            return
        # Fallback
        self._execute("todo_manager", {"action": "add", "title": text[:30], "description": text})

    def _execute_silent(self, tool_name: str, params: dict) -> None:
        """Execute a tool without emitting task_started/task_done."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(self._registry.execute(tool_name, params))

    def _do_translate(self, text: str) -> None:
        """Translate text using LLM in background thread."""
        if not self._classifier._llm_client:
            self.task_done.emit(False, "翻译需要配置LLM")
            return
        self.task_started.emit()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        prompt = f"""将以下内容翻译成中文。

如果是单词或短语，请以词典格式输出：
- 标注词性（名词、动词、形容词、副词等）
- 列出多个常用释义，用编号分条
- 如有多个词性，分别列出各词性的释义

如果是完整句子或段落，直接输出流畅的中文译文。

待翻译内容：
{text}"""
        import threading
        def _run():
            try:
                resp = self._classifier._llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=1024,
                )
                if resp.success and resp.text:
                    self.translation_ready.emit(resp.text.strip())
                else:
                    self.task_done.emit(False, "翻译失败")
            except Exception as e:
                self.task_done.emit(False, f"翻译失败: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def handle_smart_selection(self, text: str) -> None:
        """Deprecated — now using popup menu flow."""
        pass

    def handle_trigger(self, action: str, input_text: str = "") -> None:
        """Handle direct actions (music, view, etc.)."""
        if action == "music":
            self._execute("music_controller", {"action": "play_pause"})
            return
        if action == "view_todos":
            self._open_todo_viewer()
            return
        if action == "view_notes":
            self._open_note_viewer()
            return
        if action in ("add_todo", "general") and not input_text:
            self.input_requested.emit("add_todo")
            return

        if input_text:
            self._classify_and_execute(input_text)

    def handle_user_input(self, text: str, action: str = "general") -> None:
        """Handle free-text input from dialog."""
        if action == "add_todo":
            self._execute("todo_manager", {"action": "add", "title": text})
        else:
            self._classify_and_execute(text)

    def _classify_and_execute(self, text: str) -> None:
        """LLM classify → execute."""
        logger = __import__("logging").getLogger("hachicat")

        intent = self._classifier.classify(text)
        if intent and intent.tool_name in self._registry:
            logger.info("Intent: %s (source=%s, confidence=%.2f)",
                        intent.tool_name, intent.source, intent.confidence)
            self._execute(intent.tool_name, intent.params)
            return

        logger.info("No intent matched for: %.50s...", text)
        self.task_done.emit(False, "无法识别意图 🤔\n请尝试更明确的指令")

    def _open_todo_viewer(self) -> None:
        if self._db:
            cfg = self._config
            def save_bg(path: str) -> None:
                if cfg:
                    cfg.settings.pet.todo_bg = path
                    cfg.save()
            bg = cfg.settings.pet.todo_bg if cfg else ""
            self._show_non_modal(
                TodoViewer(self._db, bg_path=bg, on_bg_changed=save_bg), "_todo_viewer")

    def _open_note_viewer(self) -> None:
        if self._db:
            cfg = self._config
            def save_bg(path: str) -> None:
                if cfg:
                    cfg.settings.pet.note_bg = path
                    cfg.save()
            bg = cfg.settings.pet.note_bg if cfg else ""
            self._show_non_modal(
                NoteViewer(self._db, bg_path=bg, on_bg_changed=save_bg), "_note_viewer")

    def _show_non_modal(self, dialog, attr: str) -> None:
        """Show non-modal, reuse if already open, keep above pet."""
        import shiboken6
        existing = getattr(self, attr, None)
        if existing and shiboken6.isValid(existing) and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        setattr(self, attr, dialog)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        dialog.show()

    def _execute(self, tool_name: str, params: dict) -> None:
        self.task_started.emit()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        import threading
        def _run():
            import asyncio
            try:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self._registry.execute(tool_name, params))
                self.task_done.emit(result.success, result.message)
            except Exception as e:
                self.task_done.emit(False, f"执行失败: {e}")
        threading.Thread(target=_run, daemon=True).start()


# ======================================================================
# Bootstrap
# ======================================================================

def bootstrap() -> tuple[QApplication, ConfigManager, Database]:
    app = QApplication(sys.argv)
    app.setApplicationName("HaChiCat")
    app.setApplicationVersion("0.3.0")
    app.setOrganizationName("HaChiCat")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(app_window_style() + form_field_style() + button_style())

    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    log = setup_logger("hachicat", log_dir=data_dir)
    log.info("HaChiCat v0.3.0 starting...")

    config = ConfigManager(data_dir / "settings.json")
    db = Database(data_dir / "hachicat.db")
    db.init_tables()

    return app, config, db


# ======================================================================
# Main
# ======================================================================

def main() -> int:
    try:
        app, config, db = bootstrap()
    except Exception as e:
        print(f"Bootstrap failed: {e}", file=sys.stderr)
        return 1

    import logging
    logger = logging.getLogger("hachicat")

    # ---- Sprite ----
    from src.utils.pets import get_sprite_path
    skin = config.settings.pet.skin
    # Migrate old "default" skin name to "HaChiCat"
    if skin == "default":
        skin = "HaChiCat"
        config.settings.pet.skin = "HaChiCat"
        config.save(config.settings)
    skin_dir = Path(__file__).resolve().parent.parent / "pets" / skin

    if skin == "HaChiCat":
        # Built-in skin: use img/catpet.png with single-frame config
        sprite_config = SpriteConfig(cell_width=1024, cell_height=1024,
                                     columns=1, rows=1, default_state="idle")
        sprite_sheet = Path(__file__).resolve().parent.parent / "img" / "catpet.png"
        if not sprite_sheet.exists():
            sprite_sheet = None
    else:
        sprite_config_path = skin_dir / "sprite_config.json"
        if sprite_config_path.exists():
            sprite_config = SpriteConfig.from_dict(
                json.loads(sprite_config_path.read_text(encoding="utf-8"))
            )
        else:
            pet_json = skin_dir / "pet.json"
            if pet_json.exists():
                try:
                    pj = json.loads(pet_json.read_text(encoding="utf-8"))
                    states = pj.get("animationStates", ["idle"])
                    state_objs = []
                    for i, s in enumerate(states if isinstance(states, list) else [states]):
                        if isinstance(s, dict):
                            sn = s.get("name", f"state{i}")
                            fc = s.get("frameCount", min(9, 6))
                            fd = s.get("frameDuration", 180)
                            durations = s.get("frameDurations", [fd] * fc)
                        else:
                            sn = str(s)
                            fc = min(9, 6)
                            durations = [180] * fc
                        state_objs.append(AnimationState(
                            name=sn, row=i, frame_count=fc,
                            frame_durations=durations, loop=True,
                        ))
                    sprite_config = SpriteConfig(
                        cell_width=pj.get("frameWidth", 192),
                        cell_height=pj.get("frameHeight", 208),
                        columns=pj.get("columns", 9),
                        rows=len(state_objs) if state_objs else 8,
                        default_state=state_objs[0].name if state_objs else "idle",
                        states=state_objs,
                    )
                except Exception:
                    sprite_config = SpriteConfig(cell_width=192, cell_height=208,
                                                 columns=9, rows=8, default_state="idle")
            else:
                sprite_config = SpriteConfig(cell_width=192, cell_height=208,
                                             columns=9, rows=8, default_state="idle")
        sprite_sheet = get_sprite_path(skin)

    animator = FrameAnimator(sprite_config)

    # Auto-scale: target ~180px wide, but respect user setting
    TARGET_DISPLAY_WIDTH = 180
    auto_scale = TARGET_DISPLAY_WIDTH / sprite_config.cell_width
    pet_scale = config.settings.pet.size if config.settings.pet.size != 1.0 else auto_scale

    # ---- Pet ----
    # Restore last position
    saved_x = db.get_pet_state("window_x")
    saved_y = db.get_pet_state("window_y")
    initial_pos = None
    if saved_x and saved_y:
        try:
            initial_pos = QPoint(int(saved_x), int(saved_y))
        except (ValueError, TypeError):
            pass

    pet_window = PetWindow(
        animator=animator,
        sprite_sheet_path=sprite_sheet,
        cell_width=sprite_config.cell_width,
        cell_height=sprite_config.cell_height,
        scale=pet_scale,
        initial_position=initial_pos,
    )

    # Register alternate image for click / drag animation feedback
    alt_img = Path(__file__).resolve().parent.parent / "img" / "catpet2.png"
    if alt_img.exists():
        pet_window.set_alt_image(alt_img)
    # Breath mode always starts OFF — user must opt in each session
    pet_window.set_breath_mode(False)
    pet_window.set_snap_taskbar(config.settings.pet.snap_to_taskbar)
    pet_window.set_skin_sizes(config.settings.pet.skin_sizes)

    # Keep settings checkbox in sync (but don't persist — only user changes persist)
    def _sync_breath_checkbox(enabled: bool) -> None:
        import shiboken6
        dlg = settings_dialog_ref[0]
        if dlg and shiboken6.isValid(dlg) and dlg.isVisible():
            dlg._breath_mode_check.setChecked(enabled)
    pet_window.breath_mode_changed.connect(_sync_breath_checkbox)

    # ---- Tray ----
    tray_icon = Path(__file__).resolve().parent.parent / "img" / "setting.png"
    if tray_icon.exists():
        from PySide6.QtGui import QIcon, QPixmap, QPainter
        src = QPixmap(str(tray_icon))
        # Crop transparent padding, then render at full tray size
        img = src.toImage()
        # Find content bounds
        left, top, right, bottom = img.width(), img.height(), 0, 0
        for y in range(img.height()):
            for x in range(img.width()):
                if img.pixelColor(x, y).alpha() > 30:
                    left = min(left, x); top = min(top, y)
                    right = max(right, x); bottom = max(bottom, y)
        if right > left and bottom > top:
            src = src.copy(left, top, right - left + 1, bottom - top + 1)
        icon = QIcon()
        for sz in (16, 24, 32, 48):
            pix = QPixmap(sz, sz)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            scaled = src.scaled(sz - 2, sz - 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap((sz - scaled.width()) // 2, (sz - scaled.height()) // 2, scaled)
            painter.end()
            icon.addPixmap(pix)
        tray = SystemTray(icon=icon, parent=app)
    else:
        tray = SystemTray(icon_path=None, parent=app)
    def on_toggle():
        if pet_window.isVisible():
            pet_window.hide()
        else:
            # Ensure pet is on-screen and visible size
            screen = app.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                pw, ph = pet_window.width(), pet_window.height()
                if pw < 30 or ph < 30:
                    pet_window._pet_widget.set_scale(0.18)
                    pet_window.setFixedSize(
                        int(1024 * 0.18), int(1024 * 0.18)
                    )
                x, y = pet_window.x(), pet_window.y()
                if x < -pw + 20 or x > geo.right() - 20 or y < -ph + 20 or y > geo.bottom() - 20:
                    pet_window.move(geo.right() - pw - 40, geo.bottom() - ph - 40)
            pet_window.show()
    tray._on_toggle = on_toggle

    tray._todo_action.triggered.connect(lambda: pipeline.handle_trigger("view_todos"))
    tray._notes_action.triggered.connect(lambda: pipeline.handle_trigger("view_notes"))

    settings_dialog_ref = [None]  # mutable ref for closure

    def apply_settings_live():
        """Re-read config and apply all changes immediately — no restart needed."""
        config.load()
        s = config.settings
        # Pet
        # (breath mode handled live via toggle, not from config)
        pet_window.set_snap_taskbar(s.pet.snap_to_taskbar)
        pet_window.set_skin_sizes(s.pet.skin_sizes)
        pet_window.switch_skin(s.pet.skin, keep_scale=True)
        if s.pet.skin == "HaChiCat":
            pet_window._startup_greet()
        # LLM — recreate client if key/provider changed
        nonlocal llm_client, classifier
        new_llm = create_llm_client(LLMConfig(
            provider=s.llm.provider, model=s.llm.model,
            api_base=s.llm.api_base, api_key=s.llm.api_key,
            temperature=s.llm.temperature, max_tokens=s.llm.max_tokens,
            timeout_seconds=15.0, enabled=s.llm.enabled,
        ))
        if llm_client:
            llm_client.close()
        llm_client = new_llm
        classifier.set_llm_client(llm_client)
        # Reminder
        reminder.set_enabled(s.reminder.enabled)
        # Hotkey — re-register with new key
        hotkey_manager.stop()
        hotkey_manager._pending.clear()
        hotkey_manager._hotkey_ids.clear()
        hotkey_manager._next_id = 1
        hotkey_manager.register(s.hotkeys.general_agent, "smart_select")
        hotkey_manager.start()
        logger.info("Settings applied live. LLM=%s", "enabled" if llm_client else "disabled")

    def on_settings():
        import shiboken6
        if settings_dialog_ref[0] and shiboken6.isValid(settings_dialog_ref[0]) and settings_dialog_ref[0].isVisible():
            settings_dialog_ref[0].raise_()
            settings_dialog_ref[0].activateWindow()
            return
        dlg = SettingsDialog(config, pet_window=pet_window,
                            on_apply_live=apply_settings_live, parent=None)
        dlg.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()
        settings_dialog_ref[0] = dlg
    tray._on_settings = on_settings

    # ---- Tools ----
    registry = ToolRegistry()
    registry.register(create_todo_tool(db))
    registry.register(create_note_tool(db))
    registry.register(create_browser_tool())
    registry.register(create_music_tool())
    registry.register(create_app_launcher_tool())
    logger.info("Tools: %s", registry.tool_names())

    # ---- LLM ----
    llm_config = LLMConfig(
        provider=config.settings.llm.provider,
        model=config.settings.llm.model,
        api_base=config.settings.llm.api_base,
        api_key=config.settings.llm.api_key,
        temperature=config.settings.llm.temperature,
        max_tokens=config.settings.llm.max_tokens,
        timeout_seconds=15.0,
        enabled=config.settings.llm.enabled,
    )
    llm_client = create_llm_client(llm_config)

    # ---- Classifier ----
    classifier = IntentClassifier()
    if llm_client:
        classifier.set_llm_client(llm_client)
        logger.info("LLM enabled: %s/%s", config.settings.llm.provider, config.settings.llm.model)

    # ---- Pipeline ----
    pipeline = AgentPipeline(classifier, registry, db=db, config=config)
    pipeline.task_started.connect(pet_window.notify_task_start)
    pipeline.task_done.connect(pet_window.notify_task_done)

    def on_input_requested(action: str):
        titles = {
            "add_todo": ("添加待办", "请输入待办内容:"),
            "browser": ("打开网页/搜索", "输入网址或搜索关键词:"),
            "reminder": ("设置提醒", "输入提醒内容:"),
            "general": ("HaChiCat Agent", "输入你想做的事情:"),
        }
        title, prompt = titles.get(action, ("输入", "请输入:"))
        text, ok = QInputDialog.getText(pet_window, title, prompt)
        if ok and text.strip():
            pipeline.handle_user_input(text.strip(), action)

    pipeline.input_requested.connect(on_input_requested)
    def on_pet_action(action: str):
        if action == "show_music_panel":
            music_panel.popup()
        elif action == "music_play_pause":
            from src.tools.music_panel import _send
            _send(0xB3)  # VK_MEDIA_PLAY_PAUSE
        elif action == "music_prev":
            from src.tools.music_panel import _send
            _send(0xB1)  # VK_MEDIA_PREV_TRACK
        elif action == "music_next":
            from src.tools.music_panel import _send
            _send(0xB0)  # VK_MEDIA_NEXT_TRACK
        elif action == "view_gallery":
            show_gallery_browser()
        else:
            pipeline.handle_trigger(action)

    pet_window.agent_triggered.connect(on_pet_action)

    # ---- Reminder Engine ----
    rcfg = config.settings.reminder
    reminder = ReminderEngine(
        db=db,
        llm_client=llm_client,
        urgency_intervals={
            "urgent": (rcfg.urgent_interval * 60, int(rcfg.urgent_interval * 60 * 1.5)),
            "soon":   (rcfg.soon_interval * 60, int(rcfg.soon_interval * 60 * 1.5)),
            "later":  (rcfg.later_interval * 60, int(rcfg.later_interval * 60 * 1.5)),
        },
        wellness_interval=(rcfg.wellness_interval * 60, int(rcfg.wellness_interval * 60 * 1.3)),
        enabled=rcfg.enabled,
    )
    reminder.reminder_ready.connect(
        lambda text: pet_window.show_bubble(text, BubbleType.INFO)
    )
    # Also show working animation when reminding
    reminder.reminder_ready.connect(
        lambda _: pet_window.notify_task_done(True, "")
    )

    # ---- Hotkeys (simplified to 2) ----
    hotkey_manager = GlobalHotkeyManager()

    # Ctrl+Shift+A: smart selection (image → show, text → popup menu)
    hotkey_manager.register(config.settings.hotkeys.general_agent, "smart_select")

    def grab_selected_text() -> str:
        """Try to copy selected text to clipboard, then read it back.

        Uses two methods simultaneously:
        1. WM_COPY message to the focused control (works with standard edit controls)
        2. keybd_event Ctrl+C (works with most modern apps)

        Restores the original clipboard afterwards.
        """
        try:
            import time
            import ctypes

            # Don't touch clipboard if it currently holds an image
            try:
                if not QApplication.clipboard().image().isNull():
                    return ""
            except Exception:
                pass

            clipboard = QApplication.clipboard()
            old = clipboard.text()

            user32 = ctypes.windll.user32

            # Method 1: WM_COPY to focused control
            focus = user32.GetFocus()
            if focus:
                user32.SendMessageW(focus, 0x0301, 0, 0)  # WM_COPY

            # Method 2: keybd_event Ctrl+C
            user32.keybd_event(0x11, 0, 0, 0)   # Ctrl down
            user32.keybd_event(0x43, 0, 0, 0)   # C down
            time.sleep(0.04)
            user32.keybd_event(0x43, 0, 2, 0)   # C up
            user32.keybd_event(0x11, 0, 2, 0)   # Ctrl up

            # Wait for clipboard to settle
            time.sleep(0.18)

            new = clipboard.text()
            clipboard.setText(old)  # restore

            if new and new != old:
                return new
            return ""
        except Exception:
            return ""

    # ---- Popup Menu ----
    popup_menu = PopupMenu()

    # ---- Music Panel ----
    music_panel = MusicPanel()
    gallery_ref = [None]
    image_viewers = []

    def forget_window(refs, window) -> None:
        try:
            refs.remove(window)
        except ValueError:
            pass

    def show_image_viewer(pixmap):
        """Show an image viewer without disabling the pet window."""
        viewer = ImageViewer(pixmap)
        image_viewers.append(viewer)
        viewer.destroyed.connect(lambda _=None, v=viewer: forget_window(image_viewers, v))
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()
        return viewer

    def show_gallery_browser():
        """Show/reuse the gallery without relying on a local-only reference."""
        import shiboken6
        existing = gallery_ref[0]
        if existing and shiboken6.isValid(existing) and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return existing

        gallery = GalleryBrowser()
        gallery.destroyed.connect(lambda _=None: gallery_ref.__setitem__(0, None))
        gallery_ref[0] = gallery
        gallery.show()
        gallery.raise_()
        gallery.activateWindow()
        return gallery

    def on_hotkey(action: str):
        logger.info("Hotkey: %s", action)
        from PySide6.QtGui import QCursor

        # 1) Try to grab selected text first
        text = grab_selected_text()
        if text:
            logger.info("Selected text (%d chars)", len(text))
            _captured_text[0] = text
            popup_menu.show_at(QCursor.pos())
            return

        # 2) No selection — check clipboard
        # 2a) Image on clipboard
        pix = get_clipboard_image()
        if pix and not pix.isNull():
            v = show_image_viewer(pix)
            logger.info("Clipboard image %dx%d", pix.width(), pix.height())
            return

        # 2b) Text on clipboard
        try:
            import pyperclip
            clip_text = pyperclip.paste().strip()
        except Exception:
            clip_text = ""
        if clip_text:
            logger.info("Clipboard text (%d chars)", len(clip_text))
            _captured_text[0] = clip_text
            popup_menu.show_at(QCursor.pos())
        else:
            logger.info("Nothing to act on (no selection, no clipboard content)")

    _captured_text = [""]

    popup_menu.action_triggered.connect(
        lambda act: pipeline.handle_popup_action(act, _captured_text[0])
        if act != "__dismissed__" else None
    )

    # Translation result → show as bubble
    pipeline.translation_ready.connect(
        lambda text: pet_window.show_bubble(
            f"<div style='margin:0;padding:0;line-height:1.4;'>"
            f"🌐 {md_to_html(text)}"
            f"<br><span style='color:#94a3b8;font-size:10px;'>(点击任意位置关闭)</span>"
            f"</div>",
            BubbleType.TRANSLATION,
        )
    )

    hotkey_manager.hotkey_triggered.connect(on_hotkey, Qt.QueuedConnection)
    hotkey_manager.start()

    # ---- Lifecycle ----
    def on_closing():
        x, y = pet_window.save_position()
        db.set_pet_state("window_x", str(x))
        db.set_pet_state("window_y", str(y))
        hotkey_manager.stop()
        if llm_client:
            llm_client.close()
        db.close()
        logger.info("Goodbye!")

    pet_window.closing.connect(on_closing)

    # ---- Go ----
    pet_window.show()
    tray.show()
    logger.info("Ready. %d tools, LLM=%s.",
                len(registry),
                f"{llm_config.provider}/{llm_config.model}" if llm_client else "disabled")

    try:
        return app.exec()
    except KeyboardInterrupt:
        on_closing()
        return 0


if __name__ == "__main__":
    sys.exit(main())
