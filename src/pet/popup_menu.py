"""Floating action menu — appears near cursor on Ctrl+Shift+A."""

from PySide6.QtCore import Qt, Signal, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsOpacityEffect, QApplication,
)

from src.utils.theme import Theme, panel_style


class PopupMenu(QWidget):
    """A sleek floating menu with 4 action buttons."""

    action_triggered = Signal(str)  # "search" | "note" | "todo" | "translate"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        self.setFixedSize(200, 260)

        # Main container
        container = QWidget(self)
        container.setObjectName("container")
        container.setStyleSheet(panel_style("container"))
        container.setGeometry(0, 0, 200, 260)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)

        # Title row with close button
        title_row = QHBoxLayout()
        title_row.addStretch()
        title = QLabel("选择操作")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {Theme.muted}; font-size: 11px; letter-spacing: 0.5px;")
        title_row.addWidget(title)
        title_row.addStretch()

        close_btn = QLabel("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setAlignment(Qt.AlignCenter)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QLabel {{ color: {Theme.muted}; background: transparent; "
            "font-size: 14px; font-weight: bold; border-radius: 11px; }} "
            f"QLabel:hover {{ color: {Theme.text}; background: {Theme.accent_soft}; }}"
        )
        close_btn.mousePressEvent = lambda e: self.hide()
        title_row.addWidget(close_btn)
        layout.addLayout(title_row)

        self._add_btn(layout, "🔍  搜索", "search", "#4A90D9")
        self._add_btn(layout, "📝  记录笔记", "note", "#5B9E5B")
        self._add_btn(layout, "📋  添加待办", "todo", "#E8943A")
        self._add_btn(layout, "🌐  翻译", "translate", "#8E6FBF")

        layout.addStretch()

    def _add_btn(self, layout, text: str, action: str, color: str) -> None:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {Theme.text}; font-size: 14px; font-weight: 500;
                background: rgba(255,255,255,0.72);
                border: 1px solid {Theme.border};
                border-radius: 10px; padding: 10px 14px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {color}15;
                border-color: {color}40;
                color: {color};
            }}
        """)
        btn.clicked.connect(lambda: self._on_action(action))
        layout.addWidget(btn)

    def _on_action(self, action: str) -> None:
        self.hide()
        self.action_triggered.emit(action)

    def show_at(self, pos: QPoint) -> None:
        """Show menu at screen position, adjusting to stay on-screen."""
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = min(pos.x(), geo.right() - self.width() - 10)
            y = min(pos.y(), geo.bottom() - self.height() - 10)
            x = max(x, geo.left() + 10)
            y = max(y, geo.top() + 10)
        else:
            x, y = pos.x(), pos.y()

        self.move(x, y)
        self.show()
        self.raise_()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            # Only drag from the title bar area (top 30px or on the title text)
            local_y = event.position().y()
            if local_y < 30:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if hasattr(self, '_drag_pos') and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if hasattr(self, '_drag_pos'):
            del self._drag_pos
        super().mouseReleaseEvent(event)

    def hideEvent(self, event) -> None:
        self.action_triggered.emit("__dismissed__")
        super().hideEvent(event)
