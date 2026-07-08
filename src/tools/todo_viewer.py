"""TODO list viewer — frosted glass cards on custom background."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QCheckBox,
    QSizePolicy, QInputDialog, QFileDialog, QSlider,
)
from PySide6.QtGui import QFont, QPixmap, QPalette, QBrush

from src.memory.database import Database
from src.utils.theme import Theme, button_style, chip_button_style

CARD_STYLE = """
    QWidget#todoRow {
        background: #fefaf5;
        border: 1px solid rgba(180,140,100,0.18);
        border-radius: 14px;
    }
    QWidget#todoRow:hover {
        background: #fff7ef;
        border-color: rgba(79,124,255,0.34);
    }
"""


class TodoViewer(QDialog):
    """Scrollable TODO list with glassmorphism cards."""

    def __init__(self, db: Database, bg_path: str = "", on_bg_changed=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._show_completed = False
        self._bg_path = bg_path
        self._bg_pixmap = None
        self._on_bg_changed = on_bg_changed  # callback(bg_path) to persist

        self.setWindowTitle("📋 待办事项")
        self.setMinimumSize(440, 380)
        self.setWindowFlags(
            Qt.Tool
        )
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #dfe4ec,
                    stop: 1 #eaedf4
                );
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 0 2px 0; }}
            QScrollBar::handle:vertical {{ background: rgba(79,124,255,0.24); border-radius: 5px; min-height: 24px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba(79,124,255,0.38); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        if self._bg_path:
            self._apply_background()

        self._build_ui()
        self.refresh()

    def _apply_background(self) -> None:
        """Set background image or solid color."""
        if self._bg_path and Path(self._bg_path).exists():
            self._bg_pixmap = QPixmap(self._bg_path)
        else:
            self._bg_pixmap = None
        self.update()

    def paintEvent(self, event) -> None:
        """Draw background image if set."""
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            from PySide6.QtGui import QPainter
            p = QPainter(self)
            scaled = self._bg_pixmap.scaled(
                self.width(), self.height(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
            p.end()
        super().paintEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("📋 待办事项")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {Theme.text}; padding-bottom: 2px;")
        header.addWidget(title)
        header.addStretch()

        add_btn = QPushButton("➕ 添加")
        add_btn.setStyleSheet(button_style("primary"))
        add_btn.clicked.connect(self._on_add)
        header.addWidget(add_btn)
        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(8)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll, 1)

        # Bottom bar
        bottom = QHBoxLayout()
        self._completed_toggle = QPushButton("📁 显示已完成")
        self._completed_toggle.setCheckable(True)
        self._completed_toggle.toggled.connect(self._on_toggle_completed)
        self._completed_toggle.setStyleSheet(
            chip_button_style(Theme.accent)
            + f"QPushButton:checked {{ background: {Theme.accent_soft}; color: {Theme.accent}; }}"
        )
        bottom.addWidget(self._completed_toggle)

        bg_btn = QPushButton("🖼 背景")
        bg_btn.setToolTip("设置背景图片")
        bg_btn.setStyleSheet(chip_button_style(Theme.success))
        bg_btn.clicked.connect(self._on_set_bg)
        bottom.addWidget(bg_btn)

        reset_btn = QPushButton("↩ 默认")
        reset_btn.setToolTip("恢复默认背景")
        reset_btn.setStyleSheet(chip_button_style(Theme.muted))
        reset_btn.clicked.connect(self._on_reset_bg)
        bottom.addWidget(reset_btn)

        bottom.addStretch()
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(f"color: {Theme.muted};")
        bottom.addWidget(self._count_label)
        layout.addLayout(bottom)

    def refresh(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

        pending = self._db.fetch_all(
            "SELECT * FROM todos WHERE status='pending' ORDER BY priority DESC, created_at DESC"
        )
        for todo in pending:
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, self._make_row(todo, done=False)
            )

        if self._show_completed:
            done_items = self._db.fetch_all(
                "SELECT * FROM todos WHERE status='done' ORDER BY completed_at DESC LIMIT 20"
            )
            if done_items:
                sep = QLabel("── 已完成 ──")
                sep.setStyleSheet(f"color: {Theme.muted}; font-size: 11px; padding: 12px 4px 4px 4px;")
                self._list_layout.insertWidget(self._list_layout.count() - 1, sep)
                for todo in done_items:
                    self._list_layout.insertWidget(
                        self._list_layout.count() - 1, self._make_row(todo, done=True)
                    )

        total = len(pending)
        self._count_label.setText(f"共 {total} 条待办" if total else "✨ 全部完成")

    def _make_row(self, todo: dict, done: bool = False) -> QWidget:
        from PySide6.QtGui import QFont as QF, QCursor

        _btn_font = QF()
        _btn_font.setPointSize(9)
        _btn_font.setBold(True)

        def _icon_btn(icon, size, normal_css, hover_css, on_click):
            lbl = QLabel(icon)
            lbl.setFont(_btn_font)
            lbl.setFixedSize(size, size)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setCursor(QCursor(Qt.PointingHandCursor))
            lbl.setStyleSheet(normal_css)
            lbl._hover_css = hover_css
            lbl._normal_css = normal_css
            lbl._clicked = on_click
            lbl.enterEvent = lambda e, l=lbl: l.setStyleSheet(l._hover_css)
            lbl.leaveEvent = lambda e, l=lbl: l.setStyleSheet(l._normal_css)
            lbl.mousePressEvent = lambda e, l=lbl: l._clicked()
            return lbl

        row = QWidget()
        row.setObjectName("todoRow")
        row.setStyleSheet(CARD_STYLE)

        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        main_row = QWidget()
        main_row.setStyleSheet("background: transparent;")
        main_layout = QHBoxLayout(main_row)
        main_layout.setContentsMargins(12, 8, 8, 8)
        main_layout.setSpacing(8)

        cb = QCheckBox("")
        cb.setChecked(done)
        cb.setToolTip("标记完成")
        cb.setStyleSheet("""
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 2px solid rgba(31,41,55,0.26); border-radius: 5px;
                background: rgba(255,255,255,0.6);
            }
            QCheckBox::indicator:checked {
                background: #4f7cff; border-color: #3f66d1;
            }
            QCheckBox::indicator:hover {
                border-color: #4f7cff;
            }
        """)
        if not done:
            cb.toggled.connect(lambda checked, tid=todo["id"]: self._on_complete(tid, checked))
        main_layout.addWidget(cb)

        title_text = todo["title"]
        title_label = QLabel(title_text)
        title_label.setWordWrap(True)
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        if done:
            title_label.setStyleSheet(f"color: {Theme.muted}; text-decoration: line-through; font-size: 12px; background: transparent;")
        else:
            title_label.setStyleSheet(f"color: {Theme.text}; font-size: 12px; background: transparent;")
        main_layout.addWidget(title_label, 1)

        due = todo.get("due_date", "")
        if due:
            badge = QLabel(f"⏰ {due}")
            badge.setStyleSheet(
                f"color: {Theme.danger}; font-size: 10px; background: rgba(255,240,240,0.84); "
                "border: 1px solid rgba(194,102,102,0.22); border-radius: 999px; padding: 2px 7px;"
            )
            main_layout.addWidget(badge)

        desc = todo.get("description", "")

        expand_btn = _icon_btn(
            "▶", 24,
            "QLabel { color: #1e293b; background: rgba(31,41,55,0.06); border: 1px solid rgba(31,41,55,0.16); border-radius: 12px; }",
            "QLabel { color: #4f7cff; background: rgba(79,124,255,0.18); border: 1px solid rgba(79,124,255,0.42); border-radius: 12px; }",
            lambda: None,  # set by toggle below
        )
        main_layout.addWidget(expand_btn)

        # Delete button (on completed items only)
        if done:
            del_btn = _icon_btn(
                "✕", 24,
                "QLabel { color: #1e293b; background: rgba(31,41,55,0.06); border: 1px solid rgba(31,41,55,0.16); border-radius: 12px; }",
                "QLabel { color: #c26666; background: rgba(194,102,102,0.18); border: 1px solid rgba(194,102,102,0.42); border-radius: 12px; }",
                lambda tid=todo["id"]: self._on_delete(tid),
            )
            del_btn.setToolTip("永久删除")
            main_layout.addWidget(del_btn)
        else:
            del_btn = None

        outer.addWidget(main_row)

        # Detail panel — all editable
        detail = QWidget()
        detail.setVisible(False)
        detail.setStyleSheet("background: #fdf6f0; border-top: 1px solid rgba(180,140,100,0.14);")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(14, 8, 14, 10)
        detail_layout.setSpacing(7)

        from PySide6.QtWidgets import QLineEdit, QTextEdit

        # AI 总结标题
        title_hint = QLabel("📌 标题")
        title_hint.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {Theme.text}; background: transparent; padding: 2px;")
        detail_layout.addWidget(title_hint)
        te = QLineEdit(todo["title"])
        te.setPlaceholderText("待办标题")
        te.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {Theme.text}; border: 1px solid {Theme.border}; border-radius: 8px; padding: 5px 8px; background: rgba(255,255,255,0.92);")
        te.editingFinished.connect(lambda tid=todo["id"], e=te: self._save_field(tid, "title", e.text()))
        detail_layout.addWidget(te)

        # 截止日期
        date_hint = QLabel("⏰ 截止日期")
        date_hint.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {Theme.text}; background: transparent; padding: 2px;")
        detail_layout.addWidget(date_hint)
        de = QLineEdit(todo.get("due_date", ""))
        de.setPlaceholderText("如 2026-07-01 或 2026-07-01 15:00")
        de.setStyleSheet(f"font-size: 11px; color: {Theme.danger}; border: 1px solid rgba(194,102,102,0.26); border-radius: 8px; padding: 4px 7px; background: #fff7f7;")
        de.editingFinished.connect(lambda tid=todo["id"], e=de: self._save_field(tid, "due_date", e.text()))
        detail_layout.addWidget(de)

        # 原文
        orig_hint = QLabel("📄 原文")
        orig_hint.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {Theme.text}; background: transparent; padding: 2px;")
        detail_layout.addWidget(orig_hint)
        desc_edit = QTextEdit()
        desc_edit.setPlainText(desc)
        desc_edit.setPlaceholderText("选中文字的原文保存在这里...")
        desc_edit.setMaximumHeight(150)
        desc_edit.setStyleSheet(f"font-size: 11px; color: {Theme.text}; border: 1px solid {Theme.border}; border-radius: 8px; padding: 6px; background: rgba(255,255,255,0.92);")
        desc_edit.textChanged.connect(lambda tid=todo["id"], d=desc_edit: self._save_desc(tid, d))
        detail_layout.addWidget(desc_edit)

        created = todo.get("created_at", "")
        if created:
            info = QLabel(f"创建于 {created}")
            info.setStyleSheet(f"color: {Theme.muted}; font-size: 10px; background: transparent;")
            detail_layout.addWidget(info)

        outer.addWidget(detail)

        def toggle(checked=None, d=detail, btn=expand_btn):
            d.setVisible(not d.isVisible())
            btn.setText("▼" if d.isVisible() else "▶")
        expand_btn._clicked = toggle
        expand_btn.setToolTip("展开/收起")

        return row

    def _on_add(self) -> None:
        text, ok = QInputDialog.getText(self, "添加待办", "请输入待办内容:")
        if ok and text.strip():
            self._db.insert(
                "INSERT INTO todos (title, status, source) VALUES (?, 'pending', 'viewer')",
                (text.strip(),),
            )
            self.refresh()

    def _save_field(self, tid: int, field: str, value: str) -> None:
        if value.strip():
            self._db.update(f"UPDATE todos SET {field}=? WHERE id=?", (value.strip(), tid))
            # Refresh to update the main row display
            QTimer.singleShot(100, self.refresh)

    def _save_desc(self, tid: int, editor) -> None:
        if hasattr(self, '_desc_timers'):
            pass
        else:
            self._desc_timers = {}
        if tid in self._desc_timers:
            self._desc_timers[tid].stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._db.update(
            "UPDATE todos SET description=? WHERE id=?", (editor.toPlainText(), tid)))
        timer.start(600)
        self._desc_timers[tid] = timer

    def _on_complete(self, todo_id: int, checked: bool) -> None:
        if checked:
            self._db.update(
                "UPDATE todos SET status='done', completed_at=datetime('now','localtime') WHERE id=?",
                (todo_id,),
            )
            QTimer.singleShot(350, self.refresh)

    def _on_delete(self, todo_id: int) -> None:
        self._db.update("DELETE FROM todos WHERE id=?", (todo_id,))
        self.refresh()

    def _on_toggle_completed(self, checked: bool) -> None:
        self._show_completed = checked
        self._completed_toggle.setText("📂 隐藏已完成" if checked else "📁 显示已完成")
        self.refresh()

    def _on_set_bg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self._bg_path = path
            self._apply_background()
            if self._on_bg_changed:
                self._on_bg_changed(path)

    def _on_reset_bg(self) -> None:
        self._bg_path = ""
        self._bg_pixmap = None
        self.update()
        if self._on_bg_changed:
            self._on_bg_changed("")
