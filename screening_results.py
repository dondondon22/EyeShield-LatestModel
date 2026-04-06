"""
Results window module for EyeShield EMR application.
Contains the ResultsWindow class and clinical explanation generation.
"""
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import re
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QScrollArea, QFrame, QProgressBar, QMessageBox, QFileDialog, QStyle, QProgressDialog, QApplication, QDialog, QComboBox, QLineEdit, QTextEdit, QGridLayout
from PySide6.QtGui import QPixmap, QFont, QPainter, QColor, QIcon, QPalette, QImage, QPdfWriter, QPageSize, QPageLayout, QTextDocument
from PySide6.QtCore import Qt, QSize, QEvent, QTimer, QByteArray, QBuffer, QIODevice, QMarginsF
from screening_styles import DR_COLORS, DR_RECOMMENDATIONS, PROGRESSBAR_STYLE
from screening_widgets import ClickableImageLabel
from safety_runtime import can_write_directory, get_free_space_mb, write_activity
from auth import UserManager
ICDR_OPTIONS = ['No DR', 'Mild DR', 'Moderate DR', 'Severe DR', 'Proliferative DR']

def _generate_explanation(result_class: str, confidence_text: str, patient_data: dict | None=None) -> str:
    """
    Build a personalised clinical explanation from the DR grade,
    model confidence, and the patient's clinical profile.
    Returns HTML-ready text (paragraphs separated by <br><br>).
    """
    pd = patient_data or {}
    age = int(pd.get('age', 0))
    hba1c = float(pd.get('hba1c', 0.0))
    duration = int(pd.get('duration', 0))
    prev_tx = bool(pd.get('prev_treatment', False))
    d_type = str(pd.get('diabetes_type', '')).strip()
    eye = str(pd.get('eye', '')).strip()
    eye_phrase = f'the {eye.lower()}' if eye and eye.lower() not in ('', 'select') else 'the screened eye'
    opening_map = {'No DR': f'No signs of diabetic retinopathy were detected in {eye_phrase}', 'Mild DR': f'Early microaneurysms consistent with mild non-proliferative diabetic retinopathy (NPDR) were identified in {eye_phrase}', 'Moderate DR': f'Microaneurysms, hemorrhages, and/or hard exudates consistent with moderate non-proliferative diabetic retinopathy (NPDR) were detected in {eye_phrase}', 'Severe DR': f'Extensive hemorrhages, venous beading, or intraretinal microvascular abnormalities consistent with severe NPDR were detected in {eye_phrase}', 'Proliferative DR': f'Neovascularisation indicative of proliferative diabetic retinopathy (PDR) — a sight-threatening condition — was detected in {eye_phrase}'}
    paragraphs = [opening_map.get(result_class, f'{result_class} was detected in {eye_phrase}') + f' ({confidence_text.lower()}).']
    ctx = []
    if age > 0:
        ctx.append(f'{age}‑year‑old')
    if d_type and d_type.lower() not in ('select', ''):
        ctx.append(f'{d_type} diabetes')
    if duration > 0:
        ctx.append(f'{duration}‑year diabetes duration')
    if ctx:
        paragraphs.append('<b>Patient profile:</b> ' + ', '.join(ctx) + '.')
    risk = []
    if hba1c >= 9.0:
        risk.append(f'HbA1c of <b>{hba1c:.1f}%</b> indicates poor glycaemic control, which substantially increases the risk of retinopathy progression and macular oedema.')
    elif hba1c >= 7.5:
        risk.append(f'HbA1c of <b>{hba1c:.1f}%</b> is above the recommended target (≤7.0–7.5%). Tighter glycaemic management is advised to slow disease progression.')
    elif hba1c > 0.0:
        risk.append(f'HbA1c of <b>{hba1c:.1f}%</b> is within an acceptable range. Continue current glycaemic management strategy.')
    if duration >= 15 and result_class != 'No DR':
        risk.append(f'A diabetes duration of <b>{duration} years</b> is a recognised risk factor for bilateral retinal involvement; bilateral screening is recommended if not already performed.')
    elif result_class in ('Severe DR', 'Proliferative DR') and duration >= 10:
        risk.append(f'Diabetes duration of <b>{duration} years</b> is consistent with the advanced retinal findings observed.')
    if prev_tx and result_class != 'No DR':
        risk.append('A history of prior DR treatment requires close monitoring for recurrence, progression, or treatment-related complications.')
    if risk:
        paragraphs.append('<br>'.join(risk))
    rec_map = {'No DR': 'Maintain optimal glycaemic and blood pressure control. Annual retinal screening is recommended.', 'Mild DR': 'Intensify glycaemic and blood pressure management. Schedule a repeat retinal examination in 6–12 months.', 'Moderate DR': 'Ophthalmology referral within 3 months is advised. Reassess systemic metabolic control and consider treatment intensification.', 'Severe DR': 'Urgent ophthalmology referral is required. The 1-year risk of progression to proliferative disease is high without intervention.', 'Proliferative DR': 'Immediate ophthalmology referral is required. Treatment may include laser photocoagulation, intravitreal anti-VEGF therapy, or vitreoretinal surgery.'}
    paragraphs.append('<b>Recommendation:</b> ' + rec_map.get(result_class, 'Consult a qualified ophthalmologist for further evaluation.'))
    return '<br><br>'.join(paragraphs)

