"""Passive input monitor — detects key-presses and mouse clicks via polling.

Uses GetAsyncKeyState (Win32), which is *read-only*.  No hooks are
installed, so it is impossible for this module to interfere with
normal mouse / keyboard operation.

Mouse clicks are detected by tracking the *high bit* (real-time key
state) across polls — this catches every click reliably, even when
other processes consume the LSB flag.  Keyboard presses use the
standard LSB edge-detection.
"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal, QTimer

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
# Only scan VK ranges that real keyboards actually use
_VK_RANGES = [
    (0x08, 0x2E),   # Backspace → Delete
    (0x30, 0x5A),   # 0-9, A-Z
    (0x5B, 0x5F),   # Windows keys
    (0x70, 0x87),   # F1 → F24
    (0x90, 0x91),   # NumLock, ScrollLock
    (0xA0, 0xA5),   # Shift, Ctrl, Alt
    (0xBA, 0xBF),   # OEM ; = , - . /
    (0xC0, 0xC1),   # OEM `
    (0xDB, 0xDF),   # OEM [ \ ] '
]


class GlobalInputMonitor(QObject):
    """Detects mouse clicks and key presses via GetAsyncKeyState polling.

    Purely passive — reads key state flags, installs zero hooks.
    """

    external_activity = Signal()

    # Track previous mouse button states for high-bit edge detection.
    _prev_lbtn: int = 0
    _prev_rbtn: int = 0

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._poll_timer: QTimer | None = None
        # Keyboard scanning is expensive (~130 VK reads); do it every
        # 3rd tick (~90ms) while mouse clicks stay responsive at 30ms.
        self._kbd_skip = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._poll_timer is not None:
            return
        # Drain all LSB flags so they don't fire on first poll
        for lo, hi in _VK_RANGES:
            for vk in range(lo, hi + 1):
                ctypes.windll.user32.GetAsyncKeyState(vk)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(30)

    def stop(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        # --- Mouse clicks: high-bit edge detection ---
        # High bit = real-time physical state.  Track 0→1 edges ourselves.
        lbtn = ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000
        if lbtn and not GlobalInputMonitor._prev_lbtn:
            GlobalInputMonitor._prev_lbtn = 1
            self.external_activity.emit()
            return
        GlobalInputMonitor._prev_lbtn = 1 if lbtn else 0

        rbtn = ctypes.windll.user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000
        if rbtn and not GlobalInputMonitor._prev_rbtn:
            GlobalInputMonitor._prev_rbtn = 1
            self.external_activity.emit()
            return
        GlobalInputMonitor._prev_rbtn = 1 if rbtn else 0

        # --- Keyboard: LSB edge detection (throttled to every 3rd tick) ---
        self._kbd_skip = (self._kbd_skip + 1) % 3
        if self._kbd_skip != 0:
            return
        for lo, hi in _VK_RANGES:
            for vk in range(lo, hi + 1):
                if ctypes.windll.user32.GetAsyncKeyState(vk) & 0x0001:
                    self.external_activity.emit()
                    return
