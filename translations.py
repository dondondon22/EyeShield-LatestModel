"""Centralised translation strings for EyeShield EMR. English only."""

TRANSLATIONS = {
    "English": {
        # Settings page
        "settings_title": "Settings",
        "settings_subtitle": "Local offline preferences for this installation",
        "settings_preferences": "Preferences",
        "settings_theme": "Theme:",
        "settings_language": "Language:",
        "settings_auto_logout": "Enable auto-logout after inactivity",
        "settings_confirm": "Ask confirmation before destructive actions",
        "settings_compact": "Use compact table rows",
        "settings_about": "About",
        "settings_terms": "Terms of Use",
        "settings_privacy": "Privacy Policy",
        "settings_reset": "Reset Defaults",
        "settings_save": "Save Settings",
        # Nav labels
        "nav_dashboard": "Dashboard",
        "nav_screening": "Screening",
        "nav_camera": "Camera",
        "nav_reports": "Reports",
        "nav_users": "Users",
        "nav_settings": "Settings",
        "nav_help": "Help",
        # Dashboard
        "dash_welcome": "Welcome back",
        "dash_kpi_total": "TOTAL SCREENINGS",
        "dash_kpi_flagged": "FLAGGED FOR REVIEW",
        "dash_kpi_pending": "PENDING REVIEW",
        "dash_kpi_conf": "MODEL CONFIDENCE",
        "dash_recent": "RECENT SCREENINGS",
        "dash_actions_title": "QUICK ACTIONS",
        "dash_btn_new": "  New Screening",
        "dash_btn_reports": "  View Reports",
        "dash_insight_title": "CLINICAL INSIGHT",
        "dash_insight_default": "Start a screening to generate insight.",
        "dash_empty": "No screening records yet. Start by running a new screening.",
        "dash_kpi_total_sub": "All saved DR screenings",
        "dash_flagged_cases": "Cases flagged for review",
        "dash_no_flagged": "No cases flagged",
        "dash_awaiting": "Awaiting review",
        "dash_all_reviewed": "All reviews complete",
        "dash_conf_across": "Across {n} record",
        "dash_no_conf": "No confidence data yet",
        "dash_no_screenings": "No screenings yet. Run a new screening to see trends here.",
        "dash_insight_all_clear": "All screenings reviewed — no action needed. Continue routine monitoring.",
        # Camera
        "cam_title": "Temporary Webcam",
        "cam_subtitle": "Use this while fundus camera integration is in progress.",
        "cam_stopped": "Camera is stopped.",
        "cam_start": "Start Camera",
        "cam_stop": "Stop Camera",
        # Screening form
        "scr_patient_info": "Patient Information",
        "scr_clinical_history": "Clinical History",
        "scr_image_upload": "Fundus Image Upload",
        "scr_upload_btn": "Upload Image",
        "scr_clear_btn": "Clear",
        "scr_analyze_btn": "Analyze Image",
        "scr_label_pid": "Patient ID:",
        "scr_label_name": "Name:",
        "scr_label_dob": "Date of Birth:",
        "scr_label_age": "Age:",
        "scr_label_sex": "Sex:",
        "scr_label_contact": "Contact:",
        "scr_label_eye": "Eye Screened:",
        "scr_label_diabetes": "Diabetes Type:",
        "scr_label_duration": "Duration:",
        "scr_label_hba1c": "HbA1c:",
        "scr_label_notes": "Notes:",
        # Reports
        "rep_title": "DR Screening Reports",
        "rep_subtitle": "Complete diabetic retinopathy screening outcomes from locally saved records",
        "rep_refresh": "Refresh",
        "rep_export": "Export Results",
        "rep_archived": "Archived Records",
        "rep_archive_sel": "Archive Selected",
        "rep_quick_filters": "Quick Filters",
        "rep_summary": "Summary",
        "rep_all_results": "All Screening Results",
        "rep_stat_total": "Total Screenings",
        "rep_stat_unique": "Unique Patients",
        "rep_stat_no_dr": "No DR",
        "rep_stat_review": "Needs Review",
        "rep_stat_hba1c": "Avg HbA1c",
        # Users
        "usr_title": "User Management",
        "usr_table": "Users",
        "usr_log": "Activity Log",
        # Help & Support
        "hlp_title": "Help & Support",
        "hlp_subtitle": "Quick guidance for daily workflows, troubleshooting, and support contacts.",
        "hlp_quick_start": "Quick Start",
        "hlp_quick_start_body": """
            <ul>
                <li>Log in with your assigned role.</li>
                <li>Use <b>Screening</b> to capture patient details and upload a fundus image.</li>
                <li>Review the result, then save the screening outcome.</li>
                <li>Generate summaries in <b>Reports</b>.</li>
            </ul>
            """,
        "hlp_howto": "How-to Guides",
        "hlp_howto_body": """
            <ul>
                <li><b>New screening:</b> Enter patient info, upload image, analyze, then save.</li>
                <li><b>Review results:</b> Open <b>Reports</b> to view all DR screening outcomes.</li>
                <li><b>Export report:</b> Use <b>Reports</b> to export all screening results.</li>
            </ul>
            """,
        "hlp_faq": "FAQ",
        "hlp_faq_body": """
            <ul>
                <li><b>Cannot log in:</b> Verify username/role and reset password with Admin.</li>
                <li><b>Missing patient:</b> Check spelling, ID format, and date filters.</li>
                <li><b>Image not loading:</b> Use JPG/PNG and confirm file permissions.</li>
            </ul>
            """,
        "hlp_troubleshoot": "Troubleshooting",
        "hlp_troubleshoot_body": """
            <ul>
                <li>Restart the app if pages are unresponsive.</li>
                <li>Confirm network or storage access for saving reports.</li>
                <li>Check printer settings or switch to PDF export.</li>
            </ul>
            """,
        "hlp_privacy": "Privacy & Compliance",
        "hlp_privacy_body": """
            <ul>
                <li>Only access patient data needed for care.</li>
                <li>Do not share screenshots or exports outside approved channels.</li>
                <li>Log out when leaving the workstation.</li>
            </ul>
            """,
        "hlp_contact": "Contact Support",
        "hlp_contact_body": """
            <p><b>Email:</b> support@eyeshield.local<br>
            <b>Phone:</b> +1-000-000-0000<br>
            <b>Hours:</b> Mon-Fri, 8:00 AM - 6:00 PM</p>
            """,
    },
}


def get_pack(language: str) -> dict:
    """Return the translation pack for the given language, defaulting to English."""
    return TRANSLATIONS.get(language, TRANSLATIONS["English"])
