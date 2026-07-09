"""
ui/risk_form.py
────────────────
Add Risk / Edit Risk Form — Phase 9 migration.

Matches Image 4 exactly:
  Page header: "+  Add Risk Manually" or "✏  Edit Risk"
               subtitle: "Framework-aligned  ·  NIST SP 800-30 scoring"
               top-right: [◧ Save Draft]  [✓ Save Risk]

  Section 1 — Core Details
    Title *, Description, Category, Owner *, Status,
    Date Identified, Review Date, Priority

  Section 2 — Risk Scoring — NIST SP 800-30
    Likelihood slider (1-5 with label)
    Impact slider    (1-5 with label)
    Residual Score (entry)
    Live "Inherent Score: N — LABEL" display card (right panel)

  Section 3 — NIST CSF Mapping
    NIST Function (dropdown, cascades category)
    NIST Category (dynamic, updates when function changes)
    NIST Subcategory (text)

  Section 4 — ISO 27001:2022 | CIA | MITRE ATT&CK | CIS
    ISO 27001 Domain, ISO Control Ref,
    CIA Component, MITRE Tactic, MITRE Technique, CIS Control

  Section 5 — Mitigation & Notes
    Existing Controls (textarea)
    Mitigation Plan  (textarea)
    Notes            (textarea)

  Submit bar: [➕ Add to Register] or [💾 Save Changes] + Cancel

Emits:
    saved(int)    — risk id after successful save
    cancelled()   — user clicked Cancel
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QTextEdit,
    QGridLayout, QSlider, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from widgets.components import Toast
from core.database.db import (
    get_risk, insert_risk, update_risk,
    validate_date, today, score_label, score_color,
    CATEGORIES, RISK_STATUS, NIST_FUNCTIONS, NIST_CATEGORIES,
    ISO_DOMAINS, CIA_COMPONENTS, MITRE_TACTICS, CIS_CONTROLS,
    LIKELIHOOD_LBL, IMPACT_LBL,
)
from core.database.lookups import CIS_CONTROL_DATA
import re as _re_cis


# ── CIS display helpers ───────────────────────────────────────────────────────
# Dropdown shows "CIS-5  ·  Account Management"; DB stores "CIS-5"
_CIS_DISPLAY = [
    f"{k}  ·  {v['title']}"
    for k, v in CIS_CONTROL_DATA.items() if k != "Not Applicable"
] + ["Not Applicable"]

def _cis_to_display(short_key: str) -> str:
    """'CIS-5' → 'CIS-5  ·  Account Management'"""
    if not short_key or short_key == "Not Applicable":
        return "Not Applicable"
    m = _re_cis.match(r"(CIS-\d+)", str(short_key))
    if m:
        info = CIS_CONTROL_DATA.get(m.group(1), {})
        t    = info.get("title", "")
        return f"{m.group(1)}  ·  {t}" if t else short_key
    # Already a full display string — return as-is
    return short_key

def _cis_to_key(display_val: str) -> str:
    """'CIS-5  ·  Account Management' → 'CIS-5'"""
    if not display_val or display_val == "Not Applicable":
        return "Not Applicable"
    m = _re_cis.match(r"(CIS-\d+)", str(display_val))
    return m.group(1) if m else display_val


# ── Internal helpers ──────────────────────────────────────────────────────────

def _lbl(text, font=None,
         color=Colors.TEXT_MUTED) -> QLabel:
    l = QLabel(str(text))
    l.setFont(font or Fonts.label_sm())
    l.setStyleSheet(f"color: {color}; border: none;")
    return l


def _entry(text="", placeholder="") -> QLineEdit:
    e = QLineEdit()
    e.setText(text)
    if placeholder:
        e.setPlaceholderText(placeholder)
    e.setFixedHeight(32)
    e.setStyleSheet(f"""
        QLineEdit {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px;
            padding: 0 10px; font-size: 10pt;
        }}
        QLineEdit:focus {{
            border: 1px solid {Colors.ACCENT_BLUE};
        }}
    """)
    return e


def _combo(items: list, current: str = "") -> QComboBox:
    c = QComboBox()
    c.addItems(items)
    if current:
        idx = c.findText(current)
        if idx >= 0:
            c.setCurrentIndex(idx)
        elif current:
            c.addItem(current)
            c.setCurrentText(current)
    c.setFixedHeight(32)
    c.setStyleSheet(f"""
        QComboBox {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px;
            padding: 2px 8px; font-size: 10pt;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_BLUE};
        }}
    """)
    return c


def _textarea(text="", height=68) -> QTextEdit:
    t = QTextEdit()
    t.setPlainText(text)
    t.setFixedHeight(height)
    t.setStyleSheet(f"""
        QTextEdit {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px;
            padding: 6px 10px; font-size: 10pt;
        }}
        QTextEdit:focus {{
            border: 1px solid {Colors.ACCENT_BLUE};
        }}
    """)
    return t


def _card(title: str, number: int) -> tuple[QFrame, QGridLayout]:
    """Return (card frame, grid layout) with numbered section header."""
    container = QWidget()
    cl = QVBoxLayout(container)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(4)

    sec_lbl = QLabel(f"{number}  {title}")
    sec_lbl.setFont(QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
    sec_lbl.setStyleSheet(
        f"color: {Colors.ACCENT_BLUE}; border: none;")
    cl.addWidget(sec_lbl)

    card = QFrame()
    card.setStyleSheet(
        f"background-color: {Colors.BG_CARD};"
        f"border-radius: {Radius.LG}px;"
        f"border: 1px solid {Colors.BG_BORDER};")
    gl = QGridLayout(card)
    gl.setContentsMargins(
        Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
    gl.setSpacing(Spacing.SM)
    gl.setColumnMinimumWidth(0, 170)
    gl.setColumnStretch(1, 1)
    cl.addWidget(card)
    return container, gl


# ── Score display card (Image 4 right panel) ──────────────────────────────────

class ScoreCard(QFrame):
    """
    Live inherent score display — the orange dotted card in Image 4.
    Shows "Inherent Score", large number, label (MEDIUM / HIGH etc.)
    Updates whenever likelihood or impact changes.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 195)
        self.setStyleSheet(
            f"background-color: {Colors.BG_CARD2};"
            f"border-radius: {Radius.LG}px;"
            f"border: 2px dotted {Colors.MEDIUM};")

        vl = QVBoxLayout(self)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(4)

        # Stretch above to push content to vertical centre
        vl.addStretch(1)

        self._title = _lbl("Inherent Score",
                            font=Fonts.label_sm(),
                            color=Colors.MEDIUM)
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(self._title)

        self._num = QLabel("9")
        self._num.setFont(QFont(Fonts.FAMILY, 44, QFont.Weight.Bold))
        self._num.setStyleSheet(f"color: {Colors.MEDIUM}; border: none;")
        self._num.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(self._num)

        self._label = QLabel("MEDIUM")
        self._label.setFont(QFont(Fonts.FAMILY, 13, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {Colors.MEDIUM}; border: none;")
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(self._label)

        vl.addSpacing(4)

        self._sub = _lbl("Inherent risk level  ·  before treatments",
                          color=Colors.TEXT_DIM)
        self._sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(self._sub)

        ref = _lbl("NIST SP 800-30", color=Colors.ACCENT_BLUE)
        ref.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(ref)

        # Stretch below to push content to vertical centre
        vl.addStretch(1)

    def update_score(self, likelihood: int, impact: int) -> None:
        sc    = likelihood * impact
        color = Colors.severity_color(sc)
        lbl   = Colors.severity_label(sc)
        self._num.setText(str(sc))
        self._num.setStyleSheet(
            f"color: {color}; border: none;")
        self._label.setText(lbl)
        self._label.setStyleSheet(
            f"color: {color}; border: none;")
        self._title.setStyleSheet(
            f"color: {color}; border: none;")
        self.setStyleSheet(
            f"background-color: {Colors.BG_CARD2};"
            f"border-radius: {Radius.LG}px;"
            f"border: 2px dotted {color};")


# ── Slider row (Image 4 scoring section) ─────────────────────────────────────

class SliderRow(QWidget):
    """
    Horizontal slider with live label.
    label_map: {1: "Rare", 2: "Unlikely", ...}
    value_changed(int) emitted on every move.
    """
    value_changed = Signal(int)

    def __init__(self, label: str, initial: int,
                 label_map: dict, parent=None):
        super().__init__(parent)
        self._label_map = label_map

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(4)

        # Question text
        q_lbl = _lbl(label, color=Colors.TEXT_MUTED)
        vl.addWidget(q_lbl)

        # Slider + value label
        row = QHBoxLayout()
        row.setSpacing(Spacing.SM)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(1, 5)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(1)
        self._slider.setValue(initial)
        self._slider.setTickPosition(
            QSlider.TickPosition.TicksBelow)
        self._slider.setTickInterval(1)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {Colors.BG_BORDER};
                height: 6px; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {Colors.ACCENT_BLUE};
                width: 18px; height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Colors.ACCENT_BLUE};
                border-radius: 3px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_change)
        row.addWidget(self._slider, 1)

        self._val_lbl = QLabel()
        self._val_lbl.setFont(
            QFont(Fonts.FAMILY, 10, QFont.Weight.Bold))
        self._val_lbl.setStyleSheet(
            f"color: {Colors.ACCENT_RED}; border: none;")
        self._val_lbl.setFixedWidth(150)
        row.addWidget(self._val_lbl)
        vl.addLayout(row)

        # Tick + label row
        # Use a custom QWidget that paints tick positions accurately.
        # We compute each label's x position as a fraction of the slider's
        # available width (total width minus handle diameter).
        # This is the only reliable way to align tick numbers with Qt slider.
        from PySide6.QtWidgets import QSizePolicy as _QSP
        from PySide6.QtCore import QRect as _QRect

        class _TickBar(QWidget):
            """Draws 5 evenly-spaced tick numbers matching QSlider positions."""
            def __init__(self, slider_ref, parent=None):
                super().__init__(parent)
                self._slider = slider_ref
                self.setFixedHeight(18)
                self.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Fixed)

            def paintEvent(self, event):
                from PySide6.QtGui import QPainter, QColor, QFont as _QF
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setFont(_QF(Fonts.FAMILY, 8))
                p.setPen(QColor(Colors.TEXT_DIM))
                handle_r = 9          # half of 18px handle
                avail    = self.width() - 2 * handle_r
                for i, label in enumerate(["1","2","3","4","5"]):
                    # fraction 0..1 of 5 positions
                    frac = i / 4
                    cx   = int(handle_r + frac * avail)
                    rect = _QRect(cx - 10, 0, 20, 16)
                    p.drawText(rect,
                               Qt.AlignmentFlag.AlignHCenter |
                               Qt.AlignmentFlag.AlignVCenter,
                               label)
                p.end()

        tick_row = QHBoxLayout()
        tick_row.setContentsMargins(0, 0, 0, 0)
        tick_row.setSpacing(0)
        tick_bar = _TickBar(self._slider)
        tick_row.addWidget(tick_bar, 1)
        tick_row.addSpacing(150 + Spacing.SM)
        vl.addLayout(tick_row)

        self._on_change(initial)

    def _on_change(self, v: int) -> None:
        self._val_lbl.setText(
            f"{v} — {self._label_map.get(v, '')}")
        self.value_changed.emit(v)

    def value(self) -> int:
        return self._slider.value()


