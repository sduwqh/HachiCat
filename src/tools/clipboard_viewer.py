"""Clipboard history viewer — Win+V style, frosted glass cards.

Lists recent clipboard entries (text + images). Clicking a card copies it
back to the system clipboard (user then presses Ctrl+V themselves).
"""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QSizePolicy, QApplication,
)
from PySide6.QtGui import QFont, QPixmap, QCursor

from src.memory.database import Database
from src.utils.theme import Theme, chip_button_style
from src.utils.icons import icon, icon_pixmap


def _rot(pm, deg):
    """Rotate a pixmap while preserving its device pixel ratio."""
    from PySide6.QtGui import QTransform
    dpr = pm.devicePixelRatio()
    out = pm.transformed(QTransform().rotate(deg), Qt.SmoothTransformation)
    out.setDevicePixelRatio(dpr)
    return out


class ClipboardViewer(QDialog):
    """Scrollable clipboard-history list with glassmorphism cards."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("最近复制")
        self.setMinimumSize(420, 420)
        self.setWindowFlags(Qt.Tool)
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
            QScrollBar::handle:vertical {{ background: rgba(255,122,89,0.28); border-radius: 5px; min-height: 24px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba(255,122,89,0.44); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(icon_pixmap("clipboard", Theme.accent, 20))
        title_icon.setStyleSheet("background: transparent;")
        header.addWidget(title_icon)
        title = QLabel("最近复制")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {Theme.text}; padding-bottom: 2px; padding-left: 4px;")
        header.addWidget(title)
        header.addStretch()

        clear_btn = QPushButton(" 清空")
        clear_btn.setIcon(icon("trash", Theme.muted, 15))
        clear_btn.setToolTip("清空全部历史")
        clear_btn.setStyleSheet(chip_button_style(Theme.danger))
        clear_btn.clicked.connect(self._on_clear_all)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # Never scroll horizontally: long content (e.g. file paths) must wrap
        # to the viewport width instead of widening the whole list.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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

        hint = QLabel("点击任意一条复制到剪贴板，再按 Ctrl+V 粘贴")
        hint.setStyleSheet(f"color: {Theme.muted}; font-size: 10px; background: transparent;")
        layout.addWidget(hint)

    def refresh(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        rows = self._db.fetch_all(
            "SELECT * FROM clipboard_history ORDER BY id DESC LIMIT 50"
        )
        if not rows:
            empty = QLabel("  暂无剪贴板历史 📋\n  复制文字或图片后会自动出现在这里")
            empty.setStyleSheet(
                f"color: {Theme.muted}; padding: 30px; font-size: 12px; background: transparent;")
            self._list_layout.insertWidget(0, empty)
            return

        for row in rows:
            self._list_layout.insertWidget(
                self._list_layout.count() - 1, self._make_row(row))

    def _make_row(self, entry: dict) -> QWidget:
        row = QWidget()
        row.setObjectName("clipRow")
        row.setStyleSheet("""
            QWidget#clipRow {
                background: #fefaf5;
                border: 1px solid rgba(180,140,100,0.18);
                border-radius: 16px;
            }
            QWidget#clipRow:hover {
                background: #fff7ef;
                border-color: rgba(255,122,89,0.38);
            }
        """)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        head = QWidget()
        head.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(12, 10, 8, 10)
        hl.setSpacing(8)

        kind = entry.get("kind", "text")
        source_path = entry.get("source_path", "") or ""
        if kind == "image":
            thumb = QLabel()
            pm = QPixmap(entry.get("content", ""))
            if not pm.isNull():
                thumb.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("图片已失效")
                thumb.setStyleSheet(f"color: {Theme.muted}; font-size: 11px;")
            thumb.setStyleSheet(thumb.styleSheet() + "background: transparent;")
            hl.addWidget(thumb)
            label = QLabel("🖼 图片")
            label.setStyleSheet(f"color: {Theme.text}; font-size: 12px; background: transparent;")
        else:
            label = QLabel(entry.get("preview") or entry.get("content", "")[:80])
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {Theme.text}; font-size: 12px; background: transparent;")
        # Ignored horizontal policy: long unbroken text/paths wrap to the row
        # width instead of forcing the whole list wider than the viewport.
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        label.setMinimumWidth(0)
        hl.addWidget(label, 1)

        date = QLabel(entry.get("created_at", "")[5:16])
        date.setStyleSheet(f"color: {Theme.muted}; font-size: 10px; background: transparent;")
        hl.addWidget(date)

        def _round_btn(name, hover_color, bg_hover, border_hover, tip, on_click):
            b = QLabel()
            b.setFixedSize(24, 24)
            b.setAlignment(Qt.AlignCenter)
            b.setCursor(QCursor(Qt.PointingHandCursor))
            b.setToolTip(tip)
            b._name = name
            b._normal = "QLabel { background: rgba(31,41,55,0.06); border: 1px solid rgba(31,41,55,0.16); border-radius: 12px; }"
            b._hover = f"QLabel {{ background: {bg_hover}; border: 1px solid {border_hover}; border-radius: 12px; }}"
            b.setStyleSheet(b._normal)
            b.setPixmap(icon_pixmap(name, "#64748b", 14))
            b.enterEvent = lambda e, x=b: (x.setStyleSheet(x._hover), x.setPixmap(icon_pixmap(x._name, hover_color, 14)))
            b.leaveEvent = lambda e, x=b: (x.setStyleSheet(x._normal), x.setPixmap(icon_pixmap(x._name, "#64748b", 14)))
            b.mousePressEvent = lambda e, cb=on_click: cb()
            return b

        eid = entry["id"]

        # Collapsible detail (image source path). Built first so the expand
        # button can toggle it.
        detail = None
        if kind == "image" and source_path:
            detail = QWidget()
            detail.setVisible(False)
            detail.setStyleSheet("background: #fdf6f0; border-top: 1px solid rgba(180,140,100,0.14);")
            dl = QVBoxLayout(detail)
            dl.setContentsMargins(14, 8, 14, 10)
            dl.setSpacing(4)
            path_hint = QLabel("📄 原始路径")
            path_hint.setStyleSheet(f"color: {Theme.muted}; font-size: 10px; background: transparent;")
            dl.addWidget(path_hint)
            path_val = QLabel(source_path)
            path_val.setWordWrap(True)
            path_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            # Horizontal policy Ignored: the label never demands width, so a
            # long path wraps to the row width instead of widening the panel.
            path_val.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            path_val.setMinimumWidth(0)
            path_val.setStyleSheet(f"color: {Theme.text}; font-size: 11px; background: transparent;")
            dl.addWidget(path_val)

            expand_btn = _round_btn(
                "chevron-down", Theme.accent, "rgba(255,122,89,0.16)", "rgba(255,122,89,0.42)",
                "展开/收起路径", lambda: None)

            def _toggle(d=detail, b=expand_btn):
                vis = not d.isVisible()
                d.setVisible(vis)
                b._rotation = 180 if vis else 0
                b.setPixmap(_rot(icon_pixmap(b._name, "#64748b", 14), b._rotation))
            expand_btn.mousePressEvent = lambda e, t=_toggle: t()
            hl.addWidget(expand_btn)

        copy_btn = _round_btn(
            "check", Theme.success, "rgba(93,139,100,0.16)", "rgba(93,139,100,0.42)",
            "复制到剪贴板", lambda e=entry: self._on_copy(e))
        hl.addWidget(copy_btn)
        del_btn = _round_btn(
            "trash", Theme.danger, "rgba(194,102,102,0.16)", "rgba(194,102,102,0.42)",
            "删除", lambda i=eid: self._on_delete(i))
        hl.addWidget(del_btn)

        outer.addWidget(head)
        if detail is not None:
            outer.addWidget(detail)

        # Click the header (except buttons) also copies.
        head.mousePressEvent = lambda e, ent=entry: self._on_copy(ent)
        return row

    def _on_copy(self, entry: dict) -> None:
        clip = QApplication.clipboard()
        if entry.get("kind") == "image":
            pm = QPixmap(entry.get("content", ""))
            if not pm.isNull():
                clip.setPixmap(pm)
        else:
            clip.setText(entry.get("content", ""))
        from src.utils.toast import show_toast
        show_toast(self, "已复制")

    def _on_delete(self, entry_id: int) -> None:
        row = self._db.fetch_one(
            "SELECT kind, content FROM clipboard_history WHERE id=?", (entry_id,))
        if row and row["kind"] == "image":
            try:
                p = Path(row["content"])
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        self._db.update("DELETE FROM clipboard_history WHERE id=?", (entry_id,))
        self.refresh()

    def _on_clear_all(self) -> None:
        imgs = self._db.fetch_all(
            "SELECT content FROM clipboard_history WHERE kind='image'")
        for r in imgs:
            try:
                p = Path(r["content"])
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        self._db.update("DELETE FROM clipboard_history", ())
        self.refresh()
