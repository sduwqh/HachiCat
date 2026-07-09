"""Pet rendering widget — displays the sprite sheet frame.

References:
- DyberPet: QLabel + QPixmap for sprite rendering with frame refresh
- OpenPet: PetSprite.tsx — CSS background-position animation
- KillClawd: individual GIF files per state, CSS transform for flipping

Design:
- In sprite-sheet mode: loads a single atlas image and displays sub-rects
- In fallback mode (no sprite image): draws a cute placeholder character with QPainter
- Handles scaling via the `size` property
"""

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QMouseEvent
from PySide6.QtWidgets import QWidget


class PetWidget(QWidget):
    """Renders the current animation frame from a sprite sheet.

    If no sprite sheet is found, draws a cute placeholder character.
    """

    def __init__(
        self,
        sprite_sheet_path: Path | None = None,
        cell_width: int = 128,
        cell_height: int = 128,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._cell_width = cell_width
        self._cell_height = cell_height
        self._scale = 1.0
        self._pixmap: QPixmap | None = None
        self._current_col: int = 0
        self._current_row: int = 0
        self._use_fallback = True
        self._flip: bool = False

        if sprite_sheet_path and sprite_sheet_path.exists():
            self._pixmap = QPixmap(str(sprite_sheet_path))
            if not self._pixmap.isNull():
                self._use_fallback = False

        self.setFixedSize(
            int(cell_width * self._scale),
            int(cell_height * self._scale),
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_frame(self, col: int, row: int) -> None:
        """Set the current frame (column, row) and trigger repaint."""
        self._current_col = col
        self._current_row = row
        self.update()

    def set_scale(self, scale: float) -> None:
        """Set display scale factor.

        Lower bound accommodates large sprite sheets (e.g. 1024px HaChiCat
        scaled to ~180px display = 0.18), matching the direct-scale path
        used by switch_skin.
        """
        self._scale = max(0.05, min(3.0, scale))
        self.setFixedSize(
            int(self._cell_width * self._scale),
            int(self._cell_height * self._scale),
        )

    def swap_image(self, path: Path) -> None:
        """Swap the entire displayed pixmap to a new image file.

        Unlike set_frame (which picks a sub-rect from the existing sprite
        sheet), this replaces the whole image.  Useful for click / drag
        feedback animations.
        """
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self._pixmap = pixmap
            self._use_fallback = False
            self.update()

    def paintEvent(self, event) -> None:
        """Render the current frame or fallback character."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._use_fallback or self._pixmap is None:
            self._draw_placeholder(painter)
        else:
            self._draw_sprite_frame(painter)

        painter.end()

    def _draw_sprite_frame(self, painter: QPainter) -> None:
        """Draw the current sub-rect from the sprite sheet."""
        src_x = self._current_col * self._cell_width
        src_y = self._current_row * self._cell_height
        src_rect = QRect(src_x, src_y, self._cell_width, self._cell_height)

        target_rect = QRect(0, 0, self.width(), self.height())
        if self._flip:
            # Horizontal flip: mirror the source rect
            painter.save()
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
            target_rect = QRect(0, 0, self.width(), self.height())
        painter.drawPixmap(target_rect, self._pixmap, src_rect)
        if self._flip:
            painter.restore()

    def _draw_placeholder(self, painter: QPainter) -> None:
        """Draw a cute placeholder character — a simple round creature.

        This lets us run the pet immediately without needing sprite assets.
        The character is a round body with eyes, blush, and a small mouth.
        """
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 4

        # Body — soft orange/cream circle
        body_color = QColor(255, 200, 140)
        painter.setBrush(QBrush(body_color))
        painter.setPen(QPen(QColor(180, 130, 80), 2))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)

        # Small ears (triangles on top)
        ear_color = QColor(240, 180, 120)
        painter.setBrush(QBrush(ear_color))
        painter.setPen(QPen(QColor(180, 130, 80), 2))
        # Left ear
        painter.drawEllipse(cx - r + 10, cy - r - 8, r // 3, r // 3)
        # Right ear
        painter.drawEllipse(cx + r - 10 - r // 3, cy - r - 8, r // 3, r // 3)

        # Eyes — two dark dots
        eye_color = QColor(50, 50, 50)
        painter.setBrush(QBrush(eye_color))
        painter.setPen(Qt.NoPen)
        eye_r = max(4, r // 7)
        eye_y = cy - r // 4
        # Left eye
        painter.drawEllipse(cx - r // 3 - eye_r // 2, eye_y, eye_r, eye_r + 2)
        # Right eye
        painter.drawEllipse(cx + r // 3 - eye_r // 2, eye_y, eye_r, eye_r + 2)

        # Eye highlights
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(cx - r // 3 - eye_r // 4, eye_y + 1, eye_r // 2, eye_r // 2)
        painter.drawEllipse(cx + r // 3 + eye_r // 4, eye_y + 1, eye_r // 2, eye_r // 2)

        # Blush — two pink ovals
        blush_color = QColor(255, 160, 160, 120)
        painter.setBrush(QBrush(blush_color))
        painter.setPen(Qt.NoPen)
        blush_y = cy + r // 6
        blush_rx, blush_ry = r // 5, r // 7
        painter.drawEllipse(cx - r // 2, blush_y, blush_rx, blush_ry)
        painter.drawEllipse(cx + r // 2 - blush_rx, blush_y, blush_rx, blush_ry)

        # Mouth — small arc (smile)
        mouth_pen = QPen(QColor(120, 80, 60), 2)
        painter.setPen(mouth_pen)
        painter.setBrush(Qt.NoBrush)
        mouth_y = cy + r // 4
        mouth_w = r // 3
        painter.drawArc(cx - mouth_w // 2, mouth_y - 2, mouth_w, r // 4, 0, -180 * 16)
