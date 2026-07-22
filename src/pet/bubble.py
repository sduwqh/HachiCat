"""Floating speech/notification bubble above the pet.

References:
- DyberPet: bubbleManager.py — random/conditional/interaction bubbles with auto-dismiss
- KillClawd: thought bubbles in DOM, absolute-positioned above clawd
- Clawd on Desk: permission bubbles with Confirm/Deny buttons

Design:
- Separate frameless QWidget positioned above the pet window
- Fade animation (opacity + translateY) via QPropertyAnimation
- Types: INFO (green), WARNING (yellow), ERROR (red), ACTION (with buttons)
- Auto-dismiss after configurable TTL
"""

from enum import Enum, auto

from PySide6.QtCore import (
    Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, Signal, QEvent
)
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsOpacityEffect, QTextBrowser,
)

from src.utils.theme import Theme


class BubbleType(Enum):
    """Bubble visual style and behavior."""
    INFO = auto()        # Warm tint, auto-dismiss
    WARNING = auto()     # Amber tint, auto-dismiss
    ERROR = auto()       # Red tint, auto-dismiss
    ACTION = auto()      # Warm tint, requires button click to dismiss
    TRANSLATION = auto() # Warm tint, no auto-dismiss, click to close
    CHAT = auto()        # Pure white, short TTL, pops up close to pet
    REMINDER = auto()    # Warm coral tint, no auto-dismiss, click to close


DURATIONS: dict[BubbleType, int] = {
    BubbleType.INFO: 2000,
    BubbleType.WARNING: 3000,
    BubbleType.ERROR: 3500,
    BubbleType.ACTION: 0,        # No auto-dismiss
    BubbleType.TRANSLATION: 0,   # No auto-dismiss, user clicks to close
    BubbleType.CHAT: 800,        # Quick "bark" bubble
    BubbleType.REMINDER: 0,      # No auto-dismiss — user clicks to close
}

COLORS: dict[BubbleType, tuple[QColor, QColor]] = {
    # (background, border) — warm coral-pink theme to match the app
    BubbleType.INFO: (QColor(255, 247, 242, 248), QColor(255, 122, 89)),
    BubbleType.WARNING: (QColor(255, 249, 230, 248), QColor(194, 139, 40)),
    BubbleType.ERROR: (QColor(255, 240, 240, 248), QColor(194, 102, 102)),
    BubbleType.ACTION: (QColor(255, 247, 242, 250), QColor(255, 122, 89)),
    BubbleType.TRANSLATION: (QColor(255, 247, 242, 248), QColor(255, 122, 89)),
    BubbleType.CHAT: (QColor(255, 255, 255, 250), QColor(255, 158, 181)),
    BubbleType.REMINDER: (QColor(255, 245, 238, 250), QColor(255, 122, 89)),
}


