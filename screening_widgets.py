"""
Custom widgets for the screening module.
"""

from PySide6.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QDialog, QScrollArea, QStyle
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtCore import Qt, QSize, QEvent


# ── Pen annotation colour palette ─────────────────────────────────────────────
_PEN_COLORS = [
    ("#c81e1e", "Red"),
    ("#fde910", "Yellow"),
    ("#ffffff", "White"),
]


class DrawableZoomLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = QPixmap()
        self.zoom_factor = 1.0
        self.draw_enabled = False
        self.pen_color = QColor("#c81e1e")
        self.strokes = []
        self.current_stroke = []
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_base_pixmap(self, pixmap):
        self.base_pixmap = pixmap
        self.strokes = []
        self.current_stroke = []
        self._update_display()

    def set_zoom_factor(self, factor):
        self.zoom_factor = factor
        self._update_display()

    def set_draw_enabled(self, enabled):
        self.draw_enabled = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)

    def set_pen_color(self, color: QColor):
        self.pen_color = color

    def clear_drawings(self):
        self.strokes = []
        self.current_stroke = []
        self._update_display()

    def _map_to_image_point(self, position):
        if self.base_pixmap.isNull():
            return (0.0, 0.0)

        max_x = max(0.0, float(self.base_pixmap.width() - 1))
        max_y = max(0.0, float(self.base_pixmap.height() - 1))
        point_x = min(max(position.x() / self.zoom_factor, 0.0), max_x)
        point_y = min(max(position.y() / self.zoom_factor, 0.0), max_y)
        return (point_x, point_y)

    def _update_display(self):
        if self.base_pixmap.isNull():
            self.setPixmap(QPixmap())
            return

        canvas = self.base_pixmap.scaled(
            max(1, int(self.base_pixmap.width() * self.zoom_factor)),
            max(1, int(self.base_pixmap.height() * self.zoom_factor)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.pen_color, max(2, int(2 * self.zoom_factor)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        for stroke in self.strokes + ([self.current_stroke] if self.current_stroke else []):
            for index in range(1, len(stroke)):
                start_x, start_y = stroke[index - 1]
                end_x, end_y = stroke[index]
                painter.drawLine(
                    int(start_x * self.zoom_factor),
                    int(start_y * self.zoom_factor),
                    int(end_x * self.zoom_factor),
                    int(end_y * self.zoom_factor),
                )

        painter.end()
        self.setPixmap(canvas)
        self.resize(canvas.size())

    def mousePressEvent(self, event):
        if self.draw_enabled and event.button() == Qt.MouseButton.LeftButton and not self.base_pixmap.isNull():
            self.current_stroke = [self._map_to_image_point(event.position())]
            self._update_display()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.draw_enabled and event.buttons() & Qt.MouseButton.LeftButton and self.current_stroke:
            self.current_stroke.append(self._map_to_image_point(event.position()))
            self._update_display()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.draw_enabled and event.button() == Qt.MouseButton.LeftButton and self.current_stroke:
            self.current_stroke.append(self._map_to_image_point(event.position()))
            self.strokes.append(self.current_stroke)
            self.current_stroke = []
            self._update_display()
            return
        super().mouseReleaseEvent(event)


class ImageZoomDialog(QDialog):
    ZOOM_STEP = 1.2

    def __init__(self, pixmap, title, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self.zoom_factor = 1.0

        self.setWindowTitle(title)
        self.resize(1100, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        toolbar_grid = QGridLayout()
        toolbar_grid.setHorizontalSpacing(12)
        toolbar_grid.setVerticalSpacing(6)

        tools_label = QLabel("Tools")
        tools_label.setStyleSheet("font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;")
        toolbar_grid.addWidget(tools_label, 0, 0)

        colors_label = QLabel("Colors")
        colors_label.setStyleSheet("font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;")
        toolbar_grid.addWidget(colors_label, 0, 1)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)
        magnify_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)

        zoom_in_btn = QPushButton("Zoom +")
        zoom_in_btn.setIcon(magnify_icon)
        zoom_in_btn.setIconSize(QSize(16, 16))
        zoom_in_btn.setToolTip("Magnifying zoom in")
        zoom_in_btn.setMinimumHeight(34)
        zoom_in_btn.clicked.connect(self.zoom_in)
        tools_row.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("Zoom -")
        zoom_out_btn.setIcon(magnify_icon)
        zoom_out_btn.setIconSize(QSize(16, 16))
        zoom_out_btn.setToolTip("Magnifying zoom out")
        zoom_out_btn.setMinimumHeight(34)
        zoom_out_btn.clicked.connect(self.zoom_out)
        tools_row.addWidget(zoom_out_btn)
        tools_row.addStretch(1)
        toolbar_grid.addLayout(tools_row, 1, 0)

        colors_row = QHBoxLayout()
        colors_row.setSpacing(8)
        self._swatches = []
        for _hex, _name in _PEN_COLORS:
            _sw = QPushButton()
            _sw.setFixedSize(24, 24)
            _sw.setToolTip(_name)
            _border = "3px solid #0d6efd" if _hex == _PEN_COLORS[0][0] else "2px solid #adb5bd"
            _sw.setStyleSheet(f"background:{_hex};border-radius:12px;border:{_border};")
            _sw.clicked.connect(lambda checked=False, h=_hex: self._set_pen_color(h))
            colors_row.addWidget(_sw)
            self._swatches.append((_sw, _hex))
        clear_draw_btn = QPushButton("Clear")
        clear_draw_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        clear_draw_btn.setIconSize(QSize(16, 16))
        clear_draw_btn.setToolTip("Clear drawings")
        clear_draw_btn.setMinimumHeight(34)
        clear_draw_btn.clicked.connect(self.clear_drawings)
        colors_row.addWidget(clear_draw_btn)
        colors_row.addStretch(1)
        toolbar_grid.addLayout(colors_row, 1, 1)

        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(34)
        close_btn.clicked.connect(self.accept)
        toolbar_grid.addWidget(close_btn, 1, 2)

        toolbar_grid.setColumnStretch(0, 3)
        toolbar_grid.setColumnStretch(1, 3)
        toolbar_grid.setColumnStretch(2, 1)

        layout.addLayout(toolbar_grid)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.scroll_area, 1)

        self.image_label = DrawableZoomLabel()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.viewport().installEventFilter(self)
        self.image_label.installEventFilter(self)
        self.image_label.set_base_pixmap(self.original_pixmap)

        self._update_preview()

    def eventFilter(self, watched, event):
        if watched in (self.scroll_area.viewport(), self.image_label) and event.type() == QEvent.Type.Wheel:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            elif event.angleDelta().y() < 0:
                self.zoom_out()
            return True
        return super().eventFilter(watched, event)

    def _update_preview(self):
        if self.original_pixmap.isNull():
            self.image_label.setPixmap(QPixmap())
            return
        self.image_label.set_zoom_factor(self.zoom_factor)

    def zoom_in(self):
        self.zoom_factor = min(5.0, self.zoom_factor * self.ZOOM_STEP)
        self._update_preview()

    def zoom_out(self):
        self.zoom_factor = max(0.2, self.zoom_factor / self.ZOOM_STEP)
        self._update_preview()

    def reset_zoom(self):
        self.zoom_factor = 1.0
        self._update_preview()

    def toggle_draw_mode(self, enabled):
        self.image_label.set_draw_enabled(enabled)

    def clear_drawings(self):
        self.image_label.clear_drawings()

    def _set_pen_color(self, hex_color: str):
        self.image_label.set_pen_color(QColor(hex_color))
        for sw, h in self._swatches:
            border = "3px solid #0d6efd" if h == hex_color else "2px solid #adb5bd"
            sw.setStyleSheet(f"background:{h};border-radius:12px;border:{border};")
        # Clicking a color automatically activates draw mode.
        self.image_label.set_draw_enabled(True)


class ClickableImageLabel(QLabel):
    def __init__(self, empty_text="", viewer_title="Image Viewer", parent=None):
        super().__init__(empty_text, parent)
        self.viewer_title = viewer_title
        self.full_pixmap = QPixmap()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.open_badge = QLabel(self)
        self.open_badge.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon).pixmap(16, 16))
        self.open_badge.setFixedSize(28, 28)
        self.open_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.open_badge.setStyleSheet(
            "background: rgba(255, 255, 255, 0.92);"
            "border-radius: 14px;"
            "border: 1px solid #b8c9dd;"
        )
        self.open_badge.hide()

    def set_viewable_pixmap(self, pixmap, max_width, max_height):
        self.full_pixmap = pixmap
        scaled = pixmap.scaled(
            max_width,
            max_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setText("")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to open and zoom")
        self.open_badge.show()
        self.open_badge.raise_()
        self._position_badge()

    def clear_view(self, text):
        self.full_pixmap = QPixmap()
        self.setPixmap(QPixmap())
        self.setText(text)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip("")
        self.open_badge.hide()

    def resizeEvent(self, event):
        self._position_badge()
        super().resizeEvent(event)

    def _position_badge(self):
        self.open_badge.move(
            max(8, self.width() - self.open_badge.width() - 10),
            max(8, self.height() - self.open_badge.height() - 10),
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.full_pixmap.isNull():
            dialog = ImageZoomDialog(self.full_pixmap, self.viewer_title, self)
            dialog.exec()
            return
        super().mousePressEvent(event)
