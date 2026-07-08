"""Shared UI theme tokens and stylesheet helpers.

Keep the app visually consistent without changing layout or behavior.
"""

from __future__ import annotations


class Theme:
    """Small design token set for the desktop UI."""

    bg = "#eef2f7"
    bg_alt = "#f7f9fc"
    surface = "rgba(255, 255, 255, 0.88)"
    surface_soft = "rgba(255, 255, 255, 0.76)"
    surface_strong = "rgba(255, 255, 255, 0.96)"
    text = "#1f2937"
    muted = "#475569"
    border = "rgba(31, 41, 55, 0.14)"
    border_strong = "rgba(31, 41, 55, 0.20)"
    accent = "#4f7cff"
    accent_hover = "#3f66d1"
    accent_soft = "rgba(79, 124, 255, 0.14)"
    success = "#5d8b64"
    warning = "#c28b28"
    danger = "#c26666"
    shadow = "rgba(17, 24, 39, 0.12)"


def app_window_style() -> str:
    """Standard light window styling for dialogs and panels."""
    return f"""
        QWidget {{
            color: {Theme.text};
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        }}
        QDialog {{
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 {Theme.bg},
                stop: 1 {Theme.bg_alt}
            );
        }}
        QLabel {{
            color: {Theme.text};
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px 0 2px 0;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(79, 124, 255, 0.24);
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(79, 124, 255, 0.38);
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """


def group_box_style() -> str:
    return f"""
        QGroupBox {{
            color: {Theme.text};
            font-weight: 600;
            border: 1px solid {Theme.border};
            border-radius: 14px;
            margin-top: 14px;
            padding-top: 18px;
            background: {Theme.surface_soft};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
        }}
    """


def form_field_style() -> str:
    return f"""
        QLineEdit, QComboBox, QSpinBox {{
            background: {Theme.surface_strong};
            color: {Theme.text};
            border: 1px solid {Theme.border};
            border-radius: 8px;
            padding: 6px 10px;
            selection-background-color: {Theme.accent_soft};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border-color: {Theme.accent};
        }}
        QComboBox QAbstractItemView {{
            background: {Theme.surface_strong};
            color: {Theme.text};
            selection-background-color: {Theme.accent_soft};
            selection-color: {Theme.text};
            border: 1px solid {Theme.border};
            outline: 0;
        }}
        QCheckBox {{
            color: {Theme.text};
            spacing: 8px;
        }}
        QSlider {{
            color: {Theme.text};
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 0;
            border: none;
            background: transparent;
        }}
    """


def button_style(kind: str = "neutral") -> str:
    """Return a common button style."""
    palette = {
        "primary": (Theme.accent, Theme.accent_hover, "#ffffff"),
        "success": (Theme.success, "#4f7a57", "#ffffff"),
        "warning": (Theme.warning, "#af7a22", "#ffffff"),
        "danger": (Theme.danger, "#ad5252", "#ffffff"),
        "neutral": ("rgba(255, 255, 255, 0.92)", "rgba(255, 255, 255, 1.0)", Theme.text),
    }
    bg, hover, text = palette.get(kind, palette["neutral"])
    border = Theme.border if kind == "neutral" else "transparent"
    return f"""
        QPushButton {{
            background: {bg};
            color: {text};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            background: {hover};
        }}
        QPushButton:pressed {{
            background: {hover};
        }}
    """


def chip_button_style(color: str = Theme.accent) -> str:
    return f"""
        QPushButton {{
            color: {Theme.text};
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid {Theme.border};
            border-radius: 7px;
            padding: 6px 12px;
        }}
        QPushButton:hover {{
            background: {color}14;
            border-color: {color}40;
            color: {color};
        }}
    """


def panel_style(object_name: str = "") -> str:
    prefix = f"QWidget#{object_name}" if object_name else "QWidget"
    return f"""
        {prefix} {{
            background: {Theme.surface};
            border: 1px solid {Theme.border};
            border-radius: 14px;
        }}
    """
