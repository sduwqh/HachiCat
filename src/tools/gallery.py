"""Gallery browser."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from src.utils.theme import Theme
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QApplication,
)

GALLERY_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "gallery"
GALLERY_DIR.mkdir(parents=True, exist_ok=True)
THUMB = 140


class GalleryBrowser(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._viewers = []
        self.setWindowTitle("图库")
        self.setMinimumSize(660, 400)
        self.setWindowFlags(Qt.Tool)
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #dfe4ec,
                    stop: 1 #eaedf4
                );
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 0 2px 0; }}
            QScrollBar::handle:vertical {{ background: rgba(79,124,255,0.24); border-radius: 5px; min-height: 24px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba(79,124,255,0.38); }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        title = QLabel("图库")
        title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {Theme.text};")
        layout.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._grid = QWidget()
        self._grid.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._scroll.setWidget(self._grid)
        layout.addWidget(self._scroll, 1)

        self._cols = 4
        self._render()

    def _render(self):
        lay = self._grid_layout
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        imgs = sorted(GALLERY_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not imgs:
            e = QLabel("图库为空")
            e.setAlignment(Qt.AlignCenter)
            e.setStyleSheet(f"color: {Theme.muted}; padding: 40px;")
            lay.addWidget(e, 0, 0)
            return

        self._cols = max(1, self.width() // (THUMB + 20))
        for i, p in enumerate(imgs):
            lay.addWidget(self._card(p), i // self._cols, i % self._cols)

    def _card(self, path: Path) -> QWidget:
        from PySide6.QtGui import QFont, QCursor

        pix = QPixmap(str(path))
        thumb = pix.scaled(THUMB, THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        card = QWidget()
        card.setFixedSize(THUMB + 16, THUMB + 44)
        card.setStyleSheet(
            f"background: #fefaf5; border: 1px solid rgba(180,140,100,0.20); border-radius: 14px;"
        )

        vl = QVBoxLayout(card)
        vl.setContentsMargins(8, 6, 8, 4)
        vl.setSpacing(4)

        img = QLabel()
        img.setPixmap(thumb)
        img.setAlignment(Qt.AlignCenter)
        img.setStyleSheet("background: transparent;")
        vl.addWidget(img)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        bar.addStretch()

        btn_font = QFont()
        btn_font.setPointSize(10)
        btn_font.setBold(True)

        def _icon_btn(icon, tooltip, normal_css, hover_css, on_click):
            lbl = QLabel(icon)
            lbl.setFont(btn_font)
            lbl.setFixedSize(28, 28)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setCursor(QCursor(Qt.PointingHandCursor))
            lbl.setToolTip(tooltip)
            lbl.setStyleSheet(normal_css)
            lbl._hover_css = hover_css
            lbl._normal_css = normal_css
            lbl._clicked = on_click
            lbl.enterEvent = lambda e, l=lbl: l.setStyleSheet(l._hover_css)
            lbl.leaveEvent = lambda e, l=lbl: l.setStyleSheet(l._normal_css)
            lbl.mousePressEvent = lambda e, l=lbl: l._clicked()
            return lbl

        vb = _icon_btn(
            "🔍", "查看",
            "QLabel { color: #1e293b; background: rgba(79,124,255,0.10); border: 1px solid rgba(79,124,255,0.22); border-radius: 14px; }",
            "QLabel { color: #4f7cff; background: rgba(79,124,255,0.24); border: 1px solid rgba(79,124,255,0.50); border-radius: 14px; }",
            lambda p=path: self._view(p),
        )
        bar.addWidget(vb)

        cb = _icon_btn(
            "📋", "复制",
            "QLabel { color: #1e293b; background: rgba(93,139,100,0.10); border: 1px solid rgba(93,139,100,0.22); border-radius: 14px; }",
            "QLabel { color: #3d6b44; background: rgba(93,139,100,0.24); border: 1px solid rgba(93,139,100,0.50); border-radius: 14px; }",
            lambda p=path, l=None: self._copy(p, l),
        )
        # Fixup lambda to capture the label reference
        cb._clicked = lambda lbl=cb, p=path: self._copy(p, lbl)
        bar.addWidget(cb)

        db = _icon_btn(
            "🗑", "删除",
            "QLabel { color: #1e293b; background: rgba(194,102,102,0.10); border: 1px solid rgba(194,102,102,0.22); border-radius: 14px; }",
            "QLabel { color: #c26666; background: rgba(194,102,102,0.24); border: 1px solid rgba(194,102,102,0.50); border-radius: 14px; }",
            lambda p=path: self._delete(p),
        )
        bar.addWidget(db)

        vl.addLayout(bar)
        return card

    def _view(self, path):
        from src.tools.image_viewer import ImageViewer
        v = ImageViewer(QPixmap(str(path)), from_gallery=True)
        self._viewers.append(v)
        v.destroyed.connect(lambda _=None, viewer=v: self._forget_viewer(viewer))
        v.show()
        v.raise_()
        v.activateWindow()

    def _forget_viewer(self, viewer):
        try:
            self._viewers.remove(viewer)
        except ValueError:
            pass

    def _copy(self, path, btn):
        QApplication.clipboard().setPixmap(QPixmap(str(path)))
        btn.setText("✓")
        QTimer.singleShot(800, lambda: btn.setText("📋"))

    def _delete(self, path):
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        self._render()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        nc = max(1, self.width() // (THUMB + 20))
        if nc != self._cols:
            self._render()
