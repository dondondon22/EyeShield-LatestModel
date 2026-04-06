import re

with open('settings.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace _configure_referral_hospitals_section
code = code.replace('_configure_referral_hospitals_section', '_configure_backup_section')

# Remove leftover hospital form logic
code = re.sub(
    r'        self\.referral_hospitals_group = QGroupBox\("Trusted referred hospitals"\).*?self\.referral_hospitals_table\)',
    '''        self.backup_group = QGroupBox("Patient Records Backup")
        backup_layout = QVBoxLayout(self.backup_group)
        backup_layout.setSpacing(6)

        self.backup_hint = QLabel("Export all patient records to CSV. Restoring allows recovering historical data across updates.")
        self.backup_hint.setObjectName("metaLabel")
        self.backup_hint.setWordWrap(True)
        backup_layout.addWidget(self.backup_hint)

        button_layout = QHBoxLayout()
        self.export_records_btn = QPushButton("Export as CSV")
        self.export_records_btn.setFixedHeight(32)
        self.export_records_btn.clicked.connect(self._export_records_csv)
        self.import_records_btn = QPushButton("Import from CSV")
        self.import_records_btn.setFixedHeight(32)
        self.import_records_btn.clicked.connect(self._import_records_csv)
        
        button_layout.addWidget(self.export_records_btn)
        button_layout.addWidget(self.import_records_btn)
        backup_layout.addLayout(button_layout)''',
    code, flags=re.DOTALL
)

# Nuke hospital_form_grid to end of the section setup
code = re.sub(r'        hospital_form_grid = QGridLayout\(\).*?layout\.addWidget\(self\.hospital_save_btn\)', '', code, flags=re.DOTALL)
code = re.sub(r'        referral_layout\.addLayout\(hospital_form_grid\)\n\s*referral_layout\.addLayout\(layout\)', '', code, flags=re.DOTALL)

# replace instances of referral_hospitals_group with backup_group
code = code.replace('self.referral_hospitals_group', 'self.backup_group')

# Now for the functions block starting at _configure_backup_section...

# Find where the functions start and replace them
func_pattern = r'    def _configure_backup_section\(self\):.*?def _language_pack'
replacement = '''    def _configure_backup_section(self):
        show_backup = self._active_role() == "admin"
        self.backup_group.setVisible(show_backup)

    def _export_records_csv(self):
        from reports import ReportsPage
        try:
            # We\'ll generate a clean export via ReportsPage directly or via a static helper
            ReportsPage.export_records_to_csv_static(self)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export records: {e}")

    def _import_records_csv(self):
        import csv
        from auth import get_connection, UserManager
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        file_path, _ = QFileDialog.getOpenFileName(self, "Select Backup CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                QMessageBox.warning(self, "Import Failed", "The selected CSV file is empty.")
                return

            conn = get_connection()
            cur = conn.cursor()
            UserManager._ensure_patient_record_columns(conn)

            # Map the columns
            cur.execute("PRAGMA table_info(patient_records)")
            valid_columns = {col[1] for col in cur.fetchall()}

            imported = 0
            for row in rows:
                # skip empty rows
                if not row.get("patient_id"):
                    continue
                    
                cur.execute("SELECT 1 FROM patient_records WHERE patient_id = ? AND result = ?", (row.get("patient_id"), row.get("result", "")))
                if cur.fetchone():
                    continue

                insert_cols = []
                insert_vals = []
                for k, v in row.items():
                    if k in valid_columns and k != 'id':
                        insert_cols.append(k)
                        insert_vals.append(v)
                
                if not insert_cols:
                    continue

                placeholders = ",".join(["?"] * len(insert_cols))
                
                cur.execute(f"INSERT INTO patient_records ({','.join(insert_cols)}) VALUES ({placeholders})", insert_vals)
                imported += 1

            conn.commit()
            conn.close()
            
            # Notify the user
            QMessageBox.information(self, "Import Success", f"Successfully imported {imported} new records out of {len(rows)} total records in the backup.\\n\\nDuplicates were skipped.")
            
            # Trigger refresh for main app dashboard
            main_window = self.window()
            if hasattr(main_window, "refresh_dashboard"):
                main_window.refresh_dashboard()

        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import CSV: {e}")

    def _language_pack'''

code = re.sub(func_pattern, replacement, code, flags=re.DOTALL)

with open('settings.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Replacement successful")
