"""
Reports module for EyeShield EMR application.
Provides offline summary analytics from local patient_records data.
"""
import csv
import json
from html import escape
import os
from pathlib import Path
import sqlite3
from datetime import datetime
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QGroupBox, QTableWidget, QTableWidgetItem, QLineEdit, QComboBox, QHeaderView, QFileDialog, QDialog, QMessageBox, QMenu, QScrollArea
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter
from auth import DB_FILE, UserManager

def _is_truthy_flag(value) -> bool:
    """Normalize legacy/new boolean-like values stored in SQLite text fields."""
    return str(value or '').strip().lower() in {'true', '1', 'yes', 'checked', 'y'}

class PatientDetailsDialog(QDialog):
    """Read-only dialog displaying full patient screening details including fundus image."""

    def __init__(self, patient_record: dict, parent=None):
        super().__init__(parent)
        self.record = patient_record
        self.setWindowTitle(f"Patient Details - {patient_record.get('name', 'Unknown')}")
        self.resize(1000, 700)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(left_scroll.Shape.NoFrame)
        left_scroll.setStyleSheet('QScrollArea{border:none;background:transparent;}')
        left_scroll.setMaximumWidth(400)
        left_content = QWidget()
        left_content.setStyleSheet('background:transparent;')
        left_layout = QVBoxLayout(left_content)
        left_layout.setSpacing(14)
        left_layout.setContentsMargins(0, 0, 0, 0)

        def add_field(label_text: str, value_text: str):
            row = QHBoxLayout()
            row.setSpacing(12)
            label = QLabel(f'{label_text}:')
            label.setStyleSheet('font-weight:600;color:#3f7ca7;min-width:150px;')
            value = QLabel(value_text)
            value.setStyleSheet('color:#475569;')
            value.setWordWrap(True)
            row.addWidget(label)
            row.addWidget(value, 1)
            left_layout.addLayout(row)

        def add_section(section_title: str):
            sep = QLabel(section_title.upper())
            sep.setStyleSheet('font-size:12px;font-weight:700;color:#3f7ca7;margin-top:8px;letter-spacing:1px;')
            left_layout.addWidget(sep)
        add_section('Patient Information')
        add_field('Patient ID', str(patient_record.get('patient_id') or 'N/A'))
        add_field('Name', str(patient_record.get('name') or 'N/A'))
        add_field('Age', str(patient_record.get('age') or 'N/A'))
        add_field('Date of Birth', str(patient_record.get('birthdate') or 'N/A'))
        add_field('Sex', str(patient_record.get('sex') or 'N/A'))
        add_field('Contact', str(patient_record.get('contact') or 'N/A'))
        add_field('Eye Screened', str(patient_record.get('eyes') or 'N/A'))
        add_field('Height', str(patient_record.get('height') or 'N/A') + (' cm' if patient_record.get('height') else ''))
        add_field('Weight', str(patient_record.get('weight') or 'N/A') + (' kg' if patient_record.get('weight') else ''))
        add_field('BMI', str(patient_record.get('bmi') or 'N/A'))
        add_section('Symptoms')
        symptoms = []
        if _is_truthy_flag(patient_record.get('symptom_blurred_vision')):
            symptoms.append('Blurred vision')
        if _is_truthy_flag(patient_record.get('symptom_floaters')):
            symptoms.append('Floaters')
        if _is_truthy_flag(patient_record.get('symptom_flashes')):
            symptoms.append('Flashes')
        if _is_truthy_flag(patient_record.get('symptom_vision_loss')):
            symptoms.append('Vision loss')
        symptom_text = ', '.join(symptoms) if symptoms else 'None reported'
        add_field('Reported Symptoms', symptom_text)
        add_section('Clinical History')
        add_field('Diabetes Type', str(patient_record.get('diabetes_type') or 'N/A'))
        add_field('Diagnosis Date', str(patient_record.get('diabetes_diagnosis_date') or 'N/A'))
        add_field('Duration', str(patient_record.get('duration') or 'N/A'))
        add_field('Treatment Regimen', str(patient_record.get('treatment_regimen') or 'N/A'))
        add_field('Previous DR Stage', str(patient_record.get('prev_dr_stage') or 'N/A'))
        prev_treatment = 'Yes' if _is_truthy_flag(patient_record.get('prev_treatment')) else 'No'
        add_field('Previous DR Treatment', prev_treatment)
        add_section('Screening Result')
        add_field('AI Classification', str(patient_record.get('ai_classification') or patient_record.get('result') or 'N/A'))
        add_field('Doctor Classification', str(patient_record.get('doctor_classification') or patient_record.get('result') or 'N/A'))
        add_field('Final Diagnosis', 'Based on ICDR Severity Scale')
        add_field('Decision Mode', str(patient_record.get('decision_mode') or 'accepted').title())
        findings_text = str(patient_record.get('doctor_findings') or '').strip()
        if findings_text:
            add_field('Doctor Findings', findings_text)
        override_reason = str(patient_record.get('override_justification') or '').strip()
        if override_reason:
            add_field('Override Justification', override_reason)
        add_field('Confidence', str(patient_record.get('confidence') or 'N/A'))
        add_field('Screened At', str(patient_record.get('screened_at') or 'N/A'))
        add_field('Screened By', str(patient_record.get('original_screener_name') or patient_record.get('original_screener_username') or 'N/A'))
        notes = patient_record.get('notes') or ''
        if notes and notes.strip():
            add_section('Clinical Notes')
            notes_label = QLabel(str(notes))
            notes_label.setWordWrap(True)
            notes_label.setStyleSheet('color:#475569;background:#f6f8fb;border:1px solid #d3dae3;border-radius:6px;padding:10px;')
            left_layout.addWidget(notes_label)
        left_layout.addStretch()
        left_scroll.setWidget(left_content)
        layout.addWidget(left_scroll)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setSpacing(10)
        right_layout.setContentsMargins(0, 0, 0, 0)
        image_title = QLabel('FUNDUS IMAGE')
        image_title.setStyleSheet('font-size:12px;font-weight:700;color:#3f7ca7;letter-spacing:1px;')
        right_layout.addWidget(image_title)
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setStyleSheet('border:1px solid #d3dae3;border-radius:6px;background:#f6f8fb;')
        image_label.setMinimumSize(500, 500)
        source_image = patient_record.get('source_image_path') or ''
        if source_image and os.path.isfile(source_image):
            try:
                pixmap = QPixmap(source_image)
                if not pixmap.isNull():
                    scaled = pixmap.scaledToHeight(500, Qt.SmoothTransformation)
                    image_label.setPixmap(scaled)
                else:
                    image_label.setText('Image could not be loaded')
            except Exception:
                image_label.setText('Error loading image')
        else:
            image_label.setText('No fundus image available')
        right_layout.addWidget(image_label, 1)
        close_btn = QPushButton('Close')
        close_btn.setMinimumHeight(36)
        close_btn.setStyleSheet('QPushButton{background:#1f6fe5;color:#ffffff;border:1px solid #1a5fc4;border-radius:6px;}QPushButton:hover{background:#1b63cf;}')
        close_btn.clicked.connect(self.accept)
        right_layout.addWidget(close_btn)
        layout.addWidget(right_container)
        self.setStyleSheet('QDialog{background:#ffffff;}')

