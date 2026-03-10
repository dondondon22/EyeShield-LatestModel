"""
Reports module for EyeShield EMR application.
Provides offline summary analytics from local patient_records data.
"""

import csv
import os
import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QComboBox,
    QHeaderView,
    QFileDialog,
    QDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt

from auth import DB_FILE


class ArchivedRecordsDialog(QDialog):
    """Admin-only dialog for reviewing and restoring archived patient records."""

    def __init__(self, reports_page: "ReportsPage"):
        super().__init__(reports_page)
        self.reports_page = reports_page
        self._rows = []
        self._filtered_rows = []
        self._record_lookup = {}

        self.setWindowTitle("Archived Patient Records")
        self.resize(980, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Archived Patient Records")
        title.setStyleSheet("font-size:22px;font-weight:700;color:#007bff;")
        subtitle = QLabel("Review archived screenings and restore them back into the active dashboard and reports.")
        subtitle.setStyleSheet("font-size:13px;color:#6c757d;")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search archived records by patient ID, name, result, or archived by")
        self.search_input.textChanged.connect(self.apply_filters)
        controls.addWidget(self.search_input, 1)

        self.count_label = QLabel("0 archived")
        self.count_label.setStyleSheet("color:#6c757d;font-size:12px;")
        controls.addWidget(self.count_label)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Patient ID",
            "Name",
            "Result",
            "Archived At",
            "Archived By",
        ])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_restore_button)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        actions.addStretch(1)

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet(
            "QPushButton { background: #dc3545; color: #ffffff; border: 1px solid #bb2d3b; }"
            "QPushButton:hover { background: #c82333; }"
            "QPushButton:disabled { background: #f1aeb5; color: #ffffff; border: 1px solid #ea868f; }"
        )
        self.delete_btn.clicked.connect(self.delete_selected_record)
        actions.addWidget(self.delete_btn)

        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self.restore_selected_record)
        actions.addWidget(self.restore_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

        self.reload_rows()

    def reload_rows(self):
        self._rows = [row for row in self.reports_page._all_result_rows if row["archived_at"]]
        self._record_lookup = {row["id"]: row for row in self._rows}
        self.apply_filters()

    def apply_filters(self):
        query = self.search_input.text().strip().lower()
        filtered = []
        for row in self._rows:
            haystack = " ".join([
                str(row["patient_id"] or ""),
                str(row["name"] or ""),
                str(row["result"] or ""),
                str(row["archived_at"] or ""),
                str(row["archived_by"] or ""),
            ]).lower()
            if query and query not in haystack:
                continue
            filtered.append(row)

        self._filtered_rows = filtered
        self._render_table()

    def _render_table(self):
        self.table.setRowCount(0)
        for row in self._filtered_rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)

            patient_id_item = QTableWidgetItem(str(row["patient_id"] or ""))
            patient_id_item.setData(Qt.UserRole, row["id"])
            self.table.setItem(row_idx, 0, patient_id_item)
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(row["name"] or "")))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(row["result"] or "")))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(row["archived_at"] or "")))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(row["archived_by"] or "")))

        self.count_label.setText(f"{len(self._filtered_rows)} archived")
        self._update_restore_button()

    def _get_selected_record(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return None

        record_item = self.table.item(current_row, 0)
        if record_item is None:
            return None

        record_id = record_item.data(Qt.UserRole)
        return self._record_lookup.get(record_id)

    def _update_restore_button(self):
        has_selection = self._get_selected_record() is not None
        self.restore_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def restore_selected_record(self):
        record = self._get_selected_record()
        if not record:
            QMessageBox.information(self, "Restore Record", "Select an archived patient record to restore.")
            return

        if not self.reports_page.restore_record(record):
            return

        self.reports_page.refresh_report()
        self.reload_rows()

    def delete_selected_record(self):
        record = self._get_selected_record()
        if not record:
            QMessageBox.information(self, "Delete Record", "Select an archived patient record to delete.")
            return

        patient_label = f"{record['name'] or 'Unknown Patient'} ({record['patient_id'] or 'No ID'})"
        warning_box = QMessageBox(self)
        warning_box.setIcon(QMessageBox.Icon.Warning)
        warning_box.setWindowTitle("Delete Archived Record")
        warning_box.setText(f"Permanently delete {patient_label}?")
        warning_box.setInformativeText(
            "This action cannot be undone. The archived patient record will be removed permanently from local storage."
        )
        warning_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        warning_box.setDefaultButton(QMessageBox.StandardButton.No)
        if warning_box.exec() != QMessageBox.StandardButton.Yes:
            return

        if not self.reports_page.delete_archived_record(record):
            QMessageBox.warning(self, "Delete Record", "Unable to permanently delete the selected archived record.")
            return

        self.reports_page.refresh_report()
        self.reload_rows()


class ReportsPage(QWidget):
    """Reports page with local offline statistics."""

    def __init__(self, username: str = "", role: str = "clinician"):
        super().__init__()
        self.username = username or os.environ.get("EYESHIELD_CURRENT_USER", "")
        self.role = role or os.environ.get("EYESHIELD_CURRENT_ROLE", "clinician")
        self.is_admin = self.role == "admin"
        self.records_changed_callback = None
        self.archived_records_dialog = None
        self._summary_cache = {}
        self._all_result_rows = []
        self._filtered_rows = []
        self._record_lookup = {}
        self.setStyleSheet("""
            QWidget { background: #f8f9fa; color: #212529; font-family: 'Calibri', 'Inter', 'Arial'; }
            QGroupBox { background: #ffffff; border: 1px solid #dee2e6; border-radius: 8px; }
            QLineEdit, QComboBox, QTableWidget { background: #ffffff; border: 1px solid #ced4da; border-radius: 8px; }
            QPushButton:focus, QTableWidget:focus { border: 1px solid #0d6efd; }
            QPushButton { background: #e9ecef; color: #212529; border: 1px solid #ced4da; border-radius: 8px; padding: 8px 16px; font-weight: 600; }
            QPushButton:hover { background: #dee2e6; }
            QPushButton#primaryAction { background: #0d6efd; color: #ffffff; border: 1px solid #0b5ed7; border-radius: 8px; padding: 8px 16px; font-weight: 600; }
            QLabel#statusLabel { color: #495057; font-size: 12px; }
            QLabel#hintLabel { color: #6c757d; font-size: 12px; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        self._rep_title_lbl = QLabel("DR Screening Reports")
        self._rep_title_lbl.setObjectName("pageHeader")
        self._rep_title_lbl.setStyleSheet("font-size:24px;font-weight:700;color:#007bff;font-family:'Calibri','Inter','Arial';")
        self._rep_subtitle_lbl = QLabel("Complete diabetic retinopathy screening outcomes from locally saved records")
        self._rep_subtitle_lbl.setObjectName("pageSubtitle")
        self._rep_subtitle_lbl.setStyleSheet("font-size:13px;color:#6c757d;")

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addWidget(self._rep_title_lbl)
        top_bar.addStretch(1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_report)
        self.export_btn = QPushButton("Export Results")
        self.export_btn.setObjectName("primaryAction")
        self.export_btn.setAutoDefault(True)
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self.export_summary)
        if self.is_admin:
            self.archived_records_btn = QPushButton("Archived Records")
            self.archived_records_btn.clicked.connect(self.open_archived_records_window)
            top_bar.addWidget(self.archived_records_btn)
        else:
            self.archived_records_btn = None
        top_bar.addWidget(self.refresh_btn)
        top_bar.addWidget(self.export_btn)

        root.addLayout(top_bar)
        root.addWidget(self._rep_subtitle_lbl)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        root.addWidget(self.status_label)

        self._controls_group = QGroupBox("Quick Filters")
        controls_layout = QHBoxLayout(self._controls_group)
        controls_layout.setContentsMargins(16, 16, 16, 16)
        controls_layout.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by patient ID, name, result, diabetes type, or HbA1c")
        self.search_input.setMinimumHeight(36)
        self.search_input.textChanged.connect(self.apply_filters)
        controls_layout.addWidget(self.search_input, 1)

        self.result_filter = QComboBox()
        self.result_filter.addItems(["All", "No DR", "Mild DR", "Moderate DR", "Severe DR", "Proliferative DR"])
        self.result_filter.setMinimumHeight(36)
        self.result_filter.currentTextChanged.connect(self.apply_filters)
        controls_layout.addWidget(self.result_filter)

        self.filtered_count_label = QLabel("0 shown")
        self.filtered_count_label.setObjectName("hintLabel")
        controls_layout.addWidget(self.filtered_count_label)

        root.addWidget(self._controls_group)

        self._stats_group = QGroupBox("Summary")
        stats_layout = QHBoxLayout(self._stats_group)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(16)

        total_card, self._stat_total_title, self.total_label = self._make_stat_card("Total Screenings", "0")
        unique_card, self._stat_unique_title, self.unique_patients_label = self._make_stat_card("Unique Patients", "0")
        no_dr_card, self._stat_no_dr_title, self.no_dr_label = self._make_stat_card("No DR", "0")
        review_card, self._stat_review_title, self.review_label = self._make_stat_card("Needs Review", "0")
        hba1c_card, self._stat_hba1c_title, self.hba1c_label = self._make_stat_card("Avg HbA1c", "0.0%")

        self._stat_cards = [total_card, unique_card, no_dr_card, review_card, hba1c_card]
        for card in self._stat_cards:
            stats_layout.addWidget(card)

        root.addWidget(self._stats_group)

        self._results_group = QGroupBox("All Screening Results")
        results_layout = QVBoxLayout(self._results_group)
        results_layout.setContentsMargins(16, 16, 16, 16)
        results_layout.setSpacing(12)

        if self.is_admin:
            actions_layout = QHBoxLayout()
            actions_layout.setSpacing(8)
            actions_layout.addStretch(1)

            self.archive_btn = QPushButton("Archive Selected")
            self.archive_btn.clicked.connect(self.archive_selected_record)
            self.archive_btn.setEnabled(False)
            actions_layout.addWidget(self.archive_btn)

            results_layout.addLayout(actions_layout)
        else:
            self.archive_btn = None

        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(["Patient ID", "Name", "Result", "Confidence", "Diabetes Type", "HbA1c"])
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SingleSelection)
        self.results_table.itemSelectionChanged.connect(self._update_action_buttons)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        results_layout.addWidget(self.results_table)

        root.addWidget(self._results_group)

        self.setTabOrder(self.refresh_btn, self.export_btn)
        self.setTabOrder(self.export_btn, self.search_input)
        self.setTabOrder(self.search_input, self.result_filter)
        self.setTabOrder(self.result_filter, self.results_table)

        self.refresh_report()

    def _make_stat_card(self, title: str, value: str) -> tuple[QWidget, QLabel, QLabel]:
        container = QWidget()
        container.setObjectName("dashTile")
        container.setStyleSheet("background:#ffffff;border:1px solid #dee2e6;border-radius:8px;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("tileTitle")
        title_label.setStyleSheet("font-size:12px;font-weight:600;color:#6c757d;")
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        value_label.setStyleSheet("font-size:18px;font-weight:700;color:#343a40;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return container, title_label, value_label

    def refresh_report(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, patient_id, name, result, confidence, diabetes_type, hba1c,
                       archived_at, archived_by, archive_reason
                FROM patient_records
                ORDER BY id DESC
                """
            )
            rows = [
                {
                    "id": row[0],
                    "patient_id": row[1],
                    "name": row[2],
                    "result": row[3],
                    "confidence": row[4],
                    "diabetes_type": row[5],
                    "hba1c": row[6],
                    "archived_at": row[7],
                    "archived_by": row[8],
                    "archive_reason": row[9],
                }
                for row in cur.fetchall()
            ]
            conn.close()
        except Exception as err:
            QMessageBox.warning(self, "Reports", f"Failed to load report data: {err}")
            return

        self._all_result_rows = rows
        self._record_lookup = {row["id"]: row for row in rows}

        self.apply_filters()

        if self.archived_records_dialog is not None:
            self.archived_records_dialog.reload_rows()

        active_rows = [row for row in rows if not row["archived_at"]]
        archived_count = len(rows) - len(active_rows)
        if self.is_admin:
            self.status_label.setText(
                f"Updated {len(active_rows)} active and {archived_count} archived records at {datetime.now().strftime('%H:%M:%S')}"
            )
        else:
            self.status_label.setText(f"Updated {len(active_rows)} screenings at {datetime.now().strftime('%H:%M:%S')}")

    def apply_filters(self):
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        result_mode = self.result_filter.currentText() if hasattr(self, "result_filter") else "All"

        filtered = []
        for row in self._all_result_rows:
            if row["archived_at"]:
                continue

            patient_id = row["patient_id"]
            name = row["name"]
            result = row["result"]
            confidence = row["confidence"]
            diabetes_type = row["diabetes_type"]
            hba1c = row["hba1c"]
            result_text = str(result or "")
            normalized = " ".join([
                str(patient_id or ""),
                str(name or ""),
                result_text,
                str(confidence or ""),
                str(diabetes_type or ""),
                str(hba1c or ""),
            ]).lower()

            if query and query not in normalized:
                continue

            result_lower = result_text.lower()
            if result_mode == "No DR" and "no dr" not in result_lower:
                continue
            if result_mode == "Mild DR" and "mild" not in result_lower:
                continue
            if result_mode == "Moderate DR" and "moderate" not in result_lower:
                continue
            if result_mode == "Severe DR" and "severe" not in result_lower:
                continue
            if result_mode == "Proliferative DR" and "proliferative" not in result_lower:
                continue

            filtered.append(row)

        self._filtered_rows = filtered
        self._update_summary_cards(filtered)
        self._render_results_table()

    def _render_results_table(self):
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)

        for row in self._filtered_rows:
            row_idx = self.results_table.rowCount()
            self.results_table.insertRow(row_idx)

            patient_id_item = QTableWidgetItem(str(row["patient_id"] or ""))
            patient_id_item.setData(Qt.UserRole, row["id"])
            self.results_table.setItem(row_idx, 0, patient_id_item)
            self.results_table.setItem(row_idx, 1, QTableWidgetItem(str(row["name"] or "")))

            result_item = QTableWidgetItem(str(row["result"] or ""))
            if self._is_high_attention_result(row["result"]):
                result_item.setForeground(Qt.darkRed)
            elif "no dr" in str(row["result"] or "").lower():
                result_item.setForeground(Qt.darkGreen)
            self.results_table.setItem(row_idx, 2, result_item)

            self.results_table.setItem(row_idx, 3, QTableWidgetItem(str(row["confidence"] or "")))
            self.results_table.setItem(row_idx, 4, QTableWidgetItem(str(row["diabetes_type"] or "")))
            self.results_table.setItem(row_idx, 5, QTableWidgetItem(str(row["hba1c"] or "")))

        self.results_table.setSortingEnabled(True)
        self.filtered_count_label.setText(f"{len(self._filtered_rows)} shown")
        self._update_action_buttons()

    def _update_summary_cards(self, rows):
        total = len(rows)
        unique_patients = len({str(row["patient_id"]).strip() for row in rows if str(row["patient_id"]).strip()})
        no_dr = 0
        hba1c_values = []

        for row in rows:
            result_text = str(row["result"] or "").lower()
            if "no dr" in result_text:
                no_dr += 1
            raw_hba1c = str(row["hba1c"] or "").replace("%", "").strip()
            try:
                hba1c_values.append(float(raw_hba1c))
            except ValueError:
                pass

        needs_review = max(0, total - no_dr)
        avg_hba1c = (sum(hba1c_values) / len(hba1c_values)) if hba1c_values else 0.0

        self._summary_cache = {
            "total_screenings": total,
            "unique_patients": unique_patients,
            "no_dr": no_dr,
            "needs_review": needs_review,
            "avg_hba1c": round(avg_hba1c, 1),
        }

        self.total_label.setText(str(total))
        self.unique_patients_label.setText(str(unique_patients))
        self.no_dr_label.setText(str(no_dr))
        self.review_label.setText(str(needs_review))
        self.hba1c_label.setText(f"{avg_hba1c:.1f}%")

    def _get_selected_record(self):
        current_row = self.results_table.currentRow()
        if current_row < 0:
            return None

        record_item = self.results_table.item(current_row, 0)
        if record_item is None:
            return None

        record_id = record_item.data(Qt.UserRole)
        return self._record_lookup.get(record_id)

    def _update_action_buttons(self):
        if not self.is_admin:
            return

        record = self._get_selected_record()
        self.archive_btn.setEnabled(bool(record and not record["archived_at"]))

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
            QMessageBox.information(self, "Archive Record", "Select a patient record to archive.")
            return
        if record["archived_at"]:
            QMessageBox.information(self, "Archive Record", "The selected patient record is already archived.")
            return

        patient_label = f"{record['name'] or 'Unknown Patient'} ({record['patient_id'] or 'No ID'})"
        reply = QMessageBox.question(
            self,
            "Archive Record",
            f"Archive {patient_label}? The record will be hidden from the default dashboard and reports until restored.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self._set_record_archive_state(record["id"], archived=True):
            QMessageBox.warning(self, "Archive Record", "Unable to archive the selected patient record.")
            return

        self.refresh_report()

    def restore_record(self, record):
        if not record or not record["archived_at"]:
            QMessageBox.information(self, "Restore Record", "The selected patient record is already active.")
            return False

        patient_label = f"{record['name'] or 'Unknown Patient'} ({record['patient_id'] or 'No ID'})"
        reply = QMessageBox.question(
            self,
            "Restore Record",
            f"Restore {patient_label} to the active dashboard and reports?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        if not self._set_record_archive_state(record["id"], archived=False):
            QMessageBox.warning(self, "Restore Record", "Unable to restore the selected patient record.")
            return False

        return True

    def delete_archived_record(self, record):
        if not record or not record["archived_at"]:
            QMessageBox.information(self, "Delete Record", "Only archived patient records can be deleted.")
            return False

        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("DELETE FROM patient_records WHERE id = ? AND archived_at IS NOT NULL", (record["id"],))
            conn.commit()
            success = cur.rowcount > 0
            conn.close()
        except Exception:
            return False

        if success and callable(self.records_changed_callback):
            self.records_changed_callback()
        return success

    def _set_record_archive_state(self, record_id, archived: bool) -> bool:
        actor = self.username or os.environ.get("EYESHIELD_CURRENT_USER", "")
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            if archived:
                cur.execute(
                    """
                    UPDATE patient_records
                    SET archived_at = ?, archived_by = ?, archive_reason = ?
                    WHERE id = ?
                    """,
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), actor, None, record_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE patient_records
                    SET archived_at = NULL, archived_by = NULL, archive_reason = NULL
                    WHERE id = ?
                    """,
                    (record_id,),
                )
            conn.commit()
            success = cur.rowcount > 0
            conn.close()
        except Exception:
            return False

        if success and callable(self.records_changed_callback):
            self.records_changed_callback()
        return success

    @staticmethod
    def _is_high_attention_result(result_text):
        text = str(result_text or "").lower()
        keywords = ("moderate", "severe", "proliferative", "refer", "urgent", "dr detected")
        return any(keyword in text for keyword in keywords)

    def export_summary(self):
        if not self._summary_cache:
            self.status_label.setText("No report data to export")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export DR Screening Results", "", "CSV Files (*.csv)")
        if not path:
            return

        rows_to_export = list(self._filtered_rows)
        if not rows_to_export:
            self.status_label.setText("No visible report data to export")
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow([
                    "Patient ID",
                    "Name",
                    "Result",
                    "Confidence",
                    "Diabetes Type",
                    "HbA1c",
                    "Record Status",
                    "Archived At",
                    "Archived By",
                ])
                for row in rows_to_export:
                    writer.writerow([
                        row["patient_id"],
                        row["name"],
                        row["result"],
                        row["confidence"],
                        row["diabetes_type"],
                        row["hba1c"],
                        "Archived" if row["archived_at"] else "Active",
                        row["archived_at"],
                        row["archived_by"],
                    ])
            self.status_label.setText(f"Exported {len(rows_to_export)} rows to {path}")
        except OSError as err:
            QMessageBox.warning(self, "Export", f"Failed to export summary: {err}")

    def apply_language(self, language: str):
        from translations import get_pack
        pack = get_pack(language)
        self._rep_title_lbl.setText(pack["rep_title"])
        self._rep_subtitle_lbl.setText(pack["rep_subtitle"])
        self.refresh_btn.setText(pack["rep_refresh"])
        self.export_btn.setText(pack["rep_export"])
        if self.archived_records_btn is not None:
            self.archived_records_btn.setText(pack["rep_archived"])
        if self.archive_btn is not None:
            self.archive_btn.setText(pack["rep_archive_sel"])
        self._controls_group.setTitle(pack["rep_quick_filters"])
        self._stats_group.setTitle(pack["rep_summary"])
        self._results_group.setTitle(pack["rep_all_results"])
        self._stat_total_title.setText(pack["rep_stat_total"])
        self._stat_unique_title.setText(pack["rep_stat_unique"])
        self._stat_no_dr_title.setText(pack["rep_stat_no_dr"])
        self._stat_review_title.setText(pack["rep_stat_review"])
        self._stat_hba1c_title.setText(pack["rep_stat_hba1c"])
