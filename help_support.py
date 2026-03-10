from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGroupBox, QScrollArea
from PySide6.QtCore import Qt

class HelpSupportPage(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("background: #f8f9fa;")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        self._help_title_lbl = QLabel("Help & Support")
        self._help_title_lbl.setObjectName("pageHeader")
        self._help_title_lbl.setStyleSheet("font-size: 24px; font-weight: 700; color: #007bff;")
        root_layout.addWidget(self._help_title_lbl)

        self._help_subtitle_lbl = QLabel("Quick guidance for daily workflows, troubleshooting, and support contacts.")
        self._help_subtitle_lbl.setObjectName("pageSubtitle")
        self._help_subtitle_lbl.setStyleSheet("color: #495057; font-size: 13px;")
        root_layout.addWidget(self._help_subtitle_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        self._help_content_widget = QWidget()
        self._help_content_layout = QVBoxLayout(self._help_content_widget)
        self._help_content_layout.setSpacing(16)
        self._help_content_layout.setContentsMargins(0, 0, 0, 0)

        self._build_help_groups("English")

        scroll.setWidget(self._help_content_widget)
        root_layout.addWidget(scroll)

    def _build_help_groups(self, language: str):
        from translations import get_pack
        pack = get_pack(language)

        # Clear existing groups (and trailing stretch)
        while self._help_content_layout.count():
            item = self._help_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for title_key, body_key in [
            ("hlp_quick_start", "hlp_quick_start_body"),
            ("hlp_howto",       "hlp_howto_body"),
            ("hlp_faq",         "hlp_faq_body"),
            ("hlp_troubleshoot","hlp_troubleshoot_body"),
            ("hlp_privacy",     "hlp_privacy_body"),
            ("hlp_contact",     "hlp_contact_body"),
        ]:
            self._help_content_layout.addWidget(
                self.build_group(pack[title_key], pack[body_key])
            )

        self._help_content_layout.addStretch()

    def apply_language(self, language: str):
        from translations import get_pack
        pack = get_pack(language)
        self._help_title_lbl.setText(pack["hlp_title"])
        self._help_subtitle_lbl.setText(pack["hlp_subtitle"])
        self._build_help_groups(language)

    @staticmethod
    def build_group(title, body_html):
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox {
                font-size: 15px;
                font-weight: 700;
                color: #007bff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin-top: 8px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px 0 8px;
            }
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 28, 16, 16)

        body = QLabel(body_html)
        body.setTextFormat(Qt.RichText)
        body.setWordWrap(True)
        body.setStyleSheet("color: #495057; font-size: 13px;")
        layout.addWidget(body)
        return group
