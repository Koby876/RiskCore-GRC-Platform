"""
ui/ai_workspace.py
───────────────────
RiskCore AI Risk Analysis Workspace — Phase 2 migration.

Matches Images 8 and 9 precisely:
  - Page header with Analysis History + New Analysis buttons
  - KPI strip (shown post-analysis): Analysis Complete, Risks Identified,
    High/Critical, Frameworks Analyzed, Overall Risk Score
  - Workflow stepper: Configure → Upload → Analyse → Review → Approve
  - Three-column layout:
      Left  : API Configuration + Analysis Settings + Organisation Scope
      Centre: Upload Document panel + Analysis Progress stepper
      Right : Analysis Summary (risk distribution + framework coverage)
  - Post-analysis: Executive Summary + per-risk finding cards with
    evidence, confidence, framework mappings, NIST 800-53 recommendations
  - One-click actions: Approve All / Review Individually / Generate PDF /
    Export Register

All backend calls run on QThreads — the UI never blocks.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QCheckBox,
    QProgressBar, QSizePolicy, QFileDialog, QMessageBox,
    QGridLayout, QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from widgets.cards import (
    Card, KpiCard, SeverityBadge, Divider, FwCoverageRow,
)
from core.database.db import (
    load_api_key, save_api_key,
    get_organisation_scope, save_organisation_scope,
    get_risks, insert_risk, audit, today,
    NIST_FUNCTIONS, NIST_COLORS,
    ASSESSMENT_TYPES, ORG_SIZES, ASSET_TYPES, SCOPE_FRAMEWORKS,
)
from core.services.ai_service import (
    build_framework_coverage_report,
    build_executive_summary,
    format_evidence,
    format_confidence,
)
from core.services.analysis_worker import AnalysisWorker, ApproveWorker


# ── Helpers ───────────────────────────────────────────────────────────────────

def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"background-color: {Colors.BG_CARD};"
        f"border-radius: {Radius.LG}px;"
        f"border: 1px solid {Colors.BG_BORDER};")
    return f


def _card_title(text: str, color: str = Colors.TEXT_PRIMARY) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(Fonts.heading_3())
    lbl.setStyleSheet(f"color: {color}; border: none;")
    return lbl


def _label(text: str, font=None,
           color: str = Colors.TEXT_MUTED) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(font or Fonts.label_sm())
    lbl.setStyleSheet(f"color: {color}; border: none;")
    return lbl


def _btn(text: str, color: str = Colors.BG_BORDER,
         text_color: str = Colors.TEXT_MUTED,
         height: int = 34) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(height)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    b.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: {text_color};
            border: none;
            border-radius: {Radius.SM}px;
            padding: 0 14px;
            font-size: 11pt;
        }}
        QPushButton:hover {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
        }}
        QPushButton:disabled {{
            background-color: {Colors.BG_BORDER};
            color: {Colors.TEXT_DIM};
        }}
    """)
    return b


# ── AI Workspace Page ─────────────────────────────────────────────────────────