class ArchivedRecordsDialog(QDialog):
    """Admin-only dialog for reviewing and restoring archived patient records."""

    def __init__(self, reports_page: 'ReportsPage'):
        super().__init__(reports_page)
        self.reports_page = reports_page
        self._rows = []
        self._filtered_rows = []
        self._record_lookup = {}
        self.setWindowTitle('Archived Patient Records')
        self.resize(980, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        title = QLabel('Archived Patient Records')
        title.setStyleSheet('font-size:22px;font-weight:700;color:#007bff;')
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel('Review archived screenings and restore them back into the active dashboard and reports.')
        subtitle.setStyleSheet('font-size:13px;color:#6c757d;')
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search archived records by patient ID, name, result, or archived by')
        self.search_input.textChanged.connect(self.apply_filters)
        controls.addWidget(self.search_input, 1)
        self.count_label = QLabel('0 archived')
        self.count_label.setStyleSheet('color:#6c757d;font-size:12px;')
        self.count_label.setAlignment(Qt.AlignCenter)
        controls.addWidget(self.count_label)
        layout.addLayout(controls)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Patient ID', 'Name', 'Result', 'Archived At', 'Archived By'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_restore_button)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.delete_btn = QPushButton('Delete Selected')
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet('QPushButton{background:#dc3545;color:#fff;border:1px solid #bb2d3b;}QPushButton:hover{background:#c82333;}QPushButton:disabled{background:#f1aeb5;color:#fff;border:1px solid #ea868f;}')
        self.delete_btn.clicked.connect(self.delete_selected_record)
        actions.addWidget(self.delete_btn)
        self.restore_btn = QPushButton('Restore Selected')
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self.restore_selected_record)
        actions.addWidget(self.restore_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        layout.addLayout(actions)
        self.reload_rows()

    def reload_rows(self):
        self._rows = [r for r in self.reports_page._all_result_rows if r['archived_at']]
        self._record_lookup = {r['id']: r for r in self._rows}
        self.apply_filters()

    def apply_filters(self):
        query = self.search_input.text().strip().lower()
        filtered = []
        for row in self._rows:
            haystack = ' '.join([str(row[k] or '') for k in ('patient_id', 'name', 'result', 'archived_at', 'archived_by')]).lower()
            if query and query not in haystack:
                continue
            filtered.append(row)
        self._filtered_rows = filtered
        self._render_table()

    def _render_table(self):
        self.table.setRowCount(0)
        for row in self._filtered_rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            item = QTableWidgetItem(str(row['patient_id'] or ''))
            item.setData(Qt.UserRole, row['id'])
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, item)
            name_item = QTableWidgetItem(str(row['name'] or ''))
            name_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, name_item)
            result_item = QTableWidgetItem(str(row['result'] or ''))
            result_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, result_item)
            archived_at_item = QTableWidgetItem(str(row['archived_at'] or ''))
            archived_at_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, archived_at_item)
            archived_by_item = QTableWidgetItem(str(row['archived_by'] or ''))
            archived_by_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, archived_by_item)
        self.count_label.setText(f'{len(self._filtered_rows)} archived')
        self._update_restore_button()

    def _get_selected_record(self):
        r = self.table.currentRow()
        if r < 0:
            return None
        item = self.table.item(r, 0)
        return self._record_lookup.get(item.data(Qt.UserRole)) if item else None

    def _update_restore_button(self):
        has = self._get_selected_record() is not None
        self.restore_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)

    def restore_selected_record(self):
        record = self._get_selected_record()
        if not record:
            QMessageBox.information(self, 'Restore Record', 'Select an archived patient record to restore.')
            return
        if not self.reports_page.restore_record(record):
            return
        self.reports_page.refresh_report()
        self.reload_rows()

    def delete_selected_record(self):
        record = self._get_selected_record()
        if not record:
            QMessageBox.information(self, 'Delete Record', 'Select an archived patient record to delete.')
            return
        label = f"{record['name'] or 'Unknown Patient'} ({record['patient_id'] or 'No ID'})"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle('Delete Archived Record')
        box.setText(f'Permanently delete {label}?')
        box.setInformativeText('This action cannot be undone.')
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        if not self.reports_page.delete_archived_record(record):
            QMessageBox.warning(self, 'Delete Record', 'Unable to permanently delete the selected record.')
            return
        self.reports_page.refresh_report()
        self.reload_rows()

