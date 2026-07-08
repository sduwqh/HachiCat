"""Notes viewer — frosted glass cards with optional background image."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QTextEdit,
    QSizePolicy, QFileDialog,
)
from PySide6.QtGui import QFont, QPixmap, QPalette, QBrush

from src.memory.database import Database
from src.utils.theme import Theme, chip_button_style
from src.utils.markdown import md_to_html


class NoteViewer(QDialog):
    """View saved notes with glassmorphism cards."""

    def __init__(self, db: Database, bg_path: str = "", on_bg_changed=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._bg_path = bg_path
        self._bg_pixmap = None
        self._on_bg_changed = on_bg_changed

        self.setWindowTitle("📝 笔记")
        self.setMinimumSize(480, 400)
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
        """Set background image path and trigger repaint."""
        if self._bg_path and Path(self._bg_path).exists():
            self._bg_pixmap = QPixmap(self._bg_path)
        else:
            self._bg_pixmap = None
        self.update()

    def paintEvent(self, event) -> None:
        """Draw background image, scaled to fill."""
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

        title = QLabel("📝 笔记")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {Theme.text}; padding-bottom: 2px;")
        layout.addWidget(title)

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

        # Bottom
        bottom = QHBoxLayout()
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
        layout.addLayout(bottom)

    def refresh(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

        notes = self._db.fetch_all(
            "SELECT * FROM notes ORDER BY created_at DESC LIMIT 30"
        )
        if not notes:
            empty = QLabel("  暂无笔记 📭\n  选中知识点 → Ctrl+Shift+A 即可保存")
            empty.setStyleSheet(f"color: {Theme.muted}; padding: 30px; font-size: 12px; background: transparent;")
            self._list_layout.insertWidget(0, empty)
            return

        for note in notes:
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, self._make_row(note)
            )

    def _make_row(self, note: dict) -> QWidget:
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
        row.setObjectName("noteRow")

        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 10, 8, 10)

        title_label = QLabel(note.get("title", "无标题"))
        title_label.setStyleSheet(f"color: {Theme.text}; font-size: 13px; font-weight: bold; background: transparent;")
        hl.addWidget(title_label, 1)

        date_label = QLabel(note.get("created_at", "")[:16])
        date_label.setStyleSheet(f"color: {Theme.muted}; font-size: 10px; background: transparent;")
        hl.addWidget(date_label)

        expand_btn = _icon_btn(
            "▶", 24,
            "QLabel { color: #1e293b; background: rgba(31,41,55,0.06); border: 1px solid rgba(31,41,55,0.16); border-radius: 12px; }",
            "QLabel { color: #4f7cff; background: rgba(79,124,255,0.18); border: 1px solid rgba(79,124,255,0.42); border-radius: 12px; }",
            lambda: None,
        )
        hl.addWidget(expand_btn)

        outer.addWidget(header)

        detail = QWidget()
        detail.setVisible(False)
        detail.setStyleSheet("background: #fdf6f0; border-top: 1px solid rgba(180,140,100,0.14);")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(14, 8, 14, 10)

        # Toolbar: toggle markdown preview + delete
        nid = note["id"]
        bar_row = QHBoxLayout()

        md_toggle = QPushButton("📄 显示Markdown")
        md_toggle.setCheckable(True)
        md_font = QF()
        md_font.setPointSize(9)
        md_toggle.setFont(md_font)
        md_toggle.setStyleSheet(
            f"QPushButton {{ color: {Theme.muted}; background: rgba(255,255,255,0.72); border: 1px solid {Theme.border}; border-radius: 7px; padding: 3px 10px; font-size: 10px; }}"
            f"QPushButton:hover {{ color: {Theme.accent}; border-color: rgba(79,124,255,0.30); background: rgba(79,124,255,0.10); }}"
            f"QPushButton:checked {{ color: {Theme.accent}; background: rgba(79,124,255,0.10); border-color: rgba(79,124,255,0.30); }}"
        )
        bar_row.addWidget(md_toggle)
        bar_row.addStretch()

        del_btn = QPushButton("删除此笔记")
        del_font = QF()
        del_font.setPointSize(9)
        del_btn.setFont(del_font)
        del_btn.setStyleSheet(f"QPushButton {{ color: {Theme.muted}; background: rgba(255,255,255,0.72); border: 1px solid {Theme.border}; border-radius: 7px; padding: 3px 10px; font-size: 10px; }} QPushButton:hover {{ color: {Theme.danger}; border-color: rgba(194,102,102,0.30); background: rgba(194,102,102,0.10); }}")
        del_btn.clicked.connect(lambda checked=False, nid=nid: self._on_delete(nid))
        bar_row.addWidget(del_btn)
        dl.addLayout(bar_row)

        # Stack: source editor / rendered preview
        content_edit = QTextEdit()
        content_edit.setPlainText(note.get("content", ""))
        content_edit.setMinimumHeight(200)
        content_edit.setMaximumHeight(600)
        content_edit.setStyleSheet(f"background: rgba(255,255,255,0.88); border: 1px solid {Theme.border}; border-radius: 10px; color: {Theme.text}; font-size: 12px; padding: 6px;")
        content_edit.textChanged.connect(lambda nid=nid, ce=content_edit: self._mark_dirty(nid, ce))
        dl.addWidget(content_edit)

        # Rendered markdown preview
        from PySide6.QtWidgets import QTextBrowser
        preview = QTextBrowser()
        preview.setMinimumHeight(200)
        preview.setMaximumHeight(600)
        preview.setFrameShape(QTextBrowser.NoFrame)
        preview.setStyleSheet(f"background: rgba(255,255,255,0.88); border: 1px solid {Theme.border}; border-radius: 10px; color: {Theme.text}; font-size: 12px; padding: 6px;")
        preview.document().setDocumentMargin(4)
        preview.document().setDefaultStyleSheet(
            "ul, ol { margin: 1px 0; padding-left: 16px; }"
            "li { margin: 0; padding: 0; line-height: 1.35; }"
        )
        preview.setHtml(f"<div style='line-height:1.4;'>{md_to_html(note.get('content', ''))}</div>")
        preview.hide()
        dl.addWidget(preview)

        def toggle_md(checked):
            if checked:
                preview.setHtml(f"<div style='line-height:1.4;'>{md_to_html(content_edit.toPlainText())}</div>")
                content_edit.hide()
                preview.show()
                md_toggle.setText("📝 显示原文")
            else:
                preview.hide()
                content_edit.show()
                md_toggle.setText("📄 显示Markdown")
        md_toggle.toggled.connect(toggle_md)

        outer.addWidget(detail)

        row.setStyleSheet(f"""
            QWidget#noteRow {{
                background: #fefaf5;
                border: 1px solid rgba(180,140,100,0.18);
                border-radius: 14px;
            }}
            QWidget#noteRow:hover {{
                background: #fff7ef;
                border-color: rgba(79,124,255,0.34);
            }}
        """)

        def toggle(checked=None, d=detail, btn=expand_btn):
            d.setVisible(not d.isVisible())
            btn.setText("▼" if d.isVisible() else "▶")
        expand_btn._clicked = toggle
        expand_btn.setToolTip("展开/收起")

        return row

    def _mark_dirty(self, nid: int, editor: QTextEdit) -> None:
        """Auto-save note content after a short debounce."""
        if hasattr(self, '_save_timers'):
            pass
        else:
            self._save_timers = {}
        from PySide6.QtCore import QTimer
        if nid in self._save_timers:
            self._save_timers[nid].stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._do_save(nid, editor))
        timer.start(800)
        self._save_timers[nid] = timer

    def _do_save(self, nid: int, editor: QTextEdit) -> None:
        self._db.update("UPDATE notes SET content=? WHERE id=?", (editor.toPlainText(), nid))

    def _on_delete(self, nid: int) -> None:
        self._db.update("DELETE FROM notes WHERE id=?", (nid,))
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
