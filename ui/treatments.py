"""
ui/treatments.py
─────────────────
Treatments Page — Phase 5 migration.

Uses TreatmentTableModel (virtualised, from ui/widgets/tables.py).
Clicking a row opens TreatmentDialog — an inline QDialog for
Add / Edit treatment with the same 3-section form as the CTk version:
  Section 1 — Treatment Plan (strategy, title, description, owner)
  Section 2 — Status & Schedule (status, target, completion)
  Section 3 — Risk Scoring (residual target, residual actual,
              cost estimate, notes)

The page handles both:
  • standalone "Treatments" nav → shows all treatments
  • called from Risk Detail "＋ Add Treatment" → pre-fills risk_id
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableView, QComboBox, QSplitter,
    QLineEdit, QHeaderView, QAbstractItemView,
    QDialog, QScrollArea, QGridLayout,
    QTextEdit, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from widgets.tables import TreatmentTableModel, ProgressDelegate, TREATMENT_COLUMNS
from core.database.db import (
    get_risks, get_risk, get_risk as _get_risk,
    get_treatment, get_treatments,
    insert_treatment, update_treatment, delete_treatment,
    validate_date, get_db,
    TREATMENT_STRATEGIES, TREATMENT_STATUS,
    today, now_str,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lbl(text, font=None, color=Colors.TEXT_MUTED) -> QLabel:
    l = QLabel(str(text or ""))
    l.setFont(font or Fonts.label_sm())
    l.setStyleSheet(f"color: {color}; border: none;")
    return l


def _entry(placeholder="") -> QLineEdit:
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(32)
    e.setStyleSheet(f"""
        QLineEdit {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px;
            padding: 0 10px;
            font-size: 10pt;
        }}
        QLineEdit:focus {{
            border: 1px solid {Colors.ACCENT_BLUE};
        }}
    """)
    return e


def _combo(items: list, width=160) -> QComboBox:
    c = QComboBox()
    c.addItems(items)
    c.setFixedWidth(width)
    c.setFixedHeight(32)
    c.setStyleSheet(f"""
        QComboBox {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px;
            padding: 2px 8px;
            font-size: 10pt;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_BLUE};
        }}
    """)
    return c


def _textarea(height=60) -> QTextEdit:
    t = QTextEdit()
    t.setFixedHeight(height)
    t.setStyleSheet(f"""
        QTextEdit {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px;
            padding: 6px 10px;
            font-size: 10pt;
        }}
        QTextEdit:focus {{
            border: 1px solid {Colors.ACCENT_BLUE};
        }}
    """)
    return t


def _btn(text, color=Colors.BG_BORDER,
         text_color=Colors.TEXT_MUTED, height=32) -> QPushButton:
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
            font-size: 10pt;
        }}
        QPushButton:hover {{
            background-color: {Colors.BG_CARD2};
            color: {Colors.TEXT_PRIMARY};
        }}
    """)
    return b


# ── Background loader ─────────────────────────────────────────────────────────

class TreatmentLoader(QObject):
    finished = Signal(object)  # list — use object for cross-thread safety
    error    = Signal(str)

    def __init__(self, status="All", strategy="All",
                 search="", risk_id=None):
        super().__init__()
        self._status   = status
        self._strategy = strategy
        self._search   = search.strip().lower()
        self._risk_id  = risk_id

    def run(self) -> None:
        try:
            with get_db() as conn:
                q = ("SELECT t.*, r.title as risk_title, "
                     "r.risk_score FROM treatments t "
                     "JOIN risks r ON t.risk_id=r.id WHERE 1=1")
                p = []
                if self._risk_id is not None:
                    q += " AND t.risk_id=?"; p.append(self._risk_id)
                if self._status != "All":
                    q += " AND t.status=?"; p.append(self._status)
                if self._strategy != "All":
                    q += " AND t.strategy=?"; p.append(self._strategy)
                q += " ORDER BY t.target_date ASC, r.risk_score DESC"
                rows = [dict(r) for r in
                        conn.execute(q, p).fetchall()]
            if self._search:
                rows = [r for r in rows if
                        self._search in (r.get("title","") or "").lower() or
                        self._search in (r.get("risk_title","") or "").lower() or
                        self._search in (r.get("owner","") or "").lower() or
                        self._search in (r.get("strategy","") or "").lower()]
            self.finished.emit(rows)
        except Exception as e:
            self.error.emit(str(e))


# ── Treatment form dialog ─────────────────────────────────────────────────────