class ResultsWindow(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_page = parent
        self.setMinimumSize(900, 600)
        self._icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
        self._current_image_path = ''
        self._current_heatmap_path = ''
        self._current_result_class = 'Pending'
        self._current_confidence = ''
        self._current_eye_label = ''
        self._current_patient_name = ''
        self._first_eye_context = {}
        self._doctor_classification = 'Pending'
        self._decision_mode = 'pending'
        self._override_justification = ''
        self._doctor_findings = ''
        self._save_state_timer = QTimer(self)
        self._save_state_timer.setSingleShot(True)
        self._save_state_timer.timeout.connect(self._reset_save_button_default)
        self._uncertainty_pct = 0.0
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _outer.addWidget(_scroll)
        _container = QWidget()
        _scroll.setWidget(_container)
        layout = QVBoxLayout(_container)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        heading_col = QVBoxLayout()
        heading_col.setSpacing(8)
        self.breadcrumb_label = QLabel('SCREENING RESULTS')
        self.breadcrumb_label.setObjectName('crumbLabel')
        heading_col.addWidget(self.breadcrumb_label)
        self.title_label = QLabel('Results')
        self.title_label.setFont(QFont('Segoe UI', 26, QFont.Weight.Bold))
        self.title_label.setObjectName('pageHeader')
        heading_col.addWidget(self.title_label)
        self.subtitle_label = QLabel('Review model output, confidence, and clinical support notes.')
        self.subtitle_label.setObjectName('pageSubtitle')
        self.subtitle_label.setWordWrap(True)
        heading_col.addWidget(self.subtitle_label)
        pills_row = QHBoxLayout()
        pills_row.setSpacing(8)
        self.eye_badge_label = QLabel('• Right Eye')
        self.eye_badge_label.setObjectName('infoPill')
        self.eye_badge_label.setMinimumHeight(30)
        pills_row.addWidget(self.eye_badge_label)
        self.save_status_label = QLabel('Saved ✓')
        self.save_status_label.setObjectName('savedPill')
        self.save_status_label.setMinimumHeight(30)
        self.save_status_label.hide()
        pills_row.addWidget(self.save_status_label)
        pills_row.addStretch(1)
        heading_col.addLayout(pills_row)
        top_row.addLayout(heading_col, 1)
        layout.addLayout(top_row)
        self.btn_back = QPushButton('Back')
        self.btn_back.setObjectName('ghostAction')
        self.btn_back.setMinimumHeight(40)
        self.btn_back.setIconSize(QSize(18, 18))
        self.btn_back.clicked.connect(self.go_back)
        self.btn_save = QPushButton('Save Result')
        self.btn_save.setObjectName('ghostAction')
        self.btn_save.setMinimumHeight(40)
        self.btn_save.setIconSize(QSize(18, 18))
        self.btn_save.clicked.connect(self.save_patient)
        self.btn_report = QPushButton('Generate Report')
        self.btn_report.setObjectName('ghostAction')
        self.btn_report.setMinimumHeight(40)
        self.btn_report.setIconSize(QSize(18, 18))
        self.btn_report.setEnabled(False)
        self.btn_report.clicked.connect(self.generate_report)
        self.btn_screen_another = QPushButton('Screen Other Eye')
        self.btn_screen_another.setObjectName('ghostAction')
        self.btn_screen_another.setMinimumHeight(40)
        self.btn_screen_another.setIconSize(QSize(18, 18))
        self.btn_screen_another.clicked.connect(self._on_screen_another)
        self.btn_new = QPushButton('New Patient')
        self.btn_new.setObjectName('ghostAction')
        self.btn_new.setMinimumHeight(40)
        self.btn_new.setIconSize(QSize(18, 18))
        self.btn_new.clicked.connect(self.new_patient)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setFixedHeight(4)
        self._loading_bar.setTextVisible(False)
        self._loading_bar.setStyleSheet('\n            QProgressBar {\n                background: #e5e7eb;\n                border: none;\n                border-radius: 2px;\n            }\n            QProgressBar::chunk {\n                background: #2563eb;\n                border-radius: 2px;\n            }\n        ')
        self._loading_bar.hide()
        layout.addWidget(self._loading_bar)
        self.save_note_label = QLabel('')
        self.save_note_label.setObjectName('metaText')
        self.save_note_label.hide()
        layout.addWidget(self.save_note_label)
        source_card = QGroupBox('')
        source_card.setObjectName('resultGroupCard')
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(16, 16, 16, 16)
        source_layout.setSpacing(10)
        source_head = QHBoxLayout()
        source_head.setSpacing(6)
        source_title = QLabel('Source Image - Fundus')
        source_title.setObjectName('cardHeaderLabel')
        source_head.addWidget(source_title)
        source_head.addStretch(1)
        source_expand = QLabel('⤢')
        source_expand.setObjectName('expandGlyph')
        source_head.addWidget(source_expand)
        source_layout.addLayout(source_head)
        self.source_label = ClickableImageLabel('', 'Source Image - Fundus')
        self.source_label.setObjectName('sourceImageSurface')
        self.source_label.setMinimumHeight(330)
        self.source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_label.setWordWrap(True)
        source_layout.addWidget(self.source_label)
        heatmap_card = QGroupBox('')
        heatmap_card.setObjectName('resultGroupCard')
        heatmap_layout = QVBoxLayout(heatmap_card)
        heatmap_layout.setContentsMargins(16, 16, 16, 16)
        heatmap_layout.setSpacing(10)
        heatmap_head = QHBoxLayout()
        heatmap_head.setSpacing(6)
        heatmap_title = QLabel('Grad-CAM++ Heatmap')
        heatmap_title.setObjectName('cardHeaderLabel')
        heatmap_head.addWidget(heatmap_title)
        heatmap_head.addStretch(1)
        heatmap_expand = QLabel('⤢')
        heatmap_expand.setObjectName('expandGlyph')
        heatmap_head.addWidget(heatmap_expand)
        heatmap_layout.addLayout(heatmap_head)
        self.heatmap_label = ClickableImageLabel('', 'Grad-CAM++ Heatmap')
        self.heatmap_label.setObjectName('heatmapImageSurface')
        self.heatmap_label.setMinimumHeight(330)
        self.heatmap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heatmap_label.setWordWrap(True)
        heatmap_layout.addWidget(self.heatmap_label)
        actions_card = QGroupBox('')
        actions_card.setObjectName('resultGroupCard')
        actions_layout = QVBoxLayout(actions_card)
        actions_layout.setContentsMargins(16, 16, 16, 16)
        actions_layout.setSpacing(10)
        actions_head = QHBoxLayout()
        actions_head.setSpacing(6)
        actions_title = QLabel('Actions')
        actions_title.setObjectName('cardHeaderLabel')
        actions_head.addWidget(actions_title)
        actions_head.addStretch(1)
        actions_layout.addLayout(actions_head)
        self.step1_label = QLabel('1. Review AI result')
        self.step1_label.setObjectName('resultStatTitle')
        actions_layout.addWidget(self.step1_label)
        ai_row = QHBoxLayout()
        ai_row.setSpacing(8)
        ai_tag = QLabel('AI')
        ai_tag.setObjectName('decisionRoleTag')
        self.ai_classification_value = QLabel('Pending')
        self.ai_classification_value.setObjectName('resultStatValue')
        ai_row.addWidget(ai_tag)
        ai_row.addWidget(self.ai_classification_value, 1)
        actions_layout.addLayout(ai_row)
        self.step2_label = QLabel('2. Confirm your classification')
        self.step2_label.setObjectName('resultStatTitle')
        actions_layout.addWidget(self.step2_label)
        doctor_row = QHBoxLayout()
        doctor_row.setSpacing(8)
        doctor_tag = QLabel('Doctor')
        doctor_tag.setObjectName('doctorRoleTag')
        doctor_tag.setFixedHeight(38)
        doctor_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.doctor_classification_input = QComboBox()
        self.doctor_classification_input.addItems(['No DR', 'Mild DR', 'Moderate DR', 'Severe DR', 'Proliferative DR'])
        self.doctor_classification_input.setPlaceholderText('Select Classification...')
        self.doctor_classification_input.setCurrentIndex(-1)
        self.doctor_classification_input.setFixedHeight(38)
        self.doctor_classification_input.setStyleSheet('\n            QComboBox {\n                font-size: 14px;\n                font-weight: 600;\n                color: #1e3a8a;\n                border: 2px solid #93c5fd;\n                background: #eff6ff;\n                border-radius: 6px;\n                padding-left: 10px;\n            }\n            QComboBox:focus {\n                border-color: #2563eb;\n                background: white;\n            }\n        ')
        self.doctor_classification_input.currentTextChanged.connect(self._on_doctor_classification_changed)
        doctor_row.addWidget(doctor_tag, 0, Qt.AlignmentFlag.AlignVCenter)
        doctor_row.addWidget(self.doctor_classification_input, 1, Qt.AlignmentFlag.AlignVCenter)
        actions_layout.addLayout(doctor_row)
        self.classification_match_label = QLabel('Your current classification matches the AI')
        self.classification_match_label.setObjectName('metaText')
        self.classification_match_label.setWordWrap(True)
        actions_layout.addWidget(self.classification_match_label)
        self.documentation_panel = QFrame()
        self.documentation_panel.setObjectName('decisionStepPanel')
        self.step3_label = QLabel('3. Document your override')
        self.step3_label.setObjectName('resultStatTitle')
        documentation_layout = QVBoxLayout(self.documentation_panel)
        documentation_layout.setContentsMargins(12, 10, 12, 12)
        documentation_layout.setSpacing(8)
        documentation_layout.addWidget(self.step3_label)
        self.step4_hint = QLabel('Override requires concise clinical justification.')
        self.step4_hint.setObjectName('metaText')
        self.step4_hint.setWordWrap(True)
        documentation_layout.addWidget(self.step4_hint)
        self.override_reason_label = QLabel('Override justification of results')
        self.override_reason_label.setObjectName('metaText')
        self.override_reason_input = QTextEdit()
        self.override_reason_input.setObjectName('overrideCommentBox')
        self.override_reason_input.setPlaceholderText('Provide concise clinical justification...')
        self.override_reason_input.setMinimumHeight(60)
        self.override_reason_input.textChanged.connect(self._on_override_reason_changed)
        documentation_layout.addWidget(self.override_reason_label)
        documentation_layout.addWidget(self.override_reason_input)
        actions_layout.addWidget(self.documentation_panel)
        self.decision_hint = QLabel('AI is decision support. Doctor classification is the final authority.')
        self.decision_hint.setObjectName('metaText')
        self.decision_hint.setWordWrap(True)
        actions_layout.addWidget(self.decision_hint)
        self.optional_comment_panel = QFrame()
        self.optional_comment_panel.setObjectName('decisionStepPanel')
        optional_layout = QVBoxLayout(self.optional_comment_panel)
        optional_layout.setContentsMargins(12, 10, 12, 12)
        optional_layout.setSpacing(8)
        self.findings_label = QLabel('Optional doctor findings and comments')
        self.findings_label.setObjectName('metaText')
        self.findings_input = QTextEdit()
        self.findings_input.setObjectName('findingsCommentBox')
        self.findings_input.setPlaceholderText('Optional: add retinal findings or clinical comments...')
        self.findings_input.setMinimumHeight(60)
        self.findings_input.textChanged.connect(self._on_findings_changed)
        optional_layout.addWidget(self.findings_label)
        optional_layout.addWidget(self.findings_input)
        actions_layout.addWidget(self.optional_comment_panel)
        actions_grid = QGridLayout()
        actions_grid.setHorizontalSpacing(0)
        actions_grid.setVerticalSpacing(10)
        self.accept_ai_btn = QPushButton('Accept AI result')
        self.accept_ai_btn.setObjectName('decisionChoiceButton')
        self.accept_ai_btn.clicked.connect(self._accept_ai_classification)
        self.override_ai_btn = QPushButton('Override AI result')
        self.override_ai_btn.setObjectName('decisionChoiceButton')
        self.override_ai_btn.clicked.connect(self._prepare_override)
        actions_grid.addWidget(self.accept_ai_btn, 0, 0)
        actions_grid.addWidget(self.override_ai_btn, 1, 0)
        actions_grid.setColumnStretch(0, 1)
        actions_layout.addLayout(actions_grid)
        actions_layout.addStretch(1)
        actions_card.setMinimumWidth(300)
        extra_actions_card = QFrame()
        extra_actions_card.setObjectName('resultStatCard')
        extra_actions_layout = QVBoxLayout(extra_actions_card)
        extra_actions_layout.setContentsMargins(18, 18, 18, 18)
        extra_actions_layout.setSpacing(10)
        extra_actions_title = QLabel('WORKFLOW ACTIONS')
        extra_actions_title.setObjectName('resultStatTitle')
        extra_actions_layout.addWidget(extra_actions_title)
        extra_actions_grid = QGridLayout()
        extra_actions_grid.setSpacing(8)
        extra_actions_grid.addWidget(self.btn_screen_another, 0, 0)
        extra_actions_grid.addWidget(self.btn_save, 1, 0)
        extra_actions_grid.addWidget(self.btn_report, 2, 0)
        extra_actions_grid.addWidget(self.btn_new, 3, 0)
        extra_actions_grid.addWidget(self.btn_back, 4, 0)
        extra_actions_grid.setColumnStretch(0, 1)
        extra_actions_layout.addLayout(extra_actions_grid)
        extra_actions_layout.addStretch(1)
        class_card = QFrame()
        class_card.setObjectName('resultStatCard')
        class_layout = QVBoxLayout(class_card)
        class_layout.setContentsMargins(18, 18, 18, 18)
        class_layout.setSpacing(8)
        class_title = QLabel('AI CLASSIFICATION & CONFIDENCE')
        class_title.setObjectName('resultStatTitle')
        self.classification_value = QLabel('Pending')
        self.classification_value.setObjectName('classificationValue')
        self.classification_subtitle = QLabel('Awaiting model result')
        self.classification_subtitle.setObjectName('metaText')
        self.classification_subtitle.setWordWrap(True)
        class_layout.addWidget(class_title)
        class_layout.addWidget(self.classification_value)
        class_layout.addWidget(self.classification_subtitle)
        confidence_divider = QFrame()
        confidence_divider.setFrameShape(QFrame.Shape.HLine)
        confidence_divider.setStyleSheet('color:#d9e5f2; margin-top: 8px; margin-bottom: 8px;')
        class_layout.addWidget(confidence_divider)
        self.confidence_value = QLabel('Confidence: 0.0%')
        self.confidence_value.setObjectName('monoValue')
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 1000)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(False)
        self.confidence_bar.setObjectName('confidenceBar')
        self.confidence_bar.setFixedHeight(8)
        self.uncertainty_value = QLabel('Uncertainty: 0.0%')
        self.uncertainty_value.setObjectName('uncertaintyValue')
        self.uncertainty_bar = QProgressBar()
        self.uncertainty_bar.setRange(0, 1000)
        self.uncertainty_bar.setValue(0)
        self.uncertainty_bar.setTextVisible(False)
        self.uncertainty_bar.setObjectName('uncertaintyBar')
        self.uncertainty_bar.setFixedHeight(8)
        self.confidence_bar.hide()
        self.uncertainty_bar.hide()
        class_layout.addWidget(self.confidence_value)
        class_layout.addWidget(self.uncertainty_value)
        class_layout.addStretch()
        self.bilateral_frame = QFrame()
        self.bilateral_frame.setObjectName('resultStatCard')
        bilateral_layout = QVBoxLayout(self.bilateral_frame)
        bilateral_layout.setContentsMargins(18, 16, 18, 16)
        bilateral_layout.setSpacing(12)
        bilateral_title = QLabel('↔  Bilateral Screening Comparison')
        bilateral_title.setObjectName('resultStatTitle')
        bilateral_layout.addWidget(bilateral_title)
        brow = QHBoxLayout()
        brow.setSpacing(20)
        first_col = QVBoxLayout()
        first_col.setSpacing(4)
        self.bilateral_first_eye_lbl = QLabel('—')
        self.bilateral_first_eye_lbl.setObjectName('resultStatTitle')
        self.bilateral_first_result_lbl = QLabel('—')
        self.bilateral_first_result_lbl.setObjectName('resultStatValue')
        self.bilateral_first_saved_lbl = QLabel('✓ Saved')
        self.bilateral_first_saved_lbl.setStyleSheet('font-weight:700;font-size:13px;')
        self.bilateral_first_saved_lbl.setObjectName('successLabel')
        first_col.addWidget(self.bilateral_first_eye_lbl)
        first_col.addWidget(self.bilateral_first_result_lbl)
        first_col.addWidget(self.bilateral_first_saved_lbl)
        brow_div = QFrame()
        brow_div.setFrameShape(QFrame.Shape.VLine)
        brow_div.setFrameShadow(QFrame.Shadow.Plain)
        brow_div.setStyleSheet('color:#d9e5f2;')
        second_col = QVBoxLayout()
        second_col.setSpacing(4)
        self.bilateral_second_eye_lbl = QLabel('—')
        self.bilateral_second_eye_lbl.setObjectName('resultStatTitle')
        self.bilateral_second_result_lbl = QLabel('—')
        self.bilateral_second_result_lbl.setObjectName('resultStatValue')
        self.bilateral_second_saved_lbl = QLabel('Unsaved')
        self.bilateral_second_saved_lbl.setStyleSheet('font-weight:700;font-size:13px;')
        self.bilateral_second_saved_lbl.setObjectName('errorLabel')
        second_col.addWidget(self.bilateral_second_eye_lbl)
        second_col.addWidget(self.bilateral_second_result_lbl)
        second_col.addWidget(self.bilateral_second_saved_lbl)
        brow.addLayout(first_col)
        brow.addWidget(brow_div)
        brow.addLayout(second_col)
        bilateral_layout.addLayout(brow)
        self.bilateral_frame.hide()
        reco_card = QFrame()
        reco_card.setObjectName('resultStatCard')
        reco_layout = QVBoxLayout(reco_card)
        reco_layout.setContentsMargins(18, 18, 18, 18)
        reco_layout.setSpacing(8)
        reco_title = QLabel('AI RECOMMENDATION & SUMMARY')
        reco_title.setObjectName('resultStatTitle')
        self.recommendation_value = QLabel('Consult eye care specialist')
        self.recommendation_value.setObjectName('resultStatValue')
        self.recommendation_value.setWordWrap(True)
        self.recommendation_badge = QLabel('Routine follow-up')
        self.recommendation_badge.setObjectName('okBadge')
        reco_layout.addWidget(reco_title)
        reco_layout.addWidget(self.recommendation_value)
        reco_layout.addWidget(self.recommendation_badge, 0, Qt.AlignmentFlag.AlignLeft)
        reco_divider = QFrame()
        reco_divider.setFrameShape(QFrame.Shape.HLine)
        reco_divider.setStyleSheet('color:#d9e5f2; margin-top: 8px; margin-bottom: 8px;')
        reco_layout.addWidget(reco_divider)
        self.summary_line_1 = QLabel('No signs of diabetic retinopathy detected')
        self.summary_line_1.setObjectName('summaryRowSuccess')
        self.summary_line_1.setWordWrap(True)
        reco_layout.addWidget(self.summary_line_1)
        self.summary_line_2 = QLabel('Patient profile: awaiting demographic and glycaemic context')
        self.summary_line_2.setObjectName('summaryRowInfo')
        self.summary_line_2.setWordWrap(True)
        reco_layout.addWidget(self.summary_line_2)
        self.summary_line_3 = QLabel('Model uncertainty note: calibrate with specialist review')
        self.summary_line_3.setObjectName('summaryRowWarn')
        self.summary_line_3.setWordWrap(True)
        reco_layout.addWidget(self.summary_line_3)
        self.explanation = QLabel('')
        self.explanation.setWordWrap(True)
        self.explanation.setObjectName('summaryBody')
        reco_layout.addWidget(self.explanation)
        reco_layout.addStretch()
        main_h_layout = QHBoxLayout()
        main_h_layout.setSpacing(16)
        left_v_layout = QVBoxLayout()
        left_v_layout.setSpacing(16)
        images_h_layout = QHBoxLayout()
        images_h_layout.setSpacing(16)
        images_h_layout.addWidget(source_card, 1, Qt.AlignmentFlag.AlignTop)
        images_h_layout.addWidget(heatmap_card, 1, Qt.AlignmentFlag.AlignTop)
        self.ai_disclaimer_label = QLabel('This AI-generated output is provided solely as clinical decision support. Final diagnosis, treatment planning, and all medical decisions remain the exclusive responsibility of the attending licensed physician.')
        self.ai_disclaimer_label.setObjectName('aiDisclaimerLabel')
        self.ai_disclaimer_label.setWordWrap(True)
        left_v_layout.addLayout(images_h_layout, 1)
        left_v_layout.addWidget(self.ai_disclaimer_label, 0)
        right_v_layout = QVBoxLayout()
        right_v_layout.setSpacing(16)
        right_v_layout.addWidget(class_card, 0, Qt.AlignmentFlag.AlignTop)
        right_v_layout.addWidget(extra_actions_card, 0, Qt.AlignmentFlag.AlignTop)
        right_v_layout.addStretch(1)
        main_h_layout.addLayout(left_v_layout, 2)
        main_h_layout.addLayout(right_v_layout, 1)
        layout.addLayout(main_h_layout)
        actions_reco_row = QHBoxLayout()
        actions_reco_row.setSpacing(16)
        actions_reco_row.addWidget(actions_card, 1, Qt.AlignmentFlag.AlignTop)
        actions_reco_row.addWidget(reco_card, 1, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(actions_reco_row)
        layout.addWidget(self.bilateral_frame)
        self.bilateral_frame = QFrame()
        self.bilateral_frame.setObjectName('resultStatCard')
        bilateral_layout = QVBoxLayout(self.bilateral_frame)
        bilateral_layout.setContentsMargins(18, 16, 18, 16)
        bilateral_layout.setSpacing(12)
        bilateral_title = QLabel('↔  Bilateral Screening Comparison')
        bilateral_title.setObjectName('resultStatTitle')
        bilateral_layout.addWidget(bilateral_title)
        brow = QHBoxLayout()
        brow.setSpacing(20)
        first_col = QVBoxLayout()
        first_col.setSpacing(4)
        self.bilateral_first_eye_lbl = QLabel('—')
        self.bilateral_first_eye_lbl.setObjectName('resultStatTitle')
        self.bilateral_first_result_lbl = QLabel('—')
        self.bilateral_first_result_lbl.setObjectName('resultStatValue')
        self.bilateral_first_saved_lbl = QLabel('✓ Saved')
        self.bilateral_first_saved_lbl.setStyleSheet('font-weight:700;font-size:13px;')
        self.bilateral_first_saved_lbl.setObjectName('successLabel')
        first_col.addWidget(self.bilateral_first_eye_lbl)
        first_col.addWidget(self.bilateral_first_result_lbl)
        first_col.addWidget(self.bilateral_first_saved_lbl)
        brow_div = QFrame()
        brow_div.setFrameShape(QFrame.Shape.VLine)
        brow_div.setFrameShadow(QFrame.Shadow.Plain)
        brow_div.setStyleSheet('color:#d9e5f2;')
        second_col = QVBoxLayout()
        second_col.setSpacing(4)
        self.bilateral_second_eye_lbl = QLabel('—')
        self.bilateral_second_eye_lbl.setObjectName('resultStatTitle')
        self.bilateral_second_result_lbl = QLabel('—')
        self.bilateral_second_result_lbl.setObjectName('resultStatValue')
        self.bilateral_second_saved_lbl = QLabel('Unsaved')
        self.bilateral_second_saved_lbl.setStyleSheet('font-weight:700;font-size:13px;')
        self.bilateral_second_saved_lbl.setObjectName('errorLabel')
        second_col.addWidget(self.bilateral_second_eye_lbl)
        second_col.addWidget(self.bilateral_second_result_lbl)
        second_col.addWidget(self.bilateral_second_saved_lbl)
        brow.addLayout(first_col)
        brow.addWidget(brow_div)
        brow.addLayout(second_col)
        bilateral_layout.addLayout(brow)
        self.bilateral_frame.hide()
        self._apply_action_icons()
        self.footer_label = QLabel('Grad-CAM++ • Automated DR Screening v2.1 • Results are decision-support tools, not a clinical diagnosis')
        self.footer_label.setObjectName('footerLabel')
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer_label.setWordWrap(True)
        layout.addWidget(self.footer_label)
        self.setStyleSheet('\n            QWidget {\n                background: #ffffff;\n                color: #1f2937;\n                font-family: "Segoe UI";\n                font-size: 14px;\n            }\n            QScrollArea {\n                background: #ffffff;\n                border: none;\n            }\n            QLabel {\n                background: transparent;\n            }\n            QLabel#crumbLabel {\n                color: #6b7280;\n                font-size: 11px;\n                font-weight: 700;\n                letter-spacing: 1.3px;\n            }\n            QLabel#pageHeader {\n                font-size: 34px;\n                font-weight: 700;\n                color: #111827;\n                letter-spacing: 0.1px;\n            }\n            QLabel#pageSubtitle {\n                color: #6b7280;\n                font-size: 13px;\n            }\n            QLabel#infoPill {\n                background: #eff6ff;\n                color: #1d4ed8;\n                border: 1px solid #bfdbfe;\n                border-radius: 20px;\n                padding: 4px 12px;\n                font-size: 12px;\n                font-weight: 700;\n            }\n            QLabel#savedPill {\n                background: #ecfdf3;\n                color: #166534;\n                border: 1px solid #86efac;\n                border-radius: 20px;\n                padding: 4px 12px;\n                font-size: 12px;\n                font-weight: 700;\n            }\n            QLabel#aiDisclaimerLabel {\n                background: #fffbeb;\n                color: #7c2d12;\n                border: 1px solid #fed7aa;\n                border-radius: 8px;\n                padding: 10px 12px;\n                font-size: 12px;\n                line-height: 1.45;\n                font-weight: 600;\n            }\n            QGroupBox#resultGroupCard {\n                background: #ffffff;\n                border: 1px solid #e5e7eb;\n                border-radius: 12px;\n                margin-top: 0;\n            }\n            QGroupBox#resultGroupCard::title {\n                color: transparent;\n                subcontrol-origin: margin;\n                left: 0;\n                padding: 0;\n            }\n            QLabel#cardHeaderLabel {\n                color: #374151;\n                font-size: 13px;\n                font-weight: 700;\n            }\n            QLabel#expandGlyph {\n                color: #6b7280;\n                font-size: 14px;\n                font-weight: 700;\n            }\n            QLabel#sourceImageSurface {\n                background: #000000;\n                border: 1px solid #e5e7eb;\n                border-radius: 8px;\n                color: #9ca3af;\n                font-size: 13px;\n            }\n            QLabel#heatmapImageSurface {\n                background: #0b0f19;\n                border: 1px solid #e5e7eb;\n                border-radius: 8px;\n                color: #9ca3af;\n                font-size: 14px;\n            }\n            QFrame#resultStatCard {\n                background: #f9fafb;\n                border: 1px solid #e5e7eb;\n                border-radius: 12px;\n            }\n            QLabel#resultStatTitle {\n                color: #6b7280;\n                font-size: 12px;\n                font-weight: 600;\n                letter-spacing: 0.9px;\n            }\n            QLabel#classificationValue {\n                color: #2563eb;\n                font-size: 27px;\n                font-weight: 700;\n            }\n            QLabel#resultStatValue {\n                color: #111827;\n                font-size: 18px;\n                font-weight: 600;\n            }\n            QLabel#monoValue {\n                color: #1f2937;\n                font-family: "Segoe UI";\n                font-size: 18px;\n                font-weight: 700;\n            }\n            QProgressBar#confidenceBar {\n                border: none;\n                border-radius: 4px;\n                background: #e5e7eb;\n                height: 6px;\n            }\n            QProgressBar#confidenceBar::chunk {\n                background: #2563eb;\n                border-radius: 4px;\n            }\n            QProgressBar#uncertaintyBar {\n                border: none;\n                border-radius: 4px;\n                background: #fef3c7;\n                height: 6px;\n            }\n            QProgressBar#uncertaintyBar::chunk {\n                background: #f59e0b;\n                border-radius: 4px;\n            }\n            QLabel#metaText {\n                color: #6b7280;\n                font-size: 12px;\n                font-weight: 500;\n            }\n            QLabel#decisionRoleTag {\n                background: #f8fafc;\n                color: #334155;\n                border: 1px solid #cbd5e1;\n                border-radius: 6px;\n                padding: 3px 10px;\n                font-size: 11px;\n                font-weight: 700;\n                min-height: 20px;\n            }\n            QLabel#doctorRoleTag {\n                background: #eff6ff;\n                color: #2563eb;\n                border: 1px solid #bfdbfe;\n                border-radius: 6px;\n                padding: 3px 10px;\n                font-size: 11px;\n                font-weight: 800;\n                min-height: 20px;\n                text-transform: uppercase;\n            }\n            QFrame#decisionStepPanel {\n                background: #ffffff;\n                border: 1px solid #e5e7eb;\n                border-radius: 10px;\n            }\n            QPushButton#decisionChoiceButton {\n                background: #ffffff;\n                color: #1f2937;\n                border: 1px solid #60a5fa;\n                border-radius: 8px;\n                padding: 8px 14px;\n                font-weight: 700;\n            }\n            QPushButton#decisionChoiceButton:hover {\n                background: #eff6ff;\n                border-color: #3b82f6;\n            }\n            QPushButton#decisionChoiceButton:pressed {\n                background: #dbeafe;\n                border-color: #2563eb;\n            }\n            QPushButton#decisionChoiceButton:disabled {\n                background: #f8fafc;\n                color: #94a3b8;\n                border-color: #bfdbfe;\n            }\n            QPushButton#ghostAction {\n                background: #ffffff;\n                border: 1px solid #bfdbfe;\n                color: #1a1a1a;\n                border-radius: 8px;\n                padding: 8px 12px;\n                font-size: 13px;\n                font-family: "Segoe UI";\n                font-weight: 400;\n            }\n            QPushButton#ghostAction:hover {\n                background: #eff6ff;\n                border-color: #93c5fd;\n            }\n            QPushButton#ghostAction:disabled {\n                background: #f8fafc;\n                color: #94a3b8;\n                border-color: #dbeafe;\n            }\n            QTextEdit#overrideCommentBox,\n            QTextEdit#findingsCommentBox {\n                background: #ffffff;\n                border: 1px solid #d1d5db;\n                border-radius: 8px;\n                padding: 10px;\n                font-size: 13px;\n                color: #1f2937;\n            }\n            QTextEdit#overrideCommentBox:focus,\n            QTextEdit#findingsCommentBox:focus {\n                border: 1px solid #60a5fa;\n            }\n            QFrame#uncertaintyPanel {\n                background: #fffbeb;\n                border: 1px solid #fce7b6;\n                border-radius: 8px;\n            }\n            QLabel#uncertaintyValue {\n                color: #92400e;\n                font-size: 18px;\n                font-weight: 700;\n                letter-spacing: 0.4px;\n            }\n            QLabel#okBadge {\n                background: #ecfdf3;\n                color: #166534;\n                border: 1px solid #86efac;\n                border-radius: 20px;\n                padding: 4px 10px;\n                font-size: 11px;\n                font-weight: 700;\n            }\n            QLabel#summaryBody {\n                background: transparent;\n                border: none;\n                border-radius: 0;\n                color: #595959;\n                font-size: 13px;\n                font-weight: 500;\n                line-height: 1.6;\n                padding: 0;\n            }\n            QLabel#summaryRowSuccess {\n                background: transparent;\n                border: none;\n                border-radius: 0;\n                padding: 6px 0;\n                color: #166534;\n                font-size: 13px;\n                font-weight: 600;\n            }\n            QLabel#summaryRowInfo {\n                background: transparent;\n                border: none;\n                border-radius: 0;\n                padding: 6px 0;\n                color: #1d4ed8;\n                font-size: 13px;\n                font-weight: 600;\n            }\n            QLabel#summaryRowWarn {\n                background: transparent;\n                border: none;\n                border-radius: 0;\n                padding: 6px 0;\n                color: #b45309;\n                font-size: 13px;\n                font-weight: 600;\n            }\n            QLabel#footerLabel {\n                color: #9ca3af;\n                font-size: 11px;\n                padding-top: 12px;\n                padding-bottom: 12px;\n            }\n            QPushButton {\n                background: #ffffff;\n                color: #1f2937;\n                border: 1px solid #d1d5db;\n                border-radius: 8px;\n                padding: 10px 16px;\n                font-weight: 600;\n                font-size: 13px;\n            }\n            QPushButton:hover {\n                background: #f3f4f6;\n                border-color: #9ca3af;\n            }\n            QPushButton:pressed {\n                background: #e5e7eb;\n            }\n            QPushButton:disabled {\n                background: #f9fafb;\n                color: #d1d5db;\n                border-color: #e5e7eb;\n            }\n            QPushButton#primaryAction {\n                background: #2563eb;\n                color: #ffffff;\n                border: none;\n                font-weight: 600;\n            }\n            QPushButton#primaryAction:hover {\n                background: #1d4ed8;\n            }\n            QPushButton#primaryAction:pressed {\n                background: #1e40af;\n            }\n            QPushButton#neutralAction {\n                background: #ffffff;\n                color: #1f2937;\n                border: 1px solid #d1d5db;\n                font-weight: 600;\n            }\n            QPushButton#neutralAction:hover {\n                background: #f9fafb;\n                border-color: #9ca3af;\n            }\n            QPushButton#referAction {\n                background: #ecfeff;\n                color: #0f766e;\n                border: 1px solid #99f6e4;\n                font-weight: 700;\n            }\n            QPushButton#referAction:hover {\n                background: #ccfbf1;\n                border-color: #5eead4;\n            }\n            QPushButton#referAction:pressed {\n                background: #99f6e4;\n                border-color: #2dd4bf;\n            }\n            QPushButton#referAction:disabled {\n                background: #f8fafc;\n                color: #94a3b8;\n                border-color: #e2e8f0;\n            }\n            QPushButton#dangerAction {\n                background: #fef2f2;\n                color: #b91c1c;\n                border: 1px solid #fecaca;\n                font-weight: 600;\n            }\n            QPushButton#dangerAction:hover {\n                background: #fee2e2;\n                border-color: #fca5a5;\n            }\n        ')

    def _is_dark_theme(self) -> bool:
        bg = self.palette().color(QPalette.ColorRole.Window)
        fg = self.palette().color(QPalette.ColorRole.WindowText)
        return bg.lightness() < fg.lightness()

    def _build_action_icon(self, filename: str, fallback: QStyle.StandardPixmap) -> QIcon:
        icon_path = os.path.join(self._icons_dir, filename)
        base_icon = QIcon(icon_path) if os.path.isfile(icon_path) else self.style().standardIcon(fallback)
        source = base_icon.pixmap(QSize(24, 24))
        if source.isNull():
            return base_icon
        tint = QColor('#f8fafc') if self._is_dark_theme() else QColor('#1f2937')
        tinted = QPixmap(source.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), tint)
        painter.end()
        icon = QIcon()
        icon.addPixmap(tinted, QIcon.Mode.Normal)
        icon.addPixmap(tinted, QIcon.Mode.Active)
        disabled = QPixmap(tinted)
        p2 = QPainter(disabled)
        p2.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p2.fillRect(disabled.rect(), QColor(tint.red(), tint.green(), tint.blue(), 110))
        p2.end()
        icon.addPixmap(disabled, QIcon.Mode.Disabled)
        return icon

    def _apply_action_icons(self):
        self.btn_save.setIcon(self._build_action_icon('save_patient.svg', QStyle.StandardPixmap.SP_DialogSaveButton))
        self.btn_report.setIcon(self._build_action_icon('generate.svg', QStyle.StandardPixmap.SP_ArrowDown))
        self.btn_screen_another.setIcon(self._build_action_icon('another_eye.svg', QStyle.StandardPixmap.SP_FileDialogStart))
        self.btn_new.setIcon(self._build_action_icon('new_patient.svg', QStyle.StandardPixmap.SP_FileDialogNewFolder))
        self.btn_back.setIcon(self._build_action_icon('back_to_screening.svg', QStyle.StandardPixmap.SP_ArrowBack))
        self.accept_ai_btn.setIcon(self._build_action_icon('accep_ai_result.svg', QStyle.StandardPixmap.SP_DialogApplyButton))
        self.override_ai_btn.setIcon(self._build_action_icon('override_ai result.svg', QStyle.StandardPixmap.SP_FileDialogDetailedView))

    def _resolve_actor_username(self) -> str:
        raw_username = str(os.environ.get('EYESHIELD_CURRENT_USER') or (getattr(self.parent_page, 'username', '') if self.parent_page else '') or (getattr(self.window(), 'username', '') if self.window() is not self else '')).strip()
        return UserManager.resolve_username(raw_username)

    def changeEvent(self, event):
        if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self._apply_action_icons()
        super().changeEvent(event)

    def _create_stat_card(self, title_text):
        card = QFrame()
        card.setObjectName('resultStatCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(4)
        title = QLabel(title_text)
        title.setObjectName('resultStatTitle')
        value = QLabel('Pending')
        value.setObjectName('resultStatValue')
        value.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(value)
        return (card, value)

    @staticmethod
    def _extract_percent_value(value_text: str) -> float:
        txt = str(value_text or '')
        match = re.search('(\\d+(?:\\.\\d+)?)\\s*%', txt)
        if not match:
            return 0.0
        try:
            return max(0.0, min(100.0, float(match.group(1))))
        except ValueError:
            return 0.0

    @staticmethod
    def _format_percent(value: float) -> str:
        return f'{max(0.0, min(100.0, value)):.1f}%'

    def _reset_save_button_default(self):
        self.btn_save.setEnabled(True)
        self.btn_save.setText('Save Result')
        self.btn_save.setObjectName('ghostAction')
        self.btn_save.setStyle(self.btn_save.style())
        self.save_note_label.hide()

    def _set_save_state(self, state: str, details: str=''):
        if state == 'writing':
            self.btn_save.setEnabled(False)
            self.btn_save.setText('Saving to disk...')
            self.save_note_label.setText(details or 'Writing local record...')
            self.save_note_label.show()
            return
        if state == 'success':
            self.btn_save.setEnabled(False)
            self.btn_save.setText('Saved ✓')
            self.save_note_label.setText(details)
            self.save_note_label.show()
            self._save_state_timer.start(4000)
            return
        if state == 'unchanged':
            self.btn_save.setEnabled(True)
            self.btn_save.setText('Save Result')
            self.save_note_label.setText('No changes since last save')
            self.save_note_label.show()
            self._save_state_timer.start(4000)
            return
        if state == 'failed':
            self.btn_save.setEnabled(True)
            self.btn_save.setText('Save Failed')
            self.save_note_label.setText(details)
            self.save_note_label.show()
            return
        self._reset_save_button_default()

    def is_uncertainty_blocking(self) -> bool:
        return False

    def _acknowledge_uncertainty(self):
        return

    def _accept_ai_classification(self):
        ai_value = str(self._current_result_class or '').strip()
        if ai_value:
            self.doctor_classification_input.setCurrentText(ai_value)
            self._doctor_classification = ai_value
            self._decision_mode = 'accepted'
            self._override_justification = ''
            self.override_reason_input.clear()
            self._refresh_decision_ui_state()

    def _prepare_override(self):
        self._decision_mode = 'override'
        self._refresh_decision_ui_state()
        self.override_reason_input.setFocus()

    def _on_doctor_classification_changed(self, value: str):
        chosen = str(value or '').strip()
        self._doctor_classification = chosen
        ai_value = str(self._current_result_class or '').strip()
        if self._decision_mode in ('accepted', 'override'):
            if self._doctor_classification == ai_value:
                if self._decision_mode == 'override':
                    self._decision_mode = 'accepted'
                    self.override_reason_input.clear()
                    self._override_justification = ''
            elif self._doctor_classification:
                self._decision_mode = 'override'
        self._refresh_decision_ui_state()

    def _on_override_reason_changed(self, text: str=''):
        if text:
            self._override_justification = str(text).strip()
        else:
            self._override_justification = str(self.override_reason_input.toPlainText() or '').strip()
        self._refresh_decision_ui_state()

    def _on_findings_changed(self, text: str=''):
        if text:
            self._doctor_findings = str(text).strip()
        else:
            self._doctor_findings = str(self.findings_input.toPlainText() or '').strip()

    def _refresh_decision_ui_state(self):
        ai_value = str(self._current_result_class or '').strip()
        doctor_value = str(self.doctor_classification_input.currentText() or self._doctor_classification or '').strip()
        requires_override = bool(doctor_value and doctor_value != ai_value)
        show_documentation = self._decision_mode == 'override' or requires_override
        show_optional_comment = self._decision_mode in ('accepted', 'override') or requires_override
        show_override = self._decision_mode == 'override' or requires_override
        self.documentation_panel.setVisible(show_documentation)
        self.optional_comment_panel.setVisible(show_optional_comment)
        self.override_reason_label.setVisible(show_override)
        self.override_reason_input.setVisible(show_override)
        if not doctor_value:
            self.classification_match_label.setText('Enter your classification to continue.')
        elif doctor_value == ai_value:
            self.classification_match_label.setText('Your current classification matches the AI')
        else:
            self.classification_match_label.setText('Your classification differs from AI. Override documentation is required.')
        if requires_override:
            self.decision_hint.setText('Override selected. Provide clinical justification before saving.')
        elif self._decision_mode == 'accepted':
            self.decision_hint.setText('AI accepted. Optional doctor comments can be added below.')
        else:
            self.decision_hint.setText('Choose Accept AI or Override AI to reveal the required documentation fields.')

    def get_decision_payload(self) -> dict:
        ai_value = str(self._current_result_class or '').strip()
        doctor_value = str(self.doctor_classification_input.currentText() or self._doctor_classification or '').strip()
        requires_override = doctor_value and ai_value and (doctor_value != ai_value)
        mode = 'override' if requires_override else 'accepted'
        override_text = str(self.override_reason_input.toPlainText() or self._override_justification or '').strip()
        findings_text = str(self.findings_input.toPlainText() or self._doctor_findings or '').strip()
        self._doctor_classification = doctor_value
        self._override_justification = override_text
        self._doctor_findings = findings_text
        return {'ai_classification': ai_value, 'doctor_classification': doctor_value, 'decision_mode': mode, 'override_justification': override_text, 'final_diagnosis_icdr': doctor_value, 'doctor_findings': findings_text}

    def validate_decision_before_save(self) -> tuple[bool, str]:
        payload = self.get_decision_payload()
        doctor_value = str(payload.get('doctor_classification') or '').strip()
        if not doctor_value:
            return (False, 'Please enter doctor classification.')
        findings = str(payload.get('doctor_findings') or '').strip()
        if payload.get('decision_mode') == 'override':
            justification = str(payload.get('override_justification') or '').strip()
            if len(justification) < 8:
                return (False, 'Override requires a brief clinical justification (at least 8 characters).')
        elif not findings:
            default_note = f'Clinician reviewed and accepted AI classification: {doctor_value}.'
            self._doctor_findings = default_note
            self.findings_input.setText(default_note)
        return (True, '')

    def set_results(self, patient_name, image_path, result_class='Pending', confidence_text='Pending', eye_label='', first_eye_result=None, heatmap_path='', patient_data=None, heatmap_pending=False):
        is_loading = result_class in ('Analyzing…', 'Pending')
        is_busy = is_loading or heatmap_pending
        if patient_name:
            self.title_label.setText(f'Results for {patient_name}')
        else:
            self.title_label.setText('Results')
        self.eye_badge_label.setText(f"• {eye_label or 'Screened Eye'}")
        if is_busy:
            self._loading_bar.show()
        else:
            self._loading_bar.hide()
        self.save_status_label.hide()
        self.save_status_label.setText('Saved ✓')
        self.btn_save.setEnabled(not is_busy)
        self.btn_save.setText('Save Result')
        self.btn_save.setObjectName('ghostAction')
        self.btn_save.setStyle(self.btn_save.style())
        self.btn_screen_another.setEnabled(not is_busy)
        if first_eye_result:
            self._first_eye_context = dict(first_eye_result)
            self.bilateral_first_eye_lbl.setText(first_eye_result.get('eye', '—'))
            self.bilateral_first_result_lbl.setText(first_eye_result.get('result', '—'))
            self.bilateral_second_eye_lbl.setText(eye_label or 'Current Eye')
            self.bilateral_second_result_lbl.setText(result_class)
            self.bilateral_second_saved_lbl.setText('Unsaved')
            self.bilateral_second_saved_lbl.setStyleSheet('font-weight:700;font-size:13px;')
            self.bilateral_second_saved_lbl.setObjectName('errorLabel')
            self.bilateral_frame.show()
        else:
            self._first_eye_context = {}
            self.bilateral_frame.hide()
        self.classification_value.setText(result_class)
        self.ai_classification_value.setText(result_class)
        grade_color = DR_COLORS.get(result_class, '#1f2937')
        self.classification_value.setStyleSheet(f'color:{grade_color};font-size:33px;font-weight:800;')
        class_subtitles = {'No DR': 'No diabetic retinopathy detected', 'Mild DR': 'Mild non-proliferative diabetic retinopathy', 'Moderate DR': 'Moderate non-proliferative diabetic retinopathy', 'Severe DR': 'Severe non-proliferative diabetic retinopathy', 'Proliferative DR': 'Proliferative diabetic retinopathy'}
        self.classification_subtitle.setText(class_subtitles.get(result_class, 'Clinical review advised'))
        confidence_pct = self._extract_percent_value(confidence_text)
        confidence_display = self._format_percent(confidence_pct)
        self.confidence_value.setText(f'Confidence: {confidence_display}')
        self.confidence_bar.setValue(int(round(confidence_pct * 10)))
        uncertainty_match = re.search('uncertainty\\s*:?\\s*(\\d+(?:\\.\\d+)?)\\s*%', str(confidence_text or ''), re.IGNORECASE)
        if uncertainty_match:
            uncertainty_pct = max(0.0, min(100.0, float(uncertainty_match.group(1))))
        else:
            uncertainty_pct = max(0.0, min(100.0, 100.0 - confidence_pct))
        self._uncertainty_pct = uncertainty_pct
        self.uncertainty_value.setText(f'Uncertainty: {self._format_percent(uncertainty_pct)}')
        self.uncertainty_bar.setValue(int(round(uncertainty_pct * 10)))
        recommendation = DR_RECOMMENDATIONS.get(result_class, 'Consult an eye care specialist')
        if is_loading:
            recommendation = '—'
        self.recommendation_value.setText(recommendation)
        self.recommendation_badge.setText('Routine follow-up' if result_class == 'No DR' else 'Clinical follow-up')
        if is_loading:
            self.subtitle_label.setText('Running DR analysis — please wait…')
        elif heatmap_pending:
            conf_part = f' with confidence {confidence_display}' if confidence_text else ''
            self.subtitle_label.setText(f'Screening complete — {result_class}{conf_part}. Generating the Grad-CAM++ heatmap now.')
        else:
            conf_part = f' with confidence {confidence_display}' if not is_loading else ''
            self.subtitle_label.setText(f'Screening complete — {result_class}{conf_part}. Review source fundus, Grad-CAM++ heatmap, and the clinical summary below.')
        if image_path:
            source_pixmap = QPixmap(image_path)
            self.source_label.set_viewable_pixmap(source_pixmap, 520, 390)
            if is_loading:
                self.heatmap_label.clear_view('')
            elif heatmap_pending:
                self.heatmap_label.clear_view('')
            elif heatmap_path and os.path.isfile(heatmap_path):
                hmap_pixmap = QPixmap(heatmap_path)
                self.heatmap_label.set_viewable_pixmap(hmap_pixmap, 520, 390)
            else:
                self.heatmap_label.clear_view('')
        else:
            self.source_label.clear_view('')
            self.heatmap_label.clear_view('')
        if is_loading:
            self.summary_line_1.setText('■ No signs of diabetic retinopathy detected')
            self.summary_line_2.setText('■ Patient profile: awaiting demographic and glycaemic context')
            self.summary_line_3.setText('■ Model uncertainty note: update after analysis')
            self.explanation.setText('Awaiting model output…')
        else:
            pd = patient_data or {}
            age = pd.get('age')
            hba1c = pd.get('hba1c')
            age_txt = f'{age}-year-old' if age not in (None, '', 0, '0') else 'Patient'
            hba1c_txt = f'{hba1c}%' if hba1c not in (None, '', '0', 0) else 'unavailable'
            self.summary_line_1.setText('■ No signs of diabetic retinopathy detected — high uncertainty requires clinical correlation' if result_class == 'No DR' else f'■ {result_class} detected — confirm with clinical examination')
            self.summary_line_2.setText(f'■ Patient profile: {age_txt}; HbA1c {hba1c_txt}. Continue glycaemic strategy based on clinical targets')
            self.summary_line_3.setText(f'■ Model uncertainty note: clinical review is advised (uncertainty {self._format_percent(uncertainty_pct)}); annual screening recommended unless specialist suggests shorter follow-up')
            self.explanation.setText(_generate_explanation(result_class, confidence_text, patient_data))
        self._current_image_path = image_path or ''
        self._current_heatmap_path = heatmap_path or ''
        self._current_result_class = result_class
        self._current_confidence = confidence_text
        self._current_eye_label = eye_label
        self._current_patient_name = patient_name or ''
        if result_class in ICDR_OPTIONS:
            self.doctor_classification_input.setCurrentText(result_class)
            self._doctor_classification = result_class
            self._decision_mode = 'pending'
            self._override_justification = ''
            self.override_reason_input.clear()
            self._doctor_findings = ''
            self.findings_input.clear()
        self._refresh_decision_ui_state()
        _report_ready = not is_busy and bool(image_path) and (result_class not in ('Analyzing…', 'Pending'))
        self.btn_report.setEnabled(_report_ready)

    def mark_saved(self, name, eye_label, result_class):
        """Called by ScreeningPage after a successful save to update this panel."""
        self.save_status_label.setText('Saved ✓')
        self.save_status_label.show()
        self.btn_save.setText('Saved ✓')
        self.btn_save.setEnabled(False)
        if self.bilateral_frame.isVisible():
            self.bilateral_second_saved_lbl.setText('✓ Saved')
            self.bilateral_second_saved_lbl.setStyleSheet('font-weight:700;font-size:13px;')
            self.bilateral_second_saved_lbl.setObjectName('successLabel')

    def go_back(self):
        """Go back to screening form - clears all fields with confirmation."""
        if not self.parent_page:
            return
        page = self.parent_page
        if hasattr(page, 'stacked_widget'):
            page.stacked_widget.setCurrentIndex(0)
            write_activity('INFO', 'DIALOG_BACK_TO_SCREENING', 'User went back to patient info')
        else:
            write_activity('WARNING', 'DIALOG_BACK_TO_SCREENING', 'No stacked_widget found')

    def save_patient(self):
        if not self.parent_page or not hasattr(self.parent_page, 'save_screening'):
            return
        box = QMessageBox(self)
        box.setWindowTitle('Confirm Final Result')
        box.setText('Are you sure this classification and detail are final?')
        box.setIcon(QMessageBox.Icon.Question)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        self._set_save_state('writing', 'Saving to local records...')
        QApplication.processEvents()
        result = self.parent_page.save_screening(reset_after=False)
        if not isinstance(result, dict):
            self._set_save_state('failed', 'Save failed due to an unexpected response.')
            return
        status = result.get('status')
        if status in ('saved', 'replaced'):
            saved_path = str(result.get('path') or '')
            details = f'Saved ✓ {saved_path}' if saved_path else 'Saved ✓'
            self._set_save_state('success', details)
            return
        if status == 'unchanged':
            self._set_save_state('unchanged')
            return
        if status == 'invalid':
            self._set_save_state('failed', 'Please complete required fields before saving.')
            return
        if status == 'cancelled':
            self._set_save_state('idle')
            return
        if status in ('error', 'blocked'):
            self._set_save_state('failed', str(result.get('error') or 'Save failed'))
            box = QMessageBox(self)
            box.setWindowTitle('Save Failed')
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText(str(result.get('error') or 'Save failed'))
            retry_btn = box.addButton('Retry', QMessageBox.ButtonRole.AcceptRole)
            change_btn = box.addButton('Change Save Location', QMessageBox.ButtonRole.ActionRole)
            box.addButton('Close', QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == retry_btn:
                self.save_patient()
                return
            if box.clickedButton() == change_btn:
                folder = QFileDialog.getExistingDirectory(self, 'Choose Save Location')
                if folder:
                    self.parent_page._custom_storage_root = folder
                    self.save_patient()
            return
        self._set_save_state('failed', 'Save was not completed.')

    def new_patient(self):
        if not self.parent_page:
            return
        page = self.parent_page
        if not getattr(page, '_current_eye_saved', True):
            current_eye = page.p_eye.currentText() if hasattr(page, 'p_eye') else 'screening'
            box = QMessageBox(self)
            box.setWindowTitle('Unsaved Screening Result')
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(f'This <b>{current_eye}</b> screening result has not been saved. Starting a new patient will permanently discard it.')
            save_first_btn = box.addButton('Save First', QMessageBox.ButtonRole.AcceptRole)
            discard_btn = box.addButton('Discard and Continue', QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = box.addButton('Cancel', QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.exec()
            choice = box.clickedButton()
            if choice == save_first_btn:
                self.save_patient()
                if getattr(page, '_current_eye_saved', False):
                    write_activity('INFO', 'DIALOG_NEW_PATIENT', 'Save First')
                    page.reset_screening()
                return
            if choice != discard_btn:
                write_activity('INFO', 'DIALOG_NEW_PATIENT', 'Cancel')
                return
            write_activity('WARNING', 'DIALOG_NEW_PATIENT', 'Discard and Continue')
        has_visible_result = bool(str(getattr(self, '_current_image_path', '') or '').strip())
        if has_visible_result:
            confirm_clear = QMessageBox.question(self, 'Clear Current Results', 'Starting a new patient will clear the current results area. Continue?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if confirm_clear != QMessageBox.StandardButton.Yes:
                write_activity('INFO', 'DIALOG_NEW_PATIENT', 'Cancel Clear Results')
                return
        if hasattr(page, 'reset_screening'):
            page.reset_screening()

    def _on_screen_another(self):
        if self.parent_page and hasattr(self.parent_page, 'screen_other_eye'):
            self.parent_page.screen_other_eye()

    def generate_report(self):
        """Generate a PDF screening report for the current patient."""
        if self._current_result_class in ('Pending', 'Analyzing…') or not self._current_image_path:
            QMessageBox.information(self, 'Generate Report', 'No completed screening results to report.')
            return
        if self.parent_page and (not getattr(self.parent_page, '_current_eye_saved', False)):
            QMessageBox.warning(self, 'Generate Report', 'Please save the result before generating a report')
            return
        if not self.bilateral_frame.isVisible():
            box = QMessageBox(self)
            box.setWindowTitle('Single-Eye Report')
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText('Only one eye has been screened. Generate a single-eye report, or screen the other eye first?')
            generate_btn = box.addButton('Generate Anyway', QMessageBox.ButtonRole.AcceptRole)
            other_eye_btn = box.addButton('Screen Other Eye First', QMessageBox.ButtonRole.ActionRole)
            box.addButton('Cancel', QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == other_eye_btn:
                self._on_screen_another()
                return
            if box.clickedButton() != generate_btn:
                return
        pp = self.parent_page
        missing_profile = []
        if pp:
            if not pp.p_name.text().strip():
                missing_profile.append('Name')
            if pp.p_age.value() <= 0:
                missing_profile.append('Age')
        if missing_profile:
            QMessageBox.warning(self, 'Profile Incomplete', 'Patient profile is incomplete. Missing fields will appear blank in the report.\n\nMissing: ' + ', '.join(missing_profile))
        default_name = f"EyeShield_Report_{self._current_patient_name or 'Patient'}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, 'Save Screening Report', default_name, 'PDF Files (*.pdf)')
        if not path:
            return
        out_dir = os.path.dirname(path)
        writable, write_err = can_write_directory(out_dir)
        if not writable:
            QMessageBox.warning(self, 'Generate Report', f'Cannot write to {out_dir}. Choose a different save location.\n\n{write_err}')
            return
        free_mb = get_free_space_mb(out_dir)
        if free_mb < 50:
            QMessageBox.warning(self, 'Low Disk Space', f'Low disk space ({free_mb} MB remaining). The report may fail to save.')
        try:
            from PySide6.QtGui import QPdfWriter, QPageSize, QPageLayout, QTextDocument
            from PySide6.QtCore import QMarginsF
        except ImportError:
            QMessageBox.warning(self, 'Generate Report', 'PDF generation requires PySide6 PDF support.')
            return
        patient_id = pp.p_id.text().strip() if pp and hasattr(pp, 'p_id') else ''
        dob = pp.p_dob.text() if pp and hasattr(pp, 'p_dob') and hasattr(pp.p_dob, 'text') else ''
        age = str(pp.p_age.value()) if pp and hasattr(pp, 'p_age') else ''
        sex = pp.p_sex.currentText() if pp and hasattr(pp, 'p_sex') else ''
        contact = pp.p_contact.text().strip() if pp and hasattr(pp, 'p_contact') else ''
        diabetes_type = pp.diabetes_type.currentText() if pp and hasattr(pp, 'diabetes_type') else ''
        diabetes_diagnosis_date = pp.diabetes_diagnosis_date.text().strip() if pp and hasattr(pp, 'diabetes_diagnosis_date') else ''
        duration_val = pp.diabetes_duration.value() if pp and hasattr(pp, 'diabetes_duration') else 0
        hba1c_num = pp.hba1c.value() if pp and hasattr(pp, 'hba1c') else 0.0
        prev_tx = 'Yes' if pp and hasattr(pp, 'prev_treatment') and pp.prev_treatment.isChecked() else 'No'
        notes = pp.notes.toPlainText().strip() if pp and hasattr(pp, 'notes') else ''
        va_left = pp.va_left.text().strip() if pp and hasattr(pp, 'va_left') else ''
        va_right = pp.va_right.text().strip() if pp and hasattr(pp, 'va_right') else ''
        bp_sys = str(pp.bp_systolic.value()) if pp and hasattr(pp, 'bp_systolic') and (pp.bp_systolic.value() > 0) else ''
        bp_dia = str(pp.bp_diastolic.value()) if pp and hasattr(pp, 'bp_diastolic') and (pp.bp_diastolic.value() > 0) else ''
        fbs_val = str(pp.fbs.value()) if pp and hasattr(pp, 'fbs') and (pp.fbs.value() > 0) else ''
        rbs_val = str(pp.rbs.value()) if pp and hasattr(pp, 'rbs') and (pp.rbs.value() > 0) else ''
        height_val = str(pp.height.value()) if pp and hasattr(pp, 'height') and (pp.height.value() > 0) else ''
        weight_val = str(pp.weight.value()) if pp and hasattr(pp, 'weight') and (pp.weight.value() > 0) else ''
        bmi_val = str(pp.bmi.value()) if pp and hasattr(pp, 'bmi') and (pp.bmi.value() > 0) else ''
        treatment_regimen = pp.treatment_regimen.currentText() if pp and hasattr(pp, 'treatment_regimen') else ''
        prev_dr_stage = pp.prev_dr_stage.currentText() if pp and hasattr(pp, 'prev_dr_stage') else ''
        symptoms = []
        symptom_other_val = ''
        if pp:
            if hasattr(pp, 'symptom_blurred') and pp.symptom_blurred.isChecked():
                symptoms.append('Blurred Vision')
            if hasattr(pp, 'symptom_floaters') and pp.symptom_floaters.isChecked():
                symptoms.append('Floaters')
            if hasattr(pp, 'symptom_flashes') and pp.symptom_flashes.isChecked():
                symptoms.append('Flashes')
            if hasattr(pp, 'symptom_vision_loss') and pp.symptom_vision_loss.isChecked():
                symptoms.append('Vision Loss')
            symptom_other_val = pp.symptom_other.text().strip() if hasattr(pp, 'symptom_other') else ''
            if symptom_other_val:
                symptoms.append(symptom_other_val)

        def esc(value) -> str:
            return escape(str(value or '').strip()) or '&mdash;'

        def esc_or_dash(value) -> str:
            v = str(value or '').strip()
            return escape(v) if v and v not in ('0', 'None', 'Select') else '&mdash;'
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'config.json')
        clinic_name = 'EyeShield EMR'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            clinic_name = cfg.get('clinic_name') or cfg.get('admin_contact', {}).get('location', 'EyeShield EMR')
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        raw_confidence = str(self._current_confidence or '').strip()
        if raw_confidence.lower().startswith('confidence:'):
            raw_confidence = raw_confidence[len('confidence:'):].strip()
        confidence_display = escape(raw_confidence) if raw_confidence else '&mdash;'
        result_raw = str(self._current_result_class or '').strip()
        decision = self.get_decision_payload()
        final_dx = str(decision.get('final_diagnosis_icdr') or result_raw or '').strip()
        decision_mode = str(decision.get('decision_mode') or 'accepted').strip()
        override_note = str(decision.get('override_justification') or '').strip()
        findings_note = str(decision.get('doctor_findings') or '').strip()
        grade_color = DR_COLORS.get(result_raw, '#374151')
        grade_bg_map = {'No DR': '#d1f5e0', 'Mild DR': '#fef3e2', 'Moderate DR': '#fde8d8', 'Severe DR': '#fde8ea', 'Proliferative DR': '#f5d5d8'}
        grade_bg = grade_bg_map.get(result_raw, '#f3f4f6')
        recommendation = escape(DR_RECOMMENDATIONS.get(final_dx or result_raw, 'Consult a qualified ophthalmologist'))
        explanation_text = (self.explanation.text() or '').strip()
        if explanation_text:
            explanation_html = escape(explanation_text).replace('\n\n', '<br><br>').replace('\n', '<br>')
        else:
            summary_map = {'No DR': 'No signs of diabetic retinopathy were detected in this fundus image. Continue standard diabetes management and schedule routine annual retinal screening.', 'Mild DR': 'Early microaneurysms consistent with mild non-proliferative diabetic retinopathy (NPDR) were identified. A repeat retinal examination in 6 to 12 months is recommended.', 'Moderate DR': 'Features consistent with moderate NPDR were detected. Referral to an ophthalmologist within 3 months is advised.', 'Severe DR': 'Findings are consistent with severe NPDR. Urgent ophthalmology referral is required for further evaluation.', 'Proliferative DR': 'Proliferative diabetic retinopathy was detected, a sight-threatening condition. Immediate ophthalmology referral is required.'}
            explanation_html = escape(summary_map.get(result_raw, 'Please consult a qualified ophthalmologist.'))
        report_date = datetime.now().strftime('%B %d, %Y %I:%M %p')
        screened_by_name = str(os.environ.get('EYESHIELD_CURRENT_NAME', '') or os.environ.get('EYESHIELD_CURRENT_USER', '')).strip()
        screened_by_title = str(os.environ.get('EYESHIELD_CURRENT_TITLE', '')).strip()
        screened_by_raw = f'{screened_by_name} ({screened_by_title})' if screened_by_name and screened_by_title else screened_by_name
        screened_by = escape(screened_by_raw) if screened_by_raw else '&mdash;'
        created_by = screened_by
        finalized_by = screened_by
        duration_disp = f'{escape(str(duration_val))} year(s)' if duration_val and duration_val > 0 else '&mdash;'
        notes_disp = escape(notes) if notes else '&mdash;'
        hba1c_disp = f'{hba1c_num:.1f}%' if hba1c_num and hba1c_num > 0 else '&mdash;'
        bp_display = f'{escape(bp_sys)}/{escape(bp_dia)} mmHg' if bp_sys and bp_dia else '&mdash;'
        fbs_disp = f'{escape(fbs_val)} mg/dL' if fbs_val else '&mdash;'
        rbs_disp = f'{escape(rbs_val)} mg/dL' if rbs_val else '&mdash;'
        height_disp = f'{escape(height_val)} cm' if height_val else '&mdash;'
        weight_disp = f'{escape(weight_val)} kg' if weight_val else '&mdash;'

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
        if bmi_val:
            bmi_category, bmi_color = get_bmi_category(bmi_val)
            bmi_disp = f'{escape(bmi_val)} <span style="color:{bmi_color};font-weight:600;">({bmi_category})</span>'
        else:
            bmi_disp = '&mdash;'
        treatment_disp = esc_or_dash(treatment_regimen)
        prev_dr_disp = esc_or_dash(prev_dr_stage)
        symptom_html = ' '.join((f'<span class="symptom-pill">{escape(s)}</span>' for s in symptoms)) if symptoms else '<span style="color:#6b7280;">None reported</span>'
        other_symptom_disp = esc_or_dash(symptom_other_val)

        def resolve_image_path(path_value: str) -> str:
            raw = str(path_value or '').strip()
            if not raw:
                return ''
            if os.path.isabs(raw):
                candidate = raw
            else:
                candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), raw)
            if not os.path.isfile(candidate):
                return ''
            try:
                return str(Path(candidate).resolve())
            except OSError:
                return ''

        def build_embedded_image_uri(path_value: str, width: int=200, height: int=200) -> str:
            """Build embedded base64 image URI with proper sizing"""
            resolved = resolve_image_path(path_value)
            if not resolved:
                return ''
            src = QImage(resolved)
            if src.isNull():
                return ''
            fitted = src.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            canvas = QImage(fitted.width(), fitted.height(), QImage.Format.Format_ARGB32_Premultiplied)
            canvas.fill(QColor('#ffffff'))
            painter = QPainter(canvas)
            painter.drawImage(0, 0, fitted)
            painter.end()
            ba = QByteArray()
            buffer = QBuffer(ba)
            if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
                return ''
            canvas.save(buffer, 'PNG')
            buffer.close()
            b64 = bytes(ba.toBase64()).decode('ascii')
            return f'data:image/png;base64,{b64}'
        source_image_uri = build_embedded_image_uri(self._current_image_path, 280, 280)
        heatmap_image_uri = build_embedded_image_uri(self._current_heatmap_path, 280, 280)
        first_eye_ctx = dict(getattr(self, '_first_eye_context', {}) or {})
        first_eye_label = str(first_eye_ctx.get('eye') or '').strip()
        first_eye_result = str(first_eye_ctx.get('result') or '').strip() or '—'
        first_eye_confidence = str(first_eye_ctx.get('confidence') or '').strip() or '—'
        first_source_image_uri = build_embedded_image_uri(first_eye_ctx.get('image_path'), 280, 280) if first_eye_ctx else ''
        first_heatmap_image_uri = build_embedded_image_uri(first_eye_ctx.get('heatmap_path'), 280, 280) if first_eye_ctx else ''
        second_eye_label = str(self._current_eye_label or '').strip() or 'Current Eye'
        second_eye_result = str(result_raw or '').strip() or '—'
        second_eye_confidence = str(confidence_display or '').strip() or '—'
        bilateral_eye_labels = []
        for eye_name in (first_eye_label, second_eye_label):
            name = str(eye_name or '').strip()
            if name and name not in bilateral_eye_labels:
                bilateral_eye_labels.append(name)
        combined_eye_display = ', '.join(bilateral_eye_labels) if bilateral_eye_labels else second_eye_label or '—'
        is_bilateral_report = bool(first_eye_ctx and first_eye_label)

        def _render_eye_image_pair(eye_name: str, eye_grade: str, eye_conf: str, src_uri: str, heat_uri: str) -> str:
            source_html = f'<img src="{src_uri}" style="max-width:100%;max-height:230px;width:auto;height:auto;page-break-inside:avoid;break-inside:avoid-page;" />' if src_uri else '<div style="text-align:center;background:#ffffff;padding:30px;border:1px solid #e5e7eb;color:#9ca3af;font-style:italic;font-size:9pt;">Image not available</div>'
            heat_html = f'<img src="{heat_uri}" style="max-width:100%;max-height:230px;width:auto;height:auto;page-break-inside:avoid;break-inside:avoid-page;" />' if heat_uri else '<div style="text-align:center;background:#ffffff;padding:30px;border:1px solid #e5e7eb;color:#9ca3af;font-style:italic;font-size:9pt;">Heatmap not available</div>'

            def titled_image_block(title: str, image_html: str, margin_top: str='0') -> str:
                return f'<div style="page-break-inside:avoid;break-inside:avoid-page;margin-top:{margin_top};"><div style="font-size:8pt;font-weight:700;color:#4b5563;text-transform:uppercase;letter-spacing:0.5px;margin:0 0 6px;">{title}</div><div style="border:1px solid #d1d5db;padding:12px;background:#fafafa;">{image_html}</div></div>'
            return f"""<div class="imageBlock" style="border:1px solid #d1d5db;border-radius:6px;background:#ffffff;margin-bottom:14px;padding:12px 14px;"><table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;"><tr><td style="font-size:9pt;font-weight:700;color:#111827;">{esc(eye_name or 'Eye')}</td><td align="right"><span style="font-size:8pt;color:#6b7280;font-weight:600;">AI Results:&nbsp;</span><span style="font-size:9pt;font-weight:700;color:#111827;">{esc(eye_grade)}</span></td></tr></table><div style="font-size:8.5pt;color:#4b5563;margin-bottom:10px;">Confidence: <span style="font-weight:600;color:#374151;">{esc(eye_conf)}</span></div>{titled_image_block('Fundus', source_html)}{titled_image_block('Heatmap', heat_html, '12px')}</div>"""
        conf_display = confidence_display

        def sec(title):
            return f'<div style="margin:18px 0 10px;padding-bottom:6px;border-bottom:2px solid #1f2937;"><span style="font-size:9pt;font-weight:700;color:#1f2937;letter-spacing:1.2px;text-transform:uppercase;">{title}</span></div>'
        if is_bilateral_report:
            fundus_images_html = f"{sec('Bilateral Fundus Images')}" + _render_eye_image_pair(first_eye_label, first_eye_result, first_eye_confidence, first_source_image_uri, first_heatmap_image_uri) + _render_eye_image_pair(second_eye_label, second_eye_result, second_eye_confidence, source_image_uri, heatmap_image_uri)
        else:
            fundus_images_html = f"{sec('Fundus Images')}" + _render_eye_image_pair(second_eye_label, second_eye_result, second_eye_confidence, source_image_uri, heatmap_image_uri)
        _COL = {'No DR': '#166534', 'Mild DR': '#92400e', 'Moderate DR': '#9a3412', 'Severe DR': '#7f1d1d', 'Proliferative DR': '#6b1a1a'}
        _BG = {'No DR': '#f0fdf4', 'Mild DR': '#fefce8', 'Moderate DR': '#fff7ed', 'Severe DR': '#fff8f8', 'Proliferative DR': '#fff8f8'}
        _BORDER = {'No DR': '#16a34a', 'Mild DR': '#d97706', 'Moderate DR': '#ea580c', 'Severe DR': '#c24141', 'Proliferative DR': '#b91c1c'}
        _REC = {'No DR': 'Annual screening recommended', 'Mild DR': 'Repeat screening in 6&#8211;12 months', 'Moderate DR': 'Ophthalmology referral within 3 months', 'Severe DR': 'Urgent ophthalmology referral', 'Proliferative DR': 'Immediate ophthalmology referral'}
        _SUM = {'No DR': 'No signs of diabetic retinopathy were detected in this fundus image. Continue standard diabetes management, maintain optimal glycaemic and blood pressure control, and schedule routine annual retinal screening.', 'Mild DR': 'Early microaneurysms consistent with mild non-proliferative diabetic retinopathy (NPDR) were identified. Intensify glycaemic and blood pressure management. A repeat retinal examination in 6&#8211;12 months is recommended.', 'Moderate DR': 'Features consistent with moderate non-proliferative diabetic retinopathy (NPDR) were detected, including microaneurysms, hemorrhages, and/or hard exudates. Referral to an ophthalmologist within 3 months is advised. Reassess systemic metabolic control.', 'Severe DR': 'Findings consistent with severe non-proliferative diabetic retinopathy (NPDR) were detected. The risk of progression to proliferative disease within 12 months is high. Urgent ophthalmology referral is required.', 'Proliferative DR': 'Proliferative diabetic retinopathy (PDR) was detected &#8212; a sight-threatening condition. Immediate ophthalmology referral is required for evaluation and potential intervention, such as laser photocoagulation or intravitreal anti-VEGF therapy.'}
        gc = _COL.get(result_raw, '#1e3a5f')
        gbg = _BG.get(result_raw, '#f8faff')
        gb = _BORDER.get(result_raw, '#2563eb')
        rec = _REC.get(result_raw, 'Consult a qualified ophthalmologist')
        summary = _SUM.get(result_raw, 'Please consult a qualified ophthalmologist.')
        conf_display = confidence_display
        is_critical_grade = result_raw in ('Severe DR', 'Proliferative DR')
        if is_critical_grade:
            gbg = '#b91c1c'
            gc = '#ffffff'
            gb = '#991b1b'
            badge_bg = '#7f1d1d'
            confidence_color = '#ffffff'
            divider_color = '#fecaca'
            reco_label_opacity = '1'
        else:
            badge_bg = gb
            confidence_color = '#ffffff'
            divider_color = '#ffffff'
            reco_label_opacity = '0.95'
            gc = '#ffffff'
            gbg = gb

        def field_row(label, value, border=True):
            border_style = 'border-bottom:1px solid #e5e7eb;' if border else ''
            return f'<tr><td style="padding:8px 12px;{border_style}font-size:9pt;color:#4b5563;font-weight:500;width:35%;">{label}</td><td style="padding:8px 12px;{border_style}font-size:9pt;color:#111827;font-weight:600;">{value}</td></tr>'

        def field_grid_2col(fields):
            """Generate 2-column grid layout for fields"""
            rows_html = ''
            for i in range(0, len(fields), 2):
                left_label, left_value = fields[i]
                if i + 1 < len(fields):
                    right_label, right_value = fields[i + 1]
                else:
                    right_label, right_value = ('', '&mdash;')
                rows_html += f'<tr><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:8.5pt;color:#6b7280;font-weight:500;width:18%;">{left_label}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:9pt;color:#111827;font-weight:600;width:32%;">{left_value}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:8.5pt;color:#6b7280;font-weight:500;width:18%;">{right_label}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:9pt;color:#111827;font-weight:600;width:32%;">{right_value}</td></tr>'
            return rows_html
        result_label = escape(result_raw) if result_raw else '—'
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
        html = f"""<!DOCTYPE html>\n<html><head><meta charset="utf-8"><style>\nbody {{\n    font-family: 'Segoe UI', 'Calibri', Arial, sans-serif;\n    font-size: 10pt;\n    color: #111827;\n    background: #ffffff;\n    margin: 0;\n    padding: 0;\n    line-height: 1.5;\n}}\ntable {{\n    border-collapse: collapse;\n}}\ntd {{\n    overflow-wrap: anywhere;\n    word-break: break-word;\n}}\nimg {{\n    max-width: 100%;\n    height: auto;\n    display: block;\n}}\n.imageBlock {{\n    page-break-inside: avoid;\n    break-inside: avoid-page;\n}}\n</style></head><body>\n\n<!-- Header -->\n<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px;">\n<tr>\n    <td style="padding:16px 20px;background:#f9fafb;border-bottom:3px solid #1f2937;">\n        <div style="font-size:18pt;font-weight:700;color:#111827;margin-bottom:4px;">DIABETIC RETINOPATHY SCREENING REPORT</div>\n        <div style="font-size:8.5pt;color:#6b7280;">\n            <b>Generated:</b> {report_date} &nbsp;|&nbsp; <b>Created by:</b> {created_by}\n        </div>\n    </td>\n</tr>\n</table>\n\n<table width="100%" cellpadding="0" cellspacing="0">\n<tr><td style="padding:0 20px;">\n\n<!-- Patient Information -->\n{sec('Patient Information')}\n<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n{field_grid_2col([('Full Name', esc(self._current_patient_name)), ('Date of Birth', esc(dob)), ('Age', esc(age)), ('Sex', esc(sex)), ('Patient ID', esc(patient_id)), ('Contact', esc(contact)), ('Height', height_disp), ('Weight', weight_disp), ('BMI', bmi_disp), ('Eye Screened', esc(combined_eye_display or '—')), ('Screening Date', report_date), ('', '')])}\n</table>\n\n<!-- Clinical History & Diabetes Management -->\n{sec('Clinical History & Diabetes Management')}\n<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n{field_row('Diabetes Type', esc(diabetes_type))}\n{field_row('Diagnosis Date', esc_or_dash(diabetes_diagnosis_date))}\n{field_row('Duration', duration_disp)}\n{field_row('Treatment Regimen', treatment_disp)}\n{field_row('Previous DR Stage', prev_dr_disp)}\n{field_row('Previous DR Treatment', esc(prev_tx), False)}\n</table>\n\n<!-- Reported Symptoms -->\n{sec('Reported Symptoms')}\n<div style="padding:10px 12px;border:1px solid #d1d5db;margin-bottom:18px;background:#fafafa;">\n    <div style="font-size:9pt;color:#374151;">{symptom_html}</div>\n</div>\n\n{sec('Other Symptom Details')}\n<div style="padding:12px;border:1px solid #d1d5db;background:#fafafa;margin-bottom:18px;min-height:44px;">\n    <div style="font-size:9pt;color:#4b5563;line-height:1.65;">{other_symptom_disp}</div>\n</div>\n\n<!-- AI Classification Result -->\n{sec('AI Classification Result')}\n<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n{field_row('Classification', result_label)}\n{field_row('Confidence', conf_display, False)}\n</table>\n\n{sec('Doctor Decision')}\n<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1d5db;margin-bottom:18px;">\n{field_row('Decision Mode', esc(decision_mode.title()))}\n{field_row('Doctor Classification', esc(final_dx or '—'))}\n{field_row('Doctor Findings', esc(findings_note or '—'))}\n{field_row('Final Diagnosis', esc('Based on ICDR Severity Scale'), False)}\n</table>\n\n{sec('Doctor Comments')}\n<div style="padding:12px;border:1px solid #d1d5db;background:#fafafa;margin-bottom:18px;min-height:44px;">\n    <div style="font-size:9pt;color:#4b5563;line-height:1.65;">{(esc(findings_note) if findings_note else '&mdash;')}</div>\n</div>\n\n<div style="padding:10px 12px;border:1px solid #d1d5db;margin-bottom:18px;background:#fafafa;">\n    <div style="font-size:8.5pt;color:#374151;">\n        <b>Final Diagnosis: Based on ICDR Severity Scale</b><br>\n        AI output remains visible for transparency and decision support.\n    </div>\n</div>\n\n"""
        if decision_mode == 'override':
            html += f"""\n<div style="padding:10px 12px;border:1px solid #fecaca;margin-bottom:18px;background:#fff1f2;">\n    <div style="font-size:8.5pt;color:#7f1d1d;">\n        <b>Override Justification:</b> {esc(override_note or 'No justification provided')}\n    </div>\n</div>\n"""
        html += f"""\n\n{fundus_images_html}\n\n<!-- Clinical Analysis -->\n{sec('Clinical Analysis')}\n<div style="padding:14px;border:1px solid #d1d5db;background:#f9fafb;margin-bottom:18px;">\n    <div style="font-size:8pt;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px;">Clinical Recommendation</div>\n    <div style="font-size:9.5pt;color:#111827;font-weight:600;line-height:1.6;margin-bottom:14px;">&rarr; {rec}</div>\n    <div style="border-top:1px solid #d1d5db;padding-top:12px;margin-top:12px;">\n        <div style="font-size:9.5pt;color:#374151;line-height:1.75;">{summary}</div>\n    </div>\n</div>\n\n<!-- Clinical Notes -->\n{sec('Clinical Notes')}\n<div style="padding:12px;border:1px solid #d1d5db;background:#fafafa;margin-bottom:18px;min-height:50px;">\n    <div style="font-size:9pt;color:#4b5563;font-style:italic;line-height:1.65;">{notes_disp}</div>\n</div>\n\n<!-- Footer / Disclaimer -->\n<div style="margin-top:24px;padding-top:14px;border-top:2px solid #e5e7eb;">\n    <div style="font-size:7.5pt;color:#9ca3af;line-height:1.8;">\n        <b>Created by:</b> {created_by}<br>\n        <b>Finalized by:</b> {finalized_by}<br>\n        <b>Generated:</b> {report_date}<br>\n        <i>This report is AI-assisted and does not replace the judgment of a licensed eye care professional. All findings must be reviewed and confirmed by a qualified healthcare professional before any clinical action is taken.</i>\n    </div>\n</div>\n\n</td></tr>\n</table>\n\n</body></html>"""
        progress = QProgressDialog('Rendering images...', '', 0, 4, self)
        progress.setWindowTitle('Generating Report')
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setHtml(html)
        progress.setValue(1)
        progress.setLabelText('Composing layout...')
        QApplication.processEvents()
        progress.setValue(2)
        progress.setLabelText('Writing PDF...')
        QApplication.processEvents()
        try:
            writer = QPdfWriter(path)
            writer.setResolution(150)
            try:
                writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            except Exception:
                pass
            try:
                writer.setPageMargins(QMarginsF(14, 8, 14, 14), QPageLayout.Unit.Millimeter)
            except Exception:
                pass
            doc.print_(writer)
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise OSError('Output PDF was not written correctly.')
        except OSError as err:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            progress.close()
            write_activity('ERROR', 'REPORT_FAILED', str(err))
            QMessageBox.critical(self, 'Generate Report', f'Disk full - PDF generation stopped. Free up space and try again.\n\n{err}')
            return
        progress.setValue(4)
        progress.setLabelText('Done')
        progress.close()
        write_activity('INFO', 'REPORT_GENERATED', f'path={path}')
        done_box = QMessageBox(self)
        done_box.setWindowTitle('Report Saved')
        done_box.setIcon(QMessageBox.Icon.Information)
        done_box.setText(f'Screening report saved to:\n{path}')
        open_pdf_btn = done_box.addButton('Open PDF', QMessageBox.ButtonRole.ActionRole)
        open_folder_btn = done_box.addButton('Open Folder', QMessageBox.ButtonRole.ActionRole)
        done_box.addButton('Close', QMessageBox.ButtonRole.RejectRole)
        done_box.exec()
        if done_box.clickedButton() == open_pdf_btn:
            try:
                os.startfile(path)
            except Exception:
                pass
        elif done_box.clickedButton() == open_folder_btn:
            try:
                os.startfile(os.path.dirname(path))
            except Exception:
                pass