"""
Screening module for EyeShield EMR application.
Handles patient screening functionality and image analysis with fixed UI styling.
"""


from datetime import datetime
import secrets
import sqlite3
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout, QHBoxLayout,
    QFileDialog, QFormLayout, QGroupBox, QComboBox, QDateEdit, QMessageBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QTextEdit, QCalendarWidget, QStackedWidget,
    QGridLayout, QFrame, QStyle, QDialog, QScrollArea
)
from PySide6.QtGui import QPixmap, QFont, QRegularExpressionValidator, QPainter, QPen, QColor
from PySide6.QtCore import Qt, QDate, QRegularExpression, QSize, QEvent
from auth import DB_FILE


class DrawableZoomLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = QPixmap()
        self.zoom_factor = 1.0
        self.draw_enabled = False
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
        pen = QPen(QColor("#c81e1e"), max(2, int(2 * self.zoom_factor)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
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

        controls = QHBoxLayout()
        controls.setSpacing(8)

        zoom_in_btn = QPushButton()
        zoom_in_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        zoom_in_btn.setIconSize(QSize(18, 18))
        zoom_in_btn.setToolTip("Zoom in")
        zoom_in_btn.setFixedSize(38, 38)
        zoom_in_btn.clicked.connect(self.zoom_in)
        controls.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton()
        zoom_out_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        zoom_out_btn.setIconSize(QSize(18, 18))
        zoom_out_btn.setToolTip("Zoom out")
        zoom_out_btn.setFixedSize(38, 38)
        zoom_out_btn.clicked.connect(self.zoom_out)
        controls.addWidget(zoom_out_btn)

        reset_btn = QPushButton()
        reset_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        reset_btn.setIconSize(QSize(18, 18))
        reset_btn.setToolTip("Reset zoom")
        reset_btn.setFixedSize(38, 38)
        reset_btn.clicked.connect(self.reset_zoom)
        controls.addWidget(reset_btn)

        draw_btn = QPushButton("✎")
        draw_btn.setCheckable(True)
        draw_btn.setToolTip("Draw annotations")
        draw_btn.setFixedSize(38, 38)
        draw_btn.toggled.connect(self.toggle_draw_mode)
        controls.addWidget(draw_btn)

        clear_draw_btn = QPushButton()
        clear_draw_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        clear_draw_btn.setIconSize(QSize(18, 18))
        clear_draw_btn.setToolTip("Clear drawings")
        clear_draw_btn.setFixedSize(38, 38)
        clear_draw_btn.clicked.connect(self.clear_drawings)
        controls.addWidget(clear_draw_btn)

        controls.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        controls.addWidget(close_btn)

        layout.addLayout(controls)

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
        self.open_badge.setStyleSheet("background: rgba(13, 110, 253, 0.92); border-radius: 14px; border: 1px solid rgba(255, 255, 255, 0.65);")
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


class ScreeningPage(QWidget):
    """Patient screening page for DR detection with two-step workflow"""

    def __init__(self):
        super().__init__()
        self.current_image = None
        self.patient_counter = 0
        self.min_dob_date = QDate(1900, 1, 1)
        self.max_dob_date = QDate.currentDate()
        self.last_result_class = "Pending"
        self.last_result_conf = "Pending"
        self._current_eye_saved = False
        self._first_eye_result = None
        self.stacked_widget = QStackedWidget()
        self.init_ui()

    def init_ui(self):
        """Initialize the revised UI: patient info and image upload in one window, results in new window"""
        self._apply_ui_polish()
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)
        # Unified page: Patient Info + Image Upload
        unified_page = self.create_unified_page()
        self.results_page = ResultsWindow(self)
        self.stacked_widget.addWidget(unified_page)
        self.stacked_widget.addWidget(self.results_page)
        main_layout.addWidget(self.stacked_widget)
        self._setup_validators()

    def _apply_ui_polish(self):
        self.setStyleSheet("""
            QWidget {
                background: #f8f9fa;
                color: #212529;
                font-size: 13px;
                font-family: "Calibri", "Inter", "Arial";
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin-top: 8px;
                font-size: 16px;
                font-weight: 700;
                color: #007bff;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #007bff;
                letter-spacing: 0.2px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 8px;
                padding: 8px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
                border: 1px solid #0d6efd;
            }
            QPushButton {
                background: #e9ecef;
                color: #212529;
                border: 1px solid #ced4da;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #dee2e6;
            }
            QPushButton:focus {
                border: 1px solid #0d6efd;
            }
            QPushButton:disabled {
                background: #f1f3f5;
                color: #adb5bd;
                border: 1px solid #e9ecef;
            }
            QPushButton#primaryAction {
                background: #0d6efd;
                color: #ffffff;
                border: 1px solid #0b5ed7;
            }
            QPushButton#primaryAction:hover {
                background: #0b5ed7;
            }
            QPushButton#secondaryAction {
                background: #ffffff;
                color: #0d6efd;
                border: 1px solid #0d6efd;
            }
            QPushButton#secondaryAction:hover {
                background: #e8f0fe;
            }
            QPushButton#dangerAction {
                background: #ffffff;
                color: #dc3545;
                border: 1px solid #dc3545;
            }
            QPushButton#dangerAction:hover {
                background: #fff5f5;
            }
            QLabel#pageHeader {
                font-size: 22px;
                font-weight: 700;
                color: #007bff;
                letter-spacing: 0.2px;
                font-family: "Calibri", "Inter", "Arial";
            }
            QLabel#statusLabel {
                color: #495057;
                font-size: 12px;
            }
            QLabel#pageSubtitle {
                color: #6c757d;
                font-size: 13px;
            }
            QFrame#resultHero, QFrame#resultStatCard, QFrame#actionRail {
                background: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 12px;
            }
            QFrame#resultHero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ffffff, stop:1 #f3f8ff);
            }
            QLabel#resultChip {
                background: #e8f1ff;
                color: #0b5ed7;
                border: 1px solid #cfe2ff;
                border-radius: 999px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#resultStatTitle {
                color: #6c757d;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#resultStatValue {
                color: #1f2937;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#surfaceLabel {
                border: 2px dashed #ced4da;
                background: #f8f9fa;
                border-radius: 12px;
                color: #6c757d;
                padding: 16px;
                font-size: 12px;
            }
            QLabel#heatmapPlaceholder {
                border: 2px dashed #9ec5fe;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #eef5ff, stop:1 #e2ecff);
                border-radius: 12px;
                color: #0b5ed7;
                padding: 16px;
                font-size: 12px;
            }
            QFrame#actionRail {
                background: #f8fbff;
            }
        """)

    def create_unified_page(self):
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(12)
        grid.setContentsMargins(16, 16, 16, 16)
        # Patient Info
        self._scr_patient_group = QGroupBox("Patient Information")
        self._scr_patient_form = QFormLayout()
        self._scr_patient_form.setContentsMargins(12, 14, 12, 12)
        self._scr_patient_form.setHorizontalSpacing(14)
        self._scr_patient_form.setVerticalSpacing(10)
        self._scr_patient_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._scr_patient_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.p_id = QLineEdit()
        self.p_id.setReadOnly(True)
        self.p_id.setMinimumHeight(34)
        self.generate_patient_id()
        self._scr_patient_form.addRow("Patient ID:", self.p_id)
        self.p_name = QLineEdit()
        self.p_name.setPlaceholderText("Full name")
        self.p_name.setMinimumHeight(34)
        self._scr_patient_form.addRow("Name:", self.p_name)
        self.p_dob = QLineEdit()
        self.p_dob.setPlaceholderText("dd/mm/yyyy")
        self.p_dob.setMaxLength(10)
        self.p_dob.setMinimumHeight(34)
        self._dob_default_style = ""
        self._dob_invalid_style = """
            QLineEdit {
                border: 1.5px solid #dc3545;
                border-radius: 8px;
                padding: 8px;
            }
        """
        self.p_dob.setStyleSheet(self._dob_default_style)
        self.p_dob.textChanged.connect(self._on_dob_text_changed)
        self._scr_patient_form.addRow("Date of Birth:", self.p_dob)
        self.p_age = QSpinBox()
        self.p_age.setRange(0, 120)
        self.p_age.setSuffix(" years")
        self.p_age.setReadOnly(True)
        self.p_age.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.p_age.setSpecialValueText(" ")
        self.p_age.setValue(0)
        self.p_age.setMinimumHeight(34)
        self._scr_patient_form.addRow("Age:", self.p_age)
        self.p_sex = QComboBox()
        self.p_sex.addItems(["", "Male", "Female", "Prefer not to say"])
        self.p_sex.setMinimumHeight(34)
        self._scr_patient_form.addRow("Sex:", self.p_sex)
        self.p_contact = QLineEdit()
        self.p_contact.setPlaceholderText("Phone or Email")
        self.p_contact.setMinimumHeight(34)
        self._scr_patient_form.addRow("Contact:", self.p_contact)
        self.p_eye = QComboBox()
        self.p_eye.addItems(["", "Right Eye", "Left Eye"])
        self.p_eye.setMinimumHeight(34)
        self._scr_patient_form.addRow("Eye Screened:", self.p_eye)
        self._scr_patient_group.setLayout(self._scr_patient_form)
        # Clinical History
        self._scr_clinical_group = QGroupBox("Clinical History")
        self._scr_clinical_form = QFormLayout()
        self.diabetes_type = QComboBox()
        self.diabetes_type.addItems(["Select", "Type 1", "Type 2", "Gestational", "Other"])
        self._scr_clinical_form.addRow("Diabetes Type:", self.diabetes_type)
        self.diabetes_duration = QSpinBox()
        self.diabetes_duration.setSuffix(" years")
        self.diabetes_duration.setRange(0, 80)
        self.diabetes_duration.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.diabetes_duration.setStyleSheet("""
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 18px;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 18px;
            }
        """)
        self._scr_clinical_form.addRow("Duration:", self.diabetes_duration)
        self.hba1c = QDoubleSpinBox()
        self.hba1c.setRange(4.0, 15.0)
        self.hba1c.setDecimals(1)
        self.hba1c.setSuffix(" %")
        self.hba1c.setValue(7.0)
        self.hba1c.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.hba1c.setStyleSheet("""
            QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 18px;
            }
            QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 18px;
            }
        """)
        self._scr_clinical_form.addRow("HbA1c:", self.hba1c)
        self.prev_treatment = QCheckBox("Previous DR Treatment")
        self.prev_treatment.setStyleSheet("""
            QCheckBox {
                color: #212529;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #6c757d;
                border-radius: 3px;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #007bff;
                border: 1px solid #0056b3;
            }
        """)
        self._scr_clinical_form.addRow("", self.prev_treatment)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)
        self.notes.setMinimumHeight(80)
        self.notes.setPlaceholderText("Enter clinical notes")
        self.notes.setStyleSheet("""
            QTextEdit {
                background: #ffffff;
                border: 1px solid #6c757d;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QTextEdit:focus {
                border: 1px solid #0d6efd;
            }
        """)
        self._scr_clinical_form.addRow("Notes:", self.notes)
        self._scr_clinical_group.setLayout(self._scr_clinical_form)
        # Image Upload
        self._scr_image_group = QGroupBox("Fundus Image Upload")
        image_layout = QVBoxLayout()
        self.image_label = QLabel("No image loaded")
        self.image_label.setMinimumSize(450, 400)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("border: 2px dashed #ccc; background-color: #f9f9f9;")
        image_layout.addWidget(self.image_label)
        btn_layout = QHBoxLayout()
        self.btn_upload = QPushButton("Upload Image")
        self.btn_upload.setObjectName("primaryAction")
        self.btn_upload.clicked.connect(self.upload_image)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("dangerAction")
        self.btn_clear.clicked.connect(self.clear_image)
        btn_layout.addWidget(self.btn_upload)
        btn_layout.addWidget(self.btn_clear)
        image_layout.addLayout(btn_layout)
        self._scr_image_group.setLayout(image_layout)
        # Position widgets in grid
        grid.addWidget(self._scr_patient_group, 0, 0)
        grid.addWidget(self._scr_clinical_group, 1, 0)
        grid.addWidget(self._scr_image_group, 0, 1, 2, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        # Analyze Button at bottom right
        analyze_layout = QHBoxLayout()
        analyze_layout.addStretch()
        self.btn_analyze = QPushButton("Analyze Image")
        self.btn_analyze.setObjectName("primaryAction")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setAutoDefault(True)
        self.btn_analyze.setDefault(True)
        self.btn_analyze.clicked.connect(self.open_results_window)
        analyze_layout.addStretch()
        analyze_layout.addWidget(self.btn_analyze)
        grid.addLayout(analyze_layout, 2, 1, 1, 1)
        self._set_tab_order_unified()
        return container

    def _set_tab_order_unified(self):
        self.setTabOrder(self.p_name, self.p_dob)
        self.setTabOrder(self.p_dob, self.p_sex)
        self.setTabOrder(self.p_sex, self.p_contact)
        self.setTabOrder(self.p_contact, self.p_eye)
        self.setTabOrder(self.p_eye, self.diabetes_type)
        self.setTabOrder(self.diabetes_type, self.diabetes_duration)
        self.setTabOrder(self.diabetes_duration, self.hba1c)
        self.setTabOrder(self.hba1c, self.prev_treatment)
        self.setTabOrder(self.prev_treatment, self.notes)
        self.setTabOrder(self.notes, self.btn_upload)
        self.setTabOrder(self.btn_upload, self.btn_clear)
        self.setTabOrder(self.btn_clear, self.btn_analyze)

    def _setup_validators(self):
        self.name_regex = QRegularExpression(r"^[A-Za-z][A-Za-z\s\-']*$")
        self.p_name.setValidator(QRegularExpressionValidator(self.name_regex, self))

    def _validate_patient_basics(self):
        name = self.p_name.text().strip()
        dob_date = self._get_dob_date()
        sex = self.p_sex.currentText().strip()
        contact = self.p_contact.text().strip()

        missing_fields = []
        if not name:
            missing_fields.append("Name")
        if not dob_date.isValid():
            missing_fields.append("Date of Birth")
        if not sex:
            missing_fields.append("Sex")
        if not contact:
            missing_fields.append("Contact")

        if missing_fields:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please fill up every patient information field.\n\nMissing: " + ", ".join(missing_fields),
            )
            return False

        if not self.name_regex.match(name).hasMatch():
            QMessageBox.warning(self, "Error", "Name can only include letters, spaces, hyphens, and apostrophes")
            return False
        return True

    def _on_dob_text_changed(self, text):
        digits = "".join(ch for ch in text if ch.isdigit())[:8]
        if len(digits) <= 2:
            formatted = digits
        elif len(digits) <= 4:
            formatted = f"{digits[:2]}/{digits[2:]}"
        else:
            formatted = f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"

        if formatted != text:
            self.p_dob.blockSignals(True)
            self.p_dob.setText(formatted)
            self.p_dob.blockSignals(False)
            self.p_dob.setCursorPosition(len(formatted))

        self._update_dob_input_style(digits)

        self.update_age_from_dob(self._get_dob_date())

    def _update_dob_input_style(self, digits):
        has_invalid_value = False

        if len(digits) >= 1 and int(digits[0]) > 3:
            has_invalid_value = True

        if len(digits) >= 2:
            day = int(digits[:2])
            if day < 1 or day > 31:
                has_invalid_value = True

        if len(digits) >= 3 and int(digits[2]) > 1:
            has_invalid_value = True

        if len(digits) >= 4:
            month = int(digits[2:4])
            if month < 1 or month > 12:
                has_invalid_value = True

        if len(digits) == 8 and not self._get_dob_date().isValid():
            has_invalid_value = True

        self.p_dob.setStyleSheet(self._dob_invalid_style if has_invalid_value else self._dob_default_style)

    def _get_dob_date(self):
        if isinstance(self.p_dob, QDateEdit):
            date = self.p_dob.date()
            if date == self.min_dob_date:
                return QDate()
        else:
            date = QDate.fromString(self.p_dob.text().strip(), "dd/MM/yyyy")

        if not date.isValid():
            return QDate()
        if date < self.min_dob_date or date > QDate.currentDate():
            return QDate()
        return date

    def create_patient_info_page(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(15)

        title = QLabel("Step 1: Patient Information")
        title_font = QFont("Calibri", 16, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setObjectName("pageHeader")
        layout.addWidget(title)

        patient_group = QGroupBox("Patient Information")
        patient_form = QFormLayout()

        self.p_id = QLineEdit()
        self.p_id.setReadOnly(True)
        self.generate_patient_id()
        patient_form.addRow("Patient ID:", self.p_id)

        self.p_name = QLineEdit()
        self.p_name.setPlaceholderText("Full name")
        patient_form.addRow("Name:", self.p_name)

        self.p_dob = QDateEdit()
        self.p_dob.setCalendarPopup(True)
        self.p_dob.setDisplayFormat("yyyy-MM-dd")
        custom_calendar = QCalendarWidget()
        custom_calendar.setGridVisible(True)
        custom_calendar.setStyleSheet("""
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background-color: white;
            }
            QCalendarWidget QToolButton {
                color: black;
                font-weight: bold;
                background-color: white;
            }
            QCalendarWidget QAbstractItemView {
                color: black;
                selection-background-color: #0078d7;
                selection-color: white;
            }
        """)
        self.p_dob.setCalendarWidget(custom_calendar)
        self.p_dob.setMinimumDate(QDate(1900, 1, 1))
        self.p_dob.setSpecialValueText(" ")
        self.p_dob.setDate(self.p_dob.minimumDate())
        self.p_dob.dateChanged.connect(self.update_age_from_dob)
        patient_form.addRow("Date of Birth:", self.p_dob)

        self.p_age = QSpinBox()
        self.p_age.setRange(0, 120)
        self.p_age.setSuffix(" years")
        self.p_age.setReadOnly(True)
        self.p_age.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.p_age.setSpecialValueText(" ")
        self.p_age.setValue(0)
        patient_form.addRow("Age:", self.p_age)

        self.p_sex = QComboBox()
        self.p_sex.addItems(["", "Male", "Female", "Other"])
        patient_form.addRow("Sex:", self.p_sex)

        self.p_contact = QLineEdit()
        self.p_contact.setPlaceholderText("Phone or Email")
        patient_form.addRow("Contact:", self.p_contact)

        self.p_eye = QComboBox()
        self.p_eye.addItems(["", "Both Eyes", "Left Eye", "Right Eye"])
        patient_form.addRow("Eye(s):", self.p_eye)

        patient_group.setLayout(patient_form)
        layout.addWidget(patient_group)

        clinical_group = QGroupBox("Clinical History")
        clinical_form = QFormLayout()

        self.diabetes_type = QComboBox()
        self.diabetes_type.addItems(["Select", "Type 1", "Type 2", "Gestational", "Other"])
        clinical_form.addRow("Diabetes Type:", self.diabetes_type)

        self.diabetes_duration = QSpinBox()
        self.diabetes_duration.setSuffix(" years")
        self.diabetes_duration.setRange(0, 80)
        clinical_form.addRow("Duration:", self.diabetes_duration)

        self.hba1c = QDoubleSpinBox()
        self.hba1c.setRange(4.0, 15.0)
        self.hba1c.setDecimals(1)
        self.hba1c.setSuffix(" %")
        clinical_form.addRow("HbA1c:", self.hba1c)

        self.prev_treatment = QCheckBox("Previous DR Treatment")
        self.prev_treatment.setStyleSheet("""
            QCheckBox {
                color: #212529;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #6c757d;
                border-radius: 3px;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #007bff;
                border: 1px solid #0056b3;
            }
        """)
        clinical_form.addRow("", self.prev_treatment)

        self.notes = QTextEdit()
        self.notes.setMaximumHeight(80)
        self.notes.setMinimumHeight(80)
        self.notes.setPlaceholderText("Enter clinical notes")
        self.notes.setStyleSheet("""
            QTextEdit {
                background: #ffffff;
                border: 1px solid #6c757d;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QTextEdit:focus {
                border: 1px solid #0d6efd;
            }
        """)
        clinical_form.addRow("Notes:", self.notes)

        clinical_group.setLayout(clinical_form)
        layout.addWidget(clinical_group)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel_screening)
        button_layout.addWidget(self.btn_cancel)
        self.btn_proceed = QPushButton("Proceed to Image")
        self.btn_proceed.clicked.connect(self.validate_and_proceed)
        button_layout.addWidget(self.btn_proceed)
        layout.addLayout(button_layout)
        layout.addStretch()
        return container

    def create_image_analysis_page(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(15)

        title = QLabel("Step 2: Image Analysis")
        title_font = QFont("Calibri", 16, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setObjectName("pageHeader")
        layout.addWidget(title)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("color: #555; font-size: 11pt;")
        layout.addWidget(self.summary_label)

        image_group = QGroupBox("Fundus Image")
        image_layout = QVBoxLayout()

        self.image_label = QLabel("No image loaded")
        self.image_label.setMinimumSize(450, 400)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("border: 2px dashed #ccc; background-color: #f9f9f9;")
        image_layout.addWidget(self.image_label)

        btn_layout = QHBoxLayout()
        self.btn_upload = QPushButton("Upload Image")
        self.btn_upload.clicked.connect(self.upload_image)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_image)
        btn_layout.addWidget(self.btn_upload)
        btn_layout.addWidget(self.btn_clear)
        image_layout.addLayout(btn_layout)

        image_group.setLayout(image_layout)
        layout.addWidget(image_group, 1)

        results_group = QGroupBox("Results")
        results_layout = QFormLayout()
        self.r_class = QLabel("—")
        self.r_class.setFont(QFont("Calibri", 16, QFont.Weight.Bold))
        results_layout.addRow("Classification:", self.r_class)
        self.r_conf = QLabel("—")
        results_layout.addRow("Confidence:", self.r_conf)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.btn_analyze = QPushButton("Analyze Image")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self.analyze_image)
        button_layout.addWidget(self.btn_analyze)
        self.btn_save = QPushButton("Save Screening")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.save_screening)
        button_layout.addWidget(self.btn_save)
        self.btn_back = QPushButton("Back")
        self.btn_back.clicked.connect(self.go_back_to_patient_info)
        button_layout.addWidget(self.btn_back)
        self.btn_new = QPushButton("New Patient")
        self.btn_new.clicked.connect(self.reset_screening)
        button_layout.addWidget(self.btn_new)
        layout.addLayout(button_layout)
        return container

    # ==================== LOGIC FUNCTIONS ====================

    def generate_patient_id(self):
        pid = self._next_unique_patient_id()
        self.p_id.setText(pid)
        return pid

    def _next_unique_patient_id(self):
        for _ in range(25):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            suffix = secrets.token_hex(2).upper()
            candidate = f"ES-{stamp}-{suffix}"
            if not self._patient_id_exists(candidate):
                return candidate

        fallback = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        return f"ES-{fallback}"

    def _patient_id_exists(self, patient_id):
        patient_id = str(patient_id or "").strip()
        if not patient_id:
            return False

        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM patient_records WHERE patient_id = ? LIMIT 1", (patient_id,))
            exists = cur.fetchone() is not None
            conn.close()
            return exists
        except Exception:
            return False

    def update_age_from_dob(self, date):
        if not date.isValid():
            self.p_age.setValue(0)
            return
        today = QDate.currentDate()
        age = today.year() - date.year()
        if (today.month(), today.day()) < (date.month(), date.day()):
            age -= 1
        self.p_age.setValue(max(0, age))

    def validate_and_proceed(self):
        if not self._validate_patient_basics():
            return
        dob_date = self._get_dob_date()
        dob_str = dob_date.toString("yyyy-MM-dd") if dob_date.isValid() else ""
        summary = f"<b>{self.p_name.text()}</b> | ID: {self.p_id.text()} | DOB: {dob_str} | Age: {self.p_age.value()}"
        self.summary_label.setText(summary)
        self.stacked_widget.setCurrentIndex(1)

    def cancel_screening(self):
        reply = QMessageBox.question(
            self, "Cancel", "Are you sure you want to cancel? All data will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.reset_screening()

    def go_back_to_patient_info(self):
        reply = QMessageBox.question(
            self, "Go Back", "Going back will clear the image. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_image()
            self.stacked_widget.setCurrentIndex(0)

    def reset_screening(self):
        self.generate_patient_id()
        self.p_name.clear()
        self.p_contact.clear()
        if isinstance(self.p_dob, QDateEdit):
            self.p_dob.setDate(self.min_dob_date)
        else:
            self.p_dob.clear()
        self.p_age.setValue(0)
        self.p_sex.setCurrentIndex(0)
        self.p_eye.setCurrentIndex(0)
        self.diabetes_type.setCurrentIndex(0)
        self.diabetes_duration.setValue(0)
        self.hba1c.setValue(7.0)
        self.prev_treatment.setChecked(False)
        self.notes.clear()
        self.current_image = None
        self.image_label.clear()
        self.image_label.setText("No image loaded")
        self.image_label.setStyleSheet("border: 2px dashed #ccc; background-color: #f9f9f9;")
        self.last_result_class = "Pending"
        self.last_result_conf = "Pending"
        self._current_eye_saved = False
        self._first_eye_result = None
        self.btn_analyze.setEnabled(False)
        self.stacked_widget.setCurrentIndex(0)

    def upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Fundus Image", "", "Images (*.jpg *.png *.jpeg)"
        )
        if path:
            self.current_image = path
            pixmap = QPixmap(path).scaled(
                450,
                400,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image_label.setPixmap(pixmap)
            self.btn_analyze.setEnabled(True)

    def screen_another_image(self):
        """Pick a new image from the results page, re-run analysis, update results in place."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Fundus Image", "", "Images (*.jpg *.png *.jpeg)"
        )
        if not path:
            return
        self.current_image = path
        # Update the upload panel too so it stays in sync
        pixmap = QPixmap(path).scaled(
            450, 400,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(pixmap)
        self.btn_analyze.setEnabled(True)
        # Re-run analysis (placeholder — replace with real model call when ready)
        self.last_result_class = "No DR Detected"
        self.last_result_conf = "Confidence: 93.8%"
        self.results_page.set_results(
            self.p_name.text(),
            path,
            self.last_result_class,
            self.last_result_conf,
        )

    def open_results_window(self):
        if not self._validate_patient_basics():
            return
        if not self.current_image:
            QMessageBox.warning(self, "Error", "No image loaded")
            return
        confirm_box = QMessageBox(self)
        confirm_box.setWindowTitle("Confirm Details")
        confirm_box.setText("Please confirm all patient information is correct before proceeding to results.")
        proceed_button = confirm_box.addButton("Proceed to Results", QMessageBox.ButtonRole.AcceptRole)
        confirm_box.addButton("Edit Information", QMessageBox.ButtonRole.RejectRole)
        
        confirm_box.exec()
        if confirm_box.clickedButton() != proceed_button:
            return
        # Show results inside the same window
        self._current_eye_saved = False
        self.last_result_class = "No DR Detected"
        self.last_result_conf = "Confidence: 93.8%"
        eye_label = self.p_eye.currentText()
        self.results_page.set_results(
            self.p_name.text(),
            self.current_image,
            self.last_result_class,
            self.last_result_conf,
            eye_label=eye_label,
            first_eye_result=self._first_eye_result,
        )
        self.stacked_widget.setCurrentIndex(1)

    def clear_image(self):
        self.current_image = None
        self.image_label.clear()
        self.image_label.setText("No image loaded")
        self.image_label.setStyleSheet("border: 2px dashed #ccc; background-color: #f9f9f9;")
        self.btn_analyze.setEnabled(False)

    def save_screening(self, reset_after=True):
        if not self._validate_patient_basics():
            return
        name = self.p_name.text().strip()

        pid = self.p_id.text().strip()
        if not pid or self._patient_id_exists(pid):
            pid = self.generate_patient_id()

        dob_date = self._get_dob_date()
        dob_str = dob_date.toString("yyyy-MM-dd") if dob_date.isValid() else ""

        age = self.p_age.value()
        sex = self.p_sex.currentText()
        contact = self.p_contact.text().strip()
        eye = self.p_eye.currentText()
        diabetes_type = self.diabetes_type.currentText()
        duration = self.diabetes_duration.value()
        hba1c = f"{self.hba1c.value():.1f}%"
        prev_treatment = "Yes" if self.prev_treatment.isChecked() else "No"
        notes = self.notes.toPlainText().strip()
        result = self.last_result_class
        confidence = self.last_result_conf

        patient_data = [
            pid,
            name,
            dob_str,
            age if age > 0 else "",
            sex,
            contact,
            eye,
            diabetes_type if diabetes_type != "Select" else "",
            duration,
            hba1c,
            prev_treatment,
            notes,
            result,
            confidence,
        ]

        if not self._save_screening_to_db(patient_data):
            QMessageBox.warning(self, "Save Failed", "Unable to save screening record. Please try again.")
            return

        self._current_eye_saved = True
        if reset_after:
            self.reset_screening()
        else:
            eye_label = eye or "eye"
            self._first_eye_result = {
                "eye": eye_label,
                "result": self.last_result_class,
                "confidence": self.last_result_conf,
            }
            self.results_page.mark_saved(self.p_name.text().strip(), eye_label, self.last_result_class)

    def screen_other_eye(self):
        """Save the current eye's result and switch to the same patient's other eye."""
        current_eye = self.p_eye.currentText().strip()
        opposite_eye = "Left Eye" if current_eye == "Right Eye" else "Right Eye"

        if not self._current_eye_saved:
            eye_label = current_eye or "current eye"
            reply = QMessageBox.question(
                self,
                "Save Before Switching",
                f"The screening for the <b>{eye_label}</b> has not been saved yet.\n\n"
                f"Save it now before screening the {opposite_eye}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self.save_screening(reset_after=False)
                if not self._current_eye_saved:
                    return  # save failed, abort

        # Capture current patient demographics before resetting
        name = self.p_name.text()
        dob_text = self.p_dob.text() if not isinstance(self.p_dob, QDateEdit) else ""
        age = self.p_age.value()
        sex = self.p_sex.currentText()
        contact = self.p_contact.text()
        d_type = self.diabetes_type.currentText()
        d_dur = self.diabetes_duration.value()
        hba1c_val = self.hba1c.value()
        prev = self.prev_treatment.isChecked()
        notes_text = self.notes.toPlainText()

        # Preserve first eye result across reset so results page can show bilateral comparison
        saved_first_eye_result = self._first_eye_result

        # Full reset (generates new patient ID, clears everything)
        self.reset_screening()

        # Restore first eye result
        self._first_eye_result = saved_first_eye_result

        # Restore demographics for the same patient
        self.p_name.setText(name)
        if not isinstance(self.p_dob, QDateEdit):
            self.p_dob.setText(dob_text)
        self.p_age.setValue(age)
        self.p_sex.setCurrentText(sex)
        self.p_contact.setText(contact)
        self.diabetes_type.setCurrentText(d_type)
        self.diabetes_duration.setValue(d_dur)
        self.hba1c.setValue(hba1c_val)
        self.prev_treatment.setChecked(prev)
        self.notes.setPlainText(notes_text)

        # Pre-select the other eye
        self.p_eye.setCurrentText(opposite_eye)

        # Return to intake form — only the image needs to be uploaded
        self.stacked_widget.setCurrentIndex(0)

    def _save_screening_to_db(self, patient_data):
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO patient_records (
                    patient_id, name, birthdate, age, sex, contact, eyes, diabetes_type, duration, hba1c, prev_treatment, notes, result, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                patient_data,
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def apply_language(self, language: str):
        from translations import get_pack
        pack = get_pack(language)
        self._scr_patient_group.setTitle(pack["scr_patient_info"])
        self._scr_clinical_group.setTitle(pack["scr_clinical_history"])
        self._scr_image_group.setTitle(pack["scr_image_upload"])
        self.btn_upload.setText(pack["scr_upload_btn"])
        self.btn_clear.setText(pack["scr_clear_btn"])
        self.btn_analyze.setText(pack["scr_analyze_btn"])
        patient_labels = [
            pack["scr_label_pid"], pack["scr_label_name"], pack["scr_label_dob"],
            pack["scr_label_age"], pack["scr_label_sex"], pack["scr_label_contact"],
            pack["scr_label_eye"],
        ]
        for row, text in enumerate(patient_labels):
            item = self._scr_patient_form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item and item.widget():
                item.widget().setText(text)
        clinical_labels = [
            pack["scr_label_diabetes"], pack["scr_label_duration"], pack["scr_label_hba1c"],
            None,
            pack["scr_label_notes"],
        ]
        for row, text in enumerate(clinical_labels):
            if text is None:
                continue
            item = self._scr_clinical_form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item and item.widget():
                item.widget().setText(text)

class ResultsWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_page = parent
        self.setMinimumSize(980, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        self.title_label = QLabel("Results")
        self.title_label.setFont(QFont("Calibri", 16, QFont.Weight.Bold))
        self.title_label.setObjectName("pageHeader")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Review the screening summary, image preview, and heatmap output area.")
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        main_row = QHBoxLayout()
        main_row.setSpacing(14)

        review_column = QVBoxLayout()
        review_column.setSpacing(12)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)

        source_group = QGroupBox("Source Image")
        source_layout = QVBoxLayout(source_group)
        source_layout.setContentsMargins(14, 16, 14, 14)
        source_layout.setSpacing(10)
        self.source_label = ClickableImageLabel("", "Source Image")
        self.source_label.setObjectName("surfaceLabel")
        self.source_label.setMinimumSize(440, 340)
        self.source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_label.setWordWrap(True)
        source_layout.addWidget(self.source_label)
        self.source_note = QLabel("This panel preserves the original fundus image for comparison against the model visualization. Click the image to inspect and zoom.")
        self.source_note.setObjectName("statusLabel")
        self.source_note.setWordWrap(True)
        source_layout.addWidget(self.source_note)

        heatmap_group = QGroupBox("Heatmap Output")
        heatmap_layout = QVBoxLayout(heatmap_group)
        heatmap_layout.setContentsMargins(14, 16, 14, 14)
        heatmap_layout.setSpacing(10)
        self.heatmap_label = ClickableImageLabel("", "Heatmap Output")
        self.heatmap_label.setObjectName("heatmapPlaceholder")
        self.heatmap_label.setMinimumSize(440, 340)
        self.heatmap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heatmap_label.setWordWrap(True)
        heatmap_layout.addWidget(self.heatmap_label)
        self.heatmap_note = QLabel("Reserved for the lesion-attention or explainability overlay generated by the model. When a heatmap image is available, it will also open on click.")
        self.heatmap_note.setObjectName("statusLabel")
        self.heatmap_note.setWordWrap(True)
        heatmap_layout.addWidget(self.heatmap_note)

        preview_row.addWidget(source_group, 1)
        preview_row.addWidget(heatmap_group, 1)
        review_column.addLayout(preview_row, 1)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        classification_card, self.classification_value = self._create_stat_card("Classification")
        confidence_card, self.confidence_value = self._create_stat_card("Confidence")
        recommendation_card, self.recommendation_value = self._create_stat_card("Recommendation")
        stats_row.addWidget(classification_card)
        stats_row.addWidget(confidence_card)
        stats_row.addWidget(recommendation_card)
        review_column.addLayout(stats_row)

        # Bilateral comparison card (hidden until second eye is being reviewed)
        self.bilateral_frame = QFrame()
        self.bilateral_frame.setObjectName("resultStatCard")
        bilateral_layout = QVBoxLayout(self.bilateral_frame)
        bilateral_layout.setContentsMargins(14, 12, 14, 12)
        bilateral_layout.setSpacing(8)
        bilateral_title = QLabel("\u2194  Bilateral Screening Comparison")
        bilateral_title.setObjectName("resultStatTitle")
        bilateral_layout.addWidget(bilateral_title)
        brow = QHBoxLayout()
        brow.setSpacing(20)
        first_col = QVBoxLayout()
        first_col.setSpacing(4)
        self.bilateral_first_eye_lbl = QLabel("\u2014")
        self.bilateral_first_eye_lbl.setObjectName("resultStatTitle")
        self.bilateral_first_result_lbl = QLabel("\u2014")
        self.bilateral_first_result_lbl.setObjectName("resultStatValue")
        self.bilateral_first_saved_lbl = QLabel("\u2713 Saved")
        self.bilateral_first_saved_lbl.setStyleSheet("color:#198754;font-weight:700;font-size:12px;")
        first_col.addWidget(self.bilateral_first_eye_lbl)
        first_col.addWidget(self.bilateral_first_result_lbl)
        first_col.addWidget(self.bilateral_first_saved_lbl)
        brow_div = QFrame()
        brow_div.setFrameShape(QFrame.Shape.VLine)
        brow_div.setFrameShadow(QFrame.Shadow.Sunken)
        second_col = QVBoxLayout()
        second_col.setSpacing(4)
        self.bilateral_second_eye_lbl = QLabel("\u2014")
        self.bilateral_second_eye_lbl.setObjectName("resultStatTitle")
        self.bilateral_second_result_lbl = QLabel("\u2014")
        self.bilateral_second_result_lbl.setObjectName("resultStatValue")
        self.bilateral_second_saved_lbl = QLabel("Unsaved")
        self.bilateral_second_saved_lbl.setStyleSheet("color:#dc3545;font-weight:700;font-size:12px;")
        second_col.addWidget(self.bilateral_second_eye_lbl)
        second_col.addWidget(self.bilateral_second_result_lbl)
        second_col.addWidget(self.bilateral_second_saved_lbl)
        brow.addLayout(first_col)
        brow.addWidget(brow_div)
        brow.addLayout(second_col)
        bilateral_layout.addLayout(brow)
        self.bilateral_frame.hide()
        review_column.addWidget(self.bilateral_frame)

        main_row.addLayout(review_column, 1)

        action_rail = QFrame()
        action_rail.setObjectName("actionRail")
        action_layout = QVBoxLayout(action_rail)
        action_layout.setContentsMargins(14, 14, 14, 14)
        action_layout.setSpacing(10)

        rail_label = QLabel("Actions")
        rail_label.setObjectName("resultStatTitle")
        action_layout.addWidget(rail_label)

        self.save_status_label = QLabel("")
        self.save_status_label.setWordWrap(True)
        self.save_status_label.hide()
        action_layout.addWidget(self.save_status_label)

        self.btn_save = QPushButton("Save Patient")
        self.btn_save.setObjectName("primaryAction")
        self.btn_save.setAutoDefault(True)
        self.btn_save.setDefault(True)
        self.btn_save.setMinimumHeight(42)
        self.btn_save.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.btn_save.setIconSize(QSize(18, 18))
        self.btn_save.clicked.connect(self.save_patient)
        action_layout.addWidget(self.btn_save)

        self.btn_screen_another = QPushButton("Screen Other Eye")
        self.btn_screen_another.setObjectName("secondaryAction")
        self.btn_screen_another.setMinimumHeight(42)
        self.btn_screen_another.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogStart))
        self.btn_screen_another.setIconSize(QSize(18, 18))
        self.btn_screen_another.clicked.connect(self._on_screen_another)
        action_layout.addWidget(self.btn_screen_another)

        self.btn_new = QPushButton("New Patient")
        self.btn_new.setMinimumHeight(42)
        self.btn_new.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        self.btn_new.setIconSize(QSize(18, 18))
        self.btn_new.clicked.connect(self.new_patient)
        action_layout.addWidget(self.btn_new)

        self.btn_back = QPushButton("Back to Screening")
        self.btn_back.setObjectName("dangerAction")
        self.btn_back.setMinimumHeight(42)
        self.btn_back.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.btn_back.setIconSize(QSize(18, 18))
        self.btn_back.clicked.connect(self.go_back)
        action_layout.addWidget(self.btn_back)

        action_layout.addStretch()

        main_row.addWidget(action_rail)
        layout.addLayout(main_row, 1)

        explanation_group = QGroupBox("Clinical Summary")
        explanation_layout = QVBoxLayout(explanation_group)
        explanation_layout.setContentsMargins(14, 16, 14, 14)
        explanation_layout.setSpacing(10)
        self.explanation = QLabel("AI explanation will appear here once available.")
        self.explanation.setWordWrap(True)
        self.explanation.setStyleSheet("font-size: 11pt; color: #333; line-height: 1.45;")
        explanation_layout.addWidget(self.explanation)
        self.explanation_hint = QLabel("Use this area for screening rationale, referral guidance, and any findings tied to the future heatmap.")
        self.explanation_hint.setObjectName("statusLabel")
        self.explanation_hint.setWordWrap(True)
        explanation_layout.addWidget(self.explanation_hint)
        layout.addWidget(explanation_group)

    def _create_stat_card(self, title_text):
        card = QFrame()
        card.setObjectName("resultStatCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("resultStatTitle")
        value = QLabel("Pending")
        value.setObjectName("resultStatValue")
        value.setWordWrap(True)

        card_layout.addWidget(title)
        card_layout.addWidget(value)
        return card, value

    def set_results(self, patient_name, image_path, result_class="Pending", confidence_text="Pending", eye_label="", first_eye_result=None):
        if patient_name:
            eye_suffix = f" \u2014 {eye_label}" if eye_label else ""
            self.title_label.setText(f"Results for {patient_name}{eye_suffix}")
        else:
            self.title_label.setText("Results")

        # Reset save feedback state
        self.save_status_label.hide()
        self.save_status_label.setText("")
        self.btn_save.setEnabled(True)
        self.btn_save.setText("Save Patient")
        self.btn_save.setObjectName("primaryAction")
        self.btn_save.setStyle(self.btn_save.style())

        # Bilateral comparison
        if first_eye_result:
            self.bilateral_first_eye_lbl.setText(first_eye_result.get("eye", "\u2014"))
            self.bilateral_first_result_lbl.setText(first_eye_result.get("result", "\u2014"))
            self.bilateral_second_eye_lbl.setText(eye_label or "Current Eye")
            self.bilateral_second_result_lbl.setText(result_class)
            self.bilateral_second_saved_lbl.setText("Unsaved")
            self.bilateral_second_saved_lbl.setStyleSheet("color:#dc3545;font-weight:700;font-size:12px;")
            self.bilateral_frame.show()
        else:
            self.bilateral_frame.hide()

        self.classification_value.setText(result_class)
        self.confidence_value.setText(confidence_text)

        recommendation = "Routine follow-up"
        if "no dr" not in result_class.lower():
            recommendation = "Clinical review advised"
        self.recommendation_value.setText(recommendation)
        self.subtitle_label.setText(
            f"Current output shows {result_class.lower()} with {confidence_text.lower()}. The layout is ready for the final heatmap and explanation output."
        )

        if image_path:
            source_pixmap = QPixmap(image_path)
            self.source_label.set_viewable_pixmap(source_pixmap, 460, 360)
            self.heatmap_label.clear_view("")
        else:
            self.source_label.clear_view("")
            self.heatmap_label.clear_view("")

        self.explanation.setText(
            f"Screening result: {result_class}. Confidence: {confidence_text}. This output area is structured for a clinician-friendly review flow, with the original image on the left, the explainability heatmap on the right, and a written summary below for findings and next-step guidance."
        )

    def mark_saved(self, name, eye_label, result_class):
        """Called by ScreeningPage after a successful save to update this panel."""
        self.save_status_label.setText(f"\u2713  Saved \u2014 {name} ({eye_label}): {result_class}")
        self.save_status_label.setStyleSheet(
            "color:#0f5132;font-weight:700;font-size:12px;"
            "background:#d1e7dd;border-radius:6px;padding:6px 8px;"
        )
        self.save_status_label.show()
        self.btn_save.setText("Saved \u2713")
        self.btn_save.setEnabled(False)
        if self.bilateral_frame.isVisible():
            self.bilateral_second_saved_lbl.setText("\u2713 Saved")
            self.bilateral_second_saved_lbl.setStyleSheet("color:#198754;font-weight:700;font-size:12px;")

    def go_back(self):
        if not self.parent_page:
            return
        page = self.parent_page
        if not getattr(page, "_current_eye_saved", True):
            reply = QMessageBox.question(
                self, "Unsaved Screening",
                "This screening has not been saved yet.\n\nGo back to the intake form without saving?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if hasattr(page, "stacked_widget"):
            page.stacked_widget.setCurrentIndex(0)

    def save_patient(self):
        if self.parent_page and hasattr(self.parent_page, "save_screening"):
            self.parent_page.save_screening(reset_after=False)

    def new_patient(self):
        if not self.parent_page:
            return
        page = self.parent_page
        if not getattr(page, "_current_eye_saved", True):
            reply = QMessageBox.question(
                self, "Unsaved Screening",
                "This screening has not been saved yet.\n\nDiscard it and start a new patient?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Discard:
                return
        if hasattr(page, "reset_screening"):
            page.reset_screening()

    def _on_screen_another(self):
        if self.parent_page and hasattr(self.parent_page, "screen_other_eye"):
            self.parent_page.screen_other_eye()
