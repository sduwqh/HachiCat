"""Transparent always-on-top pet window with physics, state machine, and interactions.

References:
- DyberPet: transparent window flags + drag pattern
- KillClawd: throw physics with velocity tracking, friction, edge bounce
- OpenPet: companion events → animation mapping
- Clawd on Desk: right-click menu, permission bubbles
"""

from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QAction, QCursor, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMenu, QApplication,
    QWidgetAction, QLabel,
)

from src.pet.widget import PetWidget
from src.pet.animator import FrameAnimator
from src.pet.state_machine import PetStateMachine, PetState
from src.pet.physics import PetPhysics, PhysicsConfig
from src.pet.bubble import BubbleWidget, BubbleType
from src.input.global_monitor import GlobalInputMonitor
from src.utils.theme import Theme
from src.utils.icons import icon, icon_pixmap


class PetWindow(QWidget):
    """Main desktop pet — transparent, frameless, always-on-top.

    Integrates: state machine, physics engine, bubble notifications,
    and mouse interactions (drag, throw, click, right-click menu).
    """

    # --- Signals ---
    closing = Signal()
    agent_triggered = Signal(str)
    task_started = Signal()
    task_done = Signal(bool, str)
    breath_mode_changed = Signal(bool)

    POMO_QUOTES = [
        "专注是效率的灵魂 ✨",
        "慢慢来，比较快 🐢",
        "深度工作一小时 > 分心三小时",
        "休息不是偷懒，是充电 🔋",
        "完成比完美更重要",
        "知行合一",
        "不积跬步无以至千里",
        "少则得，多则惑",
        "今天不想跑，所以才去跑 🏃",
        "做难而正确的事",
        "你专注的样子真好看",
        "心流是最快乐的时刻",
        "水滴石穿，非一日之功 💧",
        "安静地努力，温柔地强大",
        "最好的时间就是现在",
        "每一个不曾起舞的日子，都是对生命的辜负",
    ]

    def __init__(
        self,
        animator: FrameAnimator,
        sprite_sheet_path: Path | None = None,
        cell_width: int = 128,
        cell_height: int = 128,
        scale: float = 1.0,
        initial_position: QPoint | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        # --- Window setup ---
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self._cell_width = cell_width
        self._cell_height = cell_height
        self._scale = scale

        # --- Image paths ---
        self._sprite_path = sprite_sheet_path
        self._alt_image_path: Path | None = None
        self._flash_busy = False
        self._snap_taskbar = False
        self._startup_done = False
        self._throw_allowed = False
        self._img_pad_ratio = None
        self._breath_mode = False
        self._current_skin_name = "HaChiCat"

        # --- Animation ---
        self._animator = animator
        self._animator.frame_changed.connect(self._on_frame_changed)

        # --- Pet widget ---
        self._pet_widget = PetWidget(
            sprite_sheet_path=sprite_sheet_path,
            cell_width=cell_width,
            cell_height=cell_height,
            parent=self,
        )
        self._pet_widget.set_scale(scale)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._pet_widget)
        self.setLayout(layout)
        self.adjustSize()

        # --- Physics engine ---
        self._physics = PetPhysics(PhysicsConfig(), parent=self)
        self._physics.on_position_changed = self._on_physics_move
        self._physics.set_screen_bounds(1920, 1080, self.width(), self.height())

        # --- State machine ---
        self._state_machine = PetStateMachine(parent=self)
        self._state_machine.state_changed.connect(self._on_state_changed)
        self._state_machine.walk_target_changed.connect(self._on_walk_target)

        # --- Bubbles ---
        self._bubble = BubbleWidget()
        self._chat_bubbles: list[BubbleWidget] = []
        self._think_timer = QTimer(self)
        self._think_timer.timeout.connect(self._spawn_think_bubble)

        # --- Breath mode ---
        self._breath_timer = QTimer(self)
        self._breath_timer.timeout.connect(self._breath_check)

        # --- Auto breath ---
        self._auto_breath_timer = QTimer(self)
        self._auto_breath_timer.timeout.connect(self._auto_breath_toggle)
        self._auto_breath_timer.start(30 * 60 * 1000)

        # --- Idle play ---
        self._idle_play_timer = QTimer(self)
        self._idle_play_timer.timeout.connect(self._idle_random_anim)
        self._idle_play_timer.start(8000)

        # --- Position ---
        if initial_position:
            self.move(initial_position)
        else:
            self._default_position()
        self._physics.set_position(self.x(), self.y())

        # Start idle
        self._animator.play("idle")

    # ==================================================================
    # Image helpers
    # ==================================================================

    def set_alt_image(self, path: Path) -> None:
        self._alt_image_path = path

    @property
    def _is_hachicat(self) -> bool:
        return bool(self._sprite_path) and self._sprite_path.name == "catpet.png"

    # ==================================================================
    # Mouse Events
    # ==================================================================

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            if self._is_hachicat and self._sprite_path and self._sprite_path.exists():
                from PySide6.QtGui import QImage
                img = QImage(str(self._sprite_path))
                if not img.isNull():
                    sx = int(event.position().x() / self.width() * img.width())
                    sy = int(event.position().y() / self.height() * img.height())
                    if 0 <= sx < img.width() and 0 <= sy < img.height():
                        if img.pixelColor(sx, sy).alpha() < 30:
                            super().mousePressEvent(event)
                            return
            if self._is_hachicat:
                import random
                offset_x = random.randint(-50, 50)
                offset_y = random.randint(-12, 8)
                anchor = QPoint(self.x() + self.width() // 2 + offset_x, self.y() + offset_y)
                cb = BubbleWidget()
                cb.show_message("哈~", BubbleType.CHAT, anchor)
                cb.dismissed.connect(cb.deleteLater)
                self._chat_bubbles.append(cb)
                import shiboken6
                self._chat_bubbles = [b for b in self._chat_bubbles
                                      if shiboken6.isValid(b) and not b.isHidden()]
                self._animator.play("drag")
                if self._alt_image_path and self._alt_image_path.exists():
                    self._pet_widget.swap_image(self._alt_image_path)
            else:
                self._dragging_petdex = True
                self._animator.play("run_right")
            self._state_machine.on_drag_start()
            self._state_machine.on_user_interaction()
            self._drag_on_pet = True
            self._drag_start_x = event.globalPosition().toPoint().x()
            self._drag_last_x = self._drag_start_x
            global_pos = event.globalPosition().toPoint()
            self._drag_offset = global_pos - self.frameGeometry().topLeft()
            self._physics.drag_start(global_pos.x() - self._drag_offset.x(),
                                     global_pos.y() - self._drag_offset.y())
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and hasattr(self, '_drag_offset'):
            global_pos = event.globalPosition().toPoint()
            new_pos = global_pos - self._drag_offset
            self.move(new_pos)
            self._physics.drag_move(new_pos.x(), new_pos.y())
            # Petdex: use dedicated left/right run rows (no mirroring needed)
            if not self._is_hachicat and hasattr(self, '_drag_last_x'):
                dx = global_pos.x() - self._drag_last_x
                if abs(dx) > 4:
                    want = "run_left" if dx < 0 else "run_right"
                    if self._animator.current_state_name != want:
                        self._animator.play(want)
                    self._drag_last_x = global_pos.x()
            self._pomo_follow()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and hasattr(self, '_drag_offset'):
            self._drag_on_pet = False
            self._dragging_petdex = False
            default_flip = getattr(self._pet_widget, '_default_flip', False)
            self._pet_widget._flip = default_flip
            self._pet_widget.update()
            del self._drag_offset
            if self._throw_allowed:
                was_thrown = self._physics.drag_end()
            else:
                self._physics._is_dragging = False
                was_thrown = False
            self._state_machine.on_drag_end()
            self.setCursor(Qt.ArrowCursor)
            if not was_thrown:
                self._animator.play("idle")
                self._try_snap_taskbar()
            # Restore HaChiCat sprite after release
            if self._is_hachicat and self._sprite_path and self._sprite_path.exists():
                QTimer.singleShot(120, self._restore_sprite)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._state_machine.on_user_interaction()
            self.agent_triggered.emit("double_click")
        super().mouseDoubleClickEvent(event)

    # ==================================================================
    # Sprite restore / flash
    # ==================================================================

    def _restore_sprite(self) -> None:
        if not self._sprite_path or not self._sprite_path.exists():
            return
        if self._state_machine.state == PetState.DRAGGING:
            return
        if getattr(self, '_drag_on_pet', False):
            return
        self._pet_widget.swap_image(self._sprite_path)

    def _flash_react(self) -> None:
        if not self._is_hachicat:
            return
        if self._flash_busy:
            return
        if self._state_machine.state == PetState.DRAGGING:
            return
        if self._state_machine.state == PetState.WORKING:
            return
        if not self._alt_image_path or not self._alt_image_path.exists():
            return
        self._flash_busy = True
        self._pet_widget.swap_image(self._alt_image_path)
        QTimer.singleShot(50, self._restore_sprite)
        QTimer.singleShot(80, self._clear_flash_cooldown)

    def _clear_flash_cooldown(self) -> None:
        self._flash_busy = False

    def _startup_greet(self) -> None:
        if not self._is_hachicat:
            return
        import random
        import shiboken6
        self._greet_flash = QTimer(self)
        self._greet_flash.timeout.connect(lambda: (
            self._pet_widget.swap_image(self._alt_image_path)
            if self._alt_image_path and self._alt_image_path.exists()
            else None
        ))
        self._greet_flash.start(120)
        self._greet_bubble = QTimer(self)
        def _burst():
            cb = BubbleWidget()
            anchor = QPoint(self.x() + self.width() // 2 + random.randint(-25, 25), self.y())
            cb.show_message("哈~", BubbleType.CHAT, anchor)
            cb.dismissed.connect(cb.deleteLater)
            self._chat_bubbles.append(cb)
        self._greet_bubble.timeout.connect(_burst)
        self._greet_bubble.start(350)
        def _stop():
            self._greet_flash.stop()
            self._greet_bubble.stop()
            self._restore_sprite()
        QTimer.singleShot(3000, _stop)

    # ==================================================================
    # Context Menu
    # ==================================================================

    def _show_context_menu(self, global_pos: QPoint) -> None:
        breath_was_on = self._breath_mode
        if breath_was_on:
            self.set_breath_mode(False)
        if hasattr(self, '_input_monitor'):
            self._input_monitor.stop()
        self._restore_sprite()
        if hasattr(self, '_greet_flash') and self._greet_flash.isActive():
            self._greet_flash.stop()
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(255, 255, 255, 0.96); color: #1f2937;
                border: 1px solid rgba(31, 41, 55, 0.12);
                border-radius: 12px; padding: 6px;
            }
            QMenu::item {
                padding: 7px 26px; border-radius: 8px; color: #333;
            }
            QMenu::item:selected { background: rgba(255,122,89,0.14); color: #1f2937; }
        """)
        _c = Theme.muted
        view_todo_action = menu.addAction(icon("todo", _c, 16), "  查看待办")
        view_todo_action.triggered.connect(lambda: self.agent_triggered.emit("view_todos"))
        view_note_action = menu.addAction(icon("note", _c, 16), "  查看笔记")
        view_note_action.triggered.connect(lambda: self.agent_triggered.emit("view_notes"))
        gallery_action = menu.addAction(icon("gallery", _c, 16), "  查看图库")
        gallery_action.triggered.connect(lambda: self.agent_triggered.emit("view_gallery"))
        # Pomodoro submenu
        pomo_menu = QMenu("  番茄钟", menu)
        pomo_menu.setIcon(icon("pomodoro", _c, 16))
        pomo_menu.setStyleSheet(menu.styleSheet())
        for mins, label in [(5, "5 分钟"), (15, "15 分钟"), (25, "25 分钟"), (45, "45 分钟")]:
            a = pomo_menu.addAction(label)
            a.triggered.connect(lambda checked=False, m=mins: self._start_pomodoro(m))
        menu.addMenu(pomo_menu)
        # Music inline
        music_widget = QWidget()
        music_layout = QHBoxLayout(music_widget)
        music_layout.setContentsMargins(6, 2, 6, 2)
        music_layout.setSpacing(3)
        for icon_name, action_name in [("music-prev", "music_prev"), ("music-play", "music_play_pause"), ("music-next", "music_next")]:
            btn = QLabel()
            btn.setFixedSize(30, 24)
            btn.setAlignment(Qt.AlignCenter)
            btn.setCursor(Qt.PointingHandCursor)
            btn._icon_name = icon_name
            btn.setPixmap(icon_pixmap(icon_name, "#555", 14))
            btn._normal = ("QLabel { background: rgba(255,255,255,0.72);"
                           " border: 1px solid rgba(31,41,55,0.10); border-radius: 6px; }")
            btn._hover = ("QLabel { background: rgba(255,122,89,0.14);"
                          " border: 1px solid rgba(255,122,89,0.34); border-radius: 6px; }")
            btn.setStyleSheet(btn._normal)
            btn.enterEvent = lambda e, b=btn: (b.setStyleSheet(b._hover), b.setPixmap(icon_pixmap(b._icon_name, Theme.accent, 14)))
            btn.leaveEvent = lambda e, b=btn: (b.setStyleSheet(b._normal), b.setPixmap(icon_pixmap(b._icon_name, "#555", 14)))
            btn.mousePressEvent = lambda e, a=action_name: self.agent_triggered.emit(a)
            music_layout.addWidget(btn)
        music_action = QWidgetAction(menu)
        music_action.setDefaultWidget(music_widget)
        menu.addAction(music_action)
        menu.addSeparator()
        toggle_action = menu.addAction(icon("hide", Theme.muted, 16), "  隐藏宠物")
        toggle_action.triggered.connect(self.hide)
        menu.exec(QCursor.pos())
        for d in (100, 250, 450):
            QTimer.singleShot(d, self._restore_sprite)
        if hasattr(self, '_input_monitor'):
            QTimer.singleShot(500, self._input_monitor.start)
        if breath_was_on:
            QTimer.singleShot(800, lambda: self.set_breath_mode(True))

    # ==================================================================
    # State Machine → Animation
    # ==================================================================

    def _on_state_changed(self, old: PetState, new: PetState) -> None:
        if not self._is_hachicat:
            # Only block during active drag (press→hold), not on release
            if new == PetState.DRAGGING:
                return
            _petdex_map = {
                PetState.IDLE: "idle",
                PetState.WALKING: "running",
                PetState.WORKING: "review",
                PetState.HAPPY: "jumping",
                PetState.SAD: "failed",
            }
            self._animator.play(_petdex_map.get(new, "idle"))
        else:
            self._animator.play(self._state_machine.animation_name)
        if new == PetState.WALKING:
            self._physics.stop_walking()
        elif new == PetState.IDLE:
            self._physics.stop_walking()
        elif new == PetState.SLEEPING:
            self._physics.stop_walking()

    def _on_walk_target(self, tx: int, ty: int) -> None:
        self._physics.walk_to(tx, ty)

    def _on_physics_move(self, x: int, y: int) -> None:
        self.move(x, y)
        self._pomo_follow()
        if not self._physics.is_throwing and not self._physics.is_walking:
            if self._state_machine.state == PetState.DRAGGING:
                self._state_machine.on_drag_end()
                self._try_snap_taskbar()

    def _on_frame_changed(self, col: int, row: int) -> None:
        self._pet_widget.set_frame(col, row)

    # ==================================================================
    # Bubble API
    # ==================================================================

    def show_bubble(self, text: str, bubble_type: BubbleType = BubbleType.INFO) -> None:
        if bubble_type in (BubbleType.INFO, BubbleType.TRANSLATION):
            self._think_timer.stop()
        anchor = QPoint(self.x() + self.width() // 2, self.y())
        self._bubble.show_message(text, bubble_type, anchor)

    def show_confirm_bubble(self, text: str, on_confirm, on_cancel) -> None:
        anchor = QPoint(self.x() + self.width() // 2, self.y())
        self._bubble.action_confirmed.connect(on_confirm, Qt.SingleShotConnection)
        self._bubble.action_cancelled.connect(on_cancel, Qt.SingleShotConnection)
        self._bubble.show_message(text, BubbleType.ACTION, anchor)

    # ==================================================================
    # Task Feedback
    # ==================================================================

    def notify_task_start(self) -> None:
        self._state_machine.on_task_start()
        if self._is_hachicat:
            self._animator.play("working")
        else:
            self._animator.play("review")  # focused thinking loop
        self._think_timer.start(1200)

    def _spawn_think_bubble(self) -> None:
        import random, shiboken6
        cb = BubbleWidget()
        anchor = QPoint(self.x() + self.width() // 2 + random.randint(-30, 30),
                        self.y() + random.randint(-4, 4))
        cb.show_message("...", BubbleType.CHAT, anchor)
        cb.dismissed.connect(cb.deleteLater)
        self._chat_bubbles.append(cb)
        self._chat_bubbles = [b for b in self._chat_bubbles
                              if shiboken6.isValid(b) and not b.isHidden()]

    def notify_task_done(self, success: bool = True, message: str = "") -> None:
        if hasattr(self, '_think_timer'):
            self._think_timer.stop()
        self._state_machine.on_task_done(success)
        if message:
            btype = BubbleType.INFO if success else BubbleType.ERROR
            self.show_bubble(message, btype)

    # ==================================================================
    # Position
    # ==================================================================

    def _default_position(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 40
            y = geo.bottom() - self.height() - 40
        else:
            x, y = 1200, 700
        self.move(max(0, x), max(0, y))

    def save_position(self) -> tuple[int, int]:
        return self.x(), self.y()

    def load_position(self, x: int, y: int) -> None:
        if x >= 0 and y >= 0:
            self.move(x, y)
            self._physics.set_position(x, y)

    def apply_settings(self) -> None:
        pass

    def resize_keep_center(self, w: int, h: int) -> None:
        cx = self.x() + self.width() // 2
        cy = self.y() + self.height() // 2
        self.setFixedSize(w, h)
        self.move(cx - w // 2, cy - h // 2)

    # ==================================================================
    # Skin switching
    # ==================================================================

    def set_skin_sizes(self, sizes: dict[str, float]) -> None:
        self._skin_sizes = sizes

    def switch_skin(self, skin: str, keep_scale: bool = False) -> None:
        from src.utils.pets import get_sprite_path
        import json
        from pathlib import Path

        # Only reset breath/greeting when actually changing to a DIFFERENT
        # skin. Re-applying the same skin (e.g. from apply_settings_live after
        # toggling breath mode) must not clobber the current breath state.
        skin_actually_changed = (
            getattr(self, '_current_skin_name', None) != skin
        )
        if skin_actually_changed:
            if self._breath_mode:
                self.set_breath_mode(False)
            if hasattr(self, '_greet_flash') and self._greet_flash.isActive():
                self._greet_flash.stop()
            if hasattr(self, '_greet_bubble') and self._greet_bubble.isActive():
                self._greet_bubble.stop()
            self._flash_busy = False
            self._dragging_petdex = False

        if hasattr(self, '_skin_sizes') and hasattr(self, '_current_skin_name'):
            self._skin_sizes[self._current_skin_name] = self._pet_widget._scale
        self._current_skin_name = skin

        skin_dir = Path(__file__).resolve().parent.parent.parent / "pets" / skin
        new_sprite = get_sprite_path(skin)

        anim_states = []
        if skin == "HaChiCat":
            new_sprite = skin_dir.parent.parent / "img" / "catpet.png"
            cfg = {"cell_width": 1024, "cell_height": 1024, "columns": 1, "rows": 1, "default_state": "idle"}
            anim_states = [{"name": "idle", "row": 0, "frame_count": 1, "frame_durations": [200], "loop": True}]
        elif not new_sprite or not new_sprite.exists():
            return
        else:
            config_path = skin_dir / "sprite_config.json"
            if config_path.exists():
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                for s in cfg.get("states", []):
                    anim_states.append({
                        "name": s["name"], "row": s["row"],
                        "frame_count": s.get("frame_count", 6),
                        "frame_durations": s.get("frame_durations", [180] * 6),
                        "loop": s.get("loop", True),
                    })
            else:
                pet_json = skin_dir / "pet.json"
                if pet_json.exists():
                    pj = json.loads(pet_json.read_text(encoding="utf-8"))
                    fw = pj.get("frameWidth", 192); fh = pj.get("frameHeight", 208)
                    cols = pj.get("columns", 9)
                    states = pj.get("animationStates", ["idle"])
                    state_names = [s.get("name", s) if isinstance(s, dict) else str(s)
                                   for s in states] if isinstance(states, list) else ["idle"]
                    cfg = {"cell_width": fw, "cell_height": fh, "columns": cols,
                           "rows": len(state_names), "default_state": state_names[0]}
                else:
                    cfg = {"cell_width": 192, "cell_height": 208, "columns": 9, "rows": 8, "default_state": "idle"}

        from src.pet.animator import SpriteConfig, AnimationState
        state_objs = [AnimationState(**s) for s in anim_states] if anim_states else []
        new_config = SpriteConfig(
            cell_width=cfg["cell_width"], cell_height=cfg["cell_height"],
            columns=cfg["columns"], rows=cfg["rows"],
            default_state=cfg.get("default_state", "idle"),
            states=state_objs,
        )
        self._animator.stop()
        self._animator = FrameAnimator(new_config)
        self._animator.frame_changed.connect(self._on_frame_changed)
        self._pet_widget.set_frame(0, 0)

        self._sprite_path = new_sprite
        self._pet_widget._default_flip = cfg.get("default_flip", False)
        self._pet_widget._flip = self._pet_widget._default_flip
        self._pet_widget._cell_width = cfg["cell_width"]
        self._pet_widget._cell_height = cfg["cell_height"]
        self._pet_widget.swap_image(new_sprite)

        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        if keep_scale:
            new_scale = self._pet_widget._scale
        else:
            saved = self._skin_sizes.get(skin, 0) if hasattr(self, '_skin_sizes') else 0
            new_scale = saved if saved > 0 else 180 / cfg["cell_width"]
        # Anchor the resize around the current center so the pet doesn't
        # jump, then clamp fully on-screen (a bigger new skin at an old
        # bottom/edge position would otherwise overflow off-screen).
        old_cx = self.x() + self.width() // 2
        old_cy = self.y() + self.height() // 2
        self._pet_widget.set_scale(new_scale)
        new_w = self._pet_widget.width()
        new_h = self._pet_widget.height()
        nx = old_cx - new_w // 2
        ny = old_cy - new_h // 2
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            nx = max(geo.left(), min(nx, geo.right() - new_w))
            ny = max(geo.top(), min(ny, geo.bottom() - new_h))
        self.setGeometry(nx, ny, new_w, new_h)
        self._physics.set_position(nx, ny)
        self.show()
        self._pet_widget.repaint()

        self._img_pad_ratio = None
        self._calc_img_padding()
        alt_img = skin_dir.parent.parent / "img" / "catpet2.png"
        if alt_img.exists():
            self._alt_image_path = alt_img
        self._animator.play("idle")

        import logging
        logging.getLogger("hachicat").info(
            "switch_skin: %s pix=%s w=%dx%d cell=%dx%d scale=%.3f",
            skin,
            "ok" if self._pet_widget._pixmap and not self._pet_widget._pixmap.isNull() else "null",
            new_w, new_h, cfg["cell_width"], cfg["cell_height"],
            self._pet_widget._scale,
        )

    # ==================================================================
    # Taskbar snap
    # ==================================================================

    def set_snap_taskbar(self, enabled: bool) -> None:
        self._snap_taskbar = enabled

    def _calc_img_padding(self) -> None:
        if not self._sprite_path or not self._sprite_path.exists():
            self._img_pad_ratio = 0.0
            return
        from PySide6.QtGui import QImage
        img = QImage(str(self._sprite_path))
        if img.isNull():
            self._img_pad_ratio = 0.0
            return
        w, h = img.width(), img.height()
        strips = [
            (int(w * 0.45), int(w * 0.55)),
            (int(w * 0.35), int(w * 0.65)),
            (int(w * 0.25), int(w * 0.75)),
        ]
        row = h - 1
        for left, right in strips:
            found = False
            for r in range(h - 1, -1, -1):
                for col in range(left, right, max(1, (right - left) // 20)):
                    if img.pixelColor(col, r).alpha() > 30:
                        row = r
                        found = True
                        break
                if found:
                    break
            if found:
                break
        self._img_pad_ratio = (h - 1 - row) / h

    @property
    def _img_bottom_pad(self) -> int:
        ratio = getattr(self, '_img_pad_ratio', None)
        if ratio is None:
            self._calc_img_padding()
            ratio = getattr(self, '_img_pad_ratio', 0.0)
        return int(ratio * self.height())

    def _try_snap_taskbar(self) -> None:
        if not self._snap_taskbar or not self._startup_done:
            return
        import ctypes
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd:
            return
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        screen = QApplication.primaryScreen()
        if screen:
            ratio = screen.devicePixelRatio()
            taskbar_top = rect.top / ratio
            avail = screen.availableGeometry()
        else:
            taskbar_top = rect.top
            avail = None
        img_bottom_pad = self._img_bottom_pad
        pet_bottom = self.y() + self.height()
        if pet_bottom > taskbar_top - 20:
            x = max(0, min(self.x(), avail.right() - self.width())) if avail else self.x()
            y = taskbar_top - self.height() + img_bottom_pad
            self.move(x, y)
            self._physics.set_position(x, y)

    # ==================================================================
    # Breath mode
    # ==================================================================

    def set_breath_mode(self, enabled: bool) -> None:
        if enabled and not self._is_hachicat:
            return
        self._breath_mode = enabled
        if enabled:
            # Seed the near/away state from the current cursor position so we
            # don't fire a stray "哈~" the instant the mode turns on.
            self._breath_was_near = self._cursor_is_near()
            self._breath_timer.start(200)
        else:
            self._breath_timer.stop()
        self.breath_mode_changed.emit(enabled)

    def _cursor_is_near(self) -> bool:
        """True if the mouse cursor is currently within the breath threshold."""
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        cx = self.x() + self.width() // 2
        cy = self.y() + self.height() // 2
        dist = ((pt.x - cx) ** 2 + (pt.y - cy) ** 2) ** 0.5
        return dist < max(self.width(), self.height()) * 0.85

    def _auto_breath_toggle(self) -> None:
        import random
        # Only auto-trigger for HaChiCat, and never stack on an active session
        if self._breath_mode or not self._is_hachicat:
            return
        if random.random() < 0.3:
            duration = random.randint(2, 8)
            self.set_breath_mode(True)
            QTimer.singleShot(duration * 60 * 1000, self._auto_breath_off)

    def _idle_random_anim(self) -> None:
        if self._is_hachicat or self._state_machine.state != PetState.IDLE:
            return
        import random
        self._idle_play_timer.setInterval(random.randint(8000, 20000))
        # Pick a random one-shot animation from whatever the sprite provides,
        # then return to idle. Weighted toward common cute actions.
        available = set(self._animator._states.keys())
        candidates = [
            ("jumping", 800), ("waving", 700),
            ("waiting", 1200), ("running", 900),
        ]
        choices = [(name, dur) for name, dur in candidates if name in available]
        if not choices:
            return
        name, dur = random.choice(choices)
        self._animator.play(name)
        QTimer.singleShot(dur, lambda: self._animator.play("idle"))

    def _auto_breath_off(self) -> None:
        self.set_breath_mode(False)

    def _breath_check(self) -> None:
        if not self._breath_mode or not self._is_hachicat:
            return
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        cx = self.x() + self.width() // 2
        cy = self.y() + self.height() // 2
        dist = ((pt.x - cx) ** 2 + (pt.y - cy) ** 2) ** 0.5
        near = dist < max(self.width(), self.height()) * 0.85
        was_near = getattr(self, '_breath_was_near', False)
        self._breath_was_near = near

        if near:
            # Feature: shove the cursor away when it gets close, and put on
            # the "哈气" face while doing so.
            if self._alt_image_path and self._alt_image_path.exists():
                self._pet_widget.swap_image(self._alt_image_path)
                QTimer.singleShot(400, self._restore_sprite)
            dx = pt.x - cx
            dy = pt.y - cy
            d = max(abs(dx), abs(dy), 1)
            push_x = pt.x + int(dx / d * 400)
            push_y = pt.y + int(dy / d * 400)
            ctypes.windll.user32.SetCursorPos(push_x, push_y)

        # Fire a single "哈~" only on the transition from near → away, so the
        # bubble appears once as the cursor leaves (not continuously).
        if was_near and not near:
            cb = BubbleWidget()
            cb.show_message("哈~", BubbleType.CHAT,
                            QPoint(self.x() + self.width() // 2, self.y()))
            cb.dismissed.connect(cb.deleteLater)
            self._chat_bubbles.append(cb)

    # ==================================================================
    # Pomodoro
    # ==================================================================

    def _start_pomodoro(self, minutes: int) -> None:
        if hasattr(self, '_pomo_timer') and self._pomo_timer.isActive():
            self._pomo_timer.stop()
        if hasattr(self, '_pomo_bubble') and self._pomo_bubble.isVisible():
            self._pomo_bubble.dismiss_now()
        if hasattr(self, '_celebration_timer') and self._celebration_timer.isActive():
            self._celebration_timer.stop()
        import random
        self._pomo_remaining = minutes * 60
        self._pomo_total = minutes * 60
        self._pomo_quote = random.choice(self.POMO_QUOTES)
        self._pomo_bubble = BubbleWidget()
        self._pomo_bubble._html.setMinimumWidth(180)
        self._pomo_bubble._html.setMaximumWidth(260)
        self._pomo_bubble._html.setMaximumHeight(120)
        self._pomo_timer = QTimer(self)
        self._pomo_timer.timeout.connect(self._pomo_tick)
        self._update_pomo_bubble()
        self._pomo_timer.start(1000)

    def _update_pomo_bubble(self) -> None:
        m = self._pomo_remaining // 60
        s = self._pomo_remaining % 60
        elapsed = self._pomo_total - self._pomo_remaining
        import random
        if elapsed > 0 and elapsed % 120 == 0:
            self._pomo_quote = random.choice(self.POMO_QUOTES)
        text = (f"<div style='text-align:center;padding:4px 0;'>"
                f"<div style='font-size:28px;font-weight:bold;line-height:1.2;'>🍅 {m}:{s:02d}</div>"
                f"<div style='color:#6b7280;font-size:15px;line-height:1.3;'>{self._pomo_quote}</div>"
                f"</div>")
        anchor = QPoint(self.x() + self.width() // 2, self.y())
        if not self._pomo_bubble.isVisible():
            self._pomo_bubble.show_message(text, BubbleType.TRANSLATION, anchor)
        else:
            self._pomo_bubble._html.setHtml(text)
            self._pomo_bubble._html.document().setDocumentMargin(2)

    def _pomo_follow(self) -> None:
        if not hasattr(self, '_pomo_bubble') or not self._pomo_bubble.isVisible():
            return
        anchor = QPoint(self.x() + self.width() // 2, self.y())
        x = anchor.x() - self._pomo_bubble.width() // 2
        y = anchor.y() - self._pomo_bubble.height() - 10
        self._pomo_bubble.move(max(0, x), max(0, y))

    def _pomo_tick(self) -> None:
        self._pomo_remaining -= 1
        if self._pomo_remaining <= 0:
            self._pomo_timer.stop()
            self._pomo_bubble.dismiss_now()
            self._pomo_celebrate()
        else:
            self._update_pomo_bubble()
            self._pomo_follow()

    def _pomo_celebrate(self) -> None:
        import random, shiboken6
        count = 0
        max_bubbles = 20
        def _burst():
            nonlocal count
            if count >= max_bubbles:
                self._celebration_timer.stop()
                return
            cb = BubbleWidget()
            anchor = QPoint(self.x() + self.width() // 2 + random.randint(-40, 40),
                            self.y() + random.randint(-10, 5))
            cb.show_message("哈~", BubbleType.CHAT, anchor)
            cb.dismissed.connect(cb.deleteLater)
            self._chat_bubbles.append(cb)
            self._chat_bubbles = [b for b in self._chat_bubbles
                                  if shiboken6.isValid(b) and not b.isHidden()]
            count += 1
        self._celebration_timer = QTimer(self)
        self._celebration_timer.timeout.connect(_burst)
        self._celebration_timer.start(250)
        QTimer.singleShot(5000, lambda: self._celebration_timer.stop())

    # ==================================================================
    # Lifecycle
    # ==================================================================

    def update_screen_bounds(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self._physics.set_screen_bounds(geo.width(), geo.height(), self.width(), self.height())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.update_screen_bounds()
        self._physics.set_position(self.x(), self.y())
        QTimer.singleShot(400, self._physics.start)
        self._bubble.dismiss_now()
        if not hasattr(self, '_input_monitor'):
            self._input_monitor = GlobalInputMonitor(parent=self)
            self._input_monitor.external_activity.connect(self._flash_react)
        self._input_monitor.start()
        QTimer.singleShot(600, lambda: setattr(self, '_startup_done', True))
        QTimer.singleShot(1000, lambda: setattr(self, '_throw_allowed', True))
        QTimer.singleShot(800, self._startup_greet)
        if not self._is_hachicat:
            QTimer.singleShot(600, lambda: self._animator.play("waving"))
            QTimer.singleShot(2000, lambda: self._animator.play("idle"))

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._physics.stop()
        self._bubble.dismiss_now()
        if hasattr(self, '_pomo_timer'):
            self._pomo_timer.stop()
        if hasattr(self, '_pomo_bubble'):
            self._pomo_bubble.dismiss_now()
        if hasattr(self, '_celebration_timer'):
            self._celebration_timer.stop()
        import shiboken6
        for b in self._chat_bubbles:
            if shiboken6.isValid(b):
                b.dismiss_now()
        self._chat_bubbles.clear()
        if hasattr(self, '_input_monitor'):
            self._input_monitor.stop()
        if self._breath_mode:
            self.set_breath_mode(False)

    def closeEvent(self, event) -> None:
        self.closing.emit()
        self._animator.stop()
        self._physics.stop()
        self._bubble.dismiss_now()
        if hasattr(self, '_pomo_timer'):
            self._pomo_timer.stop()
        if hasattr(self, '_pomo_bubble'):
            self._pomo_bubble.dismiss_now()
        if hasattr(self, '_celebration_timer'):
            self._celebration_timer.stop()
        import shiboken6
        for b in self._chat_bubbles:
            if shiboken6.isValid(b):
                b.dismiss_now()
        self._chat_bubbles.clear()
        if hasattr(self, '_input_monitor'):
            self._input_monitor.stop()
        if self._breath_mode:
            self.set_breath_mode(False)
        super().closeEvent(event)
