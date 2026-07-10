"""Floating image viewer — works like other app dialogs."""

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QApplication,
)

from src.utils.theme import Theme, app_window_style, button_style

GALLERY_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "gallery"
GALLERY_DIR.mkdir(parents=True, exist_ok=True)


class ImageViewer(QDialog):
    def __init__(self, pixmap: QPixmap | None = None, from_gallery: bool = False):
        super().__init__()
        self._pixmap = pixmap
        self._scale = 1.0
        self._from_gallery = from_gallery
        self._drag_pos = None
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._do_render)

        self.setWindowTitle("图片")
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAutoFillBackground(True)
        self.setMinimumSize(150, 150)
        # Solid background — avoids gradient render flash during zoom
        self.setStyleSheet(f"""
            QDialog {{ background: {Theme.bg}; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; }}
            QScrollBar::handle:vertical {{ background: rgba(79,124,255,0.24); border-radius: 5px; min-height: 24px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba(79,124,255,0.38); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._img = QLabel()
        self._img.setAlignment(Qt.AlignCenter)
        self._img.setMinimumSize(100, 100)
        self._img.setStyleSheet("background: transparent;")
        layout.addWidget(self._img, 1)

        bar = QHBoxLayout()
        self._zoom_lbl = QLabel("100%")
        self._zoom_lbl.setStyleSheet(f"color: {Theme.muted}; font-size: 10px;")
        bar.addWidget(self._zoom_lbl)
        bar.addStretch()

        if not from_gallery:
            b = QPushButton("加入图库")
            b.setStyleSheet(button_style("success"))
            b.clicked.connect(self._save)
            bar.addWidget(b)

        b2 = QPushButton("关闭")
        b2.setStyleSheet(button_style("neutral"))
        b2.clicked.connect(self.close)
        bar.addWidget(b2)

        layout.addLayout(bar)

        if pixmap:
            self._do_render()

    def _update(self) -> None:
        """Schedule a throttled render (coalesces rapid wheel events)."""
        if not self._pixmap:
            return
        self._render_timer.start(20)

    def _do_render(self) -> None:
        """Apply scale + geometry, anchored at the current window center."""
        if not self._pixmap:
            return
        self.setUpdatesEnabled(False)
        # Snap center from the *current* window (not yet resized by this zoom)
        cx = self.x() + self.width() // 2
        cy = self.y() + self.height() // 2
        w = max(50, int(self._pixmap.width() * self._scale))
        h = max(50, int(self._pixmap.height() * self._scale))
        self._img.setPixmap(self._pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._zoom_lbl.setText(f"{int(self._scale*100)}%")
        new_w, new_h = w + 24, h + 60
        if self.isVisible():
            self.setGeometry(cx - new_w // 2, cy - new_h // 2, new_w, new_h)
        else:
            self.resize(new_w, new_h)
        self.setUpdatesEnabled(True)

    def wheelEvent(self, e) -> None:
        d = e.angleDelta().y() / 120
        self._scale = max(0.1, min(5.0, self._scale * (1.12 if d > 0 else 0.89)))
        self._update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_pos and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e) -> None:
        self._drag_pos = None

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close()

    def _save(self) -> None:
        if self._pixmap:
            self._pixmap.save(str(GALLERY_DIR / f"img_{int(time.time()*1000)}.png"), "PNG")
            self.close()


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".ico"}


def get_clipboard_image() -> QPixmap | None:
    cb = QApplication.clipboard()
    pix = cb.pixmap()
    if pix and not pix.isNull():
        return pix
    img = cb.image()
    if img and not img.isNull():
        return QPixmap.fromImage(img)
    # Copying an image *file* (Explorer / OneDrive) puts a file:/// URL on the
    # clipboard, not pixel data. Load the file if it looks like an image.
    mime = cb.mimeData()
    if mime is not None and mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile():
                p = url.toLocalFile()
                if Path(p).suffix.lower() in _IMAGE_EXTS:
                    loaded = QPixmap(p)
                    if not loaded.isNull():
                        return loaded
    return None
