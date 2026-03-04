"""
Reports module for EyeShield EMR application.
Provides offline summary analytics from local patient_records data.
"""

import csv
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
    QMessageBox,
)
from PySide6.QtCore import Qt

from auth import DB_FILE


class ReportsPage(QWidget):
    """Reports page with local offline statistics."""

    def __init__(self):
        super().__init__()
        self._summary_cache = {}
        self._result_rows = []
        self._filtered_rows = []
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

        title = QLabel("DR Screening Reports")
        title.setObjectName("pageHeader")
        title.setStyleSheet("font-size:24px;font-weight:700;color:#007bff;font-family:'Calibri','Inter','Arial';")
        subtitle = QLabel("Complete diabetic retinopathy screening outcomes from locally saved records")
        subtitle.setObjectName("pageSubtitle")
        subtitle.setStyleSheet("font-size:13px;color:#6c757d;")

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        top_bar.addWidget(title)
        top_bar.addStretch(1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_report)
        self.export_btn = QPushButton("Export Results")
        self.export_btn.setObjectName("primaryAction")
        self.export_btn.setAutoDefault(True)
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self.export_summary)
        top_bar.addWidget(self.refresh_btn)
        top_bar.addWidget(self.export_btn)

        root.addLayout(top_bar)
        root.addWidget(subtitle)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        root.addWidget(self.status_label)

        controls_group = QGroupBox("Quick Filters")
        controls_layout = QHBoxLayout(controls_group)
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

        root.addWidget(controls_group)

        stats_group = QGroupBox("Summary")
        stats_layout = QHBoxLayout(stats_group)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(16)

        total_card, self.total_label = self._make_stat_card("Total Screenings", "0")
        unique_card, self.unique_patients_label = self._make_stat_card("Unique Patients", "0")
        no_dr_card, self.no_dr_label = self._make_stat_card("No DR", "0")
        review_card, self.review_label = self._make_stat_card("Needs Review", "0")
        hba1c_card, self.hba1c_label = self._make_stat_card("Avg HbA1c", "0.0%")

        self._stat_cards = [total_card, unique_card, no_dr_card, review_card, hba1c_card]
        for card in self._stat_cards:
            stats_layout.addWidget(card)

        root.addWidget(stats_group)

        results_group = QGroupBox("All Screening Results")
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(16, 16, 16, 16)
        results_layout.setSpacing(12)

        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(["Patient ID", "Name", "Result", "Confidence", "Diabetes Type", "HbA1c"])
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SingleSelection)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        results_layout.addWidget(self.results_table)

        root.addWidget(results_group)

        self.setTabOrder(self.refresh_btn, self.export_btn)
        self.setTabOrder(self.export_btn, self.search_input)
        self.setTabOrder(self.search_input, self.result_filter)
        self.setTabOrder(self.result_filter, self.results_table)

        self.refresh_report()

    def _make_stat_card(self, title: str, value: str) -> tuple[QWidget, QLabel]:
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
        return container, value_label

    def refresh_report(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT patient_id, name, result, confidence, diabetes_type, hba1c
                FROM patient_records
                ORDER BY id DESC
                """
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as err:
            QMessageBox.warning(self, "Reports", f"Failed to load report data: {err}")
            return

        total = len(rows)
        unique_patients = len({str(row[0]).strip() for row in rows if str(row[0]).strip()})
        no_dr = 0
        hba1c_values = []

        for _, _, result, _, _, hba1c in rows:
            result_text = str(result or "").lower()
            if "no dr" in result_text:
                no_dr += 1
            raw_hba1c = str(hba1c or "").replace("%", "").strip()
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
        self._result_rows = rows

        self.total_label.setText(str(total))
        self.unique_patients_label.setText(str(unique_patients))
        self.no_dr_label.setText(str(no_dr))
        self.review_label.setText(str(needs_review))
        self.hba1c_label.setText(f"{avg_hba1c:.1f}%")

        self.apply_filters()

        self.status_label.setText(f"Updated {total} screenings at {datetime.now().strftime('%H:%M:%S')}")

    def apply_filters(self):
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        result_mode = self.result_filter.currentText() if hasattr(self, "result_filter") else "All"

        filtered = []
        for row in self._result_rows:
            patient_id, name, result, confidence, diabetes_type, hba1c = row
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
        self._render_results_table()

    def _render_results_table(self):
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)

        for patient_id, name, result, confidence, diabetes_type, hba1c in self._filtered_rows:
            row_idx = self.results_table.rowCount()
            self.results_table.insertRow(row_idx)
            self.results_table.setItem(row_idx, 0, QTableWidgetItem(str(patient_id or "")))
            self.results_table.setItem(row_idx, 1, QTableWidgetItem(str(name or "")))

            result_item = QTableWidgetItem(str(result or ""))
            if self._is_high_attention_result(result):
                result_item.setForeground(Qt.darkRed)
            elif "no dr" in str(result or "").lower():
                result_item.setForeground(Qt.darkGreen)
            self.results_table.setItem(row_idx, 2, result_item)

            self.results_table.setItem(row_idx, 3, QTableWidgetItem(str(confidence or "")))
            self.results_table.setItem(row_idx, 4, QTableWidgetItem(str(diabetes_type or "")))
            self.results_table.setItem(row_idx, 5, QTableWidgetItem(str(hba1c or "")))

        self.results_table.setSortingEnabled(True)
        self.filtered_count_label.setText(f"{len(self._filtered_rows)} shown")

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
                ])
                rows_to_export = self._filtered_rows if self._filtered_rows else self._result_rows
                writer.writerows(rows_to_export)
            self.status_label.setText(f"Exported {len(rows_to_export)} rows to {path}")
        except OSError as err:
            QMessageBox.warning(self, "Export", f"Failed to export summary: {err}")
