"""System tray integration.

References:
- DyberPet: QSystemTrayIcon + QMenu with show/settings/quit actions
  + setQuitOnLastWindowClosed(False)
- Clawd on Desk: system tray with Show/Hide, Settings, Quit

Design:
- Tray icon always visible (even when pet is hidden)
- Right-click context menu for common actions
- Double-click toggles pet visibility
"""

from pathlib import Path

from PySide6.QtGui import QIcon, QAction, QPainter, QPixmap, QColor
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from src.utils.theme import Theme


def _generate_tray_icon(size: int = 32) -> QIcon:
    """Generate a simple tray icon — a small orange circle (like the pet).

    In production, replace with an actual icon file.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # transparent

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Small round orange icon
    margin = 2
    painter.setBrush(QColor(255, 180, 100))
    painter.setPen(QColor(200, 140, 60))
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)

    # Two small eye dots
    painter.setBrush(QColor(60, 60, 60))
    painter.setPen(QColor(60, 60, 60))
    eye_r = max(2, size // 12)
    painter.drawEllipse(size // 3 - 2, size // 3, eye_r, eye_r + 1)
    painter.drawEllipse(2 * size // 3 - 2, size // 3, eye_r, eye_r + 1)

    painter.end()
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):
    """System tray controller for the desktop pet."""

    def __init__(
        self,
        icon_path: Path | None = None,
        icon: QIcon | None = None,
        parent: QApplication | None = None,
    ):
        super().__init__(parent)

        # Icon
        if icon:
            self.setIcon(icon)
        elif icon_path and icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            self.setIcon(_generate_tray_icon())

        self.setToolTip("HaChiCat — Desktop Pet")

        # Context menu
        self._menu = QMenu()
        self._menu.setStyleSheet("""
            QMenu {
                background: rgba(255, 255, 255, 0.96);
                color: #1f2937;
                border: 1px solid rgba(31, 41, 55, 0.12);
                border-radius: 12px;
                padding: 6px;
            }
            QMenu::item {
                padding: 7px 24px;
                border-radius: 8px;
            }
            QMenu::item:selected {
                background: rgba(79,124,255,0.12);
                color: #1f2937;
            }
        """)

        self._toggle_action = QAction("🐱 显示/隐藏宠物")
        self._toggle_action.triggered.connect(self._on_toggle)

        self._todo_action = QAction("📋 查看待办")
        self._notes_action = QAction("📖 查看笔记")

        self._settings_action = QAction("⚙️ 设置")
        self._settings_action.triggered.connect(self._on_settings)

        self._quit_action = QAction("❌ 退出")
        self._quit_action.triggered.connect(self._on_quit)

        self._menu.addAction(self._toggle_action)
        self._menu.addSeparator()
        self._menu.addAction(self._todo_action)
        self._menu.addAction(self._notes_action)
        self._menu.addSeparator()
        self._menu.addAction(self._settings_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self.setContextMenu(self._menu)

        # Double-click toggles visibility
        self.activated.connect(self._on_activated)

    # --- Callbacks (override in main.py) ---

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.DoubleClick:
            self._on_toggle()

    def _on_toggle(self) -> None:
        """Toggle pet visibility — to be connected externally."""
        pass

    def _on_settings(self) -> None:
        """Open settings — to be connected externally (Phase 2+)."""
        pass

    def _on_quit(self) -> None:
        """Quit the application."""
        QApplication.instance().quit()