class ReportsPage(QWidget):
    """Reports page with local offline statistics."""

    def __init__(self, username: str='', role: str='clinician', display_name: str='', specialization: str=''):
        super().__init__()
        self.username = username or os.environ.get('EYESHIELD_CURRENT_USER', '')
        self.display_name = display_name or os.environ.get('EYESHIELD_CURRENT_NAME', '') or self.username
        self.role = role or os.environ.get('EYESHIELD_CURRENT_ROLE', 'clinician')
        self.specialization = str(specialization or os.environ.get('EYESHIELD_CURRENT_SPECIALIZATION', '')).strip()
        self.display_title = self.specialization if self.role == 'clinician' and self.specialization else self.role
        self.is_admin = self.role == 'admin'
        self.records_changed_callback = None
        self.archived_records_dialog = None
        self._summary_cache = {}
        self._all_result_rows = []
        self._filtered_rows = []
        self._record_lookup = {}
        self._display_row_lookup = {}
        self.setStyleSheet("\n            QWidget {\n                background: #f2f6fb;\n                color: #1f2a37;\n                font-family: 'Segoe UI';\n            }\n            QGroupBox {\n                background: #ffffff;\n                border: 1px solid #d8e2ee;\n                border-radius: 14px;\n            }\n            QLineEdit, QComboBox {\n                background: #ffffff;\n                border: 1px solid #c7d5e6;\n                border-radius: 10px;\n                padding: 8px 12px;\n            }\n            QLineEdit:hover, QComboBox:hover {\n                border: 1px solid #9eb9d8;\n            }\n            QLineEdit:focus, QComboBox:focus {\n                border: 1px solid #1f6fe5;\n            }\n            QTableWidget {\n                background: #ffffff;\n                border: 1px solid #d3deeb;\n                border-radius: 12px;\n                gridline-color: #edf2f7;\n                alternate-background-color: #f7fafd;\n                selection-background-color: #e8f0ff;\n                selection-color: #1f2a37;\n                padding: 4px;\n            }\n            QTableWidget::item {\n                padding: 10px 8px;\n                border: none;\n            }\n            QHeaderView::section {\n                background: #f3f7fc;\n                color: #3d526b;\n                border: none;\n                border-bottom: 1px solid #dbe6f2;\n                padding: 12px 8px;\n                font-weight: 700;\n            }\n            QPushButton:focus, QTableWidget:focus {\n                border: 1px solid #1f6fe5;\n            }\n            QPushButton {\n                background: #ffffff;\n                border: 1px solid #bfdbfe;\n                color: #0f172a;\n                border-radius: 8px;\n                padding: 8px 14px;\n                font-size: 13px;\n                font-family: 'Segoe UI';\n                font-weight: 600;\n            }\n            QPushButton:hover {\n                background: #eff6ff;\n                border: 1px solid #93c5fd;\n            }\n            QPushButton:disabled {\n                background: #f8fafc;\n                border: 1px solid #dbeafe;\n                color: #9ca3af;\n            }\n            QLabel#statusLabel {\n                color: #4f637a;\n                font-size: 12px;\n            }\n            QLabel#hintLabel {\n                color: #62788f;\n                font-size: 12px;\n            }\n        ")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(18)
        self._rep_title_lbl = QLabel('')
        self._rep_title_lbl.setObjectName('pageHeader')
        self._rep_title_lbl.setStyleSheet("font-size:26px;font-weight:700;color:#1f6fe5;font-family:'Segoe UI';")
        self._rep_subtitle_lbl = QLabel('')
        self._rep_subtitle_lbl.setObjectName('pageSubtitle')
        self._rep_subtitle_lbl.setStyleSheet('font-size:13px;color:#6b7f95;')
        self._rep_subtitle_lbl.setAlignment(Qt.AlignLeft)
        self._rep_title_lbl.hide()
        self.export_btn = QPushButton('Export Results')
        self.export_btn.setAutoDefault(True)
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self.export_summary)
        if self.is_admin:
            self.archive_btn = QPushButton('Archive Selected')
            self.archive_btn.clicked.connect(self.archive_selected_record)
            self.archive_btn.setEnabled(False)
        else:
            self.archive_btn = None
        if self.is_admin:
            self.archived_records_btn = QPushButton('Archived Records')
            self.archived_records_btn.clicked.connect(self.open_archived_records_window)
        else:
            self.archived_records_btn = None
        self.report_btn = QPushButton('Generate Report')
        self.report_btn.setEnabled(False)
        self.report_btn.clicked.connect(self.generate_report)
        self._rep_subtitle_lbl.hide()
        self.status_label = QLabel('')
        self.status_label.setObjectName('statusLabel')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet('color:#4f637a;background:#eaf1fb;border:1px solid #d4e2f3;border-radius:10px;padding:8px 12px;')
        self.status_label.hide()
        root.addWidget(self.status_label)
        self._controls_group = QGroupBox('')
        cl = QHBoxLayout(self._controls_group)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(14)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search')
        self.search_input.setMinimumHeight(40)
        self.search_input.textChanged.connect(self.apply_filters)
        cl.addWidget(self.search_input, 1)
        self.result_filter = QComboBox()
        self.result_filter.addItems(['All', 'No DR', 'Mild DR', 'Moderate DR', 'Severe DR', 'Proliferative DR'])
        self.result_filter.setMinimumHeight(40)
        self.result_filter.currentTextChanged.connect(self.apply_filters)
        cl.addWidget(self.result_filter)
        cl.addStretch(1)
        if self.archive_btn is not None:
            cl.addWidget(self.archive_btn)
        if self.archived_records_btn is not None:
            cl.addWidget(self.archived_records_btn)
        cl.addWidget(self.export_btn)
        cl.addWidget(self.report_btn)
        root.addWidget(self._controls_group)
        self._results_group = QGroupBox('')
        rl = QVBoxLayout(self._results_group)
        rl.setContentsMargins(18, 16, 18, 18)
        rl.setSpacing(14)
        self.results_table = QTableWidget(0, 7)
        self.results_table.setHorizontalHeaderLabels(['Patient ID', 'Name', 'Eye Screened', 'Screening Date', 'Result', 'Confidence', 'Screened by'])
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setShowGrid(False)
        self.results_table.setSortingEnabled(True)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.verticalHeader().setDefaultSectionSize(42)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SingleSelection)
        self.results_table.itemSelectionChanged.connect(self._update_action_buttons)
        self.results_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self._open_results_context_menu)
        self.results_table.doubleClicked.connect(self._on_table_row_double_clicked)
        self.results_table.setMinimumHeight(420)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        rl.addWidget(self.results_table)
        root.addWidget(self._results_group)
        self.setTabOrder(self.export_btn, self.report_btn)
        self.setTabOrder(self.report_btn, self.search_input)
        self.setTabOrder(self.search_input, self.result_filter)
        self.setTabOrder(self.result_filter, self.results_table)
        self._setup_action_buttons_ui()
        self.refresh_report()

    def _icon_path(self, filename: str) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons', filename)

    def _set_button_icon(self, button: QPushButton, icon_name: str):
        icon_file = self._icon_path(icon_name)
        if os.path.exists(icon_file):
            base_icon = QIcon(icon_file)
            source = base_icon.pixmap(QSize(24, 24))
            if source.isNull():
                button.setIcon(base_icon)
                button.setIconSize(QSize(24, 24))
                return

            def _tint(color_hex: str) -> QPixmap:
                tinted = QPixmap(source.size())
                tinted.fill(Qt.GlobalColor.transparent)
                painter = QPainter(tinted)
                painter.drawPixmap(0, 0, source)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(tinted.rect(), QColor(color_hex))
                painter.end()
                return tinted
            icon = QIcon()
            icon.addPixmap(_tint('#60a5fa'), QIcon.Mode.Normal, QIcon.State.Off)
            icon.addPixmap(_tint('#3b82f6'), QIcon.Mode.Active, QIcon.State.Off)
            icon.addPixmap(_tint('#bfdbfe'), QIcon.Mode.Disabled, QIcon.State.Off)
            button.setIcon(icon)
            button.setIconSize(QSize(22, 22))

    def _setup_action_buttons_ui(self):
        self._set_button_icon(self.export_btn, 'export.svg')
        self._set_button_icon(self.report_btn, 'generate_report.svg')
        self.export_btn.setText('Export')
        self.report_btn.setText('Report')
        self.export_btn.setToolTip('Export currently visible report rows to CSV')
        self.report_btn.setToolTip('Generate a detailed PDF report for the selected patient')
        if self.archived_records_btn is not None:
            self._set_button_icon(self.archived_records_btn, 'archives.svg')
            self.archived_records_btn.setText('Archived Records')
            self.archived_records_btn.setToolTip('Open archived records and restore or delete entries')
        if self.archive_btn is not None:
            self._set_button_icon(self.archive_btn, 'archive.svg')
            self.archive_btn.setText('Archive')
            self.archive_btn.setToolTip('Archive the selected active patient record')
        top_icon_buttons = [self.export_btn, self.report_btn]
        if self.archive_btn is not None:
            top_icon_buttons.append(self.archive_btn)
        if self.archived_records_btn is not None:
            top_icon_buttons.append(self.archived_records_btn)
        for button in top_icon_buttons:
            button.setMinimumHeight(40)

    def refresh_report(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute('\n                SELECT id, patient_id, name, eyes, screened_at, result, confidence, diabetes_type, hba1c,\n                       ai_classification, doctor_classification, decision_mode, override_justification, final_diagnosis_icdr, doctor_findings,\n                       archived_at, archived_by, archive_reason,\n                       original_screener_username, original_screener_name\n                FROM patient_records ORDER BY id DESC\n            ')
            rows = [{'id': r[0], 'patient_id': r[1], 'name': r[2], 'eyes': r[3], 'screened_at': r[4], 'result': r[5], 'confidence': r[6], 'diabetes_type': r[7], 'hba1c': r[8], 'ai_classification': r[9], 'doctor_classification': r[10], 'decision_mode': r[11], 'override_justification': r[12], 'final_diagnosis_icdr': r[13], 'doctor_findings': r[14], 'archived_at': r[15], 'archived_by': r[16], 'archive_reason': r[17], 'original_screener_username': r[18], 'original_screener_name': r[19]} for r in cur.fetchall()]
            for row in rows:
                row['result'] = row.get('final_diagnosis_icdr') or row.get('doctor_classification') or row.get('result') or ''
            conn.close()
        except Exception as err:
            QMessageBox.warning(self, 'Reports', f'Failed to load report data: {err}')
            return
        self._all_result_rows = rows
        self._record_lookup = {r['id']: r for r in rows}
        self.apply_filters()
        if self.archived_records_dialog is not None:
            self.archived_records_dialog.reload_rows()
        self.status_label.setText('')

    @staticmethod
    def _eye_sort_key(eye_value: str) -> tuple[int, str]:
        eye = str(eye_value or '').strip().lower()
        if 'right' in eye:
            return (0, eye)
        if 'left' in eye:
            return (1, eye)
        return (2, eye)

    @staticmethod
    def _format_screening_datetime(value: str) -> str:
        raw = str(value or '').strip()
        if not raw:
            return '—'
        parsed = None
        normalized = raw.replace('Z', '+00:00')
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            return raw
        hour = parsed.strftime('%I').lstrip('0') or '0'
        return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year} - {hour}:{parsed.strftime('%M')} {parsed.strftime('%p').lower()}"

    def _build_display_rows(self, rows: list[dict]) -> list[dict]:
        grouped: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            key = (str(row.get('patient_id') or '').strip(), str(row.get('screened_at') or '').strip())
            grouped.setdefault(key, []).append(row)
        display_rows = []
        for key, grouped_rows in grouped.items():
            ordered_rows = sorted(grouped_rows, key=lambda item: (self._eye_sort_key(item.get('eyes')), -int(item.get('id') or 0)))
            primary = ordered_rows[0]
            owner_name = str(primary.get('original_screener_name') or '').strip()
            owner_username = str(primary.get('original_screener_username') or '').strip()
            screened_by_display = self._format_doctor_label(owner_name or owner_username)
            record_ids = [int(item.get('id') or 0) for item in ordered_rows if int(item.get('id') or 0)]
            selection_key = f"{key[0]}|{key[1]}|{'-'.join((str(i) for i in record_ids))}"
            eyes_text = '\n'.join((str(item.get('eyes') or '—') for item in ordered_rows))
            date_values = [str(item.get('screened_at') or '').strip() for item in ordered_rows]
            date_values = [value for value in date_values if value]
            if date_values:
                unique_dates = list(dict.fromkeys(date_values))
                date_text = '\n'.join((self._format_screening_datetime(value) for value in unique_dates))
            else:
                date_text = '—'
            result_text = '\n'.join((str(item.get('final_diagnosis_icdr') or item.get('doctor_classification') or item.get('result') or '—') for item in ordered_rows))
            confidence_text = '\n'.join((str(item.get('confidence') or '—') for item in ordered_rows))
            combined_search = ' '.join([str(primary.get('patient_id') or ''), str(primary.get('name') or ''), eyes_text, date_text, result_text, confidence_text, str(primary.get('final_diagnosis_icdr') or ''), str(primary.get('doctor_classification') or ''), str(primary.get('doctor_findings') or ''), screened_by_display]).lower()
            display_rows.append({'selection_key': selection_key, 'id': primary.get('id'), 'patient_id': primary.get('patient_id'), 'name': primary.get('name'), 'eyes': eyes_text, 'screened_at': date_text, 'result': result_text, 'confidence': confidence_text, 'final_diagnosis_icdr': primary.get('final_diagnosis_icdr'), 'doctor_classification': primary.get('doctor_classification'), 'decision_mode': primary.get('decision_mode'), 'override_justification': primary.get('override_justification'), 'doctor_findings': primary.get('doctor_findings'), 'screened_by': screened_by_display, 'diabetes_type': primary.get('diabetes_type'), 'hba1c': primary.get('hba1c'), 'archived_at': primary.get('archived_at'), 'archived_by': primary.get('archived_by'), 'archive_reason': primary.get('archive_reason'), 'original_screener_username': primary.get('original_screener_username'), 'original_screener_name': primary.get('original_screener_name'), 'record_ids': record_ids, 'source_rows': ordered_rows, '_search_text': combined_search})
        display_rows.sort(key=lambda item: max(item.get('record_ids') or [0]), reverse=True)
        self._display_row_lookup = {row['selection_key']: row for row in display_rows}
        return display_rows

    def apply_filters(self):
        query = self.search_input.text().strip().lower() if hasattr(self, 'search_input') else ''
        mode = self.result_filter.currentText() if hasattr(self, 'result_filter') else 'All'
        active_rows = [row for row in self._all_result_rows if not row['archived_at']]
        display_rows = self._build_display_rows(active_rows)
        filtered = []
        for row in display_rows:
            source_rows = row.get('source_rows') or []
            if not source_rows:
                continue
            if query and query not in str(row.get('_search_text') or ''):
                continue
            result_blob = ' '.join((str(item.get('result') or '') for item in source_rows)).lower()
            if mode == 'No DR' and 'no dr' not in result_blob:
                continue
            if mode == 'Mild DR' and 'mild' not in result_blob:
                continue
            if mode == 'Moderate DR' and 'moderate' not in result_blob:
                continue
            if mode == 'Severe DR' and 'severe' not in result_blob:
                continue
            if mode == 'Proliferative DR' and 'proliferative' not in result_blob:
                continue
            filtered.append(row)
        self._filtered_rows = filtered
        self._update_summary_cards(filtered)
        self._render_results_table()

    def _render_results_table(self):
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)
        result_color = self._result_color_for_current_theme
        for row in self._filtered_rows:
            i = self.results_table.rowCount()
            self.results_table.insertRow(i)
            item = QTableWidgetItem(str(row['patient_id'] or ''))
            item.setData(Qt.UserRole, row['selection_key'])
            item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(i, 0, item)
            name_item = QTableWidgetItem(str(row['name'] or ''))
            name_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(i, 1, name_item)
            eyes_item = QTableWidgetItem(str(row.get('eyes') or ''))
            eyes_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(i, 2, eyes_item)
            screened_at_item = QTableWidgetItem(str(row.get('screened_at') or ''))
            screened_at_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(i, 3, screened_at_item)
            ri = QTableWidgetItem(str(row['result'] or ''))
            ri.setTextAlignment(Qt.AlignCenter)
            if any((self._is_high_attention_result(item.get('result')) for item in row.get('source_rows') or [])):
                ri.setForeground(result_color('high'))
            elif all(('no dr' in str(item.get('result') or '').lower() for item in row.get('source_rows') or [])):
                ri.setForeground(result_color('normal'))
            self.results_table.setItem(i, 4, ri)
            confidence_item = QTableWidgetItem(str(row['confidence'] or ''))
            confidence_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(i, 5, confidence_item)
            screened_by_item = QTableWidgetItem(str(row.get('screened_by') or '--'))
            screened_by_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(i, 6, screened_by_item)
        self.results_table.setSortingEnabled(True)
        self.results_table.resizeRowsToContents()
        if hasattr(self, 'filtered_count_label'):
            self.filtered_count_label.setText(f'Total: {len(self._filtered_rows)}')
        self._update_action_buttons()

    def _result_color_for_current_theme(self, level: str) -> QColor:
        window = self.palette().color(self.backgroundRole())
        is_dark = window.value() < 128
        if level == 'high':
            return QColor('#fca5a5') if is_dark else QColor('#991b1b')
        return QColor('#86efac') if is_dark else QColor('#166534')

    def _update_summary_cards(self, rows):
        total = len(rows)
        self._summary_cache = {'total_screenings': total}

    @staticmethod
    def _format_doctor_label(name_value: str) -> str:
        name = str(name_value or '').strip()
        if not name:
            return '--'
        if name.lower().startswith('dr'):
            return name
        return f'Dr. {name}'

    def _can_rescreen_record(self, record: dict) -> bool:
        owner_username = str(record.get('original_screener_username') or '').strip().lower()
        if not owner_username:
            return True
        return owner_username == str(self.username or '').strip().lower()

    def _record_owner_label(self, record: dict) -> str:
        owner_name = str(record.get('original_screener_name') or '').strip()
        owner_username = str(record.get('original_screener_username') or '').strip()
        return owner_name or owner_username or 'original screener'

    def _open_results_context_menu(self, pos):
        item = self.results_table.itemAt(pos)
        if item is None:
            return
        self.results_table.selectRow(item.row())
        record = self._get_selected_record()
        if not record:
            return
        menu = QMenu(self)
        view_action = menu.addAction('View Details')
        menu.addSeparator()
        generate_action = menu.addAction('Generate Report')
        archive_action = None
        if self.is_admin:
            archive_action = menu.addAction('Archive Record')
            archive_action.setEnabled(not bool(record.get('archived_at')))
        chosen = menu.exec(self.results_table.viewport().mapToGlobal(pos))
        if chosen == view_action:
            self._show_patient_details()
        elif chosen == generate_action:
            self.generate_report()
        elif archive_action is not None and chosen == archive_action:
            self.archive_selected_record()

    def _get_selected_record(self):
        r = self.results_table.currentRow()
        if r < 0:
            return None
        item = self.results_table.item(r, 0)
        return self._display_row_lookup.get(item.data(Qt.UserRole)) if item else None

    def _update_action_buttons(self):
        record = self._get_selected_record()
        self.report_btn.setEnabled(bool(record))

    def _on_table_row_double_clicked(self, index):
        """Handle double-click on table row to show patient details."""
        self._show_patient_details()

    def _show_patient_details(self):
        """Show view-only patient details dialog."""
        record = self._get_selected_record()
        if not record:
            return
        record_id = record.get('id') or (record.get('record_ids')[0] if record.get('record_ids') else None)
        if not record_id:
            QMessageBox.warning(self, 'Patient Details', 'Unable to retrieve patient record.')
            return
        full_record = self._fetch_full_patient_record(record_id)
        if not full_record:
            QMessageBox.warning(self, 'Patient Details', 'Unable to load patient details.')
            return
        UserManager.add_activity_log(self.username, f"RECORD_OPENED patient_id={full_record.get('patient_id')}; record_id={record_id}; source=reports")
        dialog = PatientDetailsDialog(full_record, self)
        dialog.exec()

    def _fetch_full_patient_record(self, record_id: int) -> dict:
        """Fetch complete patient record from database."""
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute('\n                SELECT id, patient_id, name, birthdate, age, sex, contact, eyes, \n                       diabetes_type, duration, hba1c, prev_treatment, notes, \n                       result, confidence, screened_at, archived_at, archived_by, \n                       archive_reason, original_screener_username, original_screener_name,\n                       ai_classification, doctor_classification, decision_mode, override_justification, final_diagnosis_icdr, doctor_findings,\n                       height, weight, bmi, visual_acuity_left, visual_acuity_right,\n                       blood_pressure_systolic, blood_pressure_diastolic,\n                       fasting_blood_sugar, random_blood_sugar,\n                       diabetes_diagnosis_date, treatment_regimen, prev_dr_stage,\n                       symptom_blurred_vision, symptom_floaters, symptom_flashes,\n                       symptom_vision_loss, source_image_path\n                FROM patient_records\n                WHERE id = ?\n            ', (record_id,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            return {'id': row[0], 'patient_id': row[1], 'name': row[2], 'birthdate': row[3], 'age': row[4], 'sex': row[5], 'contact': row[6], 'eyes': row[7], 'diabetes_type': row[8], 'duration': row[9], 'hba1c': row[10], 'prev_treatment': row[11], 'notes': row[12], 'result': row[13], 'confidence': row[14], 'screened_at': row[15], 'archived_at': row[16], 'archived_by': row[17], 'archive_reason': row[18], 'original_screener_username': row[19], 'original_screener_name': row[20], 'ai_classification': row[21], 'doctor_classification': row[22], 'decision_mode': row[23], 'override_justification': row[24], 'final_diagnosis_icdr': row[25], 'doctor_findings': row[26], 'height': row[27], 'weight': row[28], 'bmi': row[29], 'visual_acuity_left': row[30], 'visual_acuity_right': row[31], 'blood_pressure_systolic': row[32], 'blood_pressure_diastolic': row[33], 'fasting_blood_sugar': row[34], 'random_blood_sugar': row[35], 'diabetes_diagnosis_date': row[36], 'treatment_regimen': row[37], 'prev_dr_stage': row[38], 'symptom_blurred_vision': row[39], 'symptom_floaters': row[40], 'symptom_flashes': row[41], 'symptom_vision_loss': row[42], 'source_image_path': row[43]}
        except Exception as err:
            print(f'Error fetching patient record: {err}')
            return None

    def open_archived_records_window(self):
        self.refresh_report()
        if self.archived_records_dialog is None:
            self.archived_records_dialog = ArchivedRecordsDialog(self)
        self.archived_records_dialog.reload_rows()
        self.archived_records_dialog.show()
        self.archived_records_dialog.raise_()
        self.archived_records_dialog.activateWindow()

    def archive_selected_record(self):
        record = self._get_selected_record()
        if not record:
            QMessageBox.information(self, 'Archive Record', 'Select a patient record to archive.')
            return
        if record['archived_at']:
            QMessageBox.information(self, 'Archive Record', 'The selected patient record is already archived.')
            return
        label = f"{record['name'] or 'Unknown Patient'} ({record['patient_id'] or 'No ID'})"
        if QMessageBox.question(self, 'Archive Record', f'Archive {label}?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if not self._set_records_archive_state(record.get('record_ids') or [record['id']], archived=True):
            QMessageBox.warning(self, 'Archive Record', 'Unable to archive the selected patient record.')
            return
        self.refresh_report()

    def restore_record(self, record):
        if not record or not record['archived_at']:
            QMessageBox.information(self, 'Restore Record', 'The selected patient record is already active.')
            return False
        label = f"{record['name'] or 'Unknown Patient'} ({record['patient_id'] or 'No ID'})"
        if QMessageBox.question(self, 'Restore Record', f'Restore {label}?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return False
        if not self._set_record_archive_state(record['id'], archived=False):
            QMessageBox.warning(self, 'Restore Record', 'Unable to restore the selected patient record.')
            return False
        return True

    def delete_archived_record(self, record):
        if not record or not record['archived_at']:
            return False
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute('DELETE FROM patient_records WHERE id=? AND archived_at IS NOT NULL', (record['id'],))
            conn.commit()
            success = cur.rowcount > 0
            conn.close()
        except Exception:
            return False
        if success and callable(self.records_changed_callback):
            self.records_changed_callback()
        return success

    def _set_record_archive_state(self, record_id, archived: bool) -> bool:
        return self._set_records_archive_state([record_id], archived=archived)

    def _set_records_archive_state(self, record_ids, archived: bool) -> bool:
        actor_name = self.display_name or os.environ.get('EYESHIELD_CURRENT_NAME', '') or self.username
        actor_title = self.display_title or os.environ.get('EYESHIELD_CURRENT_TITLE', '')
        actor = f'{actor_name} ({actor_title})' if actor_name and actor_title else actor_name
        valid_ids = [int(record_id) for record_id in record_ids if int(record_id)]
        if not valid_ids:
            return False
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            placeholders = ','.join(('?' for _ in valid_ids))
            cur.execute(f'SELECT id, patient_id FROM patient_records WHERE id IN ({placeholders})', valid_ids)
            affected_rows = cur.fetchall()
            if archived:
                cur.execute(f'UPDATE patient_records SET archived_at=?,archived_by=?,archive_reason=? WHERE id IN ({placeholders})', [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), actor, None, *valid_ids])
            else:
                cur.execute(f'UPDATE patient_records SET archived_at=NULL,archived_by=NULL,archive_reason=NULL WHERE id IN ({placeholders})', valid_ids)
            conn.commit()
            success = cur.rowcount > 0
            conn.close()
        except Exception:
            return False
        if success and callable(self.records_changed_callback):
            self.records_changed_callback()
        if success:
            event = 'RECORD_ARCHIVED' if archived else 'RECORD_RESTORED'
            for rec_id, patient_id in affected_rows:
                UserManager.add_activity_log(self.username, f'{event} patient_id={patient_id}; record_id={rec_id}')
        return success

    @staticmethod
    def _is_high_attention_result(result_text):
        return any((k in str(result_text or '').lower() for k in ('moderate', 'severe', 'proliferative', 'refer', 'urgent', 'dr detected')))

    def export_summary(self):
        if not self._summary_cache:
            self.status_label.setText('No report data to export')
            return
        if not self._filtered_rows:
            self.status_label.setText('No visible report data to export')
            return
        confirm = QMessageBox.question(self, 'Export Reports', f'Export {len(self._filtered_rows)} visible report row(s) to CSV?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export DR Screening Results', '', 'CSV Files (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['Patient ID', 'Name', 'Eye Screened', 'Screening Date', 'AI Classification', 'Doctor Classification', 'Final Diagnosis (ICDR)', 'Doctor Findings', 'Decision Mode', 'Override Justification', 'Confidence', 'Diabetes Type', 'HbA1c', 'Record Status', 'Archived At', 'Archived By'])
                for row in self._filtered_rows:
                    w.writerow([row['patient_id'], row['name'], row.get('eyes', ''), row.get('screened_at', ''), row.get('ai_classification', ''), row.get('doctor_classification', ''), row.get('final_diagnosis_icdr', ''), row.get('doctor_findings', ''), row.get('decision_mode', ''), row.get('override_justification', ''), row['confidence'], row['diabetes_type'], row['hba1c'], 'Archived' if row['archived_at'] else 'Active', row['archived_at'], row['archived_by']])
            self.status_label.setText(f'Exported {len(self._filtered_rows)} rows to {path}')
            UserManager.add_activity_log(self.username, f'REPORT_EXPORT_CSV rows={len(self._filtered_rows)}; path={os.path.basename(path)}')
        except OSError as err:
            QMessageBox.warning(self, 'Export', f'Failed to export summary: {err}')

    def apply_language(self, language: str):
        from translations import get_pack
        pack = get_pack(language)
        self._rep_title_lbl.setText('')
        self._rep_subtitle_lbl.setText('')
        self._controls_group.setTitle('')
        self._results_group.setTitle('')
        self._setup_action_buttons_ui()

    def _fetch_full_record(self, record_id: int) -> 'dict | None':
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute('\n                SELECT id, patient_id, name, birthdate, age, sex, contact, eyes,\n                      diabetes_type, duration, hba1c, prev_treatment, notes,\n                      result, confidence, screened_at,\n                      ai_classification, doctor_classification, decision_mode, override_justification, final_diagnosis_icdr, doctor_findings,\n                       visual_acuity_left, visual_acuity_right,\n                       blood_pressure_systolic, blood_pressure_diastolic,\n                       fasting_blood_sugar, random_blood_sugar,\n                       symptom_blurred_vision, symptom_floaters,\n                      symptom_flashes, symptom_vision_loss,\n                      source_image_path, heatmap_image_path,\n                      image_sha256, image_saved_at,\n                      original_screener_username, original_screener_name\n                FROM patient_records WHERE id=?\n            ', (record_id,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            return {'id': row[0], 'patient_id': row[1], 'name': row[2], 'birthdate': row[3], 'age': row[4], 'sex': row[5], 'contact': row[6], 'eyes': row[7], 'diabetes_type': row[8], 'duration': row[9], 'hba1c': row[10], 'prev_treatment': row[11], 'notes': row[12], 'result': row[13], 'confidence': row[14], 'screened_at': row[15], 'ai_classification': row[16], 'doctor_classification': row[17], 'decision_mode': row[18], 'override_justification': row[19], 'final_diagnosis_icdr': row[20], 'doctor_findings': row[21], 'va_left': row[22], 'va_right': row[23], 'bp_systolic': row[24], 'bp_diastolic': row[25], 'fbs': row[26], 'rbs': row[27], 'symptom_blurred': row[28], 'symptom_floaters': row[29], 'symptom_flashes': row[30], 'symptom_vision_loss': row[31], 'source_image_path': row[32], 'heatmap_image_path': row[33], 'image_sha256': row[34], 'image_saved_at': row[35], 'original_screener_username': row[36], 'original_screener_name': row[37]}
        except Exception:
            return None

    def _fetch_report_eye_records(self, patient_id: str, screened_at: str, fallback_record_id: int) -> list[dict]:

        def eye_sort_key(record: dict) -> tuple[int, str]:
            eye = str(record.get('eyes') or '').strip().lower()
            if 'right' in eye:
                return (0, eye)
            if 'left' in eye:
                return (1, eye)
            return (2, eye)
        patient_id = str(patient_id or '').strip()
        screened_at = str(screened_at or '').strip()
        if not patient_id:
            single = self._fetch_full_record(fallback_record_id)
            return [single] if single else []
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            if screened_at:
                cur.execute('\n                    SELECT id\n                    FROM patient_records\n                    WHERE patient_id = ? AND screened_at = ?\n                    ORDER BY id ASC\n                    ', (patient_id, screened_at))
            else:
                cur.execute('\n                    SELECT id\n                    FROM patient_records\n                    WHERE patient_id = ?\n                    ORDER BY id DESC\n                    LIMIT 2\n                    ', (patient_id,))
            rows = cur.fetchall()
            conn.close()
        except Exception:
            rows = []
        records = []
        for row in rows:
            full_record = self._fetch_full_record(int(row[0]))
            if full_record:
                records.append(full_record)
        if not records:
            single = self._fetch_full_record(fallback_record_id)
            records = [single] if single else []
        unique_records = []
        seen_ids = set()
        for record in records:
            record_id = record.get('id')
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            unique_records.append(record)
        return sorted(unique_records, key=eye_sort_key)

    def generate_report(self):
        record = self._get_selected_record()
        if not record:
            QMessageBox.information(self, 'Generate Report', 'Select a patient record to generate a report for.')
            return
        patient_name_raw = str(record.get('name') or 'Patient').strip()
        default_name = f"EyeShield_Report_{patient_name_raw}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, 'Save Patient Report', default_name, 'PDF Files (*.pdf)')
        if not path:
            return
        try:
            from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument
            from PySide6.QtCore import QMarginsF
        except ImportError:
            QMessageBox.warning(self, 'Generate Report', 'PDF generation requires PySide6 PDF support.')
            return
        full = self._fetch_full_record(record['id']) or record
        eye_records = self._fetch_report_eye_records(full.get('patient_id'), full.get('screened_at'), int(full.get('id') or record['id']))
        if not eye_records:
            eye_records = [full]
        severity_rank = {'No DR': 0, 'Mild DR': 1, 'Moderate DR': 2, 'Severe DR': 3, 'Proliferative DR': 4}

        def pick_worst_grade(values: list[str]) -> str:
            best = ''
            best_rank = -1
            for raw in values:
                value = str(raw or '').strip()
                rank = severity_rank.get(value, -1)
                if rank > best_rank:
                    best = value
                    best_rank = rank
            return best
        bilateral_grades = []
        for eye_record in eye_records:
            grade = str(eye_record.get('final_diagnosis_icdr') or '').strip() or str(eye_record.get('doctor_classification') or '').strip() or str(eye_record.get('ai_classification') or '').strip() or str(eye_record.get('result') or '').strip()
            if grade:
                bilateral_grades.append(grade)
        bilateral_worst_grade = pick_worst_grade(bilateral_grades)

        def esc(v) -> str:
            s = str(v or '').strip()
            return escape(s) if s and s not in ('0', 'None', 'Select', '-') else '&#8212;'
        clinic_name = 'EyeShield EMR'
        try:
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'config.json')
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            clinic_name = cfg.get('clinic_name') or clinic_name
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        raw_conf = str(full.get('confidence') or '').strip()
        if raw_conf.lower().startswith('confidence:'):
            raw_conf = raw_conf[len('confidence:'):].strip()
        conf_display = escape(raw_conf) if raw_conf else '&#8212;'
        ai_result_raw = str(full.get('ai_classification') or full.get('result') or '').strip()
        doctor_result_raw = str(full.get('doctor_classification') or full.get('result') or '').strip()
        decision_mode_raw = str(full.get('decision_mode') or 'accepted').strip().lower()
        override_reason_raw = str(full.get('override_justification') or '').strip()
        final_dx_raw = str(full.get('final_diagnosis_icdr') or doctor_result_raw or ai_result_raw).strip()
        if bilateral_worst_grade and severity_rank.get(bilateral_worst_grade, -1) > severity_rank.get(final_dx_raw, -1):
            final_dx_raw = bilateral_worst_grade
        doctor_findings_raw = str(full.get('doctor_findings') or '').strip()
        result_raw = final_dx_raw or doctor_result_raw or ai_result_raw
        if result_raw == 'No DR':
            rec = 'Annual screening recommended.'
            summary = 'No signs of diabetic retinopathy were detected in this fundus image. Continue standard diabetes management, maintain optimal glycaemic and blood pressure control, and schedule routine annual retinal screening.'
        elif result_raw == 'Mild DR':
            rec = 'Repeat screening in 6&#8211;12 months.'
            summary = 'Early microaneurysms consistent with mild non-proliferative diabetic retinopathy (NPDR) were identified. Intensify glycaemic and blood pressure management. A repeat retinal examination in 6&#8211;12 months is recommended.'
        elif result_raw == 'Moderate DR':
            rec = 'Ophthalmology referral within 3 months.'
            summary = 'Features consistent with moderate non-proliferative diabetic retinopathy (NPDR) were detected, including microaneurysms, haemorrhages, and/or hard exudates. Referral to an ophthalmologist within 3 months is advised. Reassess systemic metabolic control.'
        elif result_raw == 'Severe DR':
            rec = 'Urgent ophthalmology referral required.'
            summary = 'Findings consistent with severe non-proliferative diabetic retinopathy (NPDR) were detected. The risk of progression to proliferative disease within 12 months is high. Urgent ophthalmology referral is required.'
        elif result_raw == 'Proliferative DR':
            rec = 'Immediate ophthalmology referral required.'
            summary = 'Proliferative diabetic retinopathy (PDR) was detected &#8212; a sight-threatening condition. Immediate ophthalmology referral is required for evaluation and potential intervention, such as laser photocoagulation or intravitreal anti-VEGF therapy.'
        else:
            rec = 'Consult a qualified ophthalmologist.'
            summary = 'Please consult a qualified ophthalmologist for further evaluation.'
        report_date = datetime.now().strftime('%B %d, %Y  %I:%M %p')
        screening_date = str(full.get('screened_at') or '').strip() or report_date
        created_by_raw = str(full.get('original_screener_name') or full.get('original_screener_username') or '').strip()
        finalized_by_raw = str(self.display_name or os.environ.get('EYESHIELD_CURRENT_NAME', '') or self.username).strip()
        created_by = escape(self._format_doctor_label(created_by_raw or finalized_by_raw))
        finalized_by = escape(self._format_doctor_label(finalized_by_raw))
        dur_raw = str(full.get('duration') or '').strip()
        dur_disp = f'{escape(dur_raw)} year(s)' if dur_raw and dur_raw != '0' else '&#8212;'
        notes_raw = str(full.get('notes') or '').strip()
        other_symptom_lines = []
        note_lines = []
        for raw_line in notes_raw.splitlines():
            line = str(raw_line or '').strip()
            if not line:
                continue
            if line.lower().startswith('other symptom:'):
                value = line.split(':', 1)[1].strip() if ':' in line else ''
                if value:
                    other_symptom_lines.append(value)
                continue
            note_lines.append(line)
        notes_clean = '\n'.join(note_lines).strip()
        notes_disp = escape(notes_clean) if notes_clean else '<span style="color:#9ca3af;font-style:italic;">None recorded</span>'
        other_symptom_disp = '<br>'.join((escape(item) for item in other_symptom_lines)) if other_symptom_lines else '<span style="color:#9ca3af;font-style:italic;">None recorded</span>'
        bp_s = str(full.get('blood_pressure_systolic') or full.get('bp_systolic') or '').strip()
        bp_d = str(full.get('blood_pressure_diastolic') or full.get('bp_diastolic') or '').strip()
        bp_disp = f'{escape(bp_s)}/{escape(bp_d)} mmHg' if bp_s and bp_s != '0' and bp_d and (bp_d != '0') else '&#8212;'
        va_l = esc(full.get('visual_acuity_left') or full.get('va_left'))
        va_r = esc(full.get('visual_acuity_right') or full.get('va_right'))
        fbs_r = str(full.get('fasting_blood_sugar') or full.get('fbs') or '').strip()
        rbs_r = str(full.get('random_blood_sugar') or full.get('rbs') or '').strip()
        fbs_disp = f'{escape(fbs_r)} mg/dL' if fbs_r and fbs_r != '0' else '&#8212;'
        rbs_disp = f'{escape(rbs_r)} mg/dL' if rbs_r and rbs_r != '0' else '&#8212;'
        height_r = str(full.get('height') or '').strip()
        weight_r = str(full.get('weight') or '').strip()
        bmi_r = str(full.get('bmi') or '').strip()
        height_disp = f'{escape(height_r)} cm' if height_r and height_r != '0' else '&#8212;'
        weight_disp = f'{escape(weight_r)} kg' if weight_r and weight_r != '0' else '&#8212;'

        def get_bmi_category(bmi_value: str) -> tuple:
            """Return (category, color) based on WHO BMI classification."""
            try:
                bmi = float(bmi_value)
                if bmi < 18.5:
                    return ('Underweight', '#ea580c')
                elif bmi < 25.0:
                    return ('Normal', '#16a34a')
                elif bmi < 30.0:
                    return ('Overweight', '#d97706')
                else:
                    return ('Obese', '#dc2626')
            except (ValueError, TypeError):
                return ('', '#6b7280')
        if bmi_r and bmi_r != '0':
            bmi_category, bmi_color = get_bmi_category(bmi_r)
            bmi_disp = f'{escape(bmi_r)} <span style="color:{bmi_color};font-weight:600;">({bmi_category})</span>'
        else:
            bmi_disp = '&#8212;'
        treatment_regimen_r = str(full.get('treatment_regimen') or '').strip()
        treatment_regimen_disp = esc(treatment_regimen_r)
        prev_dr_stage_r = str(full.get('prev_dr_stage') or '').strip()
        prev_dr_stage_disp = esc(prev_dr_stage_r)
        sym_map = [('symptom_blurred_vision', 'Blurred Vision'), ('symptom_floaters', 'Floaters'), ('symptom_flashes', 'Flashes'), ('symptom_vision_loss', 'Vision Loss')]
        active_syms = [lbl for k, lbl in sym_map if _is_truthy_flag(full.get(k))]
        sym_html = ' '.join((f'<span style="display:inline-block;background:#f3f4f6;color:#374151;border:1px solid #d1d5db;border-radius:4px;padding:3px 10px;font-size:8pt;font-weight:600;margin:2px 4px 2px 0;">{escape(s)}</span>' for s in active_syms)) if active_syms else '<span style="color:#9ca3af;font-style:italic;font-size:9pt;">None reported</span>'

        def resolve_image_uri(path_value: str) -> str:
            raw = str(path_value or '').strip()
            if not raw:
                return ''
            candidate = raw if os.path.isabs(raw) else os.path.join(os.path.dirname(os.path.abspath(__file__)), raw)
            if not os.path.isfile(candidate):
                return ''
            try:
                return Path(candidate).resolve().as_uri()
            except OSError:
                return ''

        def sec(title: str) -> str:
            return f'<div style="margin:18px 0 10px;padding-bottom:6px;border-bottom:2px solid #1f2937;"><span style="font-size:9pt;font-weight:700;color:#1f2937;letter-spacing:1.2px;text-transform:uppercase;">{title}</span></div>'

        def field_row(label: str, value: str, border: bool=True) -> str:
            border_style = 'border-bottom:1px solid #e5e7eb;' if border else ''
            return f'<tr><td style="padding:8px 12px;{border_style}font-size:9pt;color:#4b5563;font-weight:500;width:35%;">{label}</td><td style="padding:8px 12px;{border_style}font-size:9pt;color:#111827;font-weight:600;">{value}</td></tr>'

        def field_grid_2col(fields: list) -> str:
            """Generate 2-column grid layout for fields"""
            rows_html = ''
            for i in range(0, len(fields), 2):
                left_label, left_value = fields[i]
                if i + 1 < len(fields):
                    right_label, right_value = fields[i + 1]
                else:
                    right_label, right_value = ('', '&#8212;')
                rows_html += f'<tr><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:8.5pt;color:#6b7280;font-weight:500;width:18%;">{left_label}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:9pt;color:#111827;font-weight:600;width:32%;">{left_value}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:8.5pt;color:#6b7280;font-weight:500;width:18%;">{right_label}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:9pt;color:#111827;font-weight:600;width:32%;">{right_value}</td></tr>'
            return rows_html
        ai_result_label = escape(ai_result_raw) if ai_result_raw else '—'
        doctor_result_label = escape(doctor_result_raw) if doctor_result_raw else '—'
        final_dx_label = escape(final_dx_raw) if final_dx_raw else '—'
        if result_raw == 'No DR':
            result_badge_color = '#059669'
        elif result_raw == 'Mild DR':
            result_badge_color = '#d97706'
        elif result_raw in ('Moderate DR', 'Severe DR'):
            result_badge_color = '#dc2626'
        elif result_raw == 'Proliferative DR':
            result_badge_color = '#991b1b'
        else:
            result_badge_color = '#6b7280'

        def eye_result_block(eye_record: dict) -> str:
            eye_name = str(eye_record.get('eyes') or 'Eye').strip() or 'Eye'
            eye_result = str(eye_record.get('result') or '').strip()
            eye_conf = str(eye_record.get('confidence') or '').strip()
            if eye_conf.lower().startswith('confidence:'):
                eye_conf = eye_conf[len('confidence:'):].strip()
            src_uri = resolve_image_uri(eye_record.get('source_image_path', ''))
            heat_uri = resolve_image_uri(eye_record.get('heatmap_image_path', ''))

            def image_panel(uri: str, placeholder: str) -> str:
                if uri:
                    img_html = f'<img src="{uri}" style="width:100%;max-width:320px;max-height:230px;height:auto;display:block;margin:0 auto;border-radius:4px;page-break-inside:avoid;break-inside:avoid-page;" />'
                else:
                    img_html = f'<div style="width:320px;height:230px;background:#f3f4f6;border-radius:4px;display:flex;align-items:center;justify-content:center;margin:0 auto;"><span style="font-size:8pt;color:#9ca3af;font-style:italic;text-align:center;padding:20px;">{placeholder}</span></div>'
                return f'<div style="text-align:center;background:#ffffff;padding:8px;border:1px solid #e5e7eb;">{img_html}</div>'

            def titled_image_block(title: str, uri: str, placeholder: str, margin_top: str='0') -> str:
                return f'<div style="page-break-inside:avoid;break-inside:avoid-page;margin-top:{margin_top};"><div style="font-size:8pt;font-weight:700;color:#4b5563;text-transform:uppercase;letter-spacing:0.5px;margin:0 0 6px;">{title}</div>{image_panel(uri, placeholder)}</div>'
            return f"""<div style="border:1px solid #d1d5db;border-radius:6px;background:#ffffff;margin-bottom:14px;padding:14px 16px;page-break-inside:avoid;break-inside:avoid-page;"><div style="margin-bottom:12px;"><table width="100%" cellpadding="0" cellspacing="0"><tr><td style="font-size:10pt;font-weight:700;color:#111827;">{escape(eye_name)}</td><td align="right"><span style="font-size:8pt;color:#6b7280;font-weight:600;">AI Results:&nbsp;</span><span style="font-size:9pt;font-weight:700;color:#111827;">{(escape(eye_result) if eye_result else '&#8212;')}</span></td></tr></table></div><div style="font-size:8.5pt;color:#6b7280;margin-bottom:12px;">Confidence: <span style="font-weight:600;color:#374151;">{(escape(eye_conf) if eye_conf else '&#8212;')}</span></div>{titled_image_block('Fundus', src_uri, 'Source image not stored')}{titled_image_block('Heatmap', heat_uri, 'Heatmap not stored', '12px')}</div>"""
        eye_names = [str(r.get('eyes') or '').strip() for r in eye_records if str(r.get('eyes') or '').strip()]
        combined_eye_display = ', '.join(eye_names) if eye_names else str(full.get('eyes') or '')
        image_results_html = ''.join((eye_result_block(r) for r in eye_records))
        html = f"""<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n<style>\n  body {{\n    font-family: 'Segoe UI', 'Calibri', Arial, sans-serif;\n    font-size: 10pt;\n    color: #111827;\n    background: #ffffff;\n    margin: 0;\n    padding: 0;\n    line-height: 1.5;\n  }}\n  table {{ border-collapse: collapse; }}\n  td, div, span {{ word-break: break-word; }}\n  img {{ max-width: 100%; height: auto; border: 0; }}\n</style>\n</head>\n<body>\n\n<!-- HEADER -->\n<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">\n<tr>\n  <td style="padding:16px 20px;background:#f9fafb;border-bottom:3px solid #1f2937;">\n    <div style="font-size:18pt;font-weight:700;color:#111827;margin-bottom:4px;">DIABETIC RETINOPATHY SCREENING REPORT</div>\n    <div style="font-size:8.5pt;color:#6b7280;">\n            <b>Generated:</b> {report_date} &nbsp;|&nbsp; <b>Created by:</b> {created_by}\n    </div>\n  </td>\n</tr>\n</table>\n\n<!-- BODY -->\n<table width="100%" cellpadding="0" cellspacing="0">\n<tr><td style="padding:0 20px;">\n\n  {sec('Patient Information')}\n  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n  {field_grid_2col([('Full Name', esc(full.get('name'))), ('Date of Birth', esc(full.get('birthdate'))), ('Age', esc(full.get('age'))), ('Sex', esc(full.get('sex'))), ('Patient ID', esc(full.get('patient_id'))), ('Contact', esc(full.get('contact'))), ('Height', height_disp), ('Weight', weight_disp), ('BMI', bmi_disp), ('Eye(s) Screened', esc(combined_eye_display)), ('Screening Date', esc(screening_date)), ('', '')])}\n  </table>\n\n  {sec('Clinical History & Diabetes Management')}\n  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n  {field_row('Diabetes Type', esc(full.get('diabetes_type')))}\n  {field_row('Diagnosis Date', esc(full.get('diabetes_diagnosis_date')))}\n  {field_row('Duration', dur_disp)}\n  {field_row('Treatment Regimen', treatment_regimen_disp)}\n  {field_row('Previous DR Stage', prev_dr_stage_disp)}\n  {field_row('Previous DR Treatment', esc(full.get('prev_treatment')), False)}\n  </table>\n\n  {sec('Reported Symptoms')}\n  <div style="padding:10px 12px;border:1px solid #d1d5db;margin-bottom:18px;background:#fafafa;">\n    <div style="font-size:9pt;color:#374151;">{sym_html}</div>\n  </div>\n\n    {sec('Other Symptom Details')}\n    <div style="padding:12px;border:1px solid #d1d5db;background:#fafafa;margin-bottom:18px;min-height:44px;">\n        <div style="font-size:9pt;color:#4b5563;line-height:1.65;">{other_symptom_disp}</div>\n    </div>\n\n  {sec('AI Classification Result')}\n  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n  {field_row('Classification', ai_result_label)}\n  {field_row('Confidence', conf_display, False)}\n  </table>\n\n  {sec('Doctor Decision')}\n  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n  {field_row('Doctor Classification', doctor_result_label)}\n  {field_row('Decision Mode', esc(decision_mode_raw.title()))}\n  {field_row('Doctor Findings', esc(doctor_findings_raw or '—'))}\n  {field_row('Final Diagnosis', final_dx_label)}\n  {field_row('Final Diagnosis Scale', 'Based on ICDR Severity Scale', False)}\n  </table>\n\n    {sec('Doctor Comments')}\n    <div style="padding:12px;border:1px solid #d1d5db;background:#fafafa;margin-bottom:18px;min-height:44px;">\n        <div style="font-size:9pt;color:#4b5563;line-height:1.65;">{(esc(doctor_findings_raw) if doctor_findings_raw else '<span style="color:#9ca3af;font-style:italic;">No doctor comments provided</span>')}</div>\n    </div>\n"""
        if decision_mode_raw == 'override':
            html += f"""\n  <div style="padding:10px 12px;border:1px solid #fecaca;margin-bottom:18px;background:#fff1f2;">\n    <div style="font-size:8.5pt;color:#7f1d1d;">\n      <b>Override Justification:</b> {esc(override_reason_raw or 'No justification provided')}\n    </div>\n  </div>\n"""
        html += f"""\n\n  {sec('Image Results')}\n  {image_results_html}\n\n  {sec('Clinical Analysis')}\n  <div style="padding:14px;border:1px solid #d1d5db;background:#f9fafb;margin-bottom:18px;">\n    <div style="font-size:8pt;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Clinical Recommendation</div>\n    <div style="font-size:9.5pt;color:#111827;font-weight:600;line-height:1.6;margin-bottom:14px;">&rarr; {rec}</div>\n    <div style="border-top:1px solid #d1d5db;padding-top:12px;margin-top:12px;">\n      <div style="font-size:9.5pt;color:#374151;line-height:1.75;">{summary}</div>\n    </div>\n  </div>\n\n  {sec('Clinical Notes')}\n  <div style="padding:12px;border:1px solid #d1d5db;background:#fafafa;margin-bottom:18px;min-height:50px;">\n    <div style="font-size:9pt;color:#4b5563;font-style:italic;line-height:1.65;">{notes_disp}</div>\n  </div>\n\n  <!-- FOOTER -->\n  <div style="margin-top:24px;padding-top:14px;border-top:2px solid #e5e7eb;">\n    <div style="font-size:7.5pt;color:#9ca3af;line-height:1.8;">\n            <b>Created by:</b> {created_by}<br>\n            <b>Finalized by:</b> {finalized_by}<br>\n            <b>Generated:</b> {report_date}<br>\n      <i>This report is AI-assisted and does not replace the judgment of a licensed eye care professional. All findings must be reviewed and confirmed by a qualified healthcare professional before any clinical action is taken.</i>\n    </div>\n  </div>\n\n</td></tr>\n</table>\n\n</body>\n</html>"""
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setHtml(html)
        writer = QPdfWriter(path)
        writer.setResolution(150)
        try:
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        except Exception:
            pass
        try:
            writer.setPageMargins(QMarginsF(14, 10, 14, 16), QPageLayout.Unit.Millimeter)
        except Exception:
            pass
        doc.print_(writer)
        self.status_label.setText(f'Report saved: {os.path.basename(path)}')
        UserManager.add_activity_log(self.username, f"REPORT_GENERATED patient_id={full.get('patient_id')}; record_id={full.get('id')}; created_by={created_by_raw or finalized_by_raw}; finalized_by={finalized_by_raw}; file={os.path.basename(path)}")
        QMessageBox.information(self, 'Report Saved', f'Patient report saved to:\n{path}')