class AIWorkspacePage(QWidget):
    """
    Full AI Analysis Workspace (Phase 2).

    Signals
    -------
    navigate(str)                   : request page navigation
    analysis_complete(list, dict)   : risks + full analysis result
    """
    navigate          = Signal(str)
    analysis_complete = Signal(object, object)  # list, dict — cross-thread safe

    STEPS = [
        ("Configure",  "Set up analysis"),
        ("Upload",     "Select document"),
        ("Analyse",    "AI processing"),
        ("Review",     "Review findings"),
        ("Approve",    "Save to register"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._api_key       = load_api_key()
        self._pdf_path      = ""
        self._pending_risks : list = []
        self._last_analysis : dict = {}
        self._risk_checks   : dict = {}   # idx -> QCheckBox
        self._current_step  = 0

        self._setup_ui()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Page header
        root.addWidget(self._build_header())

        # KPI strip — hidden until analysis completes
        self._kpi_strip = self._build_kpi_strip()
        self._kpi_strip.setVisible(False)
        root.addWidget(self._kpi_strip)

        # Workflow stepper
        root.addWidget(self._build_stepper())

        # Main scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._body = QWidget()
        self._body.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(
            Spacing.XL, Spacing.MD, Spacing.XL, Spacing.XL)
        self._body_layout.setSpacing(Spacing.MD)
        scroll.setWidget(self._body)
        root.addWidget(scroll, 1)

        self._build_pre_analysis_body()

    def _clear_body(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── Page header ───────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, Spacing.LG, Spacing.XL, Spacing.SM)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("◎  AI Risk Analysis")
        title.setFont(Fonts.heading_1())
        title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(title)
        sub = QLabel(
            "Upload a document and let AI analyze risks "
            "across 5 frameworks.")
        sub.setFont(Fonts.label())
        sub.setStyleSheet(
            f"color: {Colors.TEXT_MUTED};")
        col.addWidget(sub)
        hl.addLayout(col)
        hl.addStretch()

        hist_btn = _btn("⊙  Analysis History",
                        Colors.BG_BORDER, Colors.TEXT_MUTED)
        hist_btn.clicked.connect(
            lambda: self.navigate.emit("audit"))
        hl.addWidget(hist_btn)

        self._new_btn = _btn(
            "＋  New Analysis", Colors.PURPLE_LT, "white")
        self._new_btn.clicked.connect(self._reset_analysis)
        hl.addWidget(self._new_btn)
        return w

    # ── KPI strip (shown post-analysis) ──────────────────────────────────────

    def _build_kpi_strip(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, 0, Spacing.XL, Spacing.SM)
        hl.setSpacing(Spacing.SM)

        self._kpi_labels = {}
        specs = [
            ("complete",  "◉", "—",       "Analysis Complete",   Colors.ACCENT_TEAL),
            ("risks",     "⊘", "—",        "Risks Identified",    Colors.TEXT_PRIMARY),
            ("high_crit", "▲", "—",        "High / Critical",     Colors.HIGH),
            ("fw",        "✓", "5 / 5",    "Frameworks Analyzed", Colors.SUCCESS_LT),
            ("score",     "⊗", "— / 25",   "Overall Risk Score",  Colors.TEXT_PRIMARY),
        ]
        for key, icon, val, lbl, color in specs:
            card = _card()
            vl = QVBoxLayout(card)
            vl.setContentsMargins(
                Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            vl.setSpacing(2)

            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont(Fonts.FAMILY, 16))
            icon_lbl.setStyleSheet(
                f"color: {color}; border: none;")
            vl.addWidget(icon_lbl)

            val_lbl = QLabel(val)
            val_lbl.setFont(Fonts.kpi_value_sm())
            val_lbl.setStyleSheet(
                f"color: {color}; border: none;")
            vl.addWidget(val_lbl)

            sub_lbl = QLabel(lbl)
            sub_lbl.setFont(Fonts.label_sm())
            sub_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            vl.addWidget(sub_lbl)

            self._kpi_labels[key] = (val_lbl, color)
            hl.addWidget(card)
        return w

    def _update_kpi_strip(self) -> None:
        risks = self._pending_risks
        n     = len(risks)
        if n == 0:
            return

        def sc(r):
            return int(r.get("inherent_score",
                r.get("likelihood", 1) * r.get("impact", 1)) or 0)

        crit = sum(1 for r in risks if sc(r) >= 15)
        high = sum(1 for r in risks if 10 <= sc(r) <= 14)
        avg  = round(sum(sc(r) for r in risks) / n, 1) if n else 0
        avg_color = Colors.severity_color(int(avg))

        self._kpi_labels["complete"][0].setText(today())
        self._kpi_labels["risks"][0].setText(str(n))
        self._kpi_labels["high_crit"][0].setText(
            str(crit + high))
        h_color = (Colors.HIGH if (crit + high) else Colors.TEXT_MUTED)
        self._kpi_labels["high_crit"][0].setStyleSheet(
            f"color: {h_color}; border: none;")
        self._kpi_labels["score"][0].setText(f"{avg} / 25")
        self._kpi_labels["score"][0].setStyleSheet(
            f"color: {avg_color}; border: none;")
        self._kpi_strip.setVisible(True)

    # ── Workflow stepper ──────────────────────────────────────────────────────

    def _build_stepper(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        w.setFixedHeight(52)
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, 0, Spacing.XL, 0)
        hl.setSpacing(0)

        self._step_labels = []
        for i, (name, sub) in enumerate(self.STEPS):
            step_w = QWidget()
            step_l = QHBoxLayout(step_w)
            step_l.setContentsMargins(0, 0, 0, 0)
            step_l.setSpacing(Spacing.SM)

            num = QLabel(str(i + 1))
            num.setFixedSize(26, 26)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setFont(QFont(Fonts.FAMILY, 9, QFont.Weight.Bold))
            num.setStyleSheet(f"""
                QLabel {{
                    background-color: {Colors.BG_BORDER};
                    color: {Colors.TEXT_MUTED};
                    border-radius: 13px;
                    border: none;
                }}
            """)

            text_col = QVBoxLayout()
            text_col.setSpacing(0)
            name_lbl = QLabel(name)
            name_lbl.setFont(QFont(Fonts.FAMILY, 9, QFont.Weight.Bold))
            name_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            sub_lbl = QLabel(sub)
            sub_lbl.setFont(QFont(Fonts.FAMILY, 7))
            sub_lbl.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none;")
            text_col.addWidget(name_lbl)
            text_col.addWidget(sub_lbl)

            step_l.addWidget(num)
            step_l.addLayout(text_col)
            hl.addWidget(step_w)
            self._step_labels.append((num, name_lbl))

            if i < len(self.STEPS) - 1:
                arr = QLabel("→")
                arr.setFont(QFont(Fonts.FAMILY, 10))
                arr.setStyleSheet(
                    f"color: {Colors.TEXT_DIM}; border: none;")
                hl.addWidget(arr)

        # Underline bar
        bar_w = QWidget()
        bar_w.setFixedHeight(3)
        self._step_bar = QProgressBar(bar_w)
        self._step_bar.setRange(0, len(self.STEPS) - 1)
        self._step_bar.setValue(0)
        self._step_bar.setTextVisible(False)
        self._step_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG_BORDER};
                border: none; border-radius: 0;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.PURPLE_LT};
            }}
        """)

        container = QVBoxLayout()
        container.setSpacing(0)
        container.addWidget(w)
        container.addWidget(bar_w)

        outer = QWidget()
        outer.setLayout(container)
        return outer

    def _set_step(self, step: int) -> None:
        self._current_step = step
        self._step_bar.setValue(step)
        for i, (num, name) in enumerate(self._step_labels):
            done    = i < step
            current = i == step
            if done:
                num.setText("✓")
                num.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Colors.SUCCESS};
                        color: white;
                        border-radius: 13px; border: none;
                    }}
                """)
                name.setStyleSheet(
                    f"color: {Colors.TEXT_PRIMARY}; border: none;")
            elif current:
                num.setText(str(i + 1))
                num.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Colors.PURPLE_LT};
                        color: white;
                        border-radius: 13px; border: none;
                    }}
                """)
                name.setStyleSheet(
                    f"color: {Colors.TEXT_PRIMARY}; "
                    f"font-weight: bold; border: none;")
            else:
                num.setText(str(i + 1))
                num.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Colors.BG_BORDER};
                        color: {Colors.TEXT_MUTED};
                        border-radius: 13px; border: none;
                    }}
                """)
                name.setStyleSheet(
                    f"color: {Colors.TEXT_MUTED}; border: none;")

    # ── Pre-analysis body (Configure + Upload + Summary) ─────────────────────

    def _build_pre_analysis_body(self) -> None:
        self._set_step(0)
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.MD)

        hl.addWidget(self._build_config_panel(), 2)
        hl.addWidget(self._build_upload_panel(), 3)
        hl.addWidget(self._build_summary_panel(), 2)

        self._body_layout.addWidget(row)
        self._body_layout.addStretch()

    # ── Left: API Config + Analysis Settings + Org Scope ─────────────────────

    def _build_config_panel(self) -> QWidget:
        panel = QWidget()
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        # API Configuration
        api_card = _card()
        al = QVBoxLayout(api_card)
        al.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        al.setSpacing(Spacing.SM)

        al.addWidget(_card_title("◈  API Configuration",
                                  Colors.PURPLE_LT))
        al.addWidget(_label(
            "Get your key at console.anthropic.com → API Keys\n"
            "(starts with sk-ant-api03-)"))

        key_row = QHBoxLayout()
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("sk-ant-api03-...")
        self._key_input.setText(self._api_key)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BG_BORDER};
                border-radius: {Radius.SM}px;
                padding: 6px 10px;
                font-size: 10pt;
            }}
        """)
        key_row.addWidget(self._key_input, 1)
        save_key_btn = _btn("Save Key", Colors.PURPLE_LT, "white", 30)
        save_key_btn.clicked.connect(self._save_key)
        key_row.addWidget(save_key_btn)
        al.addLayout(key_row)

        self._key_status = _label(
            "✅ Key loaded" if self._api_key
            else "⚠ No key — enter above",
            color=Colors.SUCCESS_LT if self._api_key else Colors.MEDIUM)
        al.addWidget(self._key_status)
        vl.addWidget(api_card)

        # Analysis Settings
        set_card = _card()
        sl = QVBoxLayout(set_card)
        sl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        sl.setSpacing(Spacing.SM)
        sl.addWidget(_card_title("⚙  Analysis Settings"))

        self._toggles: dict[str, QCheckBox] = {}
        for label, key, default in [
            ("Enable Risk Extraction",     "extract",    True),
            ("Enable Control Mapping",     "mapping",    True),
            ("Enable MITRE ATT&CK Mapping","mitre",      True),
            ("Enable Treatment Suggestions","treatments", True),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(default)
            cb.setFont(Fonts.label_sm())
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {Colors.TEXT_MUTED};
                    border: none; spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: 16px; height: 16px;
                    border-radius: 3px;
                    border: 1px solid {Colors.BG_BORDER};
                    background: {Colors.BG_CARD2};
                }}
                QCheckBox::indicator:checked {{
                    background: {Colors.ACCENT_BLUE};
                    border: 1px solid {Colors.ACCENT_BLUE};
                }}
            """)
            self._toggles[key] = cb
            sl.addWidget(cb)
        vl.addWidget(set_card)

        # Organisation Scope (compact — full edit in Settings)
        scope = get_organisation_scope()
        if scope:
            sc_card = _card()
            scl = QVBoxLayout(sc_card)
            scl.setContentsMargins(
                Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            scl.setSpacing(4)
            scl.addWidget(
                _card_title("⊙  Organisation Scope"))
            for k, label in [
                ("organisation_name", "Organisation"),
                ("industry",          "Industry"),
                ("assessment_name",   "Assessment"),
            ]:
                val = scope.get(k, "—") or "—"
                row_w = QHBoxLayout()
                row_w.addWidget(_label(label + ":"))
                row_w.addWidget(
                    _label(str(val)[:30], color=Colors.TEXT_PRIMARY))
                row_w.addStretch()
                scl.addLayout(row_w)
            vl.addWidget(sc_card)

        vl.addStretch()
        return panel

    # ── Centre: Upload + Progress ─────────────────────────────────────────────

    def _build_upload_panel(self) -> QWidget:
        card = _card()
        vl = QVBoxLayout(card)
        vl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.MD)

        vl.addWidget(_card_title("⬆  Upload Document"))
        vl.addWidget(_label(
            "Supported: PDF  ·  Security policies, audit reports,\n"
            "incident reports, vendor assessments"))

        # Drop zone
        drop_f = QFrame()
        drop_f.setFixedHeight(140)
        drop_f.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_CARD2};
                border: 2px dashed {Colors.BG_BORDER};
                border-radius: {Radius.MD}px;
            }}
        """)
        drop_vl = QVBoxLayout(drop_f)
        drop_vl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cloud = QLabel("⬆")
        cloud.setFont(QFont(Fonts.FAMILY, 32))
        cloud.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; border: none;")
        cloud.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_vl.addWidget(cloud)

        drop_hint = QLabel("Drag & drop your PDF here\nor")
        drop_hint.setFont(Fonts.label_sm())
        drop_hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_vl.addWidget(drop_hint)

        browse_btn = _btn(
            "Browse PDF", Colors.ACCENT_BLUE, "white", 32)
        browse_btn.setFixedWidth(120)
        browse_btn.clicked.connect(self._browse_pdf)
        drop_vl.addWidget(
            browse_btn,
            alignment=Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(drop_f)

        # File display row (hidden until file selected)
        self._file_row = QWidget()
        file_hl = QHBoxLayout(self._file_row)
        file_hl.setContentsMargins(0, 0, 0, 0)
        file_hl.setSpacing(Spacing.SM)
        self._file_icon  = QLabel("📄")
        self._file_name  = _label("", color=Colors.TEXT_PRIMARY)
        self._file_size  = _label("", color=Colors.TEXT_MUTED)
        file_ok          = QLabel("✓")
        file_ok.setFont(Fonts.label())
        file_ok.setStyleSheet(
            f"color: {Colors.SUCCESS_LT}; border: none;")
        file_hl.addWidget(self._file_icon)
        file_hl.addWidget(self._file_name, 1)
        file_hl.addWidget(self._file_size)
        file_hl.addWidget(file_ok)
        self._file_row.setVisible(False)
        vl.addWidget(self._file_row)

        # Classification (Image 9 shows this on the upload panel)
        clf_row = QHBoxLayout()
        clf_row.addWidget(_label("Report Classification"))
        self._clf_combo = QComboBox()
        self._clf_combo.addItems(
            ["CONFIDENTIAL", "RESTRICTED", "INTERNAL", "PUBLIC"])
        self._clf_combo.setFixedWidth(160)
        clf_row.addWidget(self._clf_combo)
        clf_row.addStretch()
        vl.addLayout(clf_row)

        vl.addWidget(Divider())

        # Progress section
        prog_title = _card_title("Analysis Progress")
        vl.addWidget(prog_title)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG_BORDER};
                border-radius: 3px; border: none;
            }}
            QProgressBar::chunk {{
                background-color: {Colors.PURPLE_LT};
                border-radius: 3px;
            }}
        """)
        vl.addWidget(self._progress_bar)

        # Step checklist
        steps = [
            "Extracting text from document",
            "Identifying risks and issues",
            "Mapping to frameworks",
            "Scoring risks (NIST SP 800-30)",
            "Generating recommendations",
            "Compiling results",
        ]
        self._progress_step_labels: dict[str, QLabel] = {}
        for step in steps:
            sr = QHBoxLayout()
            check = QLabel("○")
            check.setFont(Fonts.label_sm())
            check.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none;")
            check.setFixedWidth(16)
            sl2 = _label(step)
            status_lbl = _label("")
            status_lbl.setFixedWidth(80)
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            sr.addWidget(check)
            sr.addWidget(sl2, 1)
            sr.addWidget(status_lbl)
            vl.addLayout(sr)
            self._progress_step_labels[step] = (check, status_lbl)

        # Completion time
        self._completion_lbl = _label("")
        vl.addWidget(self._completion_lbl)
        vl.addWidget(Divider())

        # Analyse button
        self._analyse_btn = QPushButton("◎  Analyse Document with AI")
        self._analyse_btn.setFixedHeight(42)
        self._analyse_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        self._analyse_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.PURPLE_LT};
                color: white;
                border: none;
                border-radius: {Radius.MD}px;
                font-size: 13pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.PURPLE};
            }}
            QPushButton:disabled {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_DIM};
            }}
        """)
        self._analyse_btn.clicked.connect(self._start_analysis)
        vl.addWidget(self._analyse_btn)

        self._status_lbl = _label("Ready — enter API key and select a PDF")
        self._status_lbl.setWordWrap(True)
        vl.addWidget(self._status_lbl)
        vl.addStretch()
        return card

    # ── Right: Analysis Summary ───────────────────────────────────────────────

    def _build_summary_panel(self) -> QWidget:
        panel = QWidget()
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        # Risk Level Distribution
        dist_card = _card()
        dl = QVBoxLayout(dist_card)
        dl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        dl.setSpacing(Spacing.SM)
        dl.addWidget(_card_title("Risk Level Distribution"))

        self._dist_rows: dict[str, QLabel] = {}
        self._dist_bars: dict[str, QProgressBar] = {}
        for label, color in [
            ("Critical (15–25)", Colors.CRITICAL),
            ("High (10–14)",     Colors.HIGH),
            ("Medium (5–9)",     Colors.MEDIUM),
            ("Low (1–4)",        Colors.LOW),
        ]:
            dr = QHBoxLayout()
            dot = QFrame()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"background-color: {color}; "
                f"border-radius: 5px; border: none;")
            dr.addWidget(dot)
            lbl_w = _label(label)
            lbl_w.setFixedWidth(100)
            dr.addWidget(lbl_w)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {Colors.BG_BORDER};
                    border: none; border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 3px;
                }}
            """)
            dr.addWidget(bar, 1)
            cnt_lbl = _label("0")
            cnt_lbl.setFixedWidth(30)
            cnt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            dr.addWidget(cnt_lbl)
            dl.addLayout(dr)
            self._dist_bars[label] = bar
            self._dist_rows[label] = cnt_lbl

        vl.addWidget(dist_card)

        # Framework Coverage
        fw_card = _card()
        fl = QVBoxLayout(fw_card)
        fl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        fl.setSpacing(Spacing.SM)
        fl.addWidget(_card_title("Framework Coverage"))

        self._fw_rows: dict[str, QLabel] = {}
        self._fw_bars: dict[str, QProgressBar] = {}
        for fw, color in [
            ("NIST CSF 2.0",       Colors.FW_NIST),
            ("ISO/IEC 27001:2022", Colors.FW_ISO),
            ("MITRE ATT&CK",       Colors.FW_MITRE),
            ("CIS Controls v8",    Colors.FW_CIS),
            ("CIA Triad",          Colors.FW_CIA),
        ]:
            fr2 = QHBoxLayout()
            short = {
                "NIST CSF 2.0":       "NIST CSF 2.0",
                "ISO/IEC 27001:2022": "ISO 27001",
                "MITRE ATT&CK":       "MITRE",
                "CIS Controls v8":    "CIS v8",
                "CIA Triad":          "CIA Triad",
            }.get(fw, fw[:12])
            fw_lbl = _label(short, color=color)
            fw_lbl.setFont(Fonts.label_sm_bold())
            fw_lbl.setFixedWidth(74)
            fr2.addWidget(fw_lbl)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {Colors.BG_BORDER};
                    border: none; border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 3px;
                }}
            """)
            fr2.addWidget(bar, 1)
            pct_lbl = _label("0%", color=color)
            pct_lbl.setFont(Fonts.label_sm_bold())
            pct_lbl.setFixedWidth(34)
            pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            fr2.addWidget(pct_lbl)
            fl.addLayout(fr2)
            self._fw_bars[fw] = bar
            self._fw_rows[fw] = pct_lbl

        vl.addWidget(fw_card)
        vl.addStretch()
        return panel

    # ── Browse + Key actions ──────────────────────────────────────────────────

    def _browse_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF Document", "",
            "PDF Files (*.pdf);;All Files (*.*)")
        if not path:
            return
        p = Path(path)
        size_mb = round(p.stat().st_size / (1024 * 1024), 1)
        # Reject files over 20 MB before any processing
        MAX_MB = 20
        if size_mb > MAX_MB:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "File Too Large",
                f"Selected PDF is {size_mb} MB.\n\n"
                f"The maximum supported size is {MAX_MB} MB.\n\n"
                "Large files may exceed the AI model's context window and "
                "produce incomplete results. Consider splitting the document "
                "into smaller sections before uploading.")
            return
        self._pdf_path = path
        self._file_name.setText(p.name)
        self._file_size.setText(f"{size_mb} MB")
        self._file_row.setVisible(True)
        self._status_lbl.setText(
            f"Ready to analyse: {p.name}")
        self._status_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        self._set_step(1)

    def _save_key(self) -> None:
        k = self._key_input.text().strip()
        if not k.startswith("sk-ant"):
            self._key_status.setText(
                "⚠ Key must start with sk-ant-api03-")
            self._key_status.setStyleSheet(
                f"color: {Colors.CRITICAL}; border: none;")
            return
        self._api_key = k
        save_api_key(k)
        self._key_status.setText("✅ Key saved and encrypted")
        self._key_status.setStyleSheet(
            f"color: {Colors.SUCCESS_LT}; border: none;")

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _start_analysis(self) -> None:
        if not self._api_key:
            QMessageBox.critical(
                self, "API Key Required",
                "Please enter and save your Anthropic API key.\n"
                "Get it at: console.anthropic.com → API Keys")
            return
        if not self._pdf_path or not Path(self._pdf_path).exists():
            QMessageBox.critical(
                self, "No File",
                "Please select a PDF file to analyse.")
            return

        scope = get_organisation_scope()
        company = (scope.get("organisation_name", "the organisation")
                   if scope else "the organisation")

        # Reset progress
        for key_s, (check, status) in \
                self._progress_step_labels.items():
            check.setText("○")
            check.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none;")
            status.setText("")
        self._progress_bar.setValue(0)
        self._completion_lbl.setText("")
        self._analyse_btn.setEnabled(False)
        self._analyse_btn.setText("⏳  Analysing...")
        self._status_lbl.setText(
            "Analysis started — this takes 20–40 seconds...")
        self._status_lbl.setStyleSheet(
            f"color: {Colors.MEDIUM}; border: none;")
        self._set_step(2)

        # Background worker
        self._a_thread = QThread()
        self._a_worker = AnalysisWorker(
            self._pdf_path, self._api_key, company, scope)
        self._a_worker.moveToThread(self._a_thread)
        self._a_thread.started.connect(self._a_worker.run)
        self._a_worker.progress.connect(self._on_progress)
        self._a_worker.finished.connect(self._on_finished)
        self._a_worker.error.connect(self._on_error)
        self._a_worker.finished.connect(self._a_thread.quit)
        self._a_thread.start()

    def _on_progress(self, msg: str, pct: float) -> None:
        self._progress_bar.setValue(int(pct * 100))
        self._status_lbl.setText(msg)
        # Tick off step
        for key_s, (check, status) in \
                self._progress_step_labels.items():
            if key_s.lower() in msg.lower():
                check.setText("✓")
                check.setStyleSheet(
                    f"color: {Colors.SUCCESS_LT}; border: none;")
                status.setText("Completed")
                status.setStyleSheet(
                    f"color: {Colors.SUCCESS_LT}; border: none;")

    def _on_finished(self, result: dict) -> None:
        self._last_analysis = result
        self._pending_risks = result.get("risks", [])
        self._progress_bar.setValue(100)
        # Tick all steps complete
        for _, (check, status) in \
                self._progress_step_labels.items():
            check.setText("✓")
            check.setStyleSheet(
                f"color: {Colors.SUCCESS_LT}; border: none;")
            status.setText("Completed")
            status.setStyleSheet(
                f"color: {Colors.SUCCESS_LT}; border: none;")
        import datetime
        self._completion_lbl.setText(
            f"⊙  Completed at {datetime.datetime.now().strftime('%H:%M')}")
        self._completion_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")

        n = len(self._pending_risks)
        self._analyse_btn.setEnabled(True)
        self._analyse_btn.setText("◎  Analyse Another Document")
        self._status_lbl.setText(
            f"✅  Analysis complete — {n} risks found")
        self._status_lbl.setStyleSheet(
            f"color: {Colors.SUCCESS_LT}; border: none;")

        # Update right panel
        self._update_summary_panel()
        self._update_kpi_strip()
        self._set_step(3)

        # Emit so main window can cache the exec summary
        self.analysis_complete.emit(
            self._pending_risks, result)

        # Show results
        self._clear_body()
        self._build_results_body()

    def _on_error(self, msg: str) -> None:
        self._analyse_btn.setEnabled(True)
        self._analyse_btn.setText("◎  Analyse Document with AI")
        self._status_lbl.setText(f"⚠  Error: {msg}")
        self._status_lbl.setStyleSheet(
            f"color: {Colors.CRITICAL}; border: none;")
        self._progress_bar.setValue(0)
        self._set_step(1)

    def _update_summary_panel(self) -> None:
        risks = self._pending_risks
        n     = max(len(risks), 1)

        def sc(r):
            return int(r.get("inherent_score",
                r.get("likelihood", 1) * r.get("impact", 1)) or 0)

        counts = {
            "Critical (15–25)": sum(1 for r in risks if sc(r) >= 15),
            "High (10–14)":     sum(1 for r in risks if 10 <= sc(r) <= 14),
            "Medium (5–9)":     sum(1 for r in risks if 5 <= sc(r) <= 9),
            "Low (1–4)":        sum(1 for r in risks if sc(r) <= 4),
        }
        for label, cnt in counts.items():
            pct = int(cnt / n * 100)
            self._dist_bars[label].setValue(pct)
            self._dist_rows[label].setText(str(cnt))

        risk_dicts = [dict(r) for r in risks]
        cov = build_framework_coverage_report(risk_dicts)
        for fw, data in cov["per_framework"].items():
            pct = data["coverage_pct"]
            if fw in self._fw_bars:
                self._fw_bars[fw].setValue(int(pct))
                self._fw_rows[fw].setText(f"{pct:.0f}%")

    # ── Post-analysis results body ────────────────────────────────────────────

    def _build_results_body(self) -> None:
        self._set_step(3)

        # Executive Summary (if present in result)
        es = self._last_analysis.get("_exec_summary")
        if es:
            self._body_layout.addWidget(
                self._build_exec_summary_card(es))

        # One-click action bar
        self._body_layout.addWidget(
            self._build_action_bar())

        # Per-risk finding cards
        title = _card_title(
            f"Findings — {len(self._pending_risks)} Risks Identified")
        self._body_layout.addWidget(title)

        self._risk_checks = {}
        for i, risk in enumerate(self._pending_risks):
            self._body_layout.addWidget(
                self._build_risk_card(i, risk))

        # Bottom approve bar
        self._body_layout.addWidget(
            self._build_approve_bar())
        self._body_layout.addStretch()

    def _build_exec_summary_card(self, es: dict) -> QFrame:
        card = _card()
        vl = QVBoxLayout(card)
        vl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        vl.addWidget(
            _card_title("◎  AI Executive Summary"))

        posture = es.get("posture", "Unknown")
        p_color = {
            "Critical": Colors.CRITICAL, "High": Colors.HIGH,
            "Medium": Colors.MEDIUM, "Low": Colors.LOW,
        }.get(posture, Colors.TEXT_MUTED)

        # Posture + summary
        sum_row = QHBoxLayout()
        p_f = QFrame()
        p_f.setStyleSheet(
            f"background-color: {Colors.severity_bg(15 if posture=='Critical' else 10 if posture=='High' else 6 if posture=='Medium' else 1)};"
            f"border-radius: {Radius.SM}px; border: none;")
        p_l = QHBoxLayout(p_f)
        p_l.setContentsMargins(Spacing.MD, Spacing.XS,
                                Spacing.MD, Spacing.XS)
        p_lbl = QLabel(f"Overall Risk Posture: {posture}")
        p_lbl.setFont(QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
        p_lbl.setStyleSheet(f"color: {p_color}; border: none;")
        p_l.addWidget(p_lbl)
        sum_row.addWidget(p_f)
        sum_row.addStretch()
        vl.addLayout(sum_row)

        summary = es.get("summary", "")
        if summary:
            s_lbl = QLabel(summary)
            s_lbl.setFont(Fonts.label())
            s_lbl.setStyleSheet(
                f"color: {Colors.SUCCESS_LT}; border: none;")
            s_lbl.setWordWrap(True)
            vl.addWidget(s_lbl)

        # Grid of key intel
        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(Spacing.SM)
        gl.setColumnStretch(0, 1)
        gl.setColumnStretch(1, 1)

        def _cell(r, c, label, value, color):
            f = QFrame()
            f.setStyleSheet(
                f"background-color: {Colors.BG_CARD2};"
                f"border-radius: {Radius.SM}px; border: none;")
            fl = QHBoxLayout(f)
            fl.setContentsMargins(
                Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            fl.setSpacing(Spacing.SM)
            l1 = _label(label)
            l1.setFixedWidth(130)
            fl.addWidget(l1)
            v1 = QLabel(str(value or "—")[:90])
            v1.setFont(Fonts.label_sm())
            v1.setStyleSheet(f"color: {color}; border: none;")
            v1.setWordWrap(True)
            fl.addWidget(v1, 1)
            gl.addWidget(f, r, c)

        _cell(0, 0, "Strongest Areas",
              es.get("strongest_areas"), Colors.SUCCESS_LT)
        _cell(0, 1, "Weakest Areas",
              es.get("weakest_areas"), Colors.CRITICAL)
        _cell(1, 0, "Notable Observations",
              es.get("notable_observations"), Colors.TEXT_PRIMARY)
        if es.get("immediate_priorities"):
            _cell(1, 1, "Immediate Priority",
                  es["immediate_priorities"][0], Colors.HIGH)
        vl.addWidget(grid)
        return card

    def _build_action_bar(self) -> QWidget:
        """One-click actions from Image 9 bottom bar."""
        w = QWidget()
        w.setStyleSheet(
            f"background-color: {Colors.PURPLE};"
            f"border-radius: {Radius.LG}px;")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, Spacing.MD, Spacing.XL, Spacing.MD)
        hl.setSpacing(Spacing.XL)

        title_col = QVBoxLayout()
        t1 = QLabel("✦  View Analysis Results")
        t1.setFont(QFont(Fonts.FAMILY, 13, QFont.Weight.Bold))
        t1.setStyleSheet("color: white; border: none;")
        t2 = QLabel("Review risks, mappings, and AI recommendations")
        t2.setFont(Fonts.label_sm())
        t2.setStyleSheet(
            f"color: {Colors.PURPLE_LT}; border: none;")
        title_col.addWidget(t1)
        title_col.addWidget(t2)
        hl.addLayout(title_col, 1)

        for label, color, cmd in [
            ("✅  Approve All", Colors.SUCCESS, self._approve_all),
            ("✏  Review Individually", Colors.ACCENT_BLUE, None),
            ("📄  Generate PDF", Colors.ACCENT_BLUE,
             lambda: self.navigate.emit("export")),
            ("↗  Export Register", Colors.BG_BORDER, None),
        ]:
            btn = _btn(label, color, "white", 36)
            if cmd:
                btn.clicked.connect(cmd)
            hl.addWidget(btn)
        return w

    def _build_risk_card(self, idx: int, risk: dict) -> QFrame:
        def sc(r):
            return int(r.get("inherent_score",
                r.get("likelihood", 1) * r.get("impact", 1)) or 0)

        score  = sc(risk)
        ev     = format_evidence(risk)
        conf   = format_confidence(risk)
        card   = _card()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")

        vl = QVBoxLayout(card)
        vl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        # Top row: checkbox + score + title + priority
        top = QHBoxLayout()
        cb = QCheckBox()
        cb.setChecked(True)
        cb.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 18px; height: 18px;
                border-radius: 3px;
                border: 1px solid {Colors.BG_BORDER};
                background: {Colors.BG_CARD2};
            }}
            QCheckBox::indicator:checked {{
                background: {Colors.ACCENT_BLUE};
                border: 1px solid {Colors.ACCENT_BLUE};
            }}
        """)
        top.addWidget(cb)
        self._risk_checks[idx] = cb

        badge = SeverityBadge(score)
        top.addWidget(badge)

        score_lbl = QLabel(str(score))
        score_lbl.setFont(
            QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        score_lbl.setStyleSheet(
            f"color: {Colors.severity_color(score)}; border: none;")
        score_lbl.setFixedWidth(32)
        top.addWidget(score_lbl)

        title_lbl = QLabel(str(risk.get("title", "")))
        title_lbl.setFont(
            QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        top.addWidget(title_lbl, 1)

        pri = risk.get("priority", "")
        if pri:
            pri_color = {
                "Immediate": Colors.CRITICAL,
                "Short-term": Colors.HIGH,
                "Medium-term": Colors.MEDIUM,
            }.get(pri, Colors.TEXT_MUTED)
            pri_lbl = _label(pri, color=pri_color)
            top.addWidget(pri_lbl)

        vl.addLayout(top)

        # Framework meta
        meta = "  ·  ".join(filter(None, [
            f"NIST: {risk.get('nist_function','')} "
            f"› {risk.get('nist_category','')}",
            f"ISO: {risk.get('iso_domain','')}",
            f"MITRE: {risk.get('mitre_tactic','N/A')}",
            f"CIS: {risk.get('cis_control','N/A')}",
            f"CIA: {risk.get('cia_component','')}",
        ]))
        meta_lbl = _label(meta)
        meta_lbl.setWordWrap(True)
        vl.addWidget(meta_lbl)

        # Description
        desc = str(risk.get("description") or "")
        if desc:
            d_lbl = QLabel(
                desc[:160] + ("…" if len(desc) > 160 else ""))
            d_lbl.setFont(Fonts.label_sm())
            d_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            d_lbl.setWordWrap(True)
            vl.addWidget(d_lbl)

        # Confidence row
        conf_row = QHBoxLayout()
        c_color = {
            "High": Colors.SUCCESS_LT,
            "Medium": Colors.MEDIUM,
            "Low": Colors.HIGH,
        }.get(conf["level"], Colors.TEXT_MUTED)
        conf_lbl = _label(
            f"Confidence: {conf['level']}",
            font=Fonts.label_sm_bold(), color=c_color)
        conf_row.addWidget(conf_lbl)
        reason_lbl = _label(
            conf.get("reasoning", "")[:80])
        conf_row.addWidget(reason_lbl, 1)
        vl.addLayout(conf_row)

        # Evidence block
        if ev.get("has_evidence"):
            ev_f = QFrame()
            ev_f.setStyleSheet(
                f"background-color: {Colors.BG_CARD2};"
                f"border-radius: {Radius.SM}px; border: none;")
            ev_l = QVBoxLayout(ev_f)
            ev_l.setContentsMargins(
                Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            ev_l.setSpacing(2)
            src = ev.get("source_section", "")
            ev_title = _label(
                f"Evidence{f'  ·  {src}' if src else ''}",
                font=Fonts.label_sm_bold(),
                color=Colors.ACCENT_TEAL)
            ev_l.addWidget(ev_title)
            ev_text = QLabel(
                f'"{ev["display_text"][:200]}'
                f'{"…" if len(ev["display_text"])>200 else ""}"')
            ev_text.setFont(Fonts.label_sm())
            ev_text.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            ev_text.setWordWrap(True)
            ev_l.addWidget(ev_text)
            if ev.get("reasoning"):
                r_lbl = _label(
                    f"Reasoning: {ev['reasoning'][:120]}")
                r_lbl.setWordWrap(True)
                ev_l.addWidget(r_lbl)
            vl.addWidget(ev_f)

        return card

    def _build_approve_bar(self) -> QWidget:
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.MD)

        approve_btn = QPushButton(
            "✅  Approve Selected & Add to Register")
        approve_btn.setFixedHeight(42)
        approve_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        approve_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.SUCCESS};
                color: white;
                border: none;
                border-radius: {Radius.MD}px;
                font-size: 12pt; font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.SUCCESS_LT};
            }}
        """)
        approve_btn.clicked.connect(self._approve_selected)
        hl.addWidget(approve_btn)

        discard_btn = _btn(
            "Discard All", "#3D1515", Colors.CRITICAL, 42)
        discard_btn.clicked.connect(self._discard_all)
        hl.addWidget(discard_btn)
        return w

    # ── Approve / Discard ─────────────────────────────────────────────────────

    def _approve_all(self) -> None:
        for cb in self._risk_checks.values():
            cb.setChecked(True)
        self._approve_selected()

    def _approve_selected(self) -> None:
        approved = [
            self._pending_risks[i]
            for i, cb in self._risk_checks.items()
            if cb.isChecked()
        ]
        if not approved:
            QMessageBox.information(
                self, "None Selected",
                "Select at least one risk to approve.")
            return

        pdf_name = Path(self._pdf_path).name if self._pdf_path else "unknown.pdf"
        self._a_thread = QThread()
        self._approve_worker = ApproveWorker(approved, pdf_name)
        self._approve_worker.moveToThread(self._a_thread)
        self._a_thread.started.connect(self._approve_worker.run)
        self._approve_worker.finished.connect(
            self._on_approved)
        self._approve_worker.error.connect(self._on_error)
        self._approve_worker.finished.connect(
            self._a_thread.quit)
        self._a_thread.start()

    def _on_approved(self, count: int) -> None:
        self._pending_risks = []
        self._risk_checks   = {}
        self._set_step(4)
        self.navigate.emit("register")

    def _discard_all(self) -> None:
        reply = QMessageBox.question(
            self, "Discard All",
            "Discard all AI suggestions?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._pending_risks = []
            self._risk_checks   = {}
            self._reset_analysis()

    def _reset_analysis(self) -> None:
        self._pending_risks = []
        self._risk_checks   = {}
        self._last_analysis = {}
        self._pdf_path      = ""
        self._kpi_strip.setVisible(False)
        self._clear_body()
        self._build_pre_analysis_body()