class TreatmentDialog(QDialog):
    """
    Add / Edit Treatment dialog.

    Fields exactly match riskcore_phase2._open_treatment_form:
      Section 1 — Treatment Plan
      Section 2 — Status & Schedule
      Section 3 — Risk Scoring
    """
    saved = Signal()

    def __init__(self, risk_id: int,
                 treatment_id: int | None = None,
                 parent=None):
        super().__init__(parent)
        self._risk_id      = risk_id
        self._treatment_id = treatment_id
        _r = _get_risk(risk_id)
        self._risk         = dict(_r) if _r else None
        _e = get_treatment(treatment_id) if treatment_id else None
        self._existing     = dict(_e) if _e else None

        if not self._risk:
            # Risk not found — close immediately without building UI
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.reject)
            return

        self.setWindowTitle(
            "Edit Treatment" if treatment_id else "Add Treatment")
        self.resize(640, 680)
        self.setStyleSheet(
            f"background-color: {Colors.BG_DEEP}; border: none;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header band
        hdr = QFrame()
        hdr.setFixedHeight(46)
        hdr.setStyleSheet(
            f"background-color: {Colors.BG_CARD}; border: none;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        title_lbl = QLabel(
            f"{'Edit' if treatment_id else 'Add'} Treatment  ·  "
            f"{str(self._risk['title'] or '')[:36]}")
        title_lbl.setFont(
            QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        hl.addWidget(title_lbl)
        root.addWidget(hdr)

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        self._form_layout = QVBoxLayout(inner)
        self._form_layout.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.SM)
        self._form_layout.setSpacing(Spacing.MD)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self._fields = {}
        self._build_form()

        # Status label
        self._status_lbl = _lbl("")
        self._form_layout.addWidget(self._status_lbl)

        # Buttons
        btn_row = QWidget()
        btn_row.setStyleSheet("border: none;")
        bl = QHBoxLayout(btn_row)
        bl.setContentsMargins(0, 0, 0, Spacing.MD)
        bl.setSpacing(Spacing.SM)
        save_btn = _btn("💾  Save Treatment",
                        Colors.ACCENT_TEAL, "white", 42)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT_TEAL};
                color: white; border: none;
                border-radius: {Radius.MD}px;
                padding: 0 20px;
                font-size: 13pt; font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #00695C;
            }}
        """)
        save_btn.clicked.connect(self._save)
        bl.addWidget(save_btn, 1)
        cancel_btn = _btn("Cancel", Colors.BG_BORDER,
                          Colors.TEXT_MUTED, 42)
        cancel_btn.clicked.connect(self.reject)
        bl.addWidget(cancel_btn)
        self._form_layout.addWidget(btn_row)

    # ── Form construction ─────────────────────────────────────────────────────

    def _g(self, key, fallback=""):
        if not self._existing:
            return fallback
        try:
            val = self._existing[key]
            return val if val not in (None, "") else fallback
        except Exception:
            return fallback

    def _section(self, title: str) -> QWidget:
        """Section label + card container."""
        sec_title = QLabel(title)
        sec_title.setFont(
            QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
        sec_title.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE}; border: none;")
        self._form_layout.addWidget(sec_title)

        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        gl = QGridLayout(card)
        gl.setContentsMargins(
            Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
        gl.setSpacing(Spacing.SM)
        gl.setColumnMinimumWidth(0, 165)
        gl.setColumnStretch(1, 1)
        self._form_layout.addWidget(card)
        return card

    def _row(self, card: QWidget, row_i: int,
             label: str, key: str, widget: QWidget) -> None:
        lbl = _lbl(label)
        lbl.setFixedWidth(165)
        card.layout().addWidget(lbl, row_i, 0,
                                 Qt.AlignmentFlag.AlignTop)
        card.layout().addWidget(widget, row_i, 1)
        self._fields[key] = widget

    def _build_form(self) -> None:
        import datetime as _dt
        sc  = int(self._risk.get("risk_score") or 0)
        lik = int(self._risk.get("likelihood") or 0)
        imp = int(self._risk.get("impact") or 0)

        # ── Load org size for smart defaults ──────────────────────────────────
        try:
            from core.database.db import get_organisation_scope, load_settings
            _scope    = get_organisation_scope() or {}
            _settings = load_settings() or {}
            _org_size = (_scope.get("organisation_size","")
                         or _settings.get("organisation_size","")).lower()
        except Exception:
            _org_size = ""

        # Smart cost benchmark by org size + risk score
        # Sources: IBM 2024, Gartner, Sophos 2024
        # Match against exact Settings dropdown labels
        if "Enterprise" in _org_size:     # Enterprise (5,000+ employees)
            _cost_map = {(15,25):"$75,000 – $300,000",
                         (10,14):"$30,000 – $75,000",
                         (5, 9): "$10,000 – $30,000",
                         (1, 4): "$2,000 – $10,000"}
            _impact_map = {(15,25):"$2,500,000 – $9,400,000",
                           (10,14):"$800,000 – $2,500,000",
                           (5, 9): "$150,000 – $800,000",
                           (1, 4): "$10,000 – $150,000"}
        elif "Large" in _org_size:        # Large (500–5,000 employees)
            _cost_map = {(15,25):"$18,000 – $75,000",
                         (10,14):"$8,000 – $18,000",
                         (5, 9): "$3,000 – $8,000",
                         (1, 4): "$500 – $3,000"}
            _impact_map = {(15,25):"$800,000 – $2,500,000",
                           (10,14):"$250,000 – $800,000",
                           (5, 9): "$50,000 – $250,000",
                           (1, 4): "$5,000 – $50,000"}
        elif "Medium" in _org_size:       # Medium (50–500 employees)
            _cost_map = {(15,25):"$8,000 – $22,000",
                         (10,14):"$3,000 – $8,000",
                         (5, 9): "$1,000 – $3,000",
                         (1, 4): "$200 – $1,000"}
            _impact_map = {(15,25):"$150,000 – $500,000",
                           (10,14):"$50,000 – $150,000",
                           (5, 9): "$10,000 – $50,000",
                           (1, 4): "$1,000 – $10,000"}
        else:                             # Small (< 50 employees) — default
            _cost_map = {(15,25):"$4,000 – $11,000",
                         (10,14):"$1,500 – $4,000",
                         (5, 9): "$500 – $1,500",
                         (1, 4): "$100 – $500"}
            _impact_map = {(15,25):"$20,000 – $80,000",
                           (10,14):"$8,000 – $20,000",
                           (5, 9): "$2,000 – $8,000",
                           (1, 4): "$200 – $2,000"}

        def _bench_cost(s):
            for (lo,hi), v in _cost_map.items():
                if lo <= s <= hi: return v
            return "—"
        def _bench_impact(s):
            for (lo,hi), v in _impact_map.items():
                if lo <= s <= hi: return v
            return "—"

        # Smart target date: based on risk severity
        def _smart_date(days):
            d = _dt.date.today() + _dt.timedelta(days=days)
            return d.strftime("%Y-%m-%d")

        _target_days = {(15,25):7, (10,14):30, (5,9):90, (1,4):180}
        _tgt_days = next((v for (lo,hi),v in _target_days.items()
                         if lo <= sc <= hi), 90)

        # Smart strategy based on score
        _smart_strategy = (
            "Mitigate" if sc >= 10
            else "Mitigate" if sc >= 5
            else "Accept" if sc <= 4
            else "Mitigate")

        # Smart title based on risk title
        _risk_title = str(self._risk.get("title","") or "")[:40]
        _smart_title = (f"Mitigate: {_risk_title}" if _smart_strategy == "Mitigate"
                        else f"Accept: {_risk_title}" if _smart_strategy == "Accept"
                        else f"Transfer: {_risk_title}")

        # Smart description based on strategy + risk data
        _risk_owner = str(self._risk.get("owner","") or "Risk Owner")
        _sev_label  = ("Critical" if sc >= 15 else "High" if sc >= 10
                       else "Medium" if sc >= 5 else "Low")
        _smart_desc = {
            "Mitigate": (
                f"Implement technical and procedural controls to reduce the likelihood "
                f"and impact of this {_sev_label.lower()} risk. "
                f"Assign accountability to {_risk_owner}. "
                f"Verify control effectiveness before closing."),
            "Accept":   (
                f"Formally accept this {_sev_label.lower()} risk. "
                f"Document business justification and obtain sign-off from {_risk_owner}. "
                f"Schedule review in {_tgt_days} days to confirm risk level has not increased."),
            "Transfer": (
                f"Transfer this {_sev_label.lower()} risk through insurance or contractual "
                f"arrangement. Confirm coverage adequacy with {_risk_owner}. "
                f"Document transfer mechanism and review annually."),
            "Avoid":    (
                f"Eliminate the activity or system that introduces this {_sev_label.lower()} risk. "
                f"Confirm business approval from {_risk_owner} before proceeding. "
                f"Document the decision and alternatives considered."),
        }.get(_smart_strategy, "")

        # Smart notes with benchmark context
        _smart_notes = (
            f"Risk Score: {sc} ({_sev_label})  ·  "
            f"Likelihood: {lik}  ·  Impact: {imp}\n"
            f"Industry benchmark treatment cost: {_bench_cost(sc)}\n"
            f"Industry benchmark potential loss:  {_bench_impact(sc)}\n"
            f"Source: IBM Cost of a Data Breach 2024, Gartner 2024")

        # ── Section 1 — Treatment Plan ────────────────────────────────────────
        s1 = self._section("Treatment Plan")

        strat_cb = _combo(TREATMENT_STRATEGIES, 160)
        strat_cb.setCurrentText(self._g("strategy", _smart_strategy))
        strat_cb.setToolTip(
            "Mitigate: implement controls to reduce the risk\n"
            "Transfer: shift risk via insurance or contract\n"
            "Accept:   formally accept with documented justification\n"
            "Avoid:    eliminate the activity causing the risk")
        self._row(s1, 0, "Strategy *", "strategy", strat_cb)

        title_e = _entry("Treatment title")
        title_e.setText(self._g("title", _smart_title))
        title_e.setToolTip(
            "A concise title for this treatment plan.\n"
            "Example: 'Mitigate: MFA Not Enforced for Admin Accounts'")
        self._row(s1, 1, "Title *", "title", title_e)

        desc_t = _textarea(72)
        desc_t.setPlainText(self._g("description", _smart_desc))
        desc_t.setToolTip(
            "Describe what will be done, who is responsible, and how.\n"
            "A good treatment description includes:\n"
            "• The specific action to be taken\n"
            "• The person/team responsible\n"
            "• How success will be measured")
        self._row(s1, 2, "Description", "description", desc_t)

        owner_e = _entry("e.g. IT Security Manager")
        owner_e.setText(
            self._g("owner", str(self._risk.get("owner") or "")))
        owner_e.setToolTip(
            "The person accountable for delivering this treatment plan.\n"
            "Should be a named individual, not a team.")
        self._row(s1, 3, "Owner", "owner", owner_e)

        # ── Section 2 — Status & Schedule ────────────────────────────────────
        s2 = self._section("Status & Schedule")

        status_cb = _combo(TREATMENT_STATUS, 160)
        status_cb.setCurrentText(self._g("status", "Draft"))
        status_cb.setToolTip(
            "Draft:       treatment plan is being prepared\n"
            "Approved:    plan approved, not yet started\n"
            "In Progress: implementation underway\n"
            "Completed:   treatment implemented, pending verification\n"
            "Verified:    effectiveness confirmed by review\n"
            "Deferred:    postponed with documented reason")
        self._row(s2, 0, "Status", "status", status_cb)

        tgt_e = _entry("YYYY-MM-DD")
        tgt_e.setText(self._g("target_date", _smart_date(_tgt_days)))
        tgt_e.setToolTip(
            f"Target completion date (YYYY-MM-DD).\n"
            f"Recommended for a {_sev_label} risk: "
            f"{_tgt_days} days ({_smart_date(_tgt_days)})")
        self._row(s2, 1, "Target Date", "target_date", tgt_e)

        cmp_e = _entry("YYYY-MM-DD")
        cmp_e.setText(self._g("completion_date", ""))
        cmp_e.setToolTip(
            "Actual date treatment was completed (YYYY-MM-DD).\n"
            "Leave blank until treatment is confirmed done.")
        self._row(s2, 2, "Completion Date", "completion_date", cmp_e)

        # ── Section 3 — Risk Scoring & Cost ──────────────────────────────────
        s3 = self._section("Risk Scoring & Cost Intelligence")

        # Benchmark info card
        bench_info = QLabel(
            f"  📊  Benchmark ({_sev_label} risk, {_org_size or 'small org'}):  "
            f"Treatment cost {_bench_cost(sc)}  ·  "
            f"Potential loss {_bench_impact(sc)}  "
            f"  [IBM 2024 / Gartner 2024]")
        bench_info.setFont(Fonts.label_sm())
        bench_info.setWordWrap(True)
        bench_info.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE}; border: none;"
            f"background: {Colors.BG_CARD2}; padding: 6px 10px;"
            f"border-radius: 4px; border-left: 3px solid {Colors.ACCENT_BLUE};")
        s3_layout = s3.layout()
        if s3_layout:
            s3_layout.addWidget(bench_info, 0, 0, 1, 2)

        default_tgt = str(self._g("residual_score_target", max(1, sc - 4)))
        tgt_sc_e = _entry("1–25")
        tgt_sc_e.setText(default_tgt)
        tgt_sc_e.setToolTip(
            f"The expected risk score AFTER this treatment is applied.\n"
            f"Current score: {sc}  ({_sev_label})\n"
            f"Suggested target: {max(1, sc - 4)} "
            f"(reduction of ~{min(4, sc-1)} points via treatment)")
        self._row(s3, 1, "Residual Target (1–25)",
                  "residual_score_target", tgt_sc_e)

        act_sc_e = _entry("after verification")
        act_sc_e.setText(str(self._g("residual_score_actual") or ""))
        act_sc_e.setToolTip(
            "The actual residual score confirmed after verification.\n"
            "Complete this field when treatment is verified — it updates\n"
            "the risk's residual score in the register.")
        self._row(s3, 2, "Residual Actual",
                  "residual_score_actual", act_sc_e)

        cost_e = _entry(f"e.g. {_bench_cost(sc).split(' –')[0]}")
        cost_e.setText(self._g("cost_estimate", ""))
        cost_e.setToolTip(
            f"Estimated total cost to implement this treatment.\n"
            f"Industry benchmark for {_sev_label} risk: {_bench_cost(sc)}\n"
            f"Include: labour, software, hardware, consulting, training.\n"
            f"For detailed breakdown, use the Cost & ROSI tab on the risk.")
        self._row(s3, 3, "Cost Estimate", "cost_estimate", cost_e)

        notes_t = _textarea(60)
        notes_t.setPlainText(self._g("notes", _smart_notes))
        notes_t.setToolTip(
            "Additional context, dependencies, or observations.\n"
            "Industry benchmark data is pre-populated as a starting point.")
        self._row(s3, 4, "Notes", "notes", notes_t)

    # ── Get field values ──────────────────────────────────────────────────────

    def _val(self, key: str) -> str:
        w = self._fields.get(key)
        if w is None:
            return ""
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QTextEdit):
            return w.toPlainText().strip()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        return ""

    def _int_val(self, key: str):
        v = self._val(key).strip()
        try:
            return int(v) if v else None
        except ValueError:
            return None

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        title_v = self._val("title")
        if not title_v:
            self._status_lbl.setText("⚠  Title is required.")
            self._status_lbl.setStyleSheet(
                f"color: {Colors.CRITICAL}; border: none;")
            return

        for date_key in ("target_date", "completion_date"):
            dv = self._val(date_key)
            if dv and not validate_date(dv):
                self._status_lbl.setText(
                    f"⚠  {date_key.replace('_',' ')} "
                    f"must be YYYY-MM-DD.")
                self._status_lbl.setStyleSheet(
                    f"color: {Colors.CRITICAL}; border: none;")
                return

        data = {
            "risk_id":               self._risk_id,
            "strategy":              self._val("strategy"),
            "title":                 title_v,
            "description":           self._val("description"),
            "owner":                 self._val("owner"),
            "status":                self._val("status"),
            "target_date":           self._val("target_date"),
            "completion_date":       self._val("completion_date"),
            "residual_score_target": self._int_val(
                "residual_score_target"),
            "residual_score_actual": self._int_val(
                "residual_score_actual"),
            "cost_estimate":         self._val("cost_estimate"),
            "notes":                 self._val("notes"),
        }

        try:
            if self._treatment_id:
                update_treatment(self._treatment_id, data)
            else:
                insert_treatment(data)
        except Exception as e:
            self._status_lbl.setText(f"⚠  Error: {e}")
            self._status_lbl.setStyleSheet(
                f"color: {Colors.CRITICAL}; border: none;")
            return

        self.saved.emit()
        self.accept()


# ── Treatments Page ───────────────────────────────────────────────────────────

class TreatmentsPage(QWidget):
    """
    Treatments page — virtualised QTableView with:
      - Status + Strategy dropdowns
      - Live search
      - Clear Filters
      - ＋ Add Treatment button (opens risk-picker then form)
      - Click/double-click row → TreatmentDialog
      - Empty state with action cards (matching Image 7)

    Signals
    -------
    navigate(str) : request page navigation
    """
    navigate        = Signal(str)
    treatment_saved = Signal()   # emitted after any treatment save/delete

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model : TreatmentTableModel | None = None
        self._thread: QThread | None = None
        self._setup_ui()
        QTimer.singleShot(100, self.refresh)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._selected_treatment: dict | None = None

        root.addWidget(self._build_header())
        root.addWidget(self._build_filter_bar())

        # ── Master-detail splitter ────────────────────────────────────────────
        from PySide6.QtWidgets import QSplitter, QScrollArea, QTabWidget
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setHandleWidth(4)
        self._splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {Colors.BG_BORDER};
            }}
            QSplitter::handle:hover {{
                background: {Colors.ACCENT_BLUE};
            }}
        """)

        # Table (top half)
        self._table_widget = self._build_table()
        self._empty_widget = self._build_empty_state()
        self._empty_widget.setVisible(False)

        table_container = QWidget()
        tc_vl = QVBoxLayout(table_container)
        tc_vl.setContentsMargins(0,0,0,0)
        tc_vl.setSpacing(0)
        tc_vl.addWidget(self._table_widget, 1)
        tc_vl.addWidget(self._empty_widget, 1)
        self._splitter.addWidget(table_container)

        # Detail pane (bottom half)
        self._detail_container = self._build_treatment_detail_pane()
        self._splitter.addWidget(self._detail_container)
        self._splitter.setSizes([360, 300])

        root.addWidget(self._splitter, 1)
        root.addWidget(self._build_status_bar())

    def _build_treatment_detail_pane(self) -> QWidget:
        """Bottom treatment detail pane."""
        from PySide6.QtWidgets import QScrollArea, QGridLayout
        container = QWidget()
        container.setStyleSheet(
            f"background: {Colors.BG_DEEP};"
            f"border-top: 2px solid {Colors.ACCENT_BLUE};")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0,0,0,0)
        vl.setSpacing(0)

        # Pane header
        hdr = QWidget()
        hdr.setFixedHeight(40)
        hdr.setStyleSheet(
            f"background: {Colors.BG_CARD};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        hh = QHBoxLayout(hdr)
        hh.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        self._treat_detail_title = QLabel("Select a treatment to view details")
        self._treat_detail_title.setFont(Fonts.label_bold())
        self._treat_detail_title.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        hh.addWidget(self._treat_detail_title, 1)

        # Quick actions
        self._treat_action_btns = QWidget()
        ab = QHBoxLayout(self._treat_action_btns)
        ab.setContentsMargins(0,0,0,0)
        ab.setSpacing(Spacing.XS)
        def _qb(label, color, slot):
            b = QPushButton(label)
            b.setFont(Fonts.label_sm())
            b.setFixedHeight(26)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {color}; color: white;
                    border: none; border-radius: {Radius.SM}px;
                    padding: 0 12px;
                }}
            """)
            b.clicked.connect(slot)
            return b
        ab.addWidget(_qb("✏  Edit",    Colors.ACCENT_BLUE, self._treat_quick_edit))
        ab.addWidget(_qb("✓ Approve",  Colors.SUCCESS_LT,  self._treat_quick_approve))
        ab.addWidget(_qb("🗑 Delete",  Colors.CRITICAL,    self._treat_quick_delete))
        self._treat_action_btns.setVisible(False)
        hh.addWidget(self._treat_action_btns)
        vl.addWidget(hdr)

        # Content scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {Colors.BG_DEEP}; border: none;")
        self._treat_detail_inner = QWidget()
        self._treat_detail_inner.setStyleSheet(f"background: {Colors.BG_DEEP};")
        self._treat_detail_vl = QVBoxLayout(self._treat_detail_inner)
        self._treat_detail_vl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._treat_detail_vl.addWidget(
            self._make_label("Select a treatment to view details",
                              Colors.TEXT_DIM))
        scroll.setWidget(self._treat_detail_inner)
        vl.addWidget(scroll, 1)
        self._treat_detail_scroll = scroll
        return container

    def _make_label(self, text, color=None, bold=False, size=9):
        l = QLabel(str(text))
        l.setFont(QFont(Fonts.FAMILY, size,
                         QFont.Weight.Bold if bold else QFont.Weight.Normal))
        l.setStyleSheet(f"color: {color or Colors.TEXT_PRIMARY}; border: none;")
        l.setWordWrap(True)
        return l

    def _populate_treatment_detail(self, t: dict) -> None:
        self._selected_treatment = t
        self._treat_action_btns.setVisible(True)

        strat  = t.get("strategy","—")
        title  = t.get("title","Untitled")
        status = t.get("status","—")
        strat_colors = {"Mitigate": Colors.ACCENT_BLUE,
                         "Accept":   Colors.SUCCESS_LT,
                         "Transfer": Colors.PURPLE_LT,
                         "Avoid":    Colors.MEDIUM}
        sc = strat_colors.get(strat, Colors.TEXT_MUTED)
        self._treat_detail_title.setText(f"{strat}  ·  {title}")
        self._treat_detail_title.setStyleSheet(f"color: {sc}; font-weight: bold;")

        # Clear existing content
        vl = self._treat_detail_vl
        while vl.count():
            item = vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from PySide6.QtWidgets import QGridLayout

        # Score strip
        row0 = QHBoxLayout()
        row0.setSpacing(Spacing.MD)
        status_colors = {"Approved": Colors.SUCCESS_LT,
                          "In Progress": Colors.ACCENT_BLUE,
                          "Completed":   Colors.SUCCESS_LT,
                          "Verified":    Colors.SUCCESS_LT,
                          "Draft":       Colors.TEXT_MUTED,
                          "Deferred":    Colors.HIGH}
        st_c = status_colors.get(status, Colors.TEXT_MUTED)
        st_b = QLabel(f"  {status.upper()}  ")
        st_b.setFont(QFont(Fonts.FAMILY, 8, QFont.Weight.Bold))
        st_b.setStyleSheet(
            f"color: white; background: {st_c};"
            f"border-radius: 3px; padding: 2px 6px;")
        row0.addWidget(st_b)

        row0.addStretch()
        vl.addLayout(row0)

        vl.addSpacing(6)

        # Description
        if t.get("description"):
            vl.addWidget(self._make_label(
                t["description"], Colors.TEXT_MUTED, size=9))
            vl.addSpacing(6)

        # Two separate grids side by side — prevents column overlap at narrow widths
        from PySide6.QtWidgets import QHBoxLayout as _HBL
        grids_row = _HBL()
        grids_row.setSpacing(Spacing.LG)

        grid_l = QGridLayout()
        grid_l.setColumnMinimumWidth(0, 90)
        grid_l.setColumnStretch(1, 1)
        grid_l.setVerticalSpacing(6)
        grid_l.setHorizontalSpacing(8)

        grid_r = QGridLayout()
        grid_r.setColumnMinimumWidth(0, 100)
        grid_r.setColumnStretch(1, 1)
        grid_r.setVerticalSpacing(6)
        grid_r.setHorizontalSpacing(8)

        rows_l = [
            ("Owner",        t.get("owner", "—") or "—"),
            ("Strategy",     strat),
            ("Target Date",  t.get("target_date", "—") or "—"),
            ("Completion",   t.get("completion_date", "—") or "—"),
        ]
        rows_r = [
            ("Residual Target", str(t.get("residual_score_target", "—") or "—")),
            ("Residual Actual", str(t.get("residual_score_actual", "—") or "—")),
            ("Cost Estimate",   str(t.get("cost_estimate", "—") or "—")),
            ("Notes",           (t.get("notes") or "—")[:80]),
        ]

        for i, (k, v) in enumerate(rows_l):
            kl = self._make_label(k, Colors.TEXT_MUTED, size=8)
            kl.setFixedWidth(90)
            grid_l.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignTop)
            vl2 = self._make_label(v, size=9)
            vl2.setWordWrap(True)
            grid_l.addWidget(vl2, i, 1, Qt.AlignmentFlag.AlignTop)

        for i, (k, v) in enumerate(rows_r):
            kl = self._make_label(k, Colors.TEXT_MUTED, size=8)
            kl.setFixedWidth(100)
            grid_r.addWidget(kl, i, 0, Qt.AlignmentFlag.AlignTop)
            vl3 = self._make_label(v, size=9)
            vl3.setWordWrap(True)
            grid_r.addWidget(vl3, i, 1, Qt.AlignmentFlag.AlignTop)

        grids_row.addLayout(grid_l, 1)
        grids_row.addLayout(grid_r, 1)
        vl.addLayout(grids_row)
        vl.addStretch()

    # Quick actions for treatment detail pane
    def _treat_quick_edit(self):
        if not self._selected_treatment:
            return
        from core.database.db import get_risk
        rid = self._selected_treatment.get("risk_id")
        dlg = TreatmentDialog(rid, self._selected_treatment, self)
        if dlg.exec():
            self.refresh()
            self.treatment_saved.emit()

    def _treat_quick_approve(self):
        if not self._selected_treatment:
            return
        tid = self._selected_treatment.get("id")
        if not tid:
            return
        from core.database.db import update_treatment
        t = dict(self._selected_treatment)
        t["status"] = "Approved"
        update_treatment(tid, t)
        self.refresh()
        self.treatment_saved.emit()

    def _treat_quick_delete(self):
        if not self._selected_treatment:
            return
        from PySide6.QtWidgets import QMessageBox
        from core.database.db import delete_treatment
        tid   = self._selected_treatment.get("id")
        title = self._selected_treatment.get("title","?")[:50]
        resp  = QMessageBox.question(
            self, "Delete Treatment",
            f"Permanently delete:\n\n'{title}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if resp == QMessageBox.StandardButton.Yes:
            delete_treatment(tid)
            self._selected_treatment = None
            self._treat_action_btns.setVisible(False)
            self._treat_detail_title.setText("Select a treatment to view details")
            self._treat_detail_title.setStyleSheet(
                f"color: {Colors.TEXT_MUTED};")
            self.refresh()
            self.treatment_saved.emit()

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, Spacing.LG, Spacing.XL, Spacing.SM)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("◈  Treatments")
        title.setFont(Fonts.heading_1())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(title)
        sub = QLabel("All treatment plans  ·  Click a row to edit")
        sub.setFont(Fonts.label())
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        col.addWidget(sub)
        hl.addLayout(col)
        hl.addStretch()

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedSize(36, 34)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED};
                border: none; border-radius: {Radius.SM}px;
                font-size: 14pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        refresh_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)

        add_btn = QPushButton("＋  Add Treatment")
        add_btn.setFixedHeight(34)
        add_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        add_btn.setStyleSheet(f"""
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
        add_btn.clicked.connect(lambda _: self._add_treatment())
        hl.addWidget(add_btn)
        return w

    def _build_filter_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(
            Spacing.XL, Spacing.SM, Spacing.XL, Spacing.SM)
        hl.setSpacing(Spacing.MD)

        def _filter_combo(items, w=140):
            c = QComboBox()
            c.addItems(items)
            c.setFixedWidth(w)
            c.setFixedHeight(30)
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

        for lbl_txt, attr, items in [
            ("Status:",   "_status_cb",
             ["All"] + TREATMENT_STATUS),
            ("Strategy:", "_strategy_cb",
             ["All"] + TREATMENT_STRATEGIES),
        ]:
            lbl = _lbl(lbl_txt)
            hl.addWidget(lbl)
            cb = _filter_combo(items)
            cb.currentIndexChanged.connect(
                lambda _: self.refresh())
            setattr(self, attr, cb)
            hl.addWidget(cb)

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "⌕  Search treatments...")
        self._search_input.setFixedHeight(30)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BG_BORDER};
                border-radius: {Radius.SM}px;
                padding: 0 10px; font-size: 10pt;
            }}
        """)
        self._search_input.textChanged.connect(
            lambda _: self.refresh())
        hl.addWidget(self._search_input, 1)

        clear_btn = QPushButton("⊟  Clear Filters")
        clear_btn.setFixedHeight(30)
        clear_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED};
                border: none; border-radius: {Radius.SM}px;
                padding: 0 12px; font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        clear_btn.clicked.connect(self._clear_filters)
        hl.addWidget(clear_btn)
        return bar

    def _build_table(self) -> QTableView:
        t = QTableView()
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        t.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setShowGrid(False)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(36)
        t.setWordWrap(False)
        t.setStyleSheet(f"""
            QTableView {{
                background-color: {Colors.BG_CARD};
                alternate-background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
                border: none; outline: none;
                selection-background-color: {Colors.ACCENT_BLUE};
                gridline-color: transparent;
                font-size: 10pt;
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED};
                padding: 4px 8px; border: none;
                font-size: 9pt; font-weight: bold;
            }}
            QTableView::item {{ padding: 0 6px; border: none; }}
            QTableView::item:selected {{
                background-color: {Colors.ACCENT_BLUE};
                color: white;
            }}
            QTableView::item:hover {{
                background-color: {Colors.BG_CARD2};
            }}
        """)
        t.clicked.connect(self._on_row_clicked)
        t.doubleClicked.connect(self._on_row_double_clicked)
        self._table = t
        return t

    def _build_empty_state(self) -> QWidget:
        """Image 7 empty state with action cards."""
        w = QWidget()
        w.setStyleSheet(
            f"background-color: {Colors.BG_CARD}; border: none;")
        vl = QVBoxLayout(w)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("◈")
        icon.setFont(QFont(Fonts.FAMILY, 48))
        icon.setStyleSheet(
            f"color: {Colors.BG_BORDER}; border: none;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(icon)

        title = QLabel("No treatments match the current filters")
        title.setFont(
            QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(title)

        sub = QLabel(
            "Try adjusting your filters or add a new treatment plan.")
        sub.setFont(Fonts.label())
        sub.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(sub)

        # Action cards row
        cards_row = QWidget()
        cards_row.setStyleSheet("border: none;")
        cr = QHBoxLayout(cards_row)
        cr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cr.setSpacing(Spacing.MD)

        for icon_txt, label, desc, cmd in [
            ("＋", "Add Treatment",
             "Create a new treatment\nplan for a risk",
             self._add_treatment),
            ("⊟", "Clear Filters",
             "Reset all filters to\nview all treatments",
             self._clear_filters),
            ("⌕", "Search",
             "Search by title, risk,\nowner or strategy",
             lambda: self._search_input.setFocus()),
        ]:
            cf = QFrame()
            cf.setFixedSize(200, 110)
            cf.setStyleSheet(
                f"background-color: {Colors.BG_CARD2};"
                f"border-radius: {Radius.LG}px; border: none;")
            cf.setCursor(
                QCursor(Qt.CursorShape.PointingHandCursor))
            cl = QVBoxLayout(cf)
            cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            i_lbl = QLabel(icon_txt)
            i_lbl.setFont(QFont(Fonts.FAMILY, 20))
            i_lbl.setStyleSheet(
                f"color: {Colors.ACCENT_BLUE}; border: none;")
            i_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(i_lbl)
            n_lbl = QLabel(label)
            n_lbl.setFont(
                QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
            n_lbl.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            n_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(n_lbl)
            d_lbl = QLabel(desc)
            d_lbl.setFont(Fonts.label_sm())
            d_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            d_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            d_lbl.setWordWrap(True)
            cl.addWidget(d_lbl)
            if cmd:
                cf.mousePressEvent = (
                    lambda e, c=cmd: c())
            cr.addWidget(cf)
        vl.addWidget(cards_row)

        info = QLabel(
            "ⓘ  Treatments help you reduce risk by implementing "
            "controls and tracking their effectiveness.")
        info.setFont(Fonts.label_sm())
        info.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(info)
        return w

    def _build_status_bar(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(24)
        w.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};"
            f"border-top: 1px solid {Colors.BG_BORDER};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(Spacing.XL, 0, Spacing.XL, 0)
        self._status_lbl = _lbl("Loading…",
                                  color=Colors.TEXT_DIM)
        hl.addWidget(self._status_lbl)
        hl.addStretch()
        return w

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if self._thread is not None and not self._thread.isRunning():
            self._thread = None
        loader = TreatmentLoader(
            status=self._status_cb.currentText(),
            strategy=self._strategy_cb.currentText(),
            search=self._search_input.text(),
        )
        self._thread = QThread()
        loader.moveToThread(self._thread)
        self._thread.started.connect(loader.run)
        loader.finished.connect(self._on_loaded)
        loader.error.connect(
            lambda e: self._status_lbl.setText(f"⚠ {e}"))
        loader.finished.connect(self._thread.quit)
        loader.error.connect(self._thread.quit)
        self._thread.finished.connect(loader.deleteLater)
        self._thread.finished.connect(
            lambda: setattr(self, '_thread', None))
        self._loader = loader   # store before start() so GC can't collect it
        self._thread.start()

    def _on_loaded(self, rows: list) -> None:
        if not rows:
            self._table_widget.setVisible(False)
            self._empty_widget.setVisible(True)
            self._status_lbl.setText("0 treatments")
            return

        self._empty_widget.setVisible(False)
        self._table_widget.setVisible(True)

        if self._model is None:
            self._model = TreatmentTableModel(rows)
            self._table.setModel(self._model)
            self._set_column_widths()
            # Set progress delegate on last column
            self._table.setItemDelegateForColumn(
                len(TREATMENT_COLUMNS) - 1,
                ProgressDelegate(self._table))
        else:
            self._model.refresh(rows)

        self._status_lbl.setText(
            f"{len(rows)} treatment(s)  ·  {now_str()}")

    def _set_column_widths(self) -> None:
        hdr = self._table.horizontalHeader()
        for i, (_, _, w) in enumerate(TREATMENT_COLUMNS):
            if w == 0:
                hdr.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Stretch)
            else:
                hdr.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Fixed)
                self._table.setColumnWidth(i, w)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _clear_filters(self) -> None:
        self._status_cb.blockSignals(True)
        self._strategy_cb.blockSignals(True)
        self._search_input.blockSignals(True)
        self._status_cb.setCurrentIndex(0)
        self._strategy_cb.setCurrentIndex(0)
        self._search_input.clear()
        self._status_cb.blockSignals(False)
        self._strategy_cb.blockSignals(False)
        self._search_input.blockSignals(False)
        self.refresh()

    def _add_treatment(self, risk_id: int = None) -> None:
        """Open treatment form — pick first available risk if none given."""
        # Guard: Qt clicked signal passes bool; treat False/0 as None
        if not risk_id and risk_id is not None:
            risk_id = None
        if risk_id is None:
            risks = get_risks()
            if not risks:
                QMessageBox.information(
                    self, "No Risks",
                    "Add risks to the register first.")
                return
            # get_risks() returns sqlite3.Row — use index access
            risk_id = risks[0]["id"]
        # Validate risk exists before opening dialog
        from core.database.db import get_risk as _gr
        risk_row = _gr(risk_id)
        if not risk_row:
            QMessageBox.warning(
                self, "Risk Not Found",
                f"Risk #{risk_id} could not be found.")
            return
        dlg = TreatmentDialog(risk_id, parent=self)
        dlg.saved.connect(self.refresh)
        dlg.saved.connect(self.treatment_saved.emit)
        dlg.exec()

    def open_for_risk(self, risk_id: int) -> None:
        """Called from main_window when Add Treatment is triggered."""
        self._add_treatment(risk_id)

    def _on_row_clicked(self, index) -> None:
        """Single click: populate detail pane."""
        if not index.isValid() or self._model is None:
            return
        row = self._model.row_at(index.row())
        if row:
            self._populate_treatment_detail(row)

    def _on_row_double_clicked(self, index) -> None:
        """Double click: open full edit dialog."""
        if not index.isValid() or self._model is None:
            return
        row = self._model.row_at(index.row())
        if not row:
            return
        dlg = TreatmentDialog(row["risk_id"], row["id"], parent=self)
        dlg.saved.connect(self.refresh)
        dlg.saved.connect(self.treatment_saved.emit)
        dlg.exec()
