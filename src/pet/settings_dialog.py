"""Settings dialog for configuring pet and LLM options.

Opened from system tray → Settings.
Saves directly to settings.json on apply.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLineEdit, QComboBox, QSlider, QSpinBox, QPushButton,
    QLabel, QGroupBox, QCheckBox, QScrollArea, QWidget,
)
from PySide6.QtGui import QFont, QCursor

from src.memory.config import ConfigManager, Settings
from src.utils.theme import Theme, app_window_style, button_style, form_field_style, group_box_style
from src.utils.icons import icon, icon_pixmap


class _HotkeyCapture(QLineEdit):
    """A line edit that captures a key combination when focused.

    Click to focus, then press your desired hotkey (e.g. Ctrl+Shift+A).
    The captured combination is displayed in the field.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.96); color: #1f2937;
                border: 1px solid rgba(31,41,55,0.14); border-radius: 8px;
                padding: 6px 10px;
            }
            QLineEdit:focus {
                border-color: #ff7a59; background: #fff7f3;
            }
        """)

    def keyPressEvent(self, event) -> None:
        mods = event.modifiers()
        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return  # wait for the actual key
        parts = []
        if mods & Qt.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.ShiftModifier:
            parts.append("shift")
        if mods & Qt.AltModifier:
            parts.append("alt")
        if mods & Qt.MetaModifier:
            parts.append("meta")
        # Convert key to string
        from PySide6.QtGui import QKeySequence
        ks = QKeySequence(key).toString().lower()
        if ks:
            parts.append(ks)
        if parts:
            self.setText("+".join(parts))
        self.clearFocus()  # done capturing


class SettingsDialog(QDialog):
    """Settings dialog for HaChiCat."""

    def __init__(self, config: ConfigManager, pet_window=None, on_apply_live=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._settings = config.settings
        self._pet_window = pet_window
        self._on_apply_live = on_apply_live  # called when any setting changes
        self._original_scale = config.settings.pet.size
        self.setWindowTitle("HaChiCat 设置")
        self.setMinimumWidth(420)
        self.setWindowFlags(
            Qt.Window
            | Qt.Tool
        )
        self.setStyleSheet(app_window_style() + group_box_style() + form_field_style() + button_style())

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        # Title
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 0)
        title_bar.setSpacing(6)
        title_icon = QLabel()
        title_icon.setPixmap(icon_pixmap("settings", Theme.accent, 22))
        title_icon.setStyleSheet("background: transparent;")
        title_bar.addWidget(title_icon)
        title = QLabel("HaChiCat 设置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #111827; padding: 2px 0 4px 0;")
        title_bar.addWidget(title)
        title_bar.addStretch()
        layout.addLayout(title_bar)

        # ---- LLM Group ----
        llm_group = QGroupBox("大模型配置")
        llm_form = QFormLayout(llm_group)
        llm_form.setSpacing(8)

        # Provider
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(["deepseek", "ollama", "openai", "custom"])
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)
        llm_form.addRow("提供商:", self._provider_combo)

        # API Base (only shown for custom provider)
        self._api_base_edit = QLineEdit()
        self._api_base_edit.setPlaceholderText("https://api.example.com/v1")
        self._api_base_label = QLabel("API 地址:")
        llm_form.addRow(self._api_base_label, self._api_base_edit)

        # API Key
        key_layout = QHBoxLayout()
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("输入 API Key...")
        self._show_key_btn = QPushButton()
        self._show_key_btn.setIcon(icon("eye", Theme.muted, 15))
        self._show_key_btn.setFixedWidth(38)
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.toggled.connect(self._toggle_key_visibility)
        key_layout.addWidget(self._api_key_edit)
        key_layout.addWidget(self._show_key_btn)
        llm_form.addRow("API Key:", key_layout)

        # Model — editable combo (type or pick from fetched list)
        model_layout = QHBoxLayout()
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setInsertPolicy(QComboBox.NoInsert)
        self._model_combo.setMinimumWidth(180)
        # Ensure popup is visible when combo has items
        self._model_combo.view().setStyleSheet("""
            QAbstractItemView {
                background: #ffffff; color: #1f2937;
                border: 1px solid rgba(31,41,55,0.14); border-radius: 8px;
                selection-background-color: rgba(255,122,89,0.16);
                selection-color: #1f2937;
                outline: none; padding: 4px;
                min-height: 28px;
            }
        """)
        self._model_combo.setPlaceholderText("deepseek-chat")
        self._model_combo.lineEdit().setPlaceholderText("deepseek-chat")
        model_layout.addWidget(self._model_combo, 1)

        self._detect_btn = QPushButton(" 检测模型")
        self._detect_btn.setIcon(icon("detect", Theme.muted, 14))
        self._detect_btn.setToolTip("从 API 获取可用模型列表")
        self._detect_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._detect_btn.setStyleSheet("""
            QPushButton { color: #1e293b; background: rgba(255,255,255,0.82);
                     border: 1px solid rgba(31,41,55,0.14); border-radius: 7px;
                     font-size: 11px; padding: 4px 10px; }
            QPushButton:hover { background: rgba(255,122,89,0.14); color: #ff7a59;
                           border-color: rgba(255,122,89,0.34); }
        """)
        self._detect_btn.clicked.connect(self._on_detect_models)
        model_layout.addWidget(self._detect_btn)
        llm_form.addRow("模型:", model_layout)

        # Max tokens
        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(64, 4096)
        self._max_tokens_spin.setValue(512)
        self._max_tokens_spin.setSingleStep(64)
        self._max_tokens_spin.setToolTip("单次回复最大长度，越大回答越长但越慢")
        llm_form.addRow("最大Tokens:", self._max_tokens_spin)

        # Temperature
        temp_layout = QHBoxLayout()
        self._temp_slider = QSlider(Qt.Horizontal)
        self._temp_slider.setRange(0, 200)
        self._temp_slider.setValue(10)
        self._temp_slider.setToolTip("回复随机性：0=稳定精确，2=天马行空")
        self._temp_label = QLabel("0.10")
        self._temp_label.setFixedWidth(36)
        self._temp_slider.valueChanged.connect(
            lambda v: self._temp_label.setText(f"{v/100:.2f}")
        )
        temp_layout.addWidget(self._temp_slider)
        temp_layout.addWidget(self._temp_label)
        llm_form.addRow("Temperature:", temp_layout)

        # Enable LLM
        self._llm_enabled_check = QCheckBox("启用大模型")
        self._llm_enabled_check.setChecked(True)
        llm_form.addRow("", self._llm_enabled_check)

        layout.addWidget(llm_group)

        # ---- Pet Group ----
        pet_group = QGroupBox("宠物设置")
        pet_form = QFormLayout(pet_group)
        pet_form.setSpacing(8)

        size_layout = QHBoxLayout()
        size_layout.setSpacing(4)

        size_minus = self._spin_btn("−")
        size_minus.mousePressEvent = lambda e: self._on_size_click(-10)
        size_layout.addWidget(size_minus)

        # Slider: clickable but not draggable — jump to position on click
        class _ClickSlider(QSlider):
            def mouseMoveEvent(self, e): pass  # block drag
        self._pet_size_slider = _ClickSlider(Qt.Horizontal)
        self._pet_size_slider.setRange(10, 250)
        self._pet_size_slider.setValue(100)
        self._pet_size_slider.setPageStep(10)
        self._pet_size_slider.setTickPosition(QSlider.TicksBelow)
        self._pet_size_slider.setTickInterval(50)
        self._pet_size_slider.sliderReleased.connect(
            lambda: self._on_size_click(self._pet_size_slider.value()))
        size_layout.addWidget(self._pet_size_slider, 1)

        size_plus = self._spin_btn("+")
        size_plus.mousePressEvent = lambda e: self._on_size_click(10)
        size_layout.addWidget(size_plus)

        self._pet_size_label = QLabel("100%")
        self._pet_size_label.setFixedWidth(42)
        self._pet_size_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        size_layout.addWidget(self._pet_size_label)
        pet_form.addRow("大小:", size_layout)

        self._breath_mode_check = QCheckBox("哈气模式")
        self._breath_mode_check.toggled.connect(self._on_breath_mode_toggled)
        pet_form.addRow("", self._breath_mode_check)

        self._snap_taskbar_check = QCheckBox("任务栏吸附")
        pet_form.addRow("", self._snap_taskbar_check)

        self._search_engine_combo = QComboBox()
        self._search_engine_combo.addItems(["bing", "google", "baidu", "duckduckgo"])
        pet_form.addRow("搜索引擎:", self._search_engine_combo)

        # Hotkey capture
        self._hotkey_edit = _HotkeyCapture()
        self._hotkey_edit.setPlaceholderText("点击后按下组合键...")
        pet_form.addRow("快捷键:", self._hotkey_edit)

        from src.utils.pets import list_skins
        self._skins = list_skins()
        skin_layout = QHBoxLayout()
        self._skin_btn = QLabel(self._skins[0] if self._skins else "HaChiCat")
        self._skin_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._skin_btn.setStyleSheet("""
            QLabel { color: #1e293b; background: rgba(255,255,255,0.82);
                     border: 1px solid rgba(31,41,55,0.14); border-radius: 7px;
                     font-size: 12px; padding: 4px 10px; }
            QLabel:hover { background: rgba(255,122,89,0.14); color: #ff7a59;
                           border-color: rgba(255,122,89,0.34); }
        """)
        self._skin_btn.mousePressEvent = lambda e: self._show_skin_picker()
        skin_layout.addWidget(self._skin_btn)
        skin_layout.addStretch()
        pet_form.addRow("切换形象:", skin_layout)

        layout.addWidget(pet_group)

        # ---- Reminder Group ----
        rem_group = QGroupBox("提醒设置")
        rem_form = QFormLayout(rem_group)
        rem_form.setSpacing(8)

        self._rem_enabled = QCheckBox("启用主动提醒")
        self._rem_enabled.setChecked(True)
        rem_form.addRow("", self._rem_enabled)

        self._urgent_slider = self._make_slider(10, 120, 30, "分钟")
        rem_form.addRow("紧急任务 (<1天截止):", self._urgent_slider[0])

        self._soon_slider = self._make_slider(30, 360, 90, "分钟")
        rem_form.addRow("近期任务 (1-3天):", self._soon_slider[0])

        self._later_slider = self._make_slider(60, 720, 240, "分钟")
        rem_form.addRow("远期任务 (3天+):", self._later_slider[0])

        self._wellness_slider = self._make_slider(10, 120, 60, "分钟")
        rem_form.addRow("健康提醒:", self._wellness_slider[0])

        layout.addWidget(rem_group)

        # ---- Buttons ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        apply_btn = QPushButton("保存")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        apply_btn.setStyleSheet(button_style("primary"))
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _show_skin_picker(self) -> None:
        """Show a popup dialog to preview and select a pet skin (grid layout)."""
        from src.utils.pets import get_sprite_path
        from PySide6.QtGui import QPixmap, QCursor, QImage
        from pathlib import Path

        dlg = QDialog(self)
        dlg.setWindowTitle("选择宠物形象")
        dlg.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        dlg.setMinimumWidth(560)
        dlg.setStyleSheet("QDialog { background: #eaedf4; }")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("选择宠物形象")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #1f2937;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        cols = 4

        for i, skin in enumerate(self._skins):
            card = QWidget()
            card.setFixedSize(120, 170)
            card.setStyleSheet("""
                QWidget { background: rgba(255,255,255,0.88); border: 1px solid rgba(31,41,55,0.10); border-radius: 10px; }
                QWidget:hover { background: rgba(255,122,89,0.08); border-color: rgba(255,122,89,0.34); }
            """)
            card.setCursor(QCursor(Qt.PointingHandCursor))
            vl = QVBoxLayout(card)
            vl.setContentsMargins(8, 8, 8, 6)
            vl.setSpacing(4)

            # Thumbnail
            sprite = get_sprite_path(skin)
            if not sprite and skin == "HaChiCat":
                sprite = Path(__file__).resolve().parent.parent.parent / "img" / "catpet.png"
            thumb = QLabel()
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setFixedSize(96, 96)
            thumb.setStyleSheet("background: transparent; border: 1px solid rgba(31,41,55,0.10); border-radius: 4px;")
            if sprite and sprite.exists():
                img = QImage(str(sprite))
                if not img.isNull():
                    # Show first frame for sprite sheets
                    cell_w = 192; cell_h = 208
                    # Try to read config for cell size
                    config_path = Path(__file__).resolve().parent.parent.parent / "pets" / skin / "sprite_config.json"
                    if config_path.exists():
                        import json
                        cfg = json.loads(config_path.read_text(encoding="utf-8"))
                        cell_w = cfg.get("cell_width", 192)
                        cell_h = cfg.get("cell_height", 208)
                    elif skin == "HaChiCat":
                        cell_w = 1024; cell_h = 1024
                    first_frame = img.copy(0, 0, min(cell_w, img.width()), min(cell_h, img.height()))
                    pix = QPixmap.fromImage(first_frame)
                    thumb.setPixmap(pix.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    thumb.setText("?")
            else:
                thumb.setText("?")
            vl.addWidget(thumb)

            # Name
            name_lbl = QLabel(skin)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet("font-size: 10px; color: #1f2937; background: transparent; border: none;")
            vl.addWidget(name_lbl)

            if skin != "HaChiCat":
                btn_row = QHBoxLayout()
                btn_row.setSpacing(4)
                btn_row.addStretch()
                # Flip
                flip_btn = QLabel()
                flip_btn.setPixmap(icon_pixmap("flip", "#6b7280", 13))
                flip_btn.setAlignment(Qt.AlignCenter)
                flip_btn.setCursor(QCursor(Qt.PointingHandCursor))
                flip_btn.setToolTip("水平翻转")
                flip_btn.setFixedSize(22, 18)
                flip_btn.setStyleSheet("""
                    QLabel { background: rgba(31,41,55,0.04);
                             border: 1px solid rgba(31,41,55,0.08); border-radius: 3px; }
                    QLabel:hover { background: rgba(255,122,89,0.14); }
                """)
                def make_flip(s=skin):
                    return lambda e: self._flip_skin(s)
                flip_btn.mousePressEvent = make_flip()
                btn_row.addWidget(flip_btn)
                # Delete
                del_btn = QLabel()
                del_btn.setPixmap(icon_pixmap("trash", "#c26666", 13))
                del_btn.setAlignment(Qt.AlignCenter)
                del_btn.setCursor(QCursor(Qt.PointingHandCursor))
                del_btn.setToolTip("删除")
                del_btn.setFixedSize(22, 18)
                del_btn.setStyleSheet("""
                    QLabel { background: rgba(194,102,102,0.04);
                             border: 1px solid rgba(194,102,102,0.10); border-radius: 3px; }
                    QLabel:hover { background: rgba(194,102,102,0.14); }
                """)
                def make_del(s=skin):
                    return lambda e: self._delete_skin(s, dlg)
                del_btn.mousePressEvent = make_del()
                btn_row.addWidget(del_btn)
                vl.addLayout(btn_row)

            # Click handler (select)
            def make_handler(s=skin):
                return lambda e: self._apply_skin(s, dlg)
            card.mousePressEvent = make_handler()

            grid.addWidget(card, i // cols, i % cols)

        scroll.setWidget(grid_w)
        layout.addWidget(scroll, 1)

        # Add-new-pet button
        add_btn = QLabel("+ 添加新形象")
        add_btn.setAlignment(Qt.AlignCenter)
        add_btn.setCursor(QCursor(Qt.PointingHandCursor))
        add_btn.setStyleSheet("""
            QLabel { color: #ff7a59; background: rgba(255,122,89,0.08);
                     border: 1px dashed rgba(255,122,89,0.30); border-radius: 8px;
                     font-size: 12px; padding: 6px; }
            QLabel:hover { background: rgba(255,122,89,0.16); border-color: #ff7a59; }
        """)
        add_btn.mousePressEvent = lambda e: self._add_petdex_pet(dlg)
        layout.addWidget(add_btn)

        dlg.exec()

    def _add_petdex_pet(self, parent_dlg: QDialog) -> None:
        """Show a nice onboarding dialog for adding Petdex pets."""
        from PySide6.QtWidgets import QInputDialog, QMessageBox, QApplication
        from PySide6.QtGui import QPixmap
        from pathlib import Path
        import urllib.request, json, re

        # Build a dedicated dialog
        dlg = QDialog(parent_dlg)
        dlg.setWindowTitle("添加 Petdex 形象")
        dlg.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        dlg.setFixedSize(480, 560)
        dlg.setStyleSheet("QDialog { background: #1a1a1a; }")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # Title
        title = QLabel("🐾 添加 Petdex 形象")
        f = QFont(); f.setPointSize(15); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        # Intro text
        intro = QLabel("本软件已支持 Petdex 形象库！\n前往 petdex.dev 挑选你喜欢的桌宠吧 👇")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #cccccc; font-size: 12px;")
        layout.addWidget(intro)

        # petdex.png screenshot
        img_dir = Path(__file__).resolve().parent.parent.parent / "img"
        petdex_img = QLabel()
        petdex_pix = QPixmap(str(img_dir / "petdex.png"))
        if not petdex_pix.isNull():
            petdex_img.setPixmap(petdex_pix.scaled(440, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        petdex_img.setAlignment(Qt.AlignCenter)
        petdex_img.setStyleSheet("border: 1px solid #333; border-radius: 6px;")
        layout.addWidget(petdex_img)

        # Step instruction
        step = QLabel("选择喜欢的形象 → 点击右上角 Copy Page Link")
        step.setWordWrap(True)
        step.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout.addWidget(step)

        # sample.png
        sample_img = QLabel()
        sample_pix = QPixmap(str(img_dir / "sample.png"))
        if not sample_pix.isNull():
            sample_img.setPixmap(sample_pix.scaled(440, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        sample_img.setAlignment(Qt.AlignCenter)
        sample_img.setStyleSheet("border: 1px solid #333; border-radius: 6px;")
        layout.addWidget(sample_img)

        # URL input
        url_layout = QHBoxLayout()
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("粘贴链接，如 https://petdex.dev/pets/boba")
        url_edit.setStyleSheet("""
            QLineEdit { background: #2a2a2a; color: #ffffff; border: 1px solid #444;
                        border-radius: 6px; padding: 8px 12px; font-size: 13px; }
            QLineEdit:focus { border-color: #ff7a59; }
        """)
        url_layout.addWidget(url_edit, 1)

        go_btn = QLabel("下载")
        go_btn.setAlignment(Qt.AlignCenter)
        go_btn.setCursor(QCursor(Qt.PointingHandCursor))
        go_btn.setFixedSize(50, 36)
        go_btn.setStyleSheet("""
            QLabel { color: #ffffff; background: #ff7a59; border-radius: 6px;
                     font-size: 13px; font-weight: bold; }
            QLabel:hover { background: #3f66d1; }
        """)
        url_layout.addWidget(go_btn)
        layout.addLayout(url_layout)

        # Status
        status = QLabel("")
        status.setAlignment(Qt.AlignCenter)
        status.setStyleSheet("color: #ff7a59; font-size: 12px;")
        layout.addWidget(status)

        layout.addStretch()

        def do_download(e=None):
            url = url_edit.text().strip()
            if not url:
                status.setText("请输入链接")
                return
            slug = url.rstrip("/").split("/")[-1]
            safe_slug = re.sub(r'[^a-zA-Z0-9_-]', '-', slug)[:30]
            if not slug:
                status.setText("无法从链接中提取形象名称")
                return

            status.setText("⏳ 正在获取页面信息...")
            QApplication.processEvents()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    html = r.read().decode("utf-8", errors="ignore")
                m = re.search(r'https://assets\.petdex\.dev/pets/[^\"\')\s]+/sprite\.webp', html)
                if not m:
                    status.setText("❌ 未找到精灵图链接")
                    return
                sprite_url = m.group(0)
                json_url = sprite_url.rsplit("/", 1)[0] + "/petjson.json"
            except Exception as e2:
                status.setText(f"❌ {e2}")
                return

            pet_dir = Path(__file__).resolve().parent.parent.parent / "pets" / safe_slug
            pet_dir.mkdir(parents=True, exist_ok=True)
            try:
                status.setText("⏳ 正在下载精灵图...")
                QApplication.processEvents()
                req2 = urllib.request.Request(sprite_url, headers={"User-Agent": "HaChiCat/1.0"})
                with urllib.request.urlopen(req2, timeout=30) as r2:
                    (pet_dir / "spritesheet.webp").write_bytes(r2.read())
            except Exception as e3:
                status.setText(f"❌ 下载失败: {e3}")
                return

            # Official Petdex 9-row sprite layout: (name, frame_count)
            petdex_rows = [
                ("idle", 6), ("run_right", 8), ("run_left", 8),
                ("waving", 4), ("jumping", 5), ("failed", 8),
                ("waiting", 6), ("running", 6), ("review", 6),
            ]
            fw, fh = 192, 208

            (pet_dir / "sprite_config.json").write_text(json.dumps({
                "cell_width": fw, "cell_height": fh, "columns": 8,
                "rows": len(petdex_rows),
                "default_state": "idle",
                "states": [{"name": name, "row": i, "frame_count": fc,
                            "frame_durations": [120]*fc, "loop": True}
                           for i, (name, fc) in enumerate(petdex_rows)]
            }, indent=2, ensure_ascii=False), encoding="utf-8")

            status.setText(f"✅ 已添加 {safe_slug}！")
            self._current_skin = safe_slug
            self._skin_btn.setText(safe_slug)
            if self._pet_window:
                self._pet_window.switch_skin(safe_slug)
            self._refresh_picker_grid(parent_dlg)
            QTimer.singleShot(1500, dlg.accept)

        go_btn.mousePressEvent = do_download
        url_edit.returnPressed.connect(do_download)
        dlg.exec()

    def _refresh_picker_grid(self, dlg: QDialog) -> None:
        """Rebuild the picker grid in-place (no flash)."""
        # Find the scroll area and rebuild its content
        scroll = dlg.findChild(QScrollArea)
        if not scroll:
            return
        from src.utils.pets import get_sprite_path, list_skins
        from PySide6.QtGui import QPixmap, QCursor, QImage
        from pathlib import Path
        import json

        self._skins = list_skins()
        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        cols = 4

        for i, skin in enumerate(self._skins):
            card = QWidget()
            card.setFixedSize(120, 170)
            card.setStyleSheet("""
                QWidget { background: rgba(255,255,255,0.88); border: 1px solid rgba(31,41,55,0.10); border-radius: 10px; }
                QWidget:hover { background: rgba(255,122,89,0.08); border-color: rgba(255,122,89,0.34); }
            """)
            card.setCursor(QCursor(Qt.PointingHandCursor))
            vl = QVBoxLayout(card)
            vl.setContentsMargins(8, 8, 8, 6)
            vl.setSpacing(4)

            sprite = get_sprite_path(skin)
            if not sprite and skin == "HaChiCat":
                sprite = Path(__file__).resolve().parent.parent.parent / "img" / "catpet.png"
            thumb = QLabel()
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setFixedSize(96, 96)
            thumb.setStyleSheet("background: transparent; border: 1px solid rgba(31,41,55,0.10); border-radius: 4px;")
            if sprite and sprite.exists():
                img = QImage(str(sprite))
                if not img.isNull():
                    cell_w = 192; cell_h = 208
                    config_path = Path(__file__).resolve().parent.parent.parent / "pets" / skin / "sprite_config.json"
                    if config_path.exists():
                        cfg = json.loads(config_path.read_text(encoding="utf-8"))
                        cell_w = cfg.get("cell_width", 192)
                        cell_h = cfg.get("cell_height", 208)
                    elif skin == "HaChiCat":
                        cell_w = 1024; cell_h = 1024
                    first_frame = img.copy(0, 0, min(cell_w, img.width()), min(cell_h, img.height()))
                    pix = QPixmap.fromImage(first_frame)
                    thumb.setPixmap(pix.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    thumb.setText("?")
            else:
                thumb.setText("?")
            vl.addWidget(thumb)

            name_lbl = QLabel(skin)
            name_lbl.setAlignment(Qt.AlignCenter)
            name_lbl.setStyleSheet("font-size: 10px; color: #1f2937; background: transparent; border: none;")
            vl.addWidget(name_lbl)

            if skin != "HaChiCat":
                # Flip button
                btn_row = QHBoxLayout()
                btn_row.setSpacing(4)
                btn_row.addStretch()
                flip_btn = QLabel("↔")
                flip_btn.setAlignment(Qt.AlignCenter)
                flip_btn.setCursor(QCursor(Qt.PointingHandCursor))
                flip_btn.setToolTip("翻转")
                flip_btn.setFixedSize(22, 18)
                flip_btn.setStyleSheet("""
                    QLabel { color: #6b7280; background: rgba(31,41,55,0.04);
                             border: 1px solid rgba(31,41,55,0.08); border-radius: 3px;
                             font-size: 11px; }
                    QLabel:hover { background: rgba(255,122,89,0.14); color: #ff7a59; }
                """)
                def make_flip(s=skin):
                    return lambda e: self._flip_skin(s)
                flip_btn.mousePressEvent = make_flip()
                btn_row.addWidget(flip_btn)
                del_btn = QLabel()
                del_btn.setPixmap(icon_pixmap("trash", "#c26666", 13))
                del_btn.setAlignment(Qt.AlignCenter)
                del_btn.setCursor(QCursor(Qt.PointingHandCursor))
                del_btn.setToolTip("删除")
                del_btn.setFixedSize(22, 18)
                del_btn.setStyleSheet("""
                    QLabel { background: rgba(194,102,102,0.04);
                             border: 1px solid rgba(194,102,102,0.10); border-radius: 3px; }
                    QLabel:hover { background: rgba(194,102,102,0.14); }
                """)
                def make_del(s=skin):
                    return lambda e: self._delete_skin(s, dlg)
                del_btn.mousePressEvent = make_del()
                btn_row.addWidget(del_btn)
                vl.addLayout(btn_row)

            def make_handler(s=skin):
                return lambda e: self._apply_skin(s, dlg)
            card.mousePressEvent = make_handler()
            grid.addWidget(card, i // cols, i % cols)

        scroll.takeWidget().deleteLater()
        scroll.setWidget(grid_w)

    def _flip_skin(self, skin: str) -> None:
        """Toggle horizontal flip for a skin and persist."""
        from pathlib import Path
        import json
        pet_dir = Path(__file__).resolve().parent.parent.parent / "pets" / skin
        cfg_path = pet_dir / "sprite_config.json"
        if not cfg_path.exists():
            return
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["default_flip"] = not cfg.get("default_flip", False)
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        # Apply immediately if active
        if self._pet_window and skin == getattr(self, '_current_skin', ''):
            self._pet_window._pet_widget._default_flip = cfg["default_flip"]
            self._pet_window._pet_widget._flip = cfg["default_flip"]
            self._pet_window._pet_widget.update()

    def _delete_skin(self, skin: str, dlg: QDialog) -> None:
        """Delete a Petdex skin folder and refresh the picker."""
        from pathlib import Path
        pet_dir = Path(__file__).resolve().parent.parent.parent / "pets" / skin
        if pet_dir.exists():
            import shutil
            shutil.rmtree(pet_dir)
        if self._pet_window and skin == self._current_skin:
            self._current_skin = "HaChiCat"
            self._skin_btn.setText("HaChiCat")
            self._pet_window.switch_skin("HaChiCat")
        self._refresh_picker_grid(dlg)

    def _apply_skin(self, skin: str, dlg: QDialog) -> None:
        """Apply selected skin and close the picker."""
        dlg.accept()
        if self._pet_window:
            self._pet_window.switch_skin(skin)
            new_pct = int(self._pet_window._pet_widget._scale * 100)
            self._pet_size_slider.setValue(new_pct)
            self._pet_size_label.setText(f"{new_pct}%")
            is_hachi = (skin == "HaChiCat")
            self._breath_mode_check.setVisible(is_hachi)
            if not is_hachi:
                self._pet_window.set_breath_mode(False)
            self._skin_btn.setText(skin)
            self._current_skin = skin

    def _on_breath_mode_toggled(self, checked: bool) -> None:
        """Live toggle breath mode."""
        if self._pet_window:
            self._pet_window.set_breath_mode(checked)
        if self._on_apply_live:
            self._on_apply_live()

    def _on_size_click(self, value: int) -> None:
        """Apply pet size change — either a delta (±10) or absolute value."""
        if not self._pet_window:
            return
        import ctypes
        from PySide6.QtWidgets import QApplication

        if abs(value) <= 10:  # delta from ± buttons
            current = int(self._pet_window._pet_widget._scale * 100)
            value = max(10, min(250, current + value))

        self._pet_size_label.setText(f"{value}%")
        self._pet_size_slider.setValue(value)

        scale = value / 100.0
        w = self._pet_window
        cx = w.x() + w.width() / 2.0
        cy = w.y() + w.height() / 2.0
        w._pet_widget.set_scale(scale)
        new_w = w._pet_widget.width()
        new_h = w._pet_widget.height()
        nx = round(cx - new_w / 2.0)
        ny = round(cy - new_h / 2.0)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            nx = max(geo.left(), min(nx, geo.right() - new_w))
            ny = max(geo.top(), min(ny, geo.bottom() - new_h))
        hwnd = int(w.winId())
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, nx, ny, new_w, new_h, 0x0114,  # SWP_NOZORDER|NOACTIVATE|NOCOPYBITS
        )

    @staticmethod
    def _spin_btn(text: str) -> QLabel:
        """Tiny QLabel-as-button (± buttons beside sliders)."""
        btn = QLabel(text)
        btn.setFixedSize(26, 26)
        btn.setAlignment(Qt.AlignCenter)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setStyleSheet("""
            QLabel { color: #1e293b; background: rgba(255,255,255,0.82);
                     border: 1px solid rgba(31,41,55,0.14); border-radius: 7px;
                     font-size: 16px; font-weight: bold; }
            QLabel:hover { background: rgba(255,122,89,0.14); color: #ff7a59;
                           border-color: rgba(255,122,89,0.34); }
        """)
        return btn

    def _make_slider(self, lo: int, hi: int, val: int, unit: str,
                     step: int = 1, fmt: str | None = None) -> tuple:
        """Create a slider row with - / + buttons for fine adjustment.

        Returns (container_widget, get_value_fn).
        """
        from PySide6.QtWidgets import QWidget
        if fmt is None:
            fmt = f"{{v}}{unit}"

        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(4)

        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)

        minus = self._spin_btn("−")
        minus.mousePressEvent = lambda e, sl=s: sl.setValue(max(lo, sl.value() - step))

        plus = self._spin_btn("+")
        plus.mousePressEvent = lambda e, sl=s: sl.setValue(min(hi, sl.value() + step))

        label = QLabel(fmt.format(v=val))
        label.setFixedWidth(56)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        s.valueChanged.connect(lambda v: label.setText(fmt.format(v=v)))

        l.addWidget(minus)
        l.addWidget(s, 1)
        l.addWidget(plus)
        l.addWidget(label)
        return (w, lambda: s.value())

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        """Populate UI from current settings."""
        s = self._settings

        # LLM
        self._provider_combo.setCurrentText(s.llm.provider)
        self._api_key_edit.setText(s.llm.api_key)
        self._model_combo.clear()
        if s.llm.cached_models:
            self._model_combo.addItems(s.llm.cached_models)
        self._model_combo.setCurrentText(s.llm.model)
        self._api_base_edit.setText(s.llm.api_base)
        self._max_tokens_spin.setValue(s.llm.max_tokens)
        self._temp_slider.setValue(int(s.llm.temperature * 100))
        self._llm_enabled_check.setChecked(s.llm.enabled)

        # Pet
        if self._pet_window:
            actual_pct = int(self._pet_window._pet_widget._scale * 100)
            self._original_scale = self._pet_window._pet_widget._scale
        else:
            actual_pct = int(s.pet.size * 100)
        self._pet_size_slider.setValue(actual_pct)
        self._pet_size_label.setText(f"{actual_pct}%")
        self._search_engine_combo.setCurrentText(s.pet.search_engine)
        self._hotkey_edit.setText(s.hotkeys.general_agent)
        self._current_skin = s.pet.skin
        self._skin_btn.setText(s.pet.skin)
        is_hachi = (s.pet.skin == "HaChiCat")
        self._breath_mode_check.setVisible(is_hachi)
        self._snap_taskbar_check.setChecked(s.pet.snap_to_taskbar)
        if self._pet_window:
            self._breath_mode_check.setChecked(self._pet_window._breath_mode)

        # Reminder
        r = s.reminder
        self._rem_enabled.setChecked(r.enabled)
        self._urgent_slider[0].findChild(QSlider).setValue(r.urgent_interval)
        self._soon_slider[0].findChild(QSlider).setValue(r.soon_interval)
        self._later_slider[0].findChild(QSlider).setValue(r.later_interval)
        self._wellness_slider[0].findChild(QSlider).setValue(r.wellness_interval)

    def _on_apply(self) -> None:
        """Save settings and close (no popup)."""
        s = self._settings

        s.llm.provider = self._provider_combo.currentText()
        s.llm.api_key = self._api_key_edit.text().strip()
        s.llm.model = self._model_combo.currentText().strip() or "deepseek-chat"
        s.llm.api_base = self._api_base_edit.text().strip().rstrip("/") or "https://api.deepseek.com"
        s.llm.max_tokens = self._max_tokens_spin.value()
        s.llm.temperature = self._temp_slider.value() / 100.0
        s.llm.enabled = self._llm_enabled_check.isChecked()

        s.pet.size = self._pet_size_slider.value() / 100.0
        s.pet.search_engine = self._search_engine_combo.currentText()
        s.pet.skin = getattr(self, '_current_skin', 'HaChiCat')
        s.pet.snap_to_taskbar = self._snap_taskbar_check.isChecked()
        # Save per-skin size
        if self._pet_window and hasattr(self._pet_window, '_skin_sizes'):
            skin = getattr(self, '_current_skin', 'HaChiCat')
            self._pet_window._skin_sizes[skin] = self._pet_window._pet_widget._scale
            s.pet.skin_sizes = self._pet_window._skin_sizes

        s.reminder.enabled = self._rem_enabled.isChecked()
        s.reminder.urgent_interval = self._urgent_slider[0].findChild(QSlider).value()
        s.reminder.soon_interval = self._soon_slider[0].findChild(QSlider).value()
        s.reminder.later_interval = self._later_slider[0].findChild(QSlider).value()
        s.reminder.wellness_interval = self._wellness_slider[0].findChild(QSlider).value()

        s.hotkeys.general_agent = self._hotkey_edit.text().strip() or "ctrl+shift+a"

        self._config.save(s)
        if self._on_apply_live:
            self._on_apply_live()
        self.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_btn_restore(btn, text: str) -> None:
        """Restore button text (and detect icon) only if the widget still exists."""
        import shiboken6
        if shiboken6.isValid(btn):
            btn.setText(text)
            btn.setIcon(icon("detect", Theme.muted, 14))

    def _on_detect_models(self) -> None:
        """Fetch model list from the API and populate the combo box."""
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer

        api_key = self._api_key_edit.text().strip()
        api_base = self._api_base_edit.text().strip().rstrip("/") or self._api_base_edit.placeholderText()
        if not api_key:
            self._detect_btn.setText("请先填 Key")
            QTimer.singleShot(1500, lambda b=self._detect_btn: self._safe_btn_restore(b, " 检测模型"))
            return

        # Show loading state
        self._detect_btn.setText("⏳ 检测中...")
        QApplication.processEvents()

        btn = self._detect_btn
        try:
            from src.memory.config import LLMConfig
            from src.agent.llm import OpenAIClient
            cfg = LLMConfig(
                provider=self._provider_combo.currentText(),
                api_key=api_key,
                api_base=api_base,
                model="",
            )
            client = OpenAIClient(cfg)
            try:
                models = client.list_models()
            finally:
                client.close()
            if models:
                self._model_combo.clear()
                self._model_combo.addItems(models)
                self._model_combo.setCurrentIndex(0)
                # Persist: save to settings so models survive restart
                self._settings.llm.cached_models = models
                self._config.save(self._settings)
                btn.setText(f"✅ {len(models)}个")
                QTimer.singleShot(2500, lambda b=btn: self._safe_btn_restore(b, " 检测模型"))
            else:
                btn.setText("⚠ 无模型")
                QTimer.singleShot(2500, lambda b=btn: self._safe_btn_restore(b, " 检测模型"))
        except Exception as e:
            btn.setText(f"❌ {str(e)[:10]}")
            QTimer.singleShot(3000, lambda b=btn: self._safe_btn_restore(b, " 检测模型"))

    def _on_provider_changed(self, provider: str) -> None:
        """Auto-fill model + API base when switching providers."""
        defaults = {
            "deepseek": ("deepseek-chat", "https://api.deepseek.com"),
            "ollama": ("qwen3:latest", "http://localhost:11434"),
            "openai": ("gpt-4o-mini", "https://api.openai.com"),
        }
        model, base = defaults.get(provider, ("", ""))
        if provider == "custom":
            self._api_base_edit.clear()
            self._api_base_edit.setPlaceholderText("https://api.example.com/v1")
        elif base:
            self._api_base_edit.setText(base)
        self._model_combo.lineEdit().setPlaceholderText(model)
        if not self._model_combo.currentText() and model:
            self._model_combo.setCurrentText(model)

    def closeEvent(self, event) -> None:
        """X button — just restore pet visuals and close, no heavy reload."""
        if self._pet_window:
            old_cx = self._pet_window.x() + self._pet_window.width() // 2
            old_cy = self._pet_window.y() + self._pet_window.height() // 2
            self._pet_window._pet_widget.set_scale(self._original_scale)
            new_w = self._pet_window._pet_widget.width()
            new_h = self._pet_window._pet_widget.height()
            self._pet_window.setGeometry(
                old_cx - new_w // 2, old_cy - new_h // 2, new_w, new_h
            )
            self._pet_window.apply_settings()
        event.accept()
        super().closeEvent(event)

    def _toggle_key_visibility(self, checked: bool) -> None:
        """Show/hide API key."""
        if checked:
            self._api_key_edit.setEchoMode(QLineEdit.Normal)
            self._show_key_btn.setIcon(icon("hide", Theme.accent, 15))
        else:
            self._api_key_edit.setEchoMode(QLineEdit.Password)
            self._show_key_btn.setIcon(icon("eye", Theme.muted, 15))