# ── Risk Form Page ────────────────────────────────────────────────────────────

class RiskFormPage(QWidget):
    """
    Add / Edit Risk form page.

    Parameters
    ----------
    edit_id : int | None
        If set, pre-fills the form with the existing risk and
        saves as an update. If None, creates a new risk.

    Signals
    -------
    saved(int)   : risk id after save — main_window navigates to register
    cancelled()  : user clicked Cancel
    """
    saved     = Signal(int)
    cancelled = Signal()

    def __init__(self, edit_id: int | None = None,
                 parent=None):
        super().__init__(parent)
        self._edit_id  = edit_id
        r = get_risk(edit_id) if edit_id else None
        self._existing = dict(r) if r else None
        self._fields: dict = {}
        self._setup_ui()

    # ── Prefill helper ────────────────────────────────────────────────────────

    def _g(self, key: str, fallback="") -> str:
        if self._existing is None:
            return str(fallback)
        try:
            val = self._existing[key]
            return str(val) if val not in (None, "") else str(fallback)
        except Exception:
            return str(fallback)

    def _gi(self, key: str, fallback: int = 3) -> int:
        try:
            return max(1, min(5, int(float(
                self._g(key, str(fallback))))))
        except Exception:
            return fallback

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        is_edit = self._edit_id is not None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header(is_edit))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(
            Spacing.XL, Spacing.MD, Spacing.XL, Spacing.XL)
        self._body_layout.setSpacing(Spacing.MD)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self._build_section1()
        self._build_section2()
        self._build_section3()
        self._build_section4()
        self._build_section5()

        # Status label
        self._status_lbl = _lbl("", color=Colors.TEXT_MUTED)
        self._body_layout.addWidget(self._status_lbl)

        # Submit bar
        self._body_layout.addWidget(
            self._build_submit_bar(is_edit))
        self._body_layout.addStretch()

    def _build_header(self, is_edit: bool) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, Spacing.LG, Spacing.XL, Spacing.SM)

        col = QVBoxLayout()
        col.setSpacing(2)
        title_txt = ("✏  Edit Risk" if is_edit
                     else "+  Add Risk Manually")
        t = QLabel(title_txt)
        t.setFont(Fonts.heading_1())
        t.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(t)
        s = QLabel(
            "Framework-aligned  ·  NIST SP 800-30 scoring")
        s.setFont(Fonts.label())
        s.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        col.addWidget(s)
        hl.addLayout(col)
        hl.addStretch()

        # Save Draft button (grey)
        draft_btn = QPushButton("◧  Save Draft")
        draft_btn.setFixedHeight(34)
        draft_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        draft_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px;
                padding: 0 16px; font-size: 11pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        draft_btn.clicked.connect(self._save)
        hl.addWidget(draft_btn)

        # Save Risk button (blue)
        save_btn = QPushButton("✓  Save Risk")
        save_btn.setFixedHeight(34)
        save_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT_BLUE};
                color: white; border: none;
                border-radius: {Radius.SM}px;
                padding: 0 16px;
                font-size: 11pt; font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #1976D2;
            }}
        """)
        save_btn.clicked.connect(self._save)
        hl.addWidget(save_btn)
        return w

    # ── Section 1 — Core Details ──────────────────────────────────────────────

    def _build_section1(self) -> None:
        container, gl = _card("Core Details", 1)

        rows = [
            (0, "Title *",           "title",
             "entry",  "",  True,
             self._g("title"),  "Enter risk title"),
            (1, "Description",        "description",
             "text",   "",  False,
             self._g("description"), ""),
            (2, "Category",           "category",
             "combo",  CATEGORIES, False,
             self._g("category","Technical"), ""),
            (3, "Owner *",            "owner",
             "entry",  "",  True,
             self._g("owner"), "Risk owner role or name"),
            (4, "Status",             "status",
             "combo",  RISK_STATUS, False,
             self._g("status","Open"), ""),
            (5, "Date Identified",    "date_identified",
             "entry",  "",  False,
             self._g("date_identified", today()), "YYYY-MM-DD"),
            (6, "Review Date",        "review_date",
             "entry",  "",  False,
             self._g("review_date",""), "YYYY-MM-DD"),
            (7, "Priority",           "priority",
             "combo",
             ["Immediate","Short-term","Medium-term","Long-term"],
             False,
             self._g("priority","Short-term"), ""),
        ]
        _TOOLTIPS = {
            "title":          "Required. A concise, descriptive name for this risk.\n"
                              "Example: 'Multi-Factor Authentication Not Enforced for Privileged Accounts'\n"
                              "Minimum 3 characters. Avoid generic names like 'test' or 'risk 1'.",
            "description":    "Optional. Describe the risk in detail:\n"
                              "• What could go wrong?\n"
                              "• Why does it exist?\n"
                              "• What systems or data are affected?",
            "category":       "The category of risk this represents.\n"
                              "Technical: system/infrastructure risks\n"
                              "Operational: process or people risks\n"
                              "Compliance: regulatory or legal risks\n"
                              "Strategic: business direction risks\n"
                              "Financial: monetary exposure risks",
            "owner":          "Required. The person or role responsible for managing this risk.\n"
                              "Example: 'IT Security Manager', 'CISO', 'Head of Operations'\n"
                              "This person is accountable for treatment plans and reviews.",
            "status":         "The current status of this risk.\n"
                              "Open: identified, no active treatment\n"
                              "In Progress: treatment underway\n"
                              "Mitigated: controls applied, risk reduced\n"
                              "Accepted: risk accepted by management\n"
                              "Closed: risk no longer applicable",
            "date_identified": "The date this risk was first identified.\n"
                               "Format: YYYY-MM-DD (e.g. 2026-07-02)\n"
                               "Defaults to today if left blank.",
            "review_date":    "The date this risk should next be reviewed.\n"
                              "Format: YYYY-MM-DD (e.g. 2026-10-01)\n"
                              "Overdue risks appear highlighted on the Dashboard.",
            "priority":       "Treatment priority relative to other risks.\n"
                              "Immediate: treat within 72 hours\n"
                              "Short-term: treat within 30 days\n"
                              "Medium-term: treat within 90 days\n"
                              "Long-term: treat within 180+ days",
        }

        for row, label, key, wtype, opts, req, val, ph in rows:
            lbl_txt = label
            lbl_w = QLabel(lbl_txt)
            lbl_w.setFont(Fonts.label_sm())
            lbl_w.setStyleSheet(
                f"color: "
                f"{'white' if req else Colors.TEXT_MUTED};"
                f"border: none;")
            if key in _TOOLTIPS:
                lbl_w.setToolTip(_TOOLTIPS[key])
            gl.addWidget(lbl_w, row, 0,
                         Qt.AlignmentFlag.AlignTop)

            if wtype == "entry":
                w = _entry(val, ph)
            elif wtype == "text":
                w = _textarea(val)
            else:  # combo
                w = _combo(opts, val)

            if key in _TOOLTIPS:
                w.setToolTip(_TOOLTIPS[key])
            gl.addWidget(w, row, 1)
            self._fields[key] = w

        self._body_layout.addWidget(container)

    # ── Section 2 — Risk Scoring ──────────────────────────────────────────────

    def _build_section2(self) -> None:
        sec_lbl = QLabel("2  Risk Scoring — NIST SP 800-30")
        sec_lbl.setFont(
            QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
        sec_lbl.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE}; border: none;")
        self._body_layout.addWidget(sec_lbl)

        # Two-column layout: form left, score card right
        row_w = QWidget()
        row_w.setStyleSheet("border: none;")
        hl = QHBoxLayout(row_w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.MD)

        form_card = QFrame()
        form_card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        fl = QVBoxLayout(form_card)
        fl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        fl.setSpacing(Spacing.LG)

        self._lik_slider = SliderRow(
            "Likelihood (1–5) — How likely is this risk to occur?",
            self._gi("likelihood", 3),
            LIKELIHOOD_LBL)
        self._lik_slider.setToolTip(
            "Rate how likely this risk is to occur (NIST SP 800-30 Rev 1):\n\n"
            "1 — Rare:           Almost never happens in this sector\n"
            "2 — Unlikely:       Could happen but is uncommon\n"
            "3 — Possible:       Has happened in similar organisations\n"
            "4 — Likely:         Has happened here before, or is expected\n"
            "5 — Almost Certain: Is actively occurring or imminent\n\n"
            "Consider: threat actor capability, vulnerability exposure,\n"
            "active exploitation in the wild, and existing control strength.")
        fl.addWidget(self._lik_slider)

        self._imp_slider = SliderRow(
            "Impact (1–5) — What is the potential impact?",
            self._gi("impact", 3),
            IMPACT_LBL)
        self._imp_slider.setToolTip(
            "Rate the potential business impact if this risk materialises:\n\n"
            "1 — Negligible:  Minimal disruption, no financial loss\n"
            "2 — Minor:       Small financial loss or brief disruption\n"
            "3 — Moderate:    Noticeable impact, possible customer-facing issues\n"
            "4 — Major:       Significant financial or reputational damage\n"
            "5 — Critical:    Severe — regulatory breach, data loss, extended outage\n\n"
            "Consider: financial loss, regulatory fines, reputational damage,\n"
            "operational downtime, and customer impact.")
        fl.addWidget(self._imp_slider)

        # Residual score entry
        res_row = QHBoxLayout()
        _res_lbl = _lbl("Residual Score (Likelihood × Impact)")
        _res_lbl.setToolTip(
            "The remaining risk score AFTER treatment controls are applied.\n\n"
            "Range: 1 (minimal) to 25 (maximum)\n"
            "Formula: Residual Likelihood × Residual Impact\n\n"
            "Example: Inherent score 20 → after MFA deployed → Residual score 8\n\n"
            "Leave at the default if treatment is not yet planned.")
        res_row.addWidget(_res_lbl)
        self._residual_entry = _entry(
            self._g("residual_score",
                    str(max(1, self._gi("likelihood",3) *
                            self._gi("impact",3) - 3))),
            "Calculated risk score (1–25)")
        res_row.addWidget(self._residual_entry)
        fl.addLayout(res_row)
        hl.addWidget(form_card, 1)

        # Score card
        self._score_card = ScoreCard()
        self._score_card.update_score(
            self._gi("likelihood", 3),
            self._gi("impact", 3))
        hl.addWidget(self._score_card,
                     alignment=Qt.AlignmentFlag.AlignTop)

        # Wire sliders → score card
        self._lik_slider.value_changed.connect(
            self._on_score_change)
        self._imp_slider.value_changed.connect(
            self._on_score_change)

        self._body_layout.addWidget(row_w)
        self._fields["likelihood"] = self._lik_slider
        self._fields["impact"]     = self._imp_slider
        self._fields["residual_score"] = self._residual_entry

    def _on_score_change(self, _=None) -> None:
        lik = self._lik_slider.value()
        imp = self._imp_slider.value()
        self._score_card.update_score(lik, imp)

    # ── Section 3 — NIST CSF Mapping ─────────────────────────────────────────

    _NIST_TOOLTIP = (
        "Map this risk to its NIST CSF 2.0 function:\n\n"
        "GOVERN  — Policies, roles, risk management strategy\n"
        "IDENTIFY — Asset management, risk assessment\n"
        "PROTECT — Access control, training, data security\n"
        "DETECT  — Monitoring, anomaly detection\n"
        "RESPOND — Incident response, communications\n"
        "RECOVER — Recovery planning, improvements\n\n"
        "Selecting a function enables Category and Subcategory dropdowns."
    )

    _FW_TOOLTIPS = {
        "iso_domain":    ("ISO 27001:2022 Annex A Domain:\n"
                          "A.5 Organisational Controls (policies, roles, assets)\n"
                          "A.6 People Controls (screening, training, HR)\n"
                          "A.7 Physical Controls (facilities, equipment)\n"
                          "A.8 Technological Controls (access, crypto, patching)"),
        "iso_control":   ("ISO 27001:2022 control reference.\n"
                          "Example: A.8.3 (Information Access Restriction)\n"
                          "Leave blank if unknown — the domain is sufficient."),
        "cia_component": ("Which CIA Triad component does this risk primarily affect?\n"
                          "Confidentiality — unauthorised access to information\n"
                          "Integrity — unauthorised modification of data\n"
                          "Availability — denial of access to systems or data\n"
                          "All Three — risk affects all components (e.g. ransomware)"),
        "mitre_tactic":  ("MITRE ATT&CK Tactic — the adversary's tactical goal.\n"
                          "Examples:\n"
                          "Credential Access — stealing credentials\n"
                          "Privilege Escalation — gaining higher access\n"
                          "Lateral Movement — moving through the network\n"
                          "Select 'Not Applicable' if no clear tactic matches."),
        "mitre_technique": ("MITRE ATT&CK Technique ID.\n"
                             "Example: T1110 (Brute Force), T1190 (Exploit Public App)\n"
                             "Optional — leave blank if unknown."),
        "cis_control":   ("CIS Controls v8 safeguard family this risk relates to.\n"
                          "CIS-1  Inventory Enterprise Assets\n"
                          "CIS-5  Account Management\n"
                          "CIS-7  Continuous Vulnerability Management\n"
                          "CIS-12 Network Infrastructure Management\n"
                          "CIS-14 Security Awareness Training"),
    }

    def _build_section3(self) -> None:
        container, gl = _card("NIST CSF Mapping", 2)

        # NIST Function
        _nf_lbl = _lbl("NIST Function")
        _nf_lbl.setToolTip(self._NIST_TOOLTIP)
        gl.addWidget(_nf_lbl, 0, 0)
        self._nist_fn_cb = _combo(
            NIST_FUNCTIONS,
            self._g("nist_function", NIST_FUNCTIONS[0]))
        self._nist_fn_cb.setToolTip(self._NIST_TOOLTIP)
        gl.addWidget(self._nist_fn_cb, 0, 1)
        self._fields["nist_function"] = self._nist_fn_cb

        # NIST Category (dynamic)
        _nc_lbl = _lbl("NIST Category")
        _nc_lbl.setToolTip(
            "The NIST CSF 2.0 Category under the selected Function.\n"
            "Categories are auto-populated when you select a Function above.\n"
            "Example: Protect → Identity Management & Access Control")
        gl.addWidget(_nc_lbl, 1, 0)
        init_fn = self._nist_fn_cb.currentText()
        init_cats = NIST_CATEGORIES.get(
            init_fn, NIST_CATEGORIES[NIST_FUNCTIONS[0]])
        init_cat = self._g("nist_category",
                            init_cats[0] if init_cats else "")
        if init_cat and init_cat not in init_cats:
            init_cats = list(init_cats) + [init_cat]
        self._nist_cat_cb = _combo(init_cats, init_cat)
        self._nist_cat_cb.setToolTip(
            "The NIST CSF 2.0 Category under the selected Function.\n"
            "Categories are auto-populated when you select a Function above.")
        gl.addWidget(self._nist_cat_cb, 1, 1)
        self._fields["nist_category"] = self._nist_cat_cb

        # Wire function → category cascade
        self._nist_fn_cb.currentTextChanged.connect(
            self._on_nist_fn_change)

        # NIST Subcategory intentionally removed —
        # Function + Category is the enterprise standard.
        # nist_subcategory stays in the DB schema for PDF use
        # but is not shown in the form.

        self._body_layout.addWidget(container)

    def _on_nist_fn_change(self, fn: str) -> None:
        cats = NIST_CATEGORIES.get(fn, [])
        self._nist_cat_cb.blockSignals(True)
        self._nist_cat_cb.clear()
        self._nist_cat_cb.addItems(cats)
        if cats:
            self._nist_cat_cb.setCurrentIndex(0)
        self._nist_cat_cb.blockSignals(False)

    # ── Section 4 — ISO | CIA | MITRE | CIS ──────────────────────────────────

    def _build_section4(self) -> None:
        container, gl = _card(
            "ISO 27001:2022  |  CIA  |  MITRE ATT&CK  |  CIS", 4)

        saved_iso = self._g("iso_domain", ISO_DOMAINS[0])
        iso_opts  = (ISO_DOMAINS if saved_iso in ISO_DOMAINS
                     else list(ISO_DOMAINS) + [saved_iso])

        rows = [
            (0, "ISO 27001 Domain",    "iso_domain",
             "combo", iso_opts, saved_iso),
            (1, "ISO Control Ref",     "iso_control",
             "entry", [], self._g("iso_control","e.g. A.9.4.1")),
            (2, "CIA Component",       "cia_component",
             "combo", CIA_COMPONENTS,
             self._g("cia_component", CIA_COMPONENTS[0])),
            (3, "MITRE ATT&CK Tactic","mitre_tactic",
             "combo", MITRE_TACTICS,
             self._g("mitre_tactic","Not Applicable")),
            (4, "MITRE Technique",     "mitre_technique",
             "entry", [],
             self._g("mitre_technique",
                     "e.g. T1078 Valid Accounts")),
            (5, "CIS Control",         "cis_control",
             "combo", _CIS_DISPLAY,
             _cis_to_display(self._g("cis_control","Not Applicable"))),
        ]
        for row, label, key, wtype, opts, val in rows:
            _lbl4 = _lbl(label)
            if key in self._FW_TOOLTIPS:
                _lbl4.setToolTip(self._FW_TOOLTIPS[key])
            gl.addWidget(_lbl4, row, 0, Qt.AlignmentFlag.AlignTop)
            if wtype == "combo":
                w = _combo(opts, val)
            else:
                w = _entry(val if val not in (
                    "e.g. A.9.4.1",
                    "e.g. T1078 Valid Accounts") else "",
                           val if val.startswith("e.g.") else "")
                if val.startswith("e.g."):
                    w.setText("")
                    w.setPlaceholderText(val)
                else:
                    w.setText(val)
            if key in self._FW_TOOLTIPS:
                w.setToolTip(self._FW_TOOLTIPS[key])
            gl.addWidget(w, row, 1)
            self._fields[key] = w

        self._body_layout.addWidget(container)

    # ── Section 5 — Mitigation & Notes ───────────────────────────────────────

    def _build_section5(self) -> None:
        container, gl = _card("Mitigation & Notes", 5)
        _S5_TIPS = {
            "existing_controls": (
                "Document controls already in place that reduce this risk.\n"
                "Example:\n"
                "• Password complexity policy enforced\n"
                "• Email filtering deployed\n"
                "• WSUS patch management configured\n"
                "Even partial controls are worth documenting — they affect\n"
                "the residual risk score and confidence calculation."),
            "mitigation":        (
                "Describe the planned or active treatment for this risk.\n"
                "A good mitigation plan includes:\n"
                "• What will be done (specific action)\n"
                "• Who is responsible (named person or team)\n"
                "• Target completion date\n"
                "Example: 'Deploy Microsoft Authenticator for all admin\n"
                "accounts. Owner: IT Security Manager. Target: 30 Jul 2026.'"),
            "notes":             (
                "Any additional context, audit findings, or observations.\n"
                "Example:\n"
                "• 'Identified in Q2 internal audit — management acknowledged'\n"
                "• 'Budget approved, awaiting procurement'\n"
                "• 'Linked to Jira ticket RISK-142'"),
        }
        for row, label, key in [
            (0, "Existing Controls", "existing_controls"),
            (1, "Mitigation Plan",   "mitigation"),
            (2, "Notes",             "notes"),
        ]:
            lbl_w = _lbl(label)
            lbl_w.setToolTip(_S5_TIPS.get(key,""))
            gl.addWidget(lbl_w, row, 0, Qt.AlignmentFlag.AlignTop)
            w = _textarea(self._g(key, ""))
            w.setToolTip(_S5_TIPS.get(key,""))
            gl.addWidget(w, row, 1)
            self._fields[key] = w
        self._body_layout.addWidget(container)

    # ── Submit bar ────────────────────────────────────────────────────────────

    def _build_submit_bar(self, is_edit: bool) -> QWidget:
        w = QWidget()
        w.setStyleSheet("border: none;")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.SM)

        if is_edit:
            save_btn = QPushButton("💾  Save Changes")
        else:
            save_btn = QPushButton("➕  Add to Risk Register")

        save_btn.setFixedHeight(44)
        save_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT_RED};
                color: white; border: none;
                border-radius: {Radius.MD}px;
                font-size: 13pt; font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Colors.HIGH};
            }}
        """)
        save_btn.clicked.connect(self._save)
        hl.addWidget(save_btn, 1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(44)
        cancel_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.MD}px;
                font-size: 13pt; padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        cancel_btn.clicked.connect(self.cancelled.emit)
        hl.addWidget(cancel_btn)
        return w

    # ── Field value getters ───────────────────────────────────────────────────

    def _val(self, key: str) -> str:
        w = self._fields.get(key)
        if w is None:
            return ""
        if isinstance(w, QTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QComboBox):
            txt = w.currentText()
            # CIS combos store display value — extract short key
            return _cis_to_key(txt) if txt.startswith("CIS-") else txt
        if isinstance(w, SliderRow):
            return str(w.value())
        return ""

    # ── Save ──────────────────────────────────────────────────────────────────

    def _highlight_field(self, key: str, error: bool) -> None:
        """Highlight a field red on error, reset on clear."""
        w = self._fields.get(key)
        if not w:
            return
        if error:
            w.setStyleSheet(w.styleSheet() +
                f"border: 2px solid {Colors.CRITICAL} !important;")
        else:
            # Re-apply normal style by clearing override
            from PySide6.QtWidgets import QLineEdit, QTextEdit
            if isinstance(w, QLineEdit):
                w.setStyleSheet(f"""
                    QLineEdit {{
                        background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};
                        border: 1px solid {Colors.BG_BORDER};
                        border-radius: {Radius.SM}px; padding: 4px 8px;
                        font-size: 10pt;
                    }}
                    QLineEdit:focus {{
                        border: 1px solid {Colors.ACCENT_BLUE};
                    }}
                """)

    def _save(self) -> None:
        title = self._val("title")
        owner = self._val("owner")

        # Reset any previous error highlights
        self._highlight_field("title", False)
        self._highlight_field("owner", False)

        PLACEHOLDER_TITLES = {
            "l","m","n","a","b","c","x","z",
            "test","test risk","risk","1","2","3",
            "new risk","untitled","tbd","temp","todo",
            "sample","example","demo",
        }

        if not title or len(title) < 3:
            self._highlight_field("title", True)
            self._set_status(
                "⚠  Risk Title is required (minimum 3 characters). "
                "Enter a descriptive name — e.g. 'MFA Not Enforced on Admin Accounts'.",
                Colors.CRITICAL)
            self._fields["title"].setFocus()
            return
        if title.strip().lower() in PLACEHOLDER_TITLES:
            self._highlight_field("title", True)
            self._set_status(
                f"⚠  '{title}' is not a valid risk title. "
                "Enter a specific, descriptive name for this risk.",
                Colors.CRITICAL)
            self._fields["title"].setFocus()
            return
        if len(title) > 200:
            self._highlight_field("title", True)
            self._set_status(
                "⚠  Risk Title is too long (maximum 200 characters). "
                "Use the Description field for additional detail.",
                Colors.CRITICAL)
            return
        if not owner or len(owner) < 2:
            self._highlight_field("owner", True)
            self._set_status(
                "⚠  Risk Owner is required. "
                "Enter the name or role of the person accountable for this risk "
                "— e.g. 'IT Security Manager' or 'CISO'.",
                Colors.CRITICAL)
            self._fields["owner"].setFocus()
            return

        # Dates
        for date_key in ("date_identified", "review_date"):
            dv = self._val(date_key)
            if dv and not validate_date(dv):
                self._set_status(
                    f"⚠  {date_key.replace('_',' ')} "
                    f"must be YYYY-MM-DD", Colors.CRITICAL)
                return

        try:
            lik = max(1, min(5, int(float(
                self._val("likelihood")))))
        except Exception:
            lik = 3
        try:
            imp = max(1, min(5, int(float(
                self._val("impact")))))
        except Exception:
            imp = 3
        res_raw = self._val("residual_score")
        try:
            res = max(1, int(float(res_raw))) if res_raw \
                else max(1, lik * imp - 3)
        except Exception:
            res = max(1, lik * imp - 3)

        # Build data dict — all string/int values
        data: dict = {}
        skip = {"likelihood", "impact", "residual_score"}
        for k in self._fields:
            if k not in skip:
                data[k] = self._val(k)
        data.update({
            "title":           title,
            "owner":           owner,
            "likelihood":      lik,
            "impact":          imp,
            "residual_score":  res,
            "date_identified": (
                self._val("date_identified") or today()),
        })

        try:
            if self._edit_id:
                update_risk(self._edit_id, data)
                rid = self._edit_id
                action = "updated"
            else:
                rid = insert_risk(data, source="Manual")
                action = "added"
        except Exception as e:
            self._set_status(f"⚠  DB error: {e}",
                             Colors.CRITICAL)
            return

        sc = lik * imp
        self._set_status(
            f"✅  Risk #{rid} {action} — "
            f"Score: {sc} ({score_label(sc)})",
            Colors.SUCCESS_LT)
        QTimer.singleShot(900, lambda: self.saved.emit(rid))

    def _set_status(self, text: str,
                    color: str = Colors.TEXT_MUTED) -> None:
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f"color: {color}; border: none;")
