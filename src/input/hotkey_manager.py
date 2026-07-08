"""Global hotkey manager — Win32 RegisterHotKey + dedicated message-pump thread.

This is the most reliable approach on Windows:
1. RegisterHotKey(NULL, id, mods, vk) — posts WM_HOTKEY to thread message queue
2. Dedicated daemon thread runs GetMessageW loop to receive WM_HOTKEY
3. On hotkey, emit Qt signal (thread-safe cross-thread queued connection)

Completely independent of Qt's nativeEventFilter — no MSG struct parsing hacks.
"""

import ctypes
from ctypes import wintypes
import logging
import threading
import time

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("hachicat.input")

# Win32 API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

# Virtual key codes
VK_MAP: dict[str, int] = {
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "enter": 0x0D, "esc": 0x1B, "tab": 0x09,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pgup": 0x21, "pgdn": 0x22, "home": 0x24, "end": 0x23,
    "insert": 0x2D, "delete": 0x2E,
    ",": 0xBC, ".": 0xBE, "/": 0xBF, ";": 0xBA, "'": 0xDE,
    "[": 0xDB, "]": 0xDD, "\\": 0xDC, "-": 0xBD, "=": 0xBB,
    "`": 0xC0,
}

MOD_MAP: dict[str, int] = {
    "ctrl": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Parse 'ctrl+shift+t' into (mod_flags, vk_code)."""
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    mod_flags = 0
    vk_code = 0
    for p in parts:
        if p in MOD_MAP:
            mod_flags |= MOD_MAP[p]
        elif p in VK_MAP:
            vk_code = VK_MAP[p]
        else:
            raise ValueError(f"Unknown hotkey part: '{p}' in '{hotkey_str}'")
    if vk_code == 0:
        raise ValueError(f"No valid key found in '{hotkey_str}'")
    return mod_flags | MOD_NOREPEAT, vk_code


# Win32 MSG struct for GetMessageW
class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class GlobalHotkeyManager(QObject):
    """Win32 RegisterHotKey + dedicated message-pump thread.

    Usage:
        mgr = GlobalHotkeyManager()
        mgr.register('ctrl+shift+t', 'add_todo')
        mgr.hotkey_triggered.connect(my_handler)
        mgr.start()
        ...
        mgr.stop()
    """

    hotkey_triggered = Signal(str)  # action_name

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._hotkey_ids: dict[int, str] = {}  # id → action_name
        self._next_id = 1
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._thread_id: int | None = None

    def register(self, hotkey_str: str, action_name: str) -> None:
        """Queue a hotkey for registration when start() is called."""
        if not hasattr(self, '_pending'):
            self._pending: dict[str, str] = {}
        self._pending[hotkey_str] = action_name
        logger.debug("Queued: %s → %s", hotkey_str, action_name)

    def start(self) -> None:
        """Start message pump thread and register all hotkeys within it.

        RegisterHotKey(NULL, ...) posts WM_HOTKEY to the calling thread's
        message queue. So registration AND message pumping must happen
        in the SAME thread.
        """
        if self._running:
            return
        if not hasattr(self, '_pending') or not self._pending:
            return

        # Build the list of (mods, vk, action) to register in pump thread
        pending_list: list[tuple[int, int, str]] = []
        for hotkey_str, action in self._pending.items():
            try:
                mods, vk = parse_hotkey(hotkey_str)
                pending_list.append((mods, vk, action))
            except Exception as e:
                logger.error("Failed to parse '%s': %s", hotkey_str, e)

        if not pending_list:
            logger.warning("No valid hotkeys to register")
            return

        # Start pump thread — it will register hotkeys and enter message loop
        self._stop_event.clear()
        self._ready_event = threading.Event()
        self._thread = threading.Thread(
            target=self._message_pump,
            args=(pending_list,),
            name="hotkey-pump",
            daemon=True,
        )
        self._thread.start()

        # Wait for registration to complete (max 1 second)
        if self._ready_event.wait(timeout=1.0):
            self._running = True
            logger.info("Hotkey pump started")
        else:
            logger.error("Hotkey pump thread did not start in time")

    def _message_pump(self, pending_hotkeys: list[tuple[int, int, str]]) -> None:
        """Windows message pump — runs in dedicated thread.

        1. Register all hotkeys with RegisterHotKey(NULL, ...)
           → WM_HOTKEY messages will arrive in THIS thread's queue
        2. Enter PeekMessage loop to receive them
        """
        self._thread_id = kernel32.GetCurrentThreadId()

        # Step 1: Register hotkeys IN THIS THREAD
        success = 0
        for mods, vk, action in pending_hotkeys:
            hid = self._next_id
            self._next_id += 1

            result = user32.RegisterHotKey(None, hid, mods, vk)
            if result:
                self._hotkey_ids[hid] = action
                success += 1
                logger.info("Registered hotkey %s (id=%d)", action, hid)
            else:
                err = ctypes.get_last_error()
                if err == 1409:
                    logger.warning("Hotkey '%s' already taken (error 1409)", action)
                else:
                    logger.warning("Failed to register '%s' (error %d)", action, err)

        logger.info("Hotkey registration: %d/%d succeeded", success, len(pending_hotkeys))
        self._ready_event.set()

        if success == 0:
            self._thread_id = None
            return  # Nothing to pump

        # Step 2: Message pump loop
        msg = MSG()

        while not self._stop_event.is_set():
            has_msg = user32.PeekMessageW(
                ctypes.byref(msg), None, 0, 0,
                1  # PM_REMOVE
            )

            if has_msg:
                if msg.message == WM_HOTKEY:
                    action = self._hotkey_ids.get(msg.wParam)
                    if action:
                        logger.info("Hotkey: %s", action)
                        self.hotkey_triggered.emit(action)

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.005)  # Prevent busy-wait

        for hid in list(self._hotkey_ids.keys()):
            user32.UnregisterHotKey(None, hid)
        self._hotkey_ids.clear()
        self._thread_id = None

    def stop(self) -> None:
        """Unregister hotkeys and stop message pump."""
        self._stop_event.set()
        self._running = False

        # Wait for thread to exit
        if self._thread and self._thread.is_alive():
            if self._thread_id:
                user32.PostThreadMessageW(self._thread_id, WM_HOTKEY, 0, 0)
            self._thread.join(timeout=1.0)
            self._thread = None
        self._thread_id = None

        logger.info("Hotkeys stopped")

    def is_running(self) -> bool:
        return self._running
