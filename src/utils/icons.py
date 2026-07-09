"""Vector icon loader — renders Lucide SVG icons tinted to any color.

Lucide icons (ISC license) use stroke="currentColor", so we substitute
the color at load time and rasterize to a QPixmap. Results are cached
per (name, color, size) so repeated use is cheap.

Usage:
    from src.utils.icons import icon_pixmap, icon
    lbl.setPixmap(icon_pixmap("search", "#ff7a59", 18))
    btn.setIcon(icon("trash", "#c26666", 16))
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from PySide6.QtCore import Qt, QByteArray, QSize
from PySide6.QtGui import QPixmap, QPainter, QIcon
from PySide6.QtSvg import QSvgRenderer

_ICON_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"


@lru_cache(maxsize=256)
def _render(name: str, color: str, size: int, ratio_x100: int) -> QPixmap:
    """Render a tinted SVG icon to a pixmap (cached)."""
    path = _ICON_DIR / f"{name}.svg"
    if not path.exists():
        # Fallback: empty transparent pixmap so callers never crash
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm

    svg_text = path.read_text(encoding="utf-8")
    # Lucide uses currentColor for strokes; also handle explicit stroke attr
    svg_text = svg_text.replace("currentColor", color)

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    ratio = ratio_x100 / 100.0
    px = int(size * ratio)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon_pixmap(name: str, color: str = "#1f2937", size: int = 18) -> QPixmap:
    """Return a tinted icon as a QPixmap at the given logical size.

    Renders at 2x for crisp display on HiDPI screens.
    """
    return _render(name, color, size, 200)


def icon(name: str, color: str = "#1f2937", size: int = 18) -> QIcon:
    """Return a tinted icon as a QIcon (for QPushButton.setIcon)."""
    ic = QIcon()
    ic.addPixmap(icon_pixmap(name, color, size))
    return ic
