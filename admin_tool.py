import sqlite3
import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QPushButton,
    QMessageBox, QHeaderView, QLabel
)
from PySide6.QtCore import Qt

DB_FILE = "users.db"


class AdminTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Admin DB Manager (Delete Later)")
        self.resize(800, 600)
        
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        self.users_tab = QWidget()
        self.reports_tab = QWidget()
        
        self.tabs.addTab(self.users_tab, "Users")
        self.tabs.addTab(self.reports_tab, "Patient Reports")
        
        self.setup_users_tab()
        self.setup_reports_tab()
        
    def get_connection(self):
        return sqlite3.connect(DB_FILE)
        
    def setup_users_tab(self):
        layout = QVBoxLayout(self.users_tab)
        
        # Tools
        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_users)
        del_btn = QPushButton("Delete Selected User")
        del_btn.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;")
        del_btn.clicked.connect(self.delete_user)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        toolbar.addWidget(del_btn)
        
        self.users_table = QTableWidget(0, 4)
        self.users_table.setHorizontalHeaderLabels(["ID", "Username", "Full Name", "Role"])
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.users_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.users_table.setSelectionMode(QTableWidget.SingleSelection)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.users_table)
        self.load_users()

    def setup_reports_tab(self):
        layout = QVBoxLayout(self.reports_tab)
        
        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_reports)
        del_btn = QPushButton("Delete Selected Report")
        del_btn.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;")
        del_btn.clicked.connect(self.delete_report)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        toolbar.addWidget(del_btn)
        
        self.reports_table = QTableWidget(0, 6)
        self.reports_table.setHorizontalHeaderLabels(["ID", "Patient ID", "Name", "Date", "AI Class", "Doctor Class"])
        self.reports_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.reports_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.reports_table.setSelectionMode(QTableWidget.SingleSelection)
        
        layout.addLayout(toolbar)
        layout.addWidget(self.reports_table)
        self.load_reports()

    def load_users(self):
        self.users_table.setRowCount(0)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, full_name, role FROM users")
                users = cursor.fetchall()
                for row_idx, user in enumerate(users):
                    self.users_table.insertRow(row_idx)
                    for col_idx, item in enumerate(user):
                        cell = QTableWidgetItem(str(item))
                        cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                        self.users_table.setItem(row_idx, col_idx, cell)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load users: {e}")

    def delete_user(self):
        selected = self.users_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        user_id = self.users_table.item(row, 0).text()
        username = self.users_table.item(row, 1).text()
        
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete user '{username}' (ID: {user_id})?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
                    conn.commit()
                self.load_users()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not delete user: {e}")

    def load_reports(self):
        self.reports_table.setRowCount(0)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, patient_id, name, screening_date, ai_classification, doctor_classification FROM patient_records")
                reports = cursor.fetchall()
                for row_idx, report in enumerate(reports):
                    self.reports_table.insertRow(row_idx)
                    for col_idx, item in enumerate(report):
                        cell = QTableWidgetItem(str(item))
                        cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                        self.reports_table.setItem(row_idx, col_idx, cell)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load reports: {e}")

    def delete_report(self):
        selected = self.reports_table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        report_id = self.reports_table.item(row, 0).text()
        patient_id = self.reports_table.item(row, 1).text()
        name = self.reports_table.item(row, 2).text()
        
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete report for '{name}' (Patient ID: {patient_id})?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM patient_records WHERE id=?", (report_id,))
                    # Also optionally clean up referral assignments and other metadata linked to `patient_id`
                    conn.commit()
                self.load_reports()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not delete report: {e}")


if __name__ == '__main__':
    app = QApplication(sys.sysargv if hasattr(sys, 'sysargv') else sys.argv)
    window = AdminTool()
    window.show()
    sys.exit(app.exec())