class BubbleWidget(QWidget):
    """A single floating bubble notification positioned above the pet."""

    dismissed = Signal()  # Emitted when bubble auto-dismisses or is clicked away
    action_confirmed = Signal()  # Emitted when user clicks Confirm (ACTION type)
    action_cancelled = Signal()  # Emitted when user clicks Cancel (ACTION type)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._bubble_type: BubbleType = BubbleType.INFO
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(8)

        # Plain-text / simple rich-text label (INFO, WARNING, ERROR, ACTION)
        self._label = QLabel()
        self._label.setFont(QFont("Microsoft YaHei", 10))
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(220)
        self._label.setStyleSheet(f"color: {Theme.text}; background: transparent;")
        self._layout.addWidget(self._label)

        # Full HTML renderer for translation / dictionary content
        self._html = QTextBrowser()
        self._html.setFont(QFont("Microsoft YaHei", 10))
        self._html.setMinimumWidth(280)
        self._html.setMaximumWidth(340)
        self._html.setMaximumHeight(420)
        self._html.setFrameShape(QTextBrowser.NoFrame)
        self._html.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._html.setOpenExternalLinks(True)
        self._html.document().setDocumentMargin(2)
        self._html.document().setDefaultStyleSheet(
            "ul, ol { margin: 1px 0; padding-left: 16px; }"
            "li { margin: 0; padding: 0; line-height: 1.35; }"
        )
        self._html.setStyleSheet(
            f"color: {Theme.text}; background: transparent; border: none; padding: 0px;"
        )
        self._html.hide()
        self._html.installEventFilter(self)
        self._html.viewport().installEventFilter(self)
        self._layout.addWidget(self._html)

        # Action buttons (only shown for ACTION type)
        self._button_row = QHBoxLayout()
        self._button_row.setSpacing(8)

        self._confirm_btn = QPushButton("确认")
        self._confirm_btn.setFixedHeight(28)
        self._confirm_btn.setStyleSheet("""
            QPushButton {
                background: #4f7cff; color: white; border: none;
                border-radius: 8px; padding: 0 16px;
            }
            QPushButton:hover { background: #3f66d1; }
        """)
        self._confirm_btn.clicked.connect(self._on_confirm)

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setFixedHeight(28)
        self._cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.88); color: #4b5563; border: 1px solid rgba(31,41,55,0.10);
                border-radius: 8px; padding: 0 16px;
            }
            QPushButton:hover { background: rgba(79,124,255,0.10); }
        """)
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._button_row.addStretch()
        self._button_row.addWidget(self._cancel_btn)
        self._button_row.addWidget(self._confirm_btn)
        self._layout.addLayout(self._button_row)

        self._confirm_btn.hide()
        self._cancel_btn.hide()

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._animate_out)

        self.hide()

    def show_message(
        self,
        text: str,
        bubble_type: BubbleType = BubbleType.INFO,
        anchor_point: QPoint | None = None,
    ) -> None:
        """Show a bubble message at the given screen position."""
        self._bubble_type = bubble_type

        # Translation bubbles use the full HTML renderer with tighter margins
        if bubble_type == BubbleType.TRANSLATION:
            self._label.hide()
            self._layout.setContentsMargins(8, 4, 8, 4)
            self._html.show()
            self._html.setHtml(text)
        elif bubble_type == BubbleType.CHAT:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._html.hide()
            self._layout.setContentsMargins(18, 10, 18, 10)
            self._label.setFont(QFont("Microsoft YaHei", 14))
            self._label.setTextFormat(Qt.PlainText)
            self._label.setWordWrap(False)
            self._label.setMaximumWidth(16777215)
            self._label.setAlignment(Qt.AlignCenter)
            self._label.show()
            self._label.setText(text)
            self._label.adjustSize()
            self.setFixedSize(self._label.width() + 38,
                              self._label.height() + 22)
        elif bubble_type == BubbleType.REMINDER:
            # Reminder: warm text bubble, no auto-dismiss, click to close.
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._layout.setContentsMargins(16, 12, 16, 12)
            self._html.hide()
            self._label.show()
            self._label.setTextFormat(Qt.RichText)
            self._label.setFont(QFont("Microsoft YaHei", 11))
            self._label.setWordWrap(True)
            self._label.setMaximumWidth(260)
            self._label.setAlignment(Qt.AlignLeft)
            self._label.setStyleSheet(
                f"color: {Theme.text}; background: transparent;")
            self._label.setText(
                f"<div style='line-height:1.5;'>🐱 {text}"
                f"<div style='color:#b9856f; font-size:10px; margin-top:6px;'>"
                f"点击关闭</div></div>"
            )
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._layout.setContentsMargins(14, 10, 14, 10)
            self._label.setMaximumWidth(220)
            self._html.hide()
            self._label.show()
            self._label.setText(text)

        # Show/hide action buttons
        if bubble_type == BubbleType.ACTION:
            self._confirm_btn.show()
            self._cancel_btn.show()
        else:
            self._confirm_btn.hide()
            self._cancel_btn.hide()

        # Size to content (CHAT is sized above via label dimensions)
        if bubble_type != BubbleType.CHAT:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.adjustSize()

        # Position above anchor (CHAT type sits closer)
        if anchor_point is not None:
            x = anchor_point.x() - self.width() // 2
            y = anchor_point.y() - self.height() - (2 if bubble_type == BubbleType.CHAT else 10)
            self.move(max(0, x), max(0, y))

        # Animate in (CHAT: slow float with bounce)
        if bubble_type == BubbleType.CHAT:
            self._animate_in(rise_px=200, duration=2500)
        else:
            self._animate_in()

        # Auto-dismiss
        ttl = DURATIONS.get(bubble_type, 2000)
        if ttl > 0:
            self._dismiss_timer.start(ttl)

    def _animate_in(self, rise_px: int = 8, duration: int = 200) -> None:
        """Fade-in + upward float from below."""
        self._opacity_effect.setOpacity(0.0)
        current_y = self.y()
        self.move(self.x(), current_y + rise_px)

        self.show()
        self.raise_()

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(duration)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

        self._slide_anim = QPropertyAnimation(self, b"pos")
        self._slide_anim.setDuration(duration)
        self._slide_anim.setStartValue(QPoint(self.x(), current_y + rise_px))
        self._slide_anim.setEndValue(QPoint(self.x(), current_y))
        self._slide_anim.setEasingCurve(QEasingCurve.OutBack)
        self._slide_anim.start()

    def _animate_out(self) -> None:
        """Fade-out + slight upward float."""
        current_y = self.y()

        fade = QPropertyAnimation(self._opacity_effect, b"opacity")
        fade.setDuration(300)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.InCubic)

        slide = QPropertyAnimation(self, b"pos")
        slide.setDuration(300)
        slide.setStartValue(QPoint(self.x(), current_y))
        slide.setEndValue(QPoint(self.x(), current_y - 12))
        slide.setEasingCurve(QEasingCurve.InCubic)

        fade.start()
        slide.start()

        # Hide after animation completes
        QTimer.singleShot(310, self._on_dismissed)

    def _on_dismissed(self) -> None:
        """Clean up after dismiss animation."""
        self.hide()
        self.dismissed.emit()

    def _on_confirm(self) -> None:
        self.action_confirmed.emit()
        self._animate_out()

    def _on_cancel(self) -> None:
        self.action_cancelled.emit()
        self._animate_out()

    def dismiss_now(self) -> None:
        """Dismiss immediately without animation."""
        self._dismiss_timer.stop()
        self.hide()
        self.dismissed.emit()

    # --- Custom paint for rounded bubble ---

    def paintEvent(self, event) -> None:
        """Draw rounded rectangle with type-specific color."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg, border = COLORS.get(self._bubble_type, COLORS[BubbleType.INFO])

        # Background — rounded card matching the app's 16px radius, with a
        # soft translucent outer halo instead of a hard 1px line.
        halo = QColor(border)
        halo.setAlpha(40)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(halo, 3))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 15, 15)

        # Small tail/triangle pointing downward
        if self._bubble_type != BubbleType.ACTION:
            # Simple small triangle at bottom center
            tail_color = bg
            painter.setBrush(QBrush(tail_color))
            painter.setPen(QPen(border, 1))

            cx = self.width() // 2
            tail_y = self.height() - 1
            tail_w = 6

            # Draw triangle pointing down
            from PySide6.QtGui import QPolygon
            triangle = QPolygon([
                QPoint(cx - tail_w, tail_y),
                QPoint(cx + tail_w, tail_y),
                QPoint(cx, tail_y + 6),
            ])
            painter.drawPolygon(triangle)

        painter.end()

    def eventFilter(self, obj, event) -> bool:
        """Forward clicks on the HTML browser (or its viewport) to dismiss."""
        if event.type() == QEvent.MouseButtonPress:
            if obj in (self._html, self._html.viewport()):
                if self._bubble_type != BubbleType.ACTION:
                    self._animate_out()
                    return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Click on bubble dismisses it (CHAT and ACTION types excluded)."""
        if self._bubble_type in (BubbleType.ACTION, BubbleType.CHAT):
            super().mousePressEvent(event)
            return
        self._animate_out()
        super().mousePressEvent(event)
