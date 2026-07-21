"""Clipboard history monitor — Win+V style capture of copied text/images.

Listens to QClipboard.dataChanged and records each new text or image into
the clipboard_history table. Images are saved as PNG files under
data/clipboard/ with the path stored in the DB.

Privacy: this records everything copied while enabled (including passwords).
All data stays in the local SQLite DB / data folder. Toggle via
settings.privacy.clipboard_monitor (default off).
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

MAX_ENTRIES = 50            # keep only the most recent N items
_MAX_PREVIEW = 80           # preview label length for text
_DEBOUNCE_MS = 150          # coalesce rapid dataChanged bursts into one capture
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".ico"}

# --- text classification ---------------------------------------------------
_RE_URL = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Common code signals: braces/semicolons, indentation, or keywords
_CODE_KEYWORDS = (
    "def ", "class ", "import ", "function ", "const ", "let ", "var ",
    "public ", "private ", "return ", "#include", "print(", "console.log",
    "</", "/>", "<div", "<span", "<a ", "<p>", "SELECT ", "select ", "=>", "::",
)


def classify_text(text: str) -> str:
    """Best-effort category for a copied text snippet.

    Returns one of: 'link' | 'email' | 'code' | 'text'.
    Single-line checks (url/email) win first; then code heuristics.
    """
    s = (text or "").strip()
    if not s:
        return "text"
    single = "\n" not in s
    if single and _RE_URL.match(s):
        return "link"
    if single and _RE_EMAIL.match(s):
        return "email"
    # Code: multi-line with braces/semicolons/indent, or a known keyword.
    lowered = s
    has_kw = any(k in lowered for k in _CODE_KEYWORDS)
    struct = ("{" in s and "}" in s) or s.count(";") >= 2
    indented = any(ln.startswith(("    ", "\t")) for ln in s.split("\n"))
    if has_kw or (("\n" in s) and (struct or indented)):
        return "code"
    return "text"


class ClipboardMonitor(QObject):
    """Watches the system clipboard and logs history to the database."""

    def __init__(self, db, image_dir: Path, parent=None):
        super().__init__(parent)
        self._db = db
        self._image_dir = image_dir
        self._image_dir.mkdir(parents=True, exist_ok=True)
        self._paused = False
        self._last_text = ""
        self._last_image_key = ""   # dedup key for the most recent image
        self._clip = QApplication.clipboard()
        # Debounce: WeChat & Explorer fire dataChanged several times for one
        # copy (image data + file URL + text). Coalesce into a single capture.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_DEBOUNCE_MS)
        self._timer.timeout.connect(self._capture)
        self._clip.dataChanged.connect(self._on_change)
        self._connected = True

    # -- pause control (used while grab_selected_text mutates the clipboard) --
    def pause(self) -> None:
        """Fully DISCONNECT from the clipboard during a grab.

        A merely-flagged pause still leaves Qt's dataChanged listener active,
        and a listening process can hold the Windows clipboard open long enough
        that the target app's Ctrl+C (SetClipboardData) fails — which made
        synthetic-copy text capture silently return nothing. Disconnecting
        releases any clipboard hook for the duration of the grab.
        """
        self._paused = True
        try:
            self._timer.stop()
        except Exception:
            pass
        if self._connected:
            try:
                self._clip.dataChanged.disconnect(self._on_change)
            except Exception:
                pass
            self._connected = False

    def resume(self) -> None:
        # Sync last_text so the restore write doesn't get logged as new.
        try:
            self._last_text = self._clip.text() or ""
        except Exception:
            pass
        self._paused = False
        # Reconnect the listener (only if pause() actually disconnected it).
        if not self._connected:
            self._clip.dataChanged.connect(self._on_change)
            self._connected = True

    def stop(self) -> None:
        """Disconnect from the clipboard so no further history is recorded."""
        try:
            self._timer.stop()
        except Exception:
            pass
        if self._connected:
            try:
                self._clip.dataChanged.disconnect(self._on_change)
            except Exception:
                pass
            self._connected = False

    def _on_change(self) -> None:
        if self._paused:
            return
        # Restart the debounce timer; capture fires once the burst settles.
        self._timer.start()

    @staticmethod
    def _image_url_from_mime(mime):
        """Return the first local file URL that points to an image, else ''."""
        if not mime.hasUrls():
            return ""
        for url in mime.urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if Path(p).suffix.lower() in _IMAGE_EXTS:
                    return p
        return ""

    def _capture(self) -> None:
        if self._paused:
            return
        clip = self._clip
        mime = clip.mimeData()
        if mime is None:
            return

        # 1) Real bitmap image on the clipboard (screenshot, copied image data).
        #    WeChat also attaches a file URL — capture it as source_path so the
        #    image and its path live in a single entry.
        img = clip.image()
        if img is not None and not img.isNull():
            src = self._image_url_from_mime(mime)
            self._record_image(img, source_path=src)
            return

        # 2) No bitmap, but a file URL pointing at an image file (copying an
        #    image file in Explorer / OneDrive gives a file:/// URL, not pixels).
        img_path = self._image_url_from_mime(mime)
        if img_path:
            loaded = QImage(img_path)
            if not loaded.isNull():
                self._record_image(loaded, source_path=img_path)
                return

        # 3) Plain text.
        text = clip.text()
        if text and text.strip():
            if text == self._last_text:
                return  # dedup consecutive identical copies
            self._last_text = text
            self._record_text(text)

    def _record_text(self, text: str) -> None:
        preview = " ".join(text.split())[:_MAX_PREVIEW]
        category = classify_text(text)
        self._db.insert(
            "INSERT INTO clipboard_history (kind, content, preview, category) "
            "VALUES ('text', ?, ?, ?)",
            (text, preview, category),
        )
        self._trim()

    def _record_image(self, img, source_path: str = "") -> None:
        from datetime import datetime
        # Dedup: same dimensions + same source within one burst → skip.
        key = f"{img.width()}x{img.height()}|{source_path}"
        if key == self._last_image_key:
            return
        self._last_image_key = key
        self._last_text = ""  # an image copy invalidates the last-text dedup
        name = datetime.now().strftime("clip_%Y%m%d_%H%M%S_%f.png")
        path = self._image_dir / name
        if not img.save(str(path), "PNG"):
            return
        preview = "图片"
        if source_path:
            preview = f"图片 · {Path(source_path).name}"
        self._db.insert(
            "INSERT INTO clipboard_history (kind, content, preview, source_path, category) "
            "VALUES ('image', ?, ?, ?, 'image')",
            (str(path), preview, source_path),
        )
        self._trim()

    def _trim(self) -> None:
        """Keep only the most recent MAX_ENTRIES rows; delete stale image files."""
        stale = self._db.fetch_all(
            "SELECT id, kind, content FROM clipboard_history "
            "ORDER BY id DESC LIMIT -1 OFFSET ?",
            (MAX_ENTRIES,),
        )
        for row in stale:
            if row["kind"] == "image":
                try:
                    p = Path(row["content"])
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            self._db.update("DELETE FROM clipboard_history WHERE id=?", (row["id"],))
