"""
Dashboard module for EyeShield EMR application.
Contains main application window and dashboard functionality.
"""

import os
import random
import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QGroupBox, QMessageBox, QGridLayout
)
from PySide6.QtCore import Qt, QSize, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QFont
from PySide6.QtSvg import QSvgRenderer

from screening import ScreeningPage
from reports import ReportsPage
from users import UsersPage
from settings import SettingsPage, DARK_STYLESHEET
from help_support import HelpSupportPage
from camera import CameraPage
from auth import DB_FILE


class EyeShieldApp(QMainWindow):
    """Main application window"""

    def __init__(self, username, role):
        super().__init__()

        self.username = username
        self.role = role
        self._dark_mode = False
        self._saved_styles = {}
        self._logging_out = False

        self.setWindowTitle("EyeShield – DR Screening")
        self.setMinimumSize(1100, 700)
        self.resize(1400, 860)

        # Set app icon
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eyeshield_icon.svg")
        self._app_icon_pixmap = self._load_svg_pixmap(_icon_path, 256)
        self._app_icon = QIcon(self._app_icon_pixmap)
        self.setWindowIcon(self._app_icon)
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

        root = QWidget()
        root_layout = QVBoxLayout(root)

        # Create top navigation bar
        nav_bar = QWidget()
        nav_bar.setObjectName("navBar")
        nav_bar.setFixedHeight(78)
        self.nav_bar = nav_bar
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(12, 4, 12, 4)
        nav_layout.setSpacing(4)
        nav_bar.setStyleSheet("""
            QWidget#navBar {
                background: #f8f9fa;
                border-bottom: 1px solid #dee2e6;
            }
        """)


        # App title + icon in a fixed-width container so they never shift
        title_icon_container = QWidget()
        title_icon_container.setFixedSize(165, 70)
        title_icon_container.setStyleSheet("background: transparent;")
        title_icon_layout = QHBoxLayout(title_icon_container)
        title_icon_layout.setContentsMargins(0, 0, 0, 0)
        title_icon_layout.setSpacing(2)

        self.title_label = QLabel("EyeShield")
        title_label = self.title_label
        title_label.setObjectName("appTitle")
        title_label.setStyleSheet("color: #007bff; font-size: 20px; font-weight: 700; text-decoration: none;")
        title_font = QFont("Segoe UI Variable", 14)
        title_font.setBold(True)
        title_font.setUnderline(False)
        title_label.setFont(title_font)
        title_label.setFixedWidth(118)
        title_icon_layout.addWidget(title_label)

        icon_label = QLabel()
        self.nav_icon_label = icon_label
        self._icon_path = _icon_path
        icon_pixmap = self._load_svg_pixmap_colored(_icon_path, "#007bff", 256).scaled(
            QSize(38, 38), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        if not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap)
        icon_label.setFixedSize(38, 38)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        title_icon_layout.addWidget(icon_label)

        self.title_icon_container = title_icon_container
        nav_layout.addWidget(title_icon_container)
        nav_layout.addStretch(1)

        # Navigation buttons with icons and small text labels below
        def nav_button_with_label(icon_path, text):
            w = QWidget()
            w.setFixedSize(60, 66)
            w.setStyleSheet("QWidget { background: transparent; }")
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 2, 0, 2)
            v.setSpacing(2)

            btn = QPushButton("")
            btn.setProperty("navIconPath", icon_path)
            btn.setStyleSheet(self.get_nav_button_style(icon_only=True))
            btn.setFixedSize(50, 40)
            btn.setIconSize(QSize(24, 24))

            label = QLabel(text)
            label.setAlignment(Qt.AlignHCenter)
            label.setFixedWidth(60)
            lbl_font = QFont("Segoe UI Variable", 8)
            lbl_font.setUnderline(False)
            lbl_font.setStrikeOut(False)
            label.setFont(lbl_font)
            label.setStyleSheet("font-size: 10px; color: #495057; margin-top: 0px; text-decoration: none; border: none;")

            v.addWidget(btn, 0, Qt.AlignHCenter)
            v.addWidget(label, 0, Qt.AlignHCenter)
            return w, btn, label

        navs = [
            (self._resolve_existing_path(os.path.join(icons_dir, "dashboard.svg"), os.path.join(icons_dir, "dasboard.svg")), "Dashboard"),
            (self._resolve_existing_path(os.path.join(icons_dir, "screening.svg")), "Screening"),
            (self._resolve_existing_path(os.path.join(icons_dir, "camera.svg")), "Camera"),
            (self._resolve_existing_path(os.path.join(icons_dir, "reports.svg")), "Reports"),
            (self._resolve_existing_path(os.path.join(icons_dir, "users.svg")), "Users"),
            (self._resolve_existing_path(os.path.join(icons_dir, "settings.svg")), "Settings"),
            (self._resolve_existing_path(os.path.join(icons_dir, "help.svg")), "Help"),
        ]
        nav_widgets = []
        nav_buttons = []
        nav_labels = []
        for icon_path, text in navs:
            w, btn, label = nav_button_with_label(icon_path, text)
            nav_layout.addWidget(w)
            nav_layout.addStretch(1)
            nav_widgets.append(w)
            nav_buttons.append(btn)
            nav_labels.append(label)

        self.nav_buttons = nav_buttons
        self.nav_labels = nav_labels
        self.nav_widgets = nav_widgets

        # User info on the right — styled as a pill badge
        user_info = QLabel(f"  {self.username}  \u2022  {self.role}  ")
        self.user_info_label = user_info
        user_info.setObjectName("userInfo")
        user_info.setStyleSheet(
            "color: #007bff; background: #e8f0fe; border: 1px solid #b8d0f7;"
            "border-radius: 12px; font-size: 12px; font-weight: 600;"
            "padding: 2px 8px; margin-left: 12px; margin-right: 8px;"
        )
        nav_layout.addWidget(user_info)

        logout_btn = QPushButton("")
        self.logout_btn = logout_btn
        logout_btn.setObjectName("logoutBtn")
        logout_btn.setFixedSize(44, 44)
        logout_btn.setIconSize(QSize(20, 20))
        logout_btn.setToolTip("Shutdown / Log out")
        logout_btn.setStyleSheet("""
            QPushButton {
                background: #dc3545;
                color: white;
                border: 1px solid #bb2d3b;
                border-radius: 8px;
                padding: 0px;
                font-size: 18px;
                font-weight: 600;
                text-decoration: none;
            }
            QPushButton:hover { background: #c82333; }
            QPushButton:focus { outline: none; border: 1px solid #bb2d3b; }
        """)
        self._logout_icon_path = self._resolve_existing_path(os.path.join(icons_dir, "logout.svg"))
        self._update_logout_icon()
        logout_btn.clicked.connect(self.handle_logout)
        nav_layout.addWidget(logout_btn)

        # Connect buttons
        nav_buttons[0].clicked.connect(lambda: self._navigate_to(0))
        nav_buttons[1].clicked.connect(lambda: self._navigate_to(1))
        nav_buttons[2].clicked.connect(lambda: self._navigate_to(2))
        nav_buttons[3].clicked.connect(lambda: self._navigate_to(3))
        nav_buttons[4].clicked.connect(lambda: self._navigate_to(4, requires_admin=True))
        nav_buttons[5].clicked.connect(lambda: self._navigate_to(5))
        nav_buttons[6].clicked.connect(lambda: self._navigate_to(6))

        if self.role != "admin":
            nav_buttons[4].setEnabled(False)
            nav_buttons[4].setToolTip("Admins only")
            nav_labels[4].setStyleSheet("font-size: 10px; color: #adb5bd; margin-top: 0px; text-decoration: none; border: none;")

        # (All navigation button connections are now handled via nav_buttons list above)

        root_layout.addWidget(nav_bar)

        # Main content area
        main = QWidget()
        main.setStyleSheet("background: #f8f9fa;")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.pages = QStackedWidget()

        # Create main pages first so dashboard can query live data
        self.screening_page = ScreeningPage()
        self.camera_page = CameraPage()
        self.reports_page = ReportsPage()
        self.users_page = UsersPage()
        self.settings_page = SettingsPage()
        self.help_support_page = HelpSupportPage()

        # Dashboard is created after the other pages so it can be refreshed
        self.dashboard_page = self.create_dashboard_page()

        self.users_page.parent_app = self

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.screening_page)
        self.pages.addWidget(self.camera_page)
        self.pages.addWidget(self.reports_page)
        self.pages.addWidget(self.users_page)
        self.pages.addWidget(self.settings_page)
        self.pages.addWidget(self.help_support_page)
        self.pages.currentChanged.connect(self._on_page_changed)

        main_layout.addWidget(self.pages)
        root_layout.addWidget(main)
        self.setCentralWidget(root)
        self.refresh_dashboard()
        self._set_active_nav(0)

        # Ensure nav bar styles are correct for the initial theme
        self._apply_nav_theme(False)

        # Apply saved theme from settings (must run after all pages are parented)
        saved_theme = self.settings_page.theme_combo.currentText()
        if saved_theme == "Dark":
            self.apply_theme("Dark")

    @staticmethod
    def _load_svg_pixmap(svg_path: str, size: int = 64) -> QPixmap:
        """Render an SVG file to a QPixmap at the requested size."""
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return QPixmap()
        image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        return QPixmap.fromImage(image)

    @staticmethod
    def _load_svg_pixmap_colored(svg_path: str, color: str, size: int = 64) -> QPixmap:
        """Render an SVG with all black strokes/fills replaced by the given color."""
        try:
            with open(svg_path, "r", encoding="utf-8") as f:
                svg_text = f.read()
        except OSError:
            return QPixmap()
        svg_text = svg_text.replace('stroke="currentColor"', f'stroke="{color}"')
        svg_text = svg_text.replace('fill="currentColor"', f'fill="{color}"')
        svg_text = svg_text.replace('stroke="black"', f'stroke="{color}"')
        svg_text = svg_text.replace('fill="black"', f'fill="{color}"')
        svg_text = svg_text.replace('stroke="#000"', f'stroke="{color}"')
        svg_text = svg_text.replace('fill="#000"', f'fill="{color}"')
        svg_text = svg_text.replace('stroke="#000000"', f'stroke="{color}"')
        svg_text = svg_text.replace('fill="#000000"', f'fill="{color}"')
        svg_text = svg_text.replace('stroke="#e3e3e3"', f'stroke="{color}"')
        svg_text = svg_text.replace('fill="#e3e3e3"', f'fill="{color}"')
        svg_text = svg_text.replace('fill="white"', 'fill="transparent"')
        data = QByteArray(svg_text.encode("utf-8"))
        renderer = QSvgRenderer(data)
        if not renderer.isValid():
            return QPixmap()
        image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        return QPixmap.fromImage(image)

    @staticmethod
    def _resolve_existing_path(*paths: str) -> str:
        """Return the first existing path, or the first candidate as fallback."""
        for path in paths:
            if path and os.path.exists(path):
                return path
        return paths[0] if paths else ""

    def _set_button_svg_icon(self, button: QPushButton, svg_path: str, color: str, size: QSize):
        """Apply a recolored SVG icon to a button."""
        if not svg_path:
            button.setIcon(QIcon())
            return
        pixmap = self._load_svg_pixmap_colored(svg_path, color, 256)
        if pixmap.isNull():
            button.setIcon(QIcon())
            return
        button.setIcon(QIcon(pixmap))
        button.setIconSize(size)

    def _refresh_nav_button_icons(self, active_index: int):
        """Recolor navigation SVG icons to match active/inactive and theme state."""
        if not hasattr(self, "nav_buttons"):
            return
        dark = getattr(self, "_dark_mode", False)
        active_color = "#89b4fa" if dark else "#007bff"
        inactive_color = "#a6adc8" if dark else "#495057"
        disabled_color = "#6c7086" if dark else "#adb5bd"
        icon_size = QSize(24, 24)
        for i, btn in enumerate(self.nav_buttons):
            icon_path = btn.property("navIconPath") or ""
            if not btn.isEnabled():
                color = disabled_color
            elif i == active_index:
                color = active_color
            else:
                color = inactive_color
            self._set_button_svg_icon(btn, icon_path, color, icon_size)

    def _update_logout_icon(self):
        """Render the logout SVG icon using white for the red button."""
        if hasattr(self, "logout_btn"):
            self._set_button_svg_icon(self.logout_btn, getattr(self, "_logout_icon_path", ""), "#ffffff", QSize(20, 20))

    def _apply_nav_theme(self, dark: bool):
        """Explicitly re-apply nav bar styles so sizes never change between themes."""
        if dark:
            nav_bg       = "background: #181825; border-bottom: 1px solid #45475a;"
            title_style  = "color: #89b4fa; font-size: 20px; font-weight: 700; text-decoration: none;"
            user_style   = (
                "color: #cdd6f4; background: #313244; border: 1px solid #45475a;"
                "border-radius: 12px; font-size: 12px; font-weight: 600;"
                "padding: 2px 8px; margin-left: 12px; margin-right: 8px;"
            )
            inactive_lbl = "font-size: 10px; color: #a6adc8; margin-top: 0px; text-decoration: none; border: none;"
        else:
            nav_bg       = "background: #f8f9fa; border-bottom: 1px solid #dee2e6;"
            title_style  = "color: #007bff; font-size: 20px; font-weight: 700; text-decoration: none;"
            user_style   = (
                "color: #007bff; background: #e8f0fe; border: 1px solid #b8d0f7;"
                "border-radius: 12px; font-size: 12px; font-weight: 600;"
                "padding: 2px 8px; margin-left: 12px; margin-right: 8px;"
            )
            inactive_lbl = "font-size: 10px; color: #495057; margin-top: 0px; text-decoration: none; border: none;"

        if hasattr(self, "nav_bar"):
            self.nav_bar.setFixedHeight(78)
            self.nav_bar.setStyleSheet(f"QWidget#navBar {{ {nav_bg} }}")
        if hasattr(self, "title_icon_container"):
            self.title_icon_container.setFixedSize(165, 70)
            self.title_icon_container.setStyleSheet("background: transparent;")
        if hasattr(self, "title_label"):
            self.title_label.setFixedWidth(118)
            self.title_label.setStyleSheet(title_style)
            title_font = QFont("Segoe UI Variable", 14)
            title_font.setBold(True)
            title_font.setUnderline(False)
            self.title_label.setFont(title_font)
        if hasattr(self, "nav_icon_label"):
            self.nav_icon_label.setFixedSize(38, 38)
            self.nav_icon_label.setAlignment(Qt.AlignCenter)
            self.nav_icon_label.setStyleSheet("background: transparent;")
        if hasattr(self, "user_info_label"):
            self.user_info_label.setStyleSheet(user_style)

        # Transparent container so nav-bar background always shows through
        # Also re-assert fixed sizes so layout cannot shift
        if hasattr(self, "nav_widgets"):
            for w in self.nav_widgets:
                w.setFixedSize(60, 66)
                w.setStyleSheet("QWidget { background: transparent; }")

        # Re-apply button QSS so nav buttons stay visually consistent across theme switches
        btn_font = QFont("Segoe UI Variable", 14)
        btn_font.setUnderline(False)
        btn_font.setStrikeOut(False)
        if hasattr(self, "nav_buttons"):
            for btn in self.nav_buttons:
                btn.setFixedSize(50, 40)
                if btn.isEnabled():
                    btn.setStyleSheet(self.get_nav_button_style(icon_only=True))
                    btn.setFont(btn_font)
            active_index = self.pages.currentIndex() if hasattr(self, "pages") else 0
            self._refresh_nav_button_icons(active_index)
        self._update_logout_icon()

        # Re-apply label QSS + fresh QFont
        lbl_font = QFont("Segoe UI Variable", 8)
        lbl_font.setUnderline(False)
        lbl_font.setStrikeOut(False)
        if hasattr(self, "nav_labels"):
            for lbl in self.nav_labels:
                lbl.setStyleSheet(inactive_lbl)
                lbl.setFont(lbl_font)

    def _update_nav_icon(self, dark: bool):
        """Re-render the nav bar icon to match the current theme."""
        if not hasattr(self, "nav_icon_label") or not hasattr(self, "_icon_path"):
            return
        color = "#cdd6f4" if dark else "#007bff"
        pixmap = self._load_svg_pixmap_colored(self._icon_path, color, 256).scaled(
            QSize(38, 38), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        if not pixmap.isNull():
            self.nav_icon_label.setPixmap(pixmap)

    # Sidebar removed; navigation is now in the top bar

    def _navigate_to(self, index, requires_admin=False):
        if requires_admin and self.role != "admin":
            QMessageBox.warning(self, "Access Denied", "Only admins can access the Users tab.")
            return
        self.pages.setCurrentIndex(index)

    def _on_page_changed(self, index):
        self._set_active_nav(index)
        if index == 2:
            self.camera_page.enter_page()
        else:
            self.camera_page.leave_page()
        if index == 0:
            self.refresh_dashboard()

    def _set_active_nav(self, index: int):
        """Highlight the active navigation button and dim the rest."""
        if not hasattr(self, "nav_buttons"):
            return
        dark = getattr(self, '_dark_mode', False)
        if dark:
            active_btn_style = """
                QPushButton {
                    color: #89b4fa;
                    text-align: center;
                    padding: 4px 0px;
                    border: 1px solid transparent;
                    border-radius: 8px;
                    font-size: 22px;
                    font-weight: 500;
                    background: #313244;
                    text-decoration: none;
                }
                QPushButton:hover { background: #3a3a4f; }
                QPushButton:focus { outline: none; border: 1px solid transparent; }
            """
            inactive_btn_style = """
                QPushButton {
                    color: #a6adc8;
                    text-align: center;
                    padding: 4px 0px;
                    border: 1px solid transparent;
                    border-radius: 8px;
                    font-size: 22px;
                    font-weight: 500;
                    background: transparent;
                    text-decoration: none;
                }
                QPushButton:hover {
                    background: #45475a;
                    color: #89b4fa;
                }
                QPushButton:focus { outline: none; border: 1px solid transparent; }
            """
            active_label = "font-size: 10px; color: #89b4fa; margin-top: 0px; text-decoration: none; border: none;"
            inactive_label = "font-size: 10px; color: #a6adc8; margin-top: 0px; text-decoration: none; border: none;"
        else:
            active_btn_style = """
                QPushButton {
                    color: #007bff;
                    text-align: center;
                    padding: 4px 0px;
                    border: 1px solid transparent;
                    border-radius: 8px;
                    font-size: 22px;
                    font-weight: 500;
                    background: #e8f0fe;
                    text-decoration: none;
                }
                QPushButton:hover { background: #dbe4f8; }
                QPushButton:focus { outline: none; border: 1px solid transparent; }
            """
            inactive_btn_style = self.get_nav_button_style(icon_only=True)
            active_label = "font-size: 10px; color: #007bff; margin-top: 0px; text-decoration: none; border: none;"
            inactive_label = "font-size: 10px; color: #495057; margin-top: 0px; text-decoration: none; border: none;"

        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.setStyleSheet(active_btn_style)
            elif btn.isEnabled():
                btn.setStyleSheet(inactive_btn_style)
        for i, label in enumerate(self.nav_labels):
            if i == index:
                label.setStyleSheet(active_label)
            elif self.nav_buttons[i].isEnabled():
                label.setStyleSheet(inactive_label)
        self._refresh_nav_button_icons(index)

    def apply_theme(self, theme: str):
        """Apply theme across the entire application by clearing local stylesheets."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()

        # Widgets that belong to the nav bar — we manage these explicitly in
        # _apply_nav_theme so they must never be wiped or blindly restored.
        nav_protected = set()
        if hasattr(self, "nav_bar"):
            nav_protected.add(id(self.nav_bar))
            for w in self.nav_bar.findChildren(QWidget):
                nav_protected.add(id(w))

        if theme == "Dark":
            if self._dark_mode:
                return
            self._dark_mode = True
            # Lock nav sizes BEFORE the global stylesheet can affect them
            self._apply_nav_theme(True)
            self._saved_styles = {}
            for widget in self.findChildren(QWidget):
                if id(widget) in nav_protected:
                    continue
                ss = widget.styleSheet()
                if ss:
                    self._saved_styles[id(widget)] = (widget, ss)
                    widget.setStyleSheet("")
            app.setStyleSheet(DARK_STYLESHEET)
            # Re-apply after stylesheet to ensure our values win
            self._apply_nav_theme(True)
        else:
            if not self._dark_mode:
                return
            self._dark_mode = False
            # Lock nav sizes BEFORE clearing global stylesheet
            self._apply_nav_theme(False)
            app.setStyleSheet("")
            for _, (widget, ss) in self._saved_styles.items():
                try:
                    widget.setStyleSheet(ss)
                except RuntimeError:
                    pass
            self._saved_styles = {}
            # Re-apply after restore
            self._apply_nav_theme(False)

        # Force layout recalculation on nav bar
        if hasattr(self, "nav_bar"):
            self.nav_bar.updateGeometry()
            self.nav_bar.update()

        current_idx = self.pages.currentIndex()
        self._set_active_nav(current_idx)

        # Update nav icon for the new theme
        self._update_nav_icon(self._dark_mode)

        # Refresh quote label with correct accent color
        if hasattr(self, 'quote_label'):
            self.quote_label.setText(self.get_medical_quote(dark=self._dark_mode))

    def closeEvent(self, event):
        """Ask for confirmation before closing the application."""
        if getattr(self, '_logging_out', False):
            event.accept()
            return
        reply = QMessageBox.question(
            self,
            "Quit EyeShield",
            "Are you sure you want to quit EyeShield?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    def handle_logout(self):
        reply = QMessageBox.question(
            self,
            "Logout",
            "Are you sure you want to log out?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from login import LoginWindow
        self._logging_out = True
        self.login = LoginWindow()
        self.login.show()
        self.close()

    def create_dashboard_page(self):
        """Create dashboard page"""
        page = QWidget()
        page.setStyleSheet("background: #f8f9fa;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)

        def make_tile(title, accent="#007bff", minimum_height=120):
            tile = QWidget()
            tile.setObjectName("dashTile")
            tile.setMinimumHeight(minimum_height)
            tile.setStyleSheet(f"""
                QWidget#dashTile {{
                    background: white;
                    border: 1px solid #dee2e6;
                    border-left: 4px solid {accent};
                    border-radius: 8px;
                }}
                QLabel#tileTitle {{
                    color: #495057;
                    font-size: 12px;
                    font-weight: 700;
                    letter-spacing: 0.5px;
                    text-transform: uppercase;
                }}
            """)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(16, 16, 16, 16)
            tile_layout.setSpacing(8)
            title_label = QLabel(title)
            title_label.setObjectName("tileTitle")
            tile_layout.addWidget(title_label)
            return tile, tile_layout

        hero_tile, hero_layout = make_tile("Overview", accent="#007bff", minimum_height=170)
        welcome_title = QLabel(f"Welcome, {self.username}!")
        welcome_title.setObjectName("welcomeTitle")
        welcome_title.setStyleSheet("color: #007bff; font-size: 24px; font-weight: 700;")
        welcome_subtitle = QLabel("Diabetic Retinopathy Screening Command Center")
        welcome_subtitle.setObjectName("pageSubtitle")
        welcome_subtitle.setStyleSheet("color: #6c757d; font-size: 14px;")
        self.quote_label = QLabel(self.get_medical_quote(dark=self._dark_mode))
        self.quote_label.setObjectName("quoteLabel")
        self.quote_label.setStyleSheet("color: #495057; font-size: 13px; font-style: italic;")
        self.quote_label.setTextFormat(Qt.RichText)
        self.quote_label.setWordWrap(True)
        hero_layout.addWidget(welcome_title)
        hero_layout.addWidget(welcome_subtitle)
        hero_layout.addWidget(self.quote_label)
        grid.addWidget(hero_tile, 0, 0, 1, 2)

        session_tile, session_layout = make_tile("Session", accent="#17a2b8", minimum_height=170)
        self.dashboard_date_label = QLabel("")
        self.dashboard_date_label.setObjectName("dashDate")
        self.dashboard_date_label.setStyleSheet("font-size: 13px; color: #007bff; font-weight: 600;")
        role_label = QLabel(f"Role: {self.role.capitalize()}")
        role_label.setStyleSheet("font-size: 13px; color: #495057;")
        self.queue_status_label = QLabel("Queue: Ready")
        self.queue_status_label.setStyleSheet("font-size: 13px; color: #495057;")
        session_layout.addWidget(self.dashboard_date_label)
        session_layout.addWidget(role_label)
        session_layout.addWidget(self.queue_status_label)
        session_layout.addStretch()
        grid.addWidget(session_tile, 0, 2)

        total_tile, total_layout = make_tile("Total Screenings", accent="#28a745")
        self.total_screenings_value = QLabel("0")
        self.total_screenings_value.setObjectName("bigValue")
        self.total_screenings_value.setStyleSheet("font-size: 32px; font-weight: 700; color: #212529;")
        total_hint = QLabel("All saved DR screenings")
        total_hint.setObjectName("hintLabel")
        total_hint.setStyleSheet("font-size: 12px; color: #6c757d;")
        total_layout.addWidget(self.total_screenings_value)
        total_layout.addWidget(total_hint)
        total_layout.addStretch()
        grid.addWidget(total_tile, 1, 0)

        attention_tile, attention_layout = make_tile("High Attention", accent="#dc3545")
        self.high_attention_value = QLabel("0")
        self.high_attention_value.setObjectName("bigValue")
        self.high_attention_value.setStyleSheet("font-size: 32px; font-weight: 700; color: #212529;")
        self.high_attention_hint = QLabel("Cases flagged for follow-up")
        self.high_attention_hint.setObjectName("hintLabel")
        self.high_attention_hint.setStyleSheet("font-size: 12px; color: #6c757d;")
        attention_layout.addWidget(self.high_attention_value)
        attention_layout.addWidget(self.high_attention_hint)
        attention_layout.addStretch()
        grid.addWidget(attention_tile, 1, 1)

        actions_tile, actions_layout = make_tile("Clinical Actions", accent="#6f42c1", minimum_height=250)
        actions_layout.setSpacing(10)

        def make_action_btn(label, color, hover):
            btn = QPushButton(label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: white;
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: {hover}; }}
            """)
            return btn

        btn_new = make_action_btn("New Patient Screening", "#28a745", "#218838")
        btn_new.clicked.connect(lambda: self.pages.setCurrentIndex(1))

        btn_camera = make_action_btn("Open Camera", "#fd7e14", "#e66a00")
        btn_camera.clicked.connect(lambda: self.pages.setCurrentIndex(2))

        btn_reports = make_action_btn("Reports", "#17a2b8", "#117a8b")
        btn_reports.clicked.connect(lambda: self.pages.setCurrentIndex(3))

        btn_users = make_action_btn("Users", "#6f42c1", "#563d7c")
        btn_users.clicked.connect(lambda: self.pages.setCurrentIndex(4))

        actions_layout.addWidget(btn_new)
        actions_layout.addWidget(btn_camera)
        actions_layout.addWidget(btn_reports)
        actions_layout.addWidget(btn_users)
        actions_layout.addStretch()

        if self.role == "clinician":
            btn_users.setEnabled(False)
            btn_users.setToolTip("Admins only")

        grid.addWidget(actions_tile, 1, 2, 2, 1)

        confidence_tile, confidence_layout = make_tile("Average Confidence", accent="#ffc107")
        self.avg_confidence_value = QLabel("—")
        self.avg_confidence_value.setObjectName("bigValue")
        self.avg_confidence_value.setStyleSheet("font-size: 32px; font-weight: 700; color: #212529;")
        confidence_hint = QLabel("Across records with confidence data")
        confidence_hint.setObjectName("hintLabel")
        confidence_hint.setStyleSheet("font-size: 12px; color: #6c757d;")
        confidence_layout.addWidget(self.avg_confidence_value)
        confidence_layout.addWidget(confidence_hint)
        confidence_layout.addStretch()
        grid.addWidget(confidence_tile, 2, 0)

        insight_tile, insight_layout = make_tile("Clinical Insight", accent="#fd7e14")
        self.insight_label = QLabel("Start a screening to generate real-time insight.")
        self.insight_label.setObjectName("insightLabel")
        self.insight_label.setStyleSheet("font-size: 13px; color: #495057;")
        self.insight_label.setWordWrap(True)
        insight_layout.addWidget(self.insight_label)
        insight_layout.addStretch()
        grid.addWidget(insight_tile, 2, 1)

        activity_tile, activity_layout = make_tile("Recent Clinical Activity", accent="#007bff", minimum_height=180)
        self.recent_activity_label = QLabel("No recent clinical activity. Ready for patient screenings.")
        self.recent_activity_label.setObjectName("activityLabel")
        self.recent_activity_label.setStyleSheet("color: #6c757d; font-size: 14px; font-style: italic;")
        self.recent_activity_label.setWordWrap(True)
        activity_layout.addWidget(self.recent_activity_label)
        activity_layout.addStretch()
        grid.addWidget(activity_tile, 3, 0, 1, 2)

        quick_notes_tile, quick_notes_layout = make_tile("Workflow", accent="#20c997", minimum_height=180)
        quick_notes = QLabel("• Verify patient details before analysis\n• Capture clear retinal images\n• Record follow-up actions in notes")
        quick_notes.setObjectName("notesLabel")
        quick_notes.setStyleSheet("font-size: 13px; color: #495057; line-height: 1.35;")
        quick_notes.setWordWrap(True)
        quick_notes_layout.addWidget(quick_notes)
        quick_notes_layout.addStretch()
        grid.addWidget(quick_notes_tile, 3, 2)

        layout.addLayout(grid)
        layout.addStretch()
        return page

    @staticmethod
    def get_medical_quote(dark=False):
        quotes = [
            ("Wherever the art of Medicine is loved, there is also a love of Humanity.", "Hippocrates"),
            ("Healing is a matter of time, but it is sometimes also a matter of opportunity.", "Hippocrates"),
            ("Life is short, art is long, opportunity fleeting, experience treacherous, judgment difficult.", "Hippocrates"),
            ("First, do no harm.", "Hippocrates (attributed)"),
            ("Let food be thy medicine and medicine be thy food.", "Hippocrates (attributed)"),
            ("The good physician treats the disease; the great physician treats the patient who has the disease.", "William Osler"),
            ("Medicine is a science of uncertainty and an art of probability.", "William Osler"),
            ("Listen to the patient, he is telling you the diagnosis.", "William Osler"),
            ("The practice of medicine is an art, based on science.", "William Osler"),
            ("To study the phenomena of disease without books is to sail an uncharted sea; to study books without patients is not to go to sea at all.", "William Osler"),
            ("Cure sometimes, treat often, comfort always.", "Ambroise Pare"),
            ("The art of medicine consists of amusing the patient while nature cures the disease.", "Voltaire"),
            ("The best physician is also a philosopher.", "Galen (attributed)"),
            ("In nothing do men more nearly approach the gods than in giving health to men.", "Cicero"),
            ("The dose makes the poison.", "Paracelsus"),
            ("In the fields of observation, chance favors the prepared mind.", "Louis Pasteur"),
            ("Medicine is a social science, and politics is nothing else but medicine on a large scale.", "Rudolf Virchow"),
            ("He who takes medicine and neglects diet wastes the skill of the physician.", "Hippocrates (attributed)"),
            ("To cure a disease after it has taken hold is like digging a well after one is thirsty.", "Chinese proverb"),
            ("A good laugh and a long sleep are the best cures in the doctor's book.", "Irish proverb"),
        ]
        text, author = random.choice(quotes)
        accent = '#89b4fa' if dark else '#007bff'
        return f'"<i>{text}</i>"<br><span style=\'color:{accent};\'>— {author}</span>'

    def refresh_dashboard(self):
        """Refresh recent activity from screening records"""
        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT patient_id, name, result, confidence
                FROM patient_records
                ORDER BY id DESC
                """
            )
            rows = cur.fetchall()
            conn.close()

            total = len(rows)

            recent_lines = []
            high_attention = 0
            pending_count = 0
            confidence_values = []

            for _, _, result, confidence_text in rows:
                result = str(result or "")
                if self._is_high_attention_result(result):
                    high_attention += 1
                if not result or "pending" in result.lower():
                    pending_count += 1

                conf_value = self._extract_confidence_value(str(confidence_text or ""))
                if conf_value is not None:
                    confidence_values.append(conf_value)

            for patient_id, name, result, _ in rows[:5]:
                pid = str(patient_id or "")
                name = str(name or "")
                result = str(result or "")
                recent_lines.append(f"• {pid} — {name} — {result or 'Pending'}")

            avg_conf = sum(confidence_values) / len(confidence_values) if confidence_values else None

            if hasattr(self, "total_screenings_value"):
                self.total_screenings_value.setText(str(total))
            if hasattr(self, "high_attention_value"):
                self.high_attention_value.setText(str(high_attention))
            if hasattr(self, "high_attention_hint"):
                if high_attention > 0:
                    self.high_attention_hint.setText("Cases flagged for follow-up")
                else:
                    self.high_attention_hint.setText("No high-attention cases detected")
            if hasattr(self, "avg_confidence_value"):
                self.avg_confidence_value.setText(f"{avg_conf:.1f}%" if avg_conf is not None else "—")
            if hasattr(self, "queue_status_label"):
                self.queue_status_label.setText(f"Queue: {pending_count} pending review")
            if hasattr(self, "dashboard_date_label"):
                today = datetime.now().strftime('%A, %B %d, %Y')
                self.dashboard_date_label.setText(f"Today: {today}")
            if hasattr(self, "insight_label"):
                if total == 0:
                    self.insight_label.setText("No screenings yet. Start with a new screening to populate trends.")
                elif high_attention > 0:
                    self.insight_label.setText(f"{high_attention} case(s) require closer follow-up. Prioritize report review.")
                elif pending_count > 0:
                    self.insight_label.setText("Screenings are recorded. Complete pending reviews and finalize outcomes.")
                else:
                    self.insight_label.setText("All recorded screenings appear up-to-date. Continue routine monitoring.")

            if recent_lines:
                if self._dark_mode:
                    self.recent_activity_label.setStyleSheet("color: #a6adc8; font-size: 14px;")
                else:
                    self.recent_activity_label.setStyleSheet("color: #495057; font-size: 14px;")
                self.recent_activity_label.setText("\n".join(recent_lines))
            else:
                if self._dark_mode:
                    self.recent_activity_label.setStyleSheet("color: #6c7086; font-size: 14px; font-style: italic;")
                else:
                    self.recent_activity_label.setStyleSheet("color: #6c757d; font-size: 14px; font-style: italic;")
                self.recent_activity_label.setText("No recent clinical activity. Ready for patient screenings.")
        except Exception:
            pass

    @staticmethod
    def _is_high_attention_result(result_text):
        text = str(result_text or "").lower()
        keywords = ("moderate", "severe", "proliferative", "refer", "urgent", "dr detected")
        return any(word in text for word in keywords)

    @staticmethod
    def _extract_confidence_value(conf_text):
        text = str(conf_text or "")
        numeric = "".join(ch for ch in text if ch.isdigit() or ch == ".")
        if not numeric:
            return None
        try:
            return float(numeric)
        except ValueError:
            return None

    @staticmethod
    def get_nav_button_style(icon_only=False):
        """Get navigation button stylesheet. If icon_only, use smaller font and center icon."""
        if icon_only:
            return """
                QPushButton {
                    color: #495057;
                    text-align: center;
                    padding: 4px 0px;
                    border: 1px solid transparent;
                    border-radius: 8px;
                    font-size: 22px;
                    font-weight: 500;
                    background: transparent;
                    text-decoration: none;
                }
                QPushButton:hover {
                    background: #e9ecef;
                    color: #007bff;
                }
                QPushButton:focus {
                    outline: none;
                    border: 1px solid transparent;
                }
            """
        else:
            return """
                QPushButton {
                    color: #495057;
                    text-align: left;
                    padding: 15px 20px;
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: 500;
                    background: transparent;
                }
                QPushButton:hover {
                    background: #e9ecef;
                    color: #007bff;
                }
                QPushButton:focus {
                    outline: none;
                    border: none;
                }
            """
