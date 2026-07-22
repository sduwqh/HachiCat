"""Lightweight transient toast — a small centered pill that fades out.

Used for quick feedback like "已复制". Self-contained: create and call
show_toast(parent, text); it positions itself over the parent, shows briefly,
then deletes itself.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QLabel, QGraphicsOpacityEffect

from src.utils.theme import Theme


def show_toast(parent, text: str = "已复制", msec: int = 1000) -> None:
    """Show a small '已复制' style pill centered over `parent`, then fade out."""
    toast = QLabel(parent)
    toast.setText(f"✓  {text}")
    toast.setAlignment(Qt.AlignCenter)
    # NOTE: the whole string is an f-string, so CSS braces must be doubled.
    toast.setStyleSheet(
        f"QLabel {{ background: {Theme.success}; color: #ffffff;"
        f" font-size: 12px; font-weight: 600; padding: 8px 18px;"
        f" border-radius: 14px; }}"
    )
    toast.adjustSize()
    # Center over parent
    pw, ph = parent.width(), parent.height()
    tw, th = toast.width(), toast.height()
    toast.move((pw - tw) // 2, int(ph * 0.5 - th / 2))
    toast.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    toast.show()
    toast.raise_()

    eff = QGraphicsOpacityEffect(toast)
    toast.setGraphicsEffect(eff)
    eff.setOpacity(1.0)

    def _fade():
        # The parent panel (and thus toast + effect) may have been closed
        # before this timer fires — guard against dead C++ objects.
        if not shiboken6.isValid(toast) or not shiboken6.isValid(eff):
            return
        anim = QPropertyAnimation(eff, b"opacity", toast)
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.finished.connect(toast.deleteLater)
        anim.start()
        toast._anim = anim  # keep ref

    QTimer.singleShot(msec, _fade)
