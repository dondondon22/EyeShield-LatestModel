import json
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QComboBox,
    QLineEdit,
    QCheckBox,
    QMessageBox,
    QFrame,
    QScrollArea,
    QDialog,
    QTimeEdit,
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import QTime

import user_store
from user_auth import get_user_profile

_WEEKDAY_OPTIONS = [
    ("mon", "Monday"),
    ("tue", "Tuesday"),
    ("wed", "Wednesday"),
    ("thu", "Thursday"),
    ("fri", "Friday"),
    ("sat", "Saturday"),
    ("sun", "Sunday"),
]

DARK_STYLESHEET = """
    /* ---- Base ---- */
    QWidget {
        background: #20242b;
        color: #d6dbe4;
    }
    QMainWindow, QStackedWidget {
        background: #20242b;
    }

    /* ---- Inputs ---- */
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background: #2a3038;
        color: #d6dbe4;
        border: 1px solid #3e4652;
        border-radius: 8px;
        padding: 8px;
        selection-background-color: #4b5563;
    }
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {
        border: 1px solid #7ea6d9;
    }
    QComboBox QAbstractItemView {
        background: #2a3038;
        color: #d6dbe4;
        selection-background-color: #3e4652;
    }

    /* ---- Tables ---- */
    QTableWidget {
        background: #2a3038;
        alternate-background-color: #252b33;
        color: #d6dbe4;
        gridline-color: #3e4652;
        border: 1px solid #3e4652;
        border-radius: 8px;
    }
    QHeaderView::section {
        background: #303744;
        color: #c7cfdb;
        padding: 8px;
        border: none;
    }
    QTableWidget::item {
        padding: 8px;
    }

    /* ---- Group boxes ---- */
    QGroupBox {
        background: #242a33;
        border: 1px solid #3e4652;
        border-radius: 8px;
        margin-top: 10px;
        color: #7ea6d9;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px;
        color: #7ea6d9;
    }

    /* ---- Buttons ---- */
    QPushButton {
        background: #3e4652;
        color: #d6dbe4;
        border: 1px solid #4b5563;
        border-radius: 8px;
        padding: 8px 16px;
    }
    QPushButton:hover {
        background: #4b5563;
    }
    QPushButton:focus {
        border: 1px solid #7ea6d9;
    }
    QPushButton:disabled {
        background: #2a3038;
        color: #7a8594;
        border: 1px solid #3e4652;
    }
    QPushButton#primaryAction {
        background: #5f8fc4;
        color: #f4f7fb;
        border: 1px solid #6ea0d8;
    }
    QPushButton#primaryAction:hover {
        background: #6a9bd3;
    }
    QPushButton#dangerAction {
        background: #2b2a31;
        color: #e4a1b1;
        border: 1px solid #d18a9a;
    }
    QPushButton#dangerAction:hover {
        background: #35303a;
    }
    QPushButton#logoutBtn {
        background: #cf7288;
        color: #f7f9fc;
        border: 1px solid #bf667c;
        border-radius: 8px;
        padding: 8px 16px;
    }
    QPushButton#logoutBtn:hover {
        background: #d47f94;
    }

    /* ---- Labels ---- */
    QLabel {
        background: transparent;
        color: #cdd6f4;
    }
    QLabel#tileTitle {
        color: #a6adc8;
        letter-spacing: 0.5px;
    }
    QLabel#statusLabel {
        color: #a6adc8;
    }
    QLabel#hintLabel {
        color: #6c7086;
    }
    QLabel#pageHeader {
        color: #89b4fa;
    }
    QLabel#pageSubtitle {
        color: #a6adc8;
    }
    QLabel#appTitle {
        color: #7ea6d9;
        margin-right: 24px;
    }
    QLabel#userInfo {
        color: #a6adc8;
        margin-left: 16px;
        margin-right: 8px;
    }
    QLabel#welcomeTitle {
        color: #89b4fa;
    }
    QLabel#bigValue {
        color: #cdd6f4;
    }
    QLabel#quoteLabel {
        color: #a6adc8;
        font-style: italic;
    }
    QLabel#dashDate {
        color: #7ea6d9;
    }
    QLabel#insightLabel {
        color: #a6adc8;
    }
    QLabel#activityLabel {
        color: #a6adc8;
    }
    QLabel#notesLabel {
        color: #a6adc8;
    }
    QLabel#statValue {
        color: #cdd6f4;
    }

    /* ---- Keep Settings text metrics identical to light mode ---- */
    QLabel#headerTitle {
        color: #7ea6d9;
        font-size: 24px;
        font-weight: 700;
    }
    QLabel#fieldLabel {
        color: #bac2de;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    QLabel#statusLabel {
        color: #a6adc8;
        font-size: 12px;
    }
    QLabel#metaLabel {
        color: #a6adc8;
        font-size: 13px;
    }

    QGroupBox::title {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }

    /* ---- Checkboxes ---- */
    QCheckBox {
        color: #cdd6f4;
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 1px solid #758192;
        border-radius: 4px;
        background: #2a3038;
    }
    QCheckBox::indicator:checked {
        background: #7ea6d9;
        border: 1px solid #6ea0d8;
    }

    /* ---- Scroll areas ---- */
    QScrollArea {
        background: #20242b;
        border: none;
    }
    QScrollBar:vertical {
        background: #2a3038;
        width: 10px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #4b5563;
        border-radius: 5px;
    }

    /* ---- Calendar ---- */
    QCalendarWidget {
        background: #2a3038;
        color: #d6dbe4;
    }

    /* ---- Dashboard tiles ---- */
    QWidget#dashTile {
        background: #242a33;
        border: 1px solid #3e4652;
        border-radius: 8px;
    }
    QWidget#navBar {
        background: #1c2128;
        border-bottom: 1px solid #3e4652;
    }

    /* ---- Video widget ---- */
    QVideoWidget {
        background: #000000;
    }

    /* ---- Dialogs / Message boxes ---- */
    QDialog {
        background: #20242b;
    }
    QMessageBox {
        background: #20242b;
    }
    QMessageBox QLabel {
        color: #d6dbe4;
    }
"""


