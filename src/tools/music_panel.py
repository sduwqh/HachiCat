"""Music control panel — appears at cursor, auto-dismiss."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton

from src.utils.theme import Theme, app_window_style, chip_button_style
from src.utils.icons import icon

VK = {"pp": 0xB3, "prev": 0xB1, "next": 0xB0}

def _send(vk: int) -> None:
    import ctypes
    ctypes.windll.user32.keybd_event(vk, 0, 0x0001, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 0x0001 | 0x0002, 0)


class MusicPanel(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(140, 44)

        self.setStyleSheet(app_window_style())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        _icon_for = {"prev": "music-prev", "pp": "music-play", "next": "music-next"}
        for key in ["prev", "pp", "next"]:
            btn = QPushButton()
            btn.setIcon(icon(_icon_for[key], Theme.accent, 16))
            btn.setToolTip({"prev":"上一首","pp":"播放/暂停","next":"下一首"}[key])
            btn.setStyleSheet(chip_button_style(Theme.accent))
            btn.clicked.connect(lambda checked=False, k=key: _send(VK[k]))
            layout.addWidget(btn)

        self._timer = QTimer(self, singleShot=True, timeout=self.hide)
        self.hide()

    def popup(self) -> None:
        pos = QCursor.pos()
        self.move(pos.x() - 70, pos.y() - 50)
        self.show()
        self.raise_()
        self._timer.start(3000)