def _add_eye_toggle(field: QLineEdit):
    """Attach a show/hide password toggle icon to a QLineEdit."""
    icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
    show_icon = QIcon(os.path.join(icon_dir, "eye_open.svg"))
    hide_icon = QIcon(os.path.join(icon_dir, "eye_closed.svg"))

    action = QAction(show_icon, "", field)
    action.setCheckable(True)
    action.setToolTip("Show / hide password")

    def _toggle(visible: bool):
        action.setIcon(hide_icon if visible else show_icon)
        field.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)

    action.toggled.connect(_toggle)
    field.addAction(action, QLineEdit.TrailingPosition)


class SettingsPage(QWidget):
    SETTINGS_FILE = "settings_data.json"
    CONFIG_FILE = "config.json"

    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QWidget {
                background: #ffffff;
                color: #1f2a37;
                font-size: 13px;
            }
            QLabel#headerTitle {
                color: #0b63ce;
                font-size: 24px;
                font-weight: 700;
                background: transparent;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d7dde5;
                border-radius: 10px;
                margin-top: 12px;
                font-weight: 700;
                padding: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #0b63ce;
                font-size: 12px;
                letter-spacing: 0.5px;
            }
            QLabel#fieldLabel {
                color: #2f4054;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            QComboBox {
                background: #ffffff;
                border: 1px solid #bfd0e0;
                border-radius: 10px;
                padding: 8px 10px;
                min-height: 20px;
            }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #bfd0e0;
                border-radius: 10px;
                padding: 10px 12px;
                min-height: 24px;
            }
            QLineEdit:hover {
                border: 1px solid #90b4db;
            }
            QLineEdit:focus {
                border: 1px solid #0b63ce;
            }
            QComboBox:hover {
                border: 1px solid #90b4db;
            }
            QComboBox:focus {
                border: 1px solid #0b63ce;
            }
            QPushButton {
                background: #edf2f7;
                color: #243447;
                border: 1px solid #ccd8e5;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #e2eaf2;
            }
            QPushButton:focus {
                border: 1px solid #0b63ce;
            }
            QPushButton#primaryAction {
                background: #0b63ce;
                color: #ffffff;
                border: 1px solid #0a58ca;
            }
            QPushButton#primaryAction:hover {
                background: #0a58ca;
            }
            QLabel#statusLabel {
                color: #3f556e;
                font-size: 12px;
                padding: 2px 0;
                border: none;
                background: transparent;
            }
            QLabel#metaLabel {
                color: #51667d;
                font-size: 13px;
            }
        """)
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        self.scroll_area.setWidget(content)
        _outer.addWidget(self.scroll_area)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.title_label = QLabel("Settings")
        self.title_label.setObjectName("headerTitle")
        layout.addWidget(self.title_label)

        pref_group = QGroupBox("Preferences")
        self.pref_group = pref_group
        pref_layout = QVBoxLayout(pref_group)
        pref_layout.setSpacing(8)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_label = QLabel("Theme:")
        self.theme_label.setObjectName("fieldLabel")
        pref_layout.addWidget(self.theme_label)
        pref_layout.addWidget(self.theme_combo)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English"])
        self.language_label = QLabel("Language:")
        self.language_label.setObjectName("fieldLabel")
        pref_layout.addWidget(self.language_label)
        pref_layout.addWidget(self.lang_combo)

        self.admin_contact_group = QGroupBox("Admin Contact (Login Page)")
        admin_contact_layout = QVBoxLayout(self.admin_contact_group)
        admin_contact_layout.setSpacing(8)

        self.admin_contact_name_label = QLabel("Admin Name:")
        self.admin_contact_name_label.setObjectName("fieldLabel")
        self.admin_contact_name_input = QLineEdit()
        self.admin_contact_name_input.setPlaceholderText("Name shown in Contact Admin")
        admin_contact_layout.addWidget(self.admin_contact_name_label)
        admin_contact_layout.addWidget(self.admin_contact_name_input)

        self.admin_contact_email_label = QLabel("Admin Email:")
        self.admin_contact_email_label.setObjectName("fieldLabel")
        self.admin_contact_email_input = QLineEdit()
        self.admin_contact_email_input.setPlaceholderText("admin@example.com")
        admin_contact_layout.addWidget(self.admin_contact_email_label)
        admin_contact_layout.addWidget(self.admin_contact_email_input)

        self.admin_contact_phone_label = QLabel("Admin Phone:")
        self.admin_contact_phone_label.setObjectName("fieldLabel")
        self.admin_contact_phone_input = QLineEdit()
        self.admin_contact_phone_input.setPlaceholderText("+63 900 000 0000")
        admin_contact_layout.addWidget(self.admin_contact_phone_label)
        admin_contact_layout.addWidget(self.admin_contact_phone_input)

        self.admin_contact_location_label = QLabel("Admin Location:")
        self.admin_contact_location_label.setObjectName("fieldLabel")
        self.admin_contact_location_input = QLineEdit()
        self.admin_contact_location_input.setPlaceholderText("Office / Department")
        admin_contact_layout.addWidget(self.admin_contact_location_label)
        admin_contact_layout.addWidget(self.admin_contact_location_input)

        self.account_group = QGroupBox("My Account")
        account_layout = QVBoxLayout(self.account_group)
        account_layout.setSpacing(8)

        self.display_name_label = QLabel("Display Name:")
        self.display_name_label.setObjectName("fieldLabel")
        self.display_name_input = QLineEdit()
        self.display_name_input.setPlaceholderText("Display name")
        account_layout.addWidget(self.display_name_label)
        account_layout.addWidget(self.display_name_input)

        self.dr_prefix_check = QCheckBox("Add Dr.")
        self.dr_prefix_check.setStyleSheet("margin-top: -2px; margin-bottom: 4px;")
        account_layout.addWidget(self.dr_prefix_check)

        self.username_label = QLabel("Username:")
        self.username_label.setObjectName("fieldLabel")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        account_layout.addWidget(self.username_label)
        account_layout.addWidget(self.username_input)

        self.new_password_label = QLabel("New Password (optional):")
        self.new_password_label.setObjectName("fieldLabel")
        self.new_password_input = QLineEdit()
        self.new_password_input.setPlaceholderText("Leave blank to keep current password")
        self.new_password_input.setEchoMode(QLineEdit.Password)
        _add_eye_toggle(self.new_password_input)
        account_layout.addWidget(self.new_password_label)
        account_layout.addWidget(self.new_password_input)

        account_btn_row = QHBoxLayout()
        account_btn_row.addStretch(1)
        self.account_save_btn = QPushButton("Update Account")
        self.account_save_btn.setObjectName("primaryAction")
        self.account_save_btn.clicked.connect(self.update_account)
        account_btn_row.addWidget(self.account_save_btn)
        account_layout.addLayout(account_btn_row)

        self.schedule_group = QGroupBox("My Schedule")
        schedule_layout = QVBoxLayout(self.schedule_group)
        schedule_layout.setSpacing(8)

        self.schedule_hint_label = QLabel("Set your weekly clinic availability shown on your dashboard.")
        self.schedule_hint_label.setObjectName("metaLabel")
        self.schedule_hint_label.setWordWrap(True)
        schedule_layout.addWidget(self.schedule_hint_label)

        schedule_time_row = QHBoxLayout()
        schedule_time_row.setSpacing(8)
        self.schedule_start_label = QLabel("From:")
        self.schedule_start_label.setObjectName("fieldLabel")
        self.schedule_start_time = QTimeEdit()
        self.schedule_start_time.setDisplayFormat("hh:mm AP")
        self.schedule_start_time.setTime(QTime(9, 0))
        self.schedule_end_label = QLabel("To:")
        self.schedule_end_label.setObjectName("fieldLabel")
        self.schedule_end_time = QTimeEdit()
        self.schedule_end_time.setDisplayFormat("hh:mm AP")
        self.schedule_end_time.setTime(QTime(17, 0))
        schedule_time_row.addWidget(self.schedule_start_label)
        schedule_time_row.addWidget(self.schedule_start_time)
        schedule_time_row.addSpacing(12)
        schedule_time_row.addWidget(self.schedule_end_label)
        schedule_time_row.addWidget(self.schedule_end_time)
        schedule_time_row.addStretch(1)
        schedule_layout.addLayout(schedule_time_row)

        self.schedule_days_label = QLabel("Available Days:")
        self.schedule_days_label.setObjectName("fieldLabel")
        schedule_layout.addWidget(self.schedule_days_label)

        self.schedule_day_checks = []
        for idx, (day_key, day_label) in enumerate(_WEEKDAY_OPTIONS):
            checkbox = QCheckBox(day_label)
            checkbox.setChecked(idx < 5)
            self.schedule_day_checks.append((day_key, checkbox))
            schedule_layout.addWidget(checkbox)

        schedule_btn_row = QHBoxLayout()
        schedule_btn_row.addStretch(1)
        self.schedule_save_btn = QPushButton("Update Schedule")
        self.schedule_save_btn.setObjectName("primaryAction")
        self.schedule_save_btn.clicked.connect(self.update_schedule)
        schedule_btn_row.addWidget(self.schedule_save_btn)
        schedule_layout.addLayout(schedule_btn_row)

        layout.addWidget(self.account_group)
        layout.addWidget(self.schedule_group)
        layout.addWidget(pref_group)
        layout.addWidget(self.admin_contact_group)

        # ── Action buttons (right after preferences) ──────────────────────
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.reset_btn = QPushButton("Reset Defaults")
        self.reset_btn.clicked.connect(self.reset_defaults)
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("primaryAction")
        self.save_btn.setAutoDefault(True)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save_settings)
        button_row.addWidget(self.reset_btn)
        button_row.addWidget(self.save_btn)
        layout.addLayout(button_row)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        # ── Divider ───────────────────────────────────────────────────────
        divider = QLabel()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:#dee2e6; margin: 4px 0;")
        layout.addWidget(divider)

        # ── About ─────────────────────────────────────────────────────────
        about_group = QGroupBox("About")
        self.about_group = about_group
        about_layout = QVBoxLayout(about_group)
        about_layout.setSpacing(4)
        self.about_version_label = QLabel("EyeShield EMR v1.0.0")
        self.about_copyright_label = QLabel("© 2026 EyeShield Team")
        self.about_contact_label = QLabel("For support, contact: support@eyeshield.local")
        for lbl in (self.about_version_label, self.about_copyright_label, self.about_contact_label):
            lbl.setObjectName("metaLabel")
        about_layout.addWidget(self.about_version_label)
        about_layout.addWidget(self.about_copyright_label)
        about_layout.addWidget(self.about_contact_label)
        sections_row = QHBoxLayout()
        sections_row.setSpacing(10)
        sections_row.addWidget(about_group, 1)

        # ── Terms of Use ──────────────────────────────────────────────────
        terms_group = QGroupBox("Terms of Use")
        self.terms_group = terms_group
        terms_layout = QVBoxLayout(terms_group)
        self.terms_label = QLabel(
            "By using EyeShield EMR you agree to use the software solely for its "
            "intended medical-records purpose. Unauthorised reproduction, distribution, "
            "or reverse engineering is prohibited. The software is provided 'as is' "
            "without warranty of any kind. The EyeShield Team is not liable for any "
            "loss arising from the use or inability to use this software."
        )
        self.terms_label.setWordWrap(True)
        self.terms_label.setStyleSheet("color:#495057; font-size:12px; line-height:1.5;")
        terms_layout.addWidget(self.terms_label)
        sections_row.addWidget(terms_group, 1)

        # ── Privacy Policy ────────────────────────────────────────────────
        privacy_group = QGroupBox("Privacy Policy")
        self.privacy_group = privacy_group
        privacy_layout = QVBoxLayout(privacy_group)
        self.privacy_label = QLabel(
            "EyeShield EMR stores all patient and user data locally on this device. "
            "No personal information is transmitted to external servers. You are "
            "responsible for securing access to this device and its data. Regular "
            "backups are recommended. For data-deletion requests or privacy concerns, "
            "please contact your system administrator."
        )
        self.privacy_label.setWordWrap(True)
        self.privacy_label.setStyleSheet("color:#495057; font-size:12px; line-height:1.5;")
        privacy_layout.addWidget(self.privacy_label)
        sections_row.addWidget(privacy_group, 1)
        layout.addLayout(sections_row)

        self.load_settings()
        self.theme_combo.currentTextChanged.connect(self.apply_live_preview)
        self.lang_combo.currentTextChanged.connect(self.apply_live_preview)
        self._configure_account_section()
        self._configure_schedule_section()
        self._configure_admin_contact_section()

        self.theme_combo.setFocus()
        self.setTabOrder(self.theme_combo, self.lang_combo)
        self.setTabOrder(self.lang_combo, self.reset_btn)
        self.setTabOrder(self.reset_btn, self.save_btn)

        layout.addStretch()

    def _active_role(self) -> str:
        main_window = self.window()
        role = getattr(main_window, "role", None) if main_window is not self else None
        return str(role or os.environ.get("EYESHIELD_CURRENT_ROLE") or "").strip().lower()

    def _active_username(self) -> str:
        main_window = self.window()
        username = getattr(main_window, "username", None) if main_window is not self else None
        return str(username or os.environ.get("EYESHIELD_CURRENT_USER") or "").strip()

    def _configure_account_section(self):
        role = self._active_role()
        show_account = role == "clinician"
        self.account_group.setVisible(show_account)
        if not show_account:
            return

        username = self._active_username()
        profile = get_user_profile(username) or {}
        display_name = str(profile.get("display_name") or username)
        self.display_name_input.setText(display_name)
        self.dr_prefix_check.setChecked(display_name.strip().lower().startswith("dr. "))
        self.username_input.setText(str(profile.get("username") or username))
        self.new_password_input.clear()

    def _configure_schedule_section(self):
        show_schedule = self._active_role() == "clinician"
        self.schedule_group.setVisible(show_schedule)
        if not show_schedule:
            return
        self._load_schedule_fields()

    def _configure_admin_contact_section(self):
        show_admin_contact = self._active_role() == "admin"
        self.admin_contact_group.setVisible(show_admin_contact)
        if not show_admin_contact:
            return
        self._load_admin_contact_into_fields()

    def _language_pack(self, language: str) -> dict:
        from translations import get_pack
        p = get_pack(language)
        return {
            "title": p["settings_title"],
            "preferences": p["settings_preferences"],
            "theme": p["settings_theme"],
            "language": p["settings_language"],
            "about": p["settings_about"],
            "terms": p["settings_terms"],
            "privacy": p["settings_privacy"],
            "reset": p["settings_reset"],
            "save": p["settings_save"],
        }

    def apply_live_preview(self, _value=None):
        theme = self.theme_combo.currentText()

        # Delegate theme to the main window which clears local styles
        main_window = self.window()
        if main_window is not self and hasattr(main_window, 'apply_theme'):
            main_window.apply_theme(theme)
        else:
            # Fallback during init (settings page not yet parented)
            app = QApplication.instance()
            if app:
                app.setStyleSheet(DARK_STYLESHEET if theme == "Dark" else "")

        # Update language labels
        pack = self._language_pack(self.lang_combo.currentText())
        self.title_label.setText(pack["title"])
        self.pref_group.setTitle(pack["preferences"])
        self.theme_label.setText(pack["theme"])
        self.language_label.setText(pack["language"])
        self.about_group.setTitle(pack["about"])
        self.terms_group.setTitle(pack["terms"])
        self.privacy_group.setTitle(pack["privacy"])
        self.reset_btn.setText(pack["reset"])
        self.save_btn.setText(pack["save"])

        self.status_label.setText(f"Live preview: {theme} / {self.lang_combo.currentText()}")

        # Propagate language change to all other tabs
        lang = self.lang_combo.currentText()
        main_window = self.window()
        if main_window is not self and hasattr(main_window, 'apply_language'):
            main_window.apply_language(lang)

    def _settings_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), self.SETTINGS_FILE)

    def _config_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), self.CONFIG_FILE)

    def _default_settings(self) -> dict:
        return {
            "theme": "Light",
            "language": "English",
        }

    @staticmethod
    def _default_admin_contact() -> dict:
        return {
            "name": "",
            "email": "",
            "phone": "",
            "location": "",
        }

    def _load_admin_contact_data(self) -> dict:
        data = self._default_admin_contact()
        path = self._config_path()
        if not os.path.exists(path):
            return data
        try:
            with open(path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
            if isinstance(loaded, dict):
                contact = loaded.get("admin_contact")
                if isinstance(contact, dict):
                    for key in data:
                        data[key] = str(contact.get(key, "") or "").strip()
        except (OSError, json.JSONDecodeError):
            pass
        return data

    def _load_admin_contact_into_fields(self):
        contact = self._load_admin_contact_data()
        self.admin_contact_name_input.setText(contact["name"])
        self.admin_contact_email_input.setText(contact["email"])
        self.admin_contact_phone_input.setText(contact["phone"])
        self.admin_contact_location_input.setText(contact["location"])

    def _save_admin_contact_data(self) -> tuple[bool, str]:
        path = self._config_path()
        config = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                if isinstance(loaded, dict):
                    config = loaded
            except (OSError, json.JSONDecodeError):
                config = {}
        config["admin_contact"] = {
            "name": self.admin_contact_name_input.text().strip(),
            "email": self.admin_contact_email_input.text().strip(),
            "phone": self.admin_contact_phone_input.text().strip(),
            "location": self.admin_contact_location_input.text().strip(),
        }
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(config, file, indent=2)
            return True, ""
        except OSError as err:
            return False, str(err)

    def _current_admin_contact_values(self) -> dict:
        return {
            "name": self.admin_contact_name_input.text().strip(),
            "email": self.admin_contact_email_input.text().strip(),
            "phone": self.admin_contact_phone_input.text().strip(),
            "location": self.admin_contact_location_input.text().strip(),
        }

    @staticmethod
    def _default_schedule_payload() -> dict:
        return {
            "mode": "weekly-template",
            "start_time": "09:00 AM",
            "end_time": "05:00 PM",
            "days": ["mon", "tue", "wed", "thu", "fri"],
        }

    @staticmethod
    def _parse_time_value(value: str) -> QTime:
        text = str(value or "").strip()
        if not text:
            return QTime()
        for fmt in ("hh:mm AP", "h:mm AP", "hh:mm ap", "h:mm ap", "HH:mm"):
            parsed = QTime.fromString(text, fmt)
            if parsed.isValid():
                return parsed
        return QTime()

    def _load_schedule_fields(self):
        payload = self._default_schedule_payload()
        profile = get_user_profile(self._active_username()) or {}
        raw_availability = profile.get("availability_json")
        try:
            loaded = json.loads(raw_availability) if isinstance(raw_availability, str) and raw_availability else raw_availability
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            payload.update({
                "start_time": str(loaded.get("start_time") or payload["start_time"]),
                "end_time": str(loaded.get("end_time") or payload["end_time"]),
                "days": loaded.get("days") or payload["days"],
            })

        start_time = self._parse_time_value(payload.get("start_time"))
        end_time = self._parse_time_value(payload.get("end_time"))
        if start_time.isValid():
            self.schedule_start_time.setTime(start_time)
        if end_time.isValid():
            self.schedule_end_time.setTime(end_time)

        selected_days = payload.get("days") or []
        selected_set = {str(day).strip().lower() for day in selected_days} if isinstance(selected_days, list) else set()
        for day_key, checkbox in self.schedule_day_checks:
            checkbox.setChecked(day_key in selected_set)

    def _current_schedule_payload(self) -> dict:
        return {
            "mode": "weekly-template",
            "start_time": self.schedule_start_time.time().toString("hh:mm AP"),
            "end_time": self.schedule_end_time.time().toString("hh:mm AP"),
            "days": [day for day, checkbox in self.schedule_day_checks if checkbox.isChecked()],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _prompt_current_password(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Confirm Account Update")
        dialog.setModal(True)
        dialog.setMinimumWidth(360)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel("Enter your current password to continue:")
        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.Password)
        password_input.setPlaceholderText("Current password")
        _add_eye_toggle(password_input)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        ok_btn = QPushButton("Confirm")
        ok_btn.setObjectName("primaryAction")
        ok_btn.setDefault(True)

        cancel_btn.clicked.connect(dialog.reject)
        ok_btn.clicked.connect(dialog.accept)
        password_input.returnPressed.connect(dialog.accept)

        button_row.addWidget(cancel_btn)
        button_row.addWidget(ok_btn)

        layout.addWidget(label)
        layout.addWidget(password_input)
        layout.addLayout(button_row)

        confirmed = dialog.exec() == QDialog.DialogCode.Accepted
        return password_input.text(), confirmed

    def load_settings(self):
        settings = self._default_settings()
        path = self._settings_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                if isinstance(loaded, dict):
                    settings.update(loaded)
            except (OSError, json.JSONDecodeError):
                pass

        self.theme_combo.setCurrentText(settings.get("theme", "Light"))
        saved_language = settings.get("language", "English")
        if saved_language not in {self.lang_combo.itemText(i) for i in range(self.lang_combo.count())}:
            saved_language = "English"
        self.lang_combo.setCurrentText(saved_language)
        if self._active_role() == "admin":
            self._load_admin_contact_into_fields()
        if self._active_role() == "clinician":
            self._load_schedule_fields()
        self.apply_live_preview()
        self.status_label.setText("Settings loaded")

    def save_settings(self):
        admin_contact_changed = False
        if self._active_role() == "admin":
            existing_contact = self._load_admin_contact_data()
            pending_contact = self._current_admin_contact_values()
            admin_contact_changed = pending_contact != existing_contact
            if admin_contact_changed:
                reply = QMessageBox.question(
                    self,
                    "Confirm Admin Contact Update",
                    "Apply updated Contact Admin details to the login page?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.status_label.setText("Save cancelled")
                    return

        settings = {
            "theme": self.theme_combo.currentText(),
            "language": self.lang_combo.currentText(),
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as file:
                json.dump(settings, file, indent=2)
            if self._active_role() == "admin":
                ok, error_message = self._save_admin_contact_data()
                if not ok:
                    self.status_label.setText("Save failed")
                    QMessageBox.warning(self, "Settings", f"Failed to save admin contact: {error_message}")
                    return
            timestamp = datetime.now().strftime("%I:%M %p").lstrip("0")
            self.status_label.setText(f"Saved locally at {timestamp}")
            if admin_contact_changed:
                QMessageBox.information(
                    self,
                    "Settings Updated",
                    "Contact Admin information was updated successfully.",
                )
        except OSError as err:
            self.status_label.setText("Save failed")
            QMessageBox.warning(self, "Settings", f"Failed to save settings: {err}")

    def update_account(self):
        if self._active_role() != "clinician":
            QMessageBox.warning(self, "Account", "Only clinicians can update this section.")
            return

        current_username = self._active_username()
        new_display_name = self.display_name_input.text().strip()
        new_username = self.username_input.text().strip()
        new_password = self.new_password_input.text()

        current_password, confirmed = self._prompt_current_password()
        if not confirmed:
            return
        current_password = str(current_password or "")

        if self.dr_prefix_check.isChecked() and new_display_name:
            if not new_display_name.lower().startswith("dr. "):
                new_display_name = f"Dr. {new_display_name}"

        if not new_display_name:
            QMessageBox.warning(self, "Account", "Display name cannot be empty.")
            return
        if not new_username:
            QMessageBox.warning(self, "Account", "Username cannot be empty.")
            return
        if not current_password:
            QMessageBox.warning(self, "Account", "Enter your current password to continue.")
            return

        ok, message, updated_username = user_store.update_own_account(
            current_username=current_username,
            current_password=current_password,
            new_display_name=new_display_name,
            new_username=new_username,
            new_password=new_password,
        )
        if not ok:
            QMessageBox.warning(self, "Account", message)
            return

        updated_username = str(updated_username or current_username)
        os.environ["EYESHIELD_CURRENT_USER"] = updated_username
        os.environ["EYESHIELD_CURRENT_NAME"] = new_display_name

        main_window = self.window()
        if main_window is not self:
            if hasattr(main_window, "username"):
                main_window.username = updated_username
            if hasattr(main_window, "display_name"):
                main_window.display_name = new_display_name
            if hasattr(main_window, "user_info_label"):
                display_title = getattr(main_window, "display_title", "")
                main_window.user_info_label.setText(f"  {new_display_name}  •  {display_title}  ")

        self.new_password_input.clear()
        self.username_input.setText(updated_username)
        self.status_label.setText("Account updated")
        requires_relogin = (updated_username != current_username) or bool(new_password)
        if requires_relogin:
            QMessageBox.information(
                self,
                "Account",
                f"{message}\n\nPlease re-login to apply all account changes.",
            )
        else:
            QMessageBox.information(
                self,
                "Account",
                f"{message}\n\nDisplay name changes are applied immediately.",
            )

    def update_schedule(self):
        if self._active_role() != "clinician":
            QMessageBox.warning(self, "Schedule", "Only clinicians can update this section.")
            return

        selected_days = [day for day, checkbox in self.schedule_day_checks if checkbox.isChecked()]
        if not selected_days:
            QMessageBox.warning(self, "Schedule", "Select at least one available weekday.")
            return
        if self.schedule_end_time.time() <= self.schedule_start_time.time():
            QMessageBox.warning(self, "Schedule", "End time must be later than start time.")
            return

        availability_json = json.dumps(
            self._current_schedule_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        ok, message = user_store.update_own_availability(
            current_username=self._active_username(),
            availability_json=availability_json,
        )
        if not ok:
            QMessageBox.warning(self, "Schedule", message)
            return

        self.status_label.setText("Schedule updated")
        main_window = self.window()
        if main_window is not self and hasattr(main_window, "refresh_dashboard"):
            main_window.refresh_dashboard()
        QMessageBox.information(
            self,
            "Schedule Updated",
            message,
        )

    def reset_defaults(self):
        defaults = self._default_settings()
        self.theme_combo.setCurrentText(defaults["theme"])
        self.lang_combo.setCurrentText(defaults["language"])
        if self._active_role() == "admin":
            admin_defaults = self._default_admin_contact()
            self.admin_contact_name_input.setText(admin_defaults["name"])
            self.admin_contact_email_input.setText(admin_defaults["email"])
            self.admin_contact_phone_input.setText(admin_defaults["phone"])
            self.admin_contact_location_input.setText(admin_defaults["location"])
        if self._active_role() == "clinician":
            default_schedule = self._default_schedule_payload()
            start_time = self._parse_time_value(default_schedule["start_time"])
            end_time = self._parse_time_value(default_schedule["end_time"])
            if start_time.isValid():
                self.schedule_start_time.setTime(start_time)
            if end_time.isValid():
                self.schedule_end_time.setTime(end_time)
            selected_days = set(default_schedule["days"])
            for day_key, checkbox in self.schedule_day_checks:
                checkbox.setChecked(day_key in selected_days)
        self.status_label.setText("Defaults restored (not yet saved)")
