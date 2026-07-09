"""
ui/risk_register.py  — RiskCore v1.5
Master-detail Risk Register workspace.

Layout matches the reference screenshots:
  ┌─ Header: title + KPI cards + actions ───────────────────────┐
  ├─ Filter: search + combos ───────────────────────────────────┤
  ├─ QSplitter ─────────────────────────────────────────────────┤
  │  TOP: QTableView (virtualised, 5 col) ──────────────────────│
  │  BTM: Detail pane (3 columns) ──────────────────────────────│
  │    Left:  Overview (title/desc/scores/fields) ──────────────│
  │    Mid:   Linked Treatments ────────────────────────────────│
  │    Right: Framework Mapping ────────────────────────────────│
  └─────────────────────────────────────────────────────────────┘
  └─ Status bar ────────────────────────────────────────────────┘
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableView, QComboBox,
    QLineEdit, QHeaderView, QAbstractItemView,
    QSizePolicy, QSplitter, QScrollArea, QGridLayout,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer, QModelIndex
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from widgets.tables import RiskTableModel, RiskFilterProxy, RISK_COLUMNS
from core.database.db import (
    get_risks, get_owners, get_db, today, now_str,
    RISK_STATUS, NIST_FUNCTIONS,
)


# ── Background loader ─────────────────────────────────────────────────────────

class RegisterLoader(QObject):
    finished = Signal(object, object)  # list, dict — object is cross-thread safe
    error    = Signal(str)

    def __init__(self, search="", status="All", nist="All",
                 score="All", owner="All", parent=None):
        super().__init__(parent)
        self._s, self._st = search, status
        self._n, self._sc, self._ow = nist, score, owner

    def run(self) -> None:
        try:
            risks = [dict(r) for r in get_risks(
                search=self._s, status_filter=self._st,
                nist_filter=self._n, score_filter=self._sc,
                owner_filter=self._ow)]
            ids = [r["id"] for r in risks]
            tc_map: dict[int, int] = {}
            if ids:
                ph = ",".join("?" * len(ids))
                with get_db() as conn:
                    rows = conn.execute(
                        f"SELECT risk_id, COUNT(*) c FROM treatments "
                        f"WHERE risk_id IN ({ph}) GROUP BY risk_id", ids
                    ).fetchall()
                    # Convert int keys to str — Qt Signal(dict) drops int-keyed dicts
                    tc_map = {str(r["risk_id"]): r["c"] for r in rows}
            self.finished.emit(risks, tc_map)
        except Exception as e:
            self.error.emit(str(e))


# ── Main Page ─────────────────────────────────────────────────────────────────

class RiskRegisterPage(QWidget):
    navigate                = Signal(str)
    add_risk_requested      = Signal()
    edit_risk_requested     = Signal(int)
    add_treatment_requested = Signal(int)
    data_changed            = Signal()

    # FW pill colours matching the nav badges
    _FW_COLORS = {
        "NIST CSF 2.0":   Colors.FW_NIST,
        "ISO 27001:2022": Colors.FW_ISO,
        "MITRE ATT&CK":   Colors.FW_MITRE,
        "CIS Controls v8":Colors.FW_CIS,
        "CIA Triad":      Colors.FW_CIA,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model  : RiskTableModel | None = None
        self._proxy  : RiskFilterProxy | None = None
        self._thread : QThread | None         = None
        self._sel    : dict | None            = None   # selected risk
        self._all    : list[dict]             = []
        self._setup_ui()
        QTimer.singleShot(100, self.refresh)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UI construction
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_kpi_strip())
        root.addWidget(self._build_filter_bar())

        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setHandleWidth(5)
        self._splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {Colors.BG_BORDER};
            }}
            QSplitter::handle:hover {{
                background: {Colors.ACCENT_BLUE};
            }}
        """)
        self._splitter.addWidget(self._build_table())
        self._splitter.addWidget(self._build_detail_pane())
        self._splitter.setSizes([420, 360])
        root.addWidget(self._splitter, 1)
        root.addWidget(self._build_status_bar())

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(56)
        w.setStyleSheet(f"background: {Colors.BG_DEEP};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(Spacing.XL, 0, Spacing.LG, 0)

        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel("Risk Register")
        t.setFont(Fonts.heading_2())
        t.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(t)
        s = QLabel(
            "All risks  ·  Click a row to view details  ·  "
            "Colour-coded by severity")
        s.setFont(Fonts.label_sm())
        s.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        col.addWidget(s)
        hl.addLayout(col, 1)

        ref = self._icon_btn("↺")
        ref.setToolTip("Refresh")
        ref.clicked.connect(self.refresh)
        hl.addWidget(ref)
        hl.addSpacing(Spacing.SM)

        add = QPushButton("  +  Add Risk")
        add.setFont(Fonts.label_bold())
        add.setFixedHeight(34)
        add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_RED}; color: white;
                border: none; border-radius: {Radius.SM}px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: {Colors.HIGH}; }}
        """)
        add.clicked.connect(self.add_risk_requested.emit)
        hl.addWidget(add)
        return w

    def _icon_btn(self, icon: str) -> QPushButton:
        b = QPushButton(icon)
        b.setFixedSize(32, 32)
        b.setFont(QFont(Fonts.FAMILY, 14))
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BG_BORDER};
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                color: {Colors.TEXT_PRIMARY};
                border-color: {Colors.ACCENT_BLUE};
            }}
        """)
        return b

    # ── KPI strip ─────────────────────────────────────────────────────────────

    def _build_kpi_strip(self) -> QWidget:
        strip = QWidget()
        strip.setFixedHeight(52)
        strip.setStyleSheet(
            f"background: {Colors.BG_DEEP};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        hl = QHBoxLayout(strip)
        hl.setContentsMargins(Spacing.XL, 4, Spacing.LG, 4)
        hl.setSpacing(Spacing.SM)

        self._kpi_nums: dict[str, QLabel] = {}
        for key, label, color, sub in [
            ("critical", "Critical",    Colors.CRITICAL,   "Score ≥ 15"),
            ("high",     "High",        Colors.HIGH,       "Score 10–14"),
            ("medium",   "Medium",      Colors.MEDIUM,     "Score 5–9"),
            ("low",      "Low",         Colors.SUCCESS_LT, "Score < 5"),
            ("total",    "Total Risks", Colors.ACCENT_BLUE,"In register"),
        ]:
            card = QFrame()
            card.setFixedWidth(125)
            card.setStyleSheet(f"""
                QFrame {{
                    background: {Colors.BG_CARD};
                    border-radius: {Radius.SM}px;
                    border: 1px solid {Colors.BG_BORDER};
                    border-top: 3px solid {color};
                }}
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 4, 10, 4)
            cl.setSpacing(0)

            row = QHBoxLayout()
            lbl_w = QLabel(label.upper())
            lbl_w.setFont(QFont(Fonts.FAMILY, 6, QFont.Weight.Bold))
            lbl_w.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none; letter-spacing: 1px;")
            row.addWidget(lbl_w, 1)
            num = QLabel("–")
            num.setFont(QFont(Fonts.FAMILY, 16, QFont.Weight.Bold))
            num.setStyleSheet(f"color: {color}; border: none;")
            num.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(num)
            cl.addLayout(row)

            sub_lbl = QLabel(sub)
            sub_lbl.setFont(QFont(Fonts.FAMILY, 7))
            sub_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; border: none;")
            cl.addWidget(sub_lbl)
            hl.addWidget(card)
            self._kpi_nums[key] = num

        hl.addStretch()
        return strip

    def _update_kpi_strip(self, risks: list[dict]) -> None:
        def sc(r): return int(r.get("risk_score") or 0)
        counts = {
            "critical": sum(1 for r in risks if sc(r) >= 15),
            "high":     sum(1 for r in risks if 10 <= sc(r) <= 14),
            "medium":   sum(1 for r in risks if 5  <= sc(r) <= 9),
            "low":      sum(1 for r in risks if sc(r) < 5),
            "total":    len(risks),
        }
        for k, lbl in self._kpi_nums.items():
            lbl.setText(str(counts.get(k, 0)))

    # ── Filter bar ────────────────────────────────────────────────────────────

    def _build_filter_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            f"background: {Colors.BG_CARD};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(bar)
        vl.setContentsMargins(Spacing.XL, Spacing.SM, Spacing.XL, Spacing.SM)
        vl.setSpacing(Spacing.XS)

        # Row 1: search + clear
        r1 = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText(
            "Search risks, owners, NIST, ISO, MITRE…")
        self._search.setFixedHeight(32)
        self._search.setFont(Fonts.label())
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BG_BORDER};
                border-radius: {Radius.SM}px; padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {Colors.ACCENT_BLUE}; }}
        """)
        self._search.textChanged.connect(self._on_search_changed)
        r1.addWidget(self._search, 1)

        clr = QPushButton("Clear")
        clr.setFont(Fonts.label_sm())
        clr.setFixedHeight(32)
        clr.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clr.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Colors.TEXT_MUTED};
                border: 1px solid {Colors.BG_BORDER};
                border-radius: {Radius.SM}px; padding: 0 12px;
            }}
            QPushButton:hover {{
                color: {Colors.ACCENT_BLUE};
                border-color: {Colors.ACCENT_BLUE};
            }}
        """)
        clr.clicked.connect(self._clear_filters)
        r1.addWidget(clr)
        vl.addLayout(r1)

        # Row 2: combos
        r2 = QHBoxLayout()
        r2.setSpacing(Spacing.SM)
        defs = [
            ("_f_status",   "Status:",   ["All"] + list(RISK_STATUS)),
            ("_f_nist",     "NIST:",     ["All"] + list(NIST_FUNCTIONS)),
            ("_f_severity", "Severity:", ["All", "Critical (≥15)",
                                          "High (10–14)", "Medium (5–9)", "Low (<5)"]),
            ("_f_owner",    "Owner:",    ["All"]),
        ]
        for attr, lbl_txt, items in defs:
            lbl = QLabel(lbl_txt)
            lbl.setFont(Fonts.label_sm())
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            r2.addWidget(lbl)
            cb = self._combo(items, 140)
            cb.currentTextChanged.connect(self._on_filter_changed)
            setattr(self, attr, cb)
            r2.addWidget(cb)
        r2.addStretch()
        vl.addLayout(r2)
        return bar

    def _combo(self, items, w=140) -> QComboBox:
        cb = QComboBox()
        cb.addItems(items)
        cb.setFixedWidth(w)
        cb.setFixedHeight(28)
        cb.setFont(Fonts.label_sm())
        cb.setStyleSheet(f"""
            QComboBox {{
                background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BG_BORDER};
                border-radius: {Radius.SM}px; padding: 0 8px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.ACCENT_BLUE};
                border: 1px solid {Colors.BG_BORDER};
            }}
        """)
        return cb

    # ── Table ─────────────────────────────────────────────────────────────────

    def _build_table(self) -> QTableView:
        self._table = QTableView()
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(38)
        self._table.setStyleSheet(f"""
            QTableView {{
                background: {Colors.BG_CARD};
                alternate-background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
                border: none;
                selection-background-color: rgba(27,95,207,0.22);
                outline: none;
                font-size: 10pt;
            }}
            QHeaderView::section {{
                background: {Colors.BG_DEEP};
                color: {Colors.TEXT_MUTED};
                padding: 6px 8px;
                border: none;
                border-right: 1px solid {Colors.BG_BORDER};
                border-bottom: 2px solid {Colors.ACCENT_BLUE};
                font-size: 8.5pt;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            QTableView::item {{
                padding: 4px 6px;
                border-bottom: 1px solid {Colors.BG_BORDER};
            }}
            QTableView::item:selected {{
                background: rgba(27,95,207,0.22);
                color: {Colors.TEXT_PRIMARY};
                border-left: 3px solid {Colors.ACCENT_BLUE};
            }}
            QTableView::item:hover {{
                background: {Colors.BG_CARD2};
            }}
        """)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.clicked.connect(self._on_row_clicked)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        return self._table

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Detail pane  (matches reference screenshots exactly)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _build_detail_pane(self) -> QWidget:
        outer = QFrame()
        outer.setStyleSheet(
            f"background: {Colors.BG_DEEP};"
            f"border-top: 2px solid {Colors.ACCENT_BLUE};")
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # ── Pane header bar ───────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(40)
        hdr.setStyleSheet(
            f"background: {Colors.BG_CARD};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        hh = QHBoxLayout(hdr)
        hh.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)

        self._det_title = QLabel("Select a risk to view details")
        self._det_title.setFont(Fonts.label_bold())
        self._det_title.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        hh.addWidget(self._det_title, 1)

        self._det_actions = QWidget()
        ab = QHBoxLayout(self._det_actions)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(Spacing.XS)

        def _qbtn(text, bg, slot):
            b = QPushButton(text)
            b.setFont(Fonts.label_sm())
            b.setFixedHeight(26)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: white;
                    border: none; border-radius: {Radius.SM}px;
                    padding: 0 12px;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)
            b.clicked.connect(slot)
            return b

        ab.addWidget(_qbtn("✏  Edit",       Colors.ACCENT_BLUE, self._act_edit))
        ab.addWidget(_qbtn("+ Treatment",   Colors.SUCCESS_LT,  self._act_add_treatment))
        ab.addWidget(_qbtn("🗑  Delete",     Colors.CRITICAL,    self._act_delete))
        self._det_actions.setVisible(False)
        hh.addWidget(self._det_actions)
        vl.addWidget(hdr)

        # ── Three-column body ─────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {Colors.BG_DEEP};")
        bh = QHBoxLayout(body)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)

        # Col 1 — Overview (scrollable)
        self._col_overview = self._make_scroll_col()
        bh.addWidget(self._col_overview, 5)

        bh.addWidget(self._vdiv())

        # Col 2 — Linked Treatments
        self._col_treatments = self._make_scroll_col()
        bh.addWidget(self._col_treatments, 3)

        bh.addWidget(self._vdiv())

        # Col 3 — Framework Mapping
        self._col_frameworks = self._make_scroll_col()
        bh.addWidget(self._col_frameworks, 3)

        # Empty placeholder (before selection)
        self._det_empty = QLabel("← Select any risk row to see details here")
        self._det_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._det_empty.setFont(Fonts.label())
        self._det_empty.setStyleSheet(f"color: {Colors.TEXT_DIM}; padding: 40px;")

        # Stack body vs empty
        from PySide6.QtWidgets import QStackedWidget
        self._det_stack = QStackedWidget()
        self._det_stack.addWidget(self._det_empty)   # idx 0
        self._det_stack.addWidget(body)               # idx 1
        self._det_stack.setCurrentIndex(0)
        vl.addWidget(self._det_stack, 1)
        return outer

    def _make_scroll_col(self) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setStyleSheet(f"background: {Colors.BG_DEEP}; border: none;")
        inner = QWidget()
        inner.setStyleSheet(f"background: {Colors.BG_DEEP};")
        # Create the layout ONCE here — _clear_scroll will clear it in-place
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)
        sa.setWidget(inner)
        return sa

    def _vdiv(self) -> QFrame:
        f = QFrame()
        f.setFixedWidth(1)
        f.setStyleSheet(f"background: {Colors.BG_BORDER};")
        return f

    # ── Helpers for building detail content ───────────────────────────────────

    @staticmethod
    def _clear_scroll(sa: QScrollArea) -> QVBoxLayout:
        """Clear and return the existing VBoxLayout from the scroll area.
        
        NEVER calls inner.setLayout() — that would trigger the Qt warning
        'QLayout: Attempting to add QLayout to QWidget which already has a layout'.
        Instead we clear the existing layout in-place and return it.
        """
        inner = sa.widget()
        vl = inner.layout()
        if vl is None:
            # First call — create the layout
            vl = QVBoxLayout(inner)
            vl.setContentsMargins(Spacing.LG, Spacing.MD,
                                   Spacing.LG, Spacing.MD)
            vl.setSpacing(Spacing.SM)
        else:
            # Subsequent calls — clear children in-place
            while vl.count():
                item = vl.takeAt(0)
                w = item.widget()
                if w:
                    w.hide()
                    w.deleteLater()
                sub = item.layout()
                if sub:
                    # Recursively clear sub-layouts
                    while sub.count():
                        child = sub.takeAt(0)
                        cw = child.widget()
                        if cw:
                            cw.hide()
                            cw.deleteLater()
        return vl

    @staticmethod
    def _L(text, bold=False, color=None, size=9, wrap=True) -> QLabel:
        l = QLabel(str(text or "—"))
        l.setFont(QFont(Fonts.FAMILY, size,
                         QFont.Weight.Bold if bold else QFont.Weight.Normal))
        l.setStyleSheet(
            f"color: {color or Colors.TEXT_PRIMARY}; border: none;")
        l.setWordWrap(wrap)
        return l

    @staticmethod
    def _section(text) -> QLabel:
        l = QLabel(text.upper())
        l.setFont(QFont(Fonts.FAMILY, 7, QFont.Weight.Bold))
        l.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; letter-spacing: 1px; border: none;")
        return l

    @staticmethod
    def _badge(text, bg, fg="white") -> QLabel:
        l = QLabel(f"  {text}  ")
        l.setFont(QFont(Fonts.FAMILY, 8, QFont.Weight.Bold))
        l.setStyleSheet(
            f"color: {fg}; background: {bg};"
            f"border-radius: 4px; padding: 2px 6px;")
        l.setFixedHeight(20)
        return l

    @staticmethod
    def _hdiv() -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background: {Colors.BG_BORDER};")
        return f

    # ── Populate detail ───────────────────────────────────────────────────────

    def _populate_detail(self, risk: dict) -> None:
        self._sel = risk
        sc = int(risk.get("risk_score") or 0)
        sev_lbl = Colors.severity_label(sc)
        sev_col = Colors.severity_color(sc)

        # Header bar
        self._det_title.setText(str(risk.get("title") or "Untitled")[:80])
        self._det_title.setStyleSheet(
            f"color: {sev_col}; font-weight: bold;")
        self._det_actions.setVisible(True)
        self._det_stack.setCurrentIndex(1)

        self._fill_overview(risk, sc, sev_lbl, sev_col)
        self._fill_treatments_col(risk)
        self._fill_frameworks_col(risk)

    def _fill_overview(self, r, sc, sev_lbl, sev_col) -> None:
        vl = self._clear_scroll(self._col_overview)

        # Score + severity row
        sr = QHBoxLayout()
        sc_lbl = QLabel(str(sc))
        sc_lbl.setFont(QFont(Fonts.FAMILY, 32, QFont.Weight.Bold))
        sc_lbl.setStyleSheet(f"color: {sev_col}; border: none;")
        sr.addWidget(sc_lbl)

        badges_col = QVBoxLayout()
        badges_col.setSpacing(3)
        badges_col.addWidget(self._badge(sev_lbl, sev_col))

        st = str(r.get("status") or "Open")
        st_c = {"Open": Colors.MEDIUM, "In Progress": Colors.ACCENT_BLUE,
                 "Mitigated": Colors.SUCCESS_LT, "Closed": Colors.SUCCESS_LT,
                 "Accepted": Colors.TEXT_MUTED}.get(st, Colors.TEXT_MUTED)
        badges_col.addWidget(self._badge(st, st_c))
        sr.addLayout(badges_col)
        sr.addStretch()
        vl.addLayout(sr)

        # Description
        if r.get("description"):
            vl.addWidget(self._L(
                r["description"], size=9, color=Colors.TEXT_MUTED))

        vl.addWidget(self._hdiv())

        # Info grid
        lik = int(r.get("likelihood") or 0)
        imp = int(r.get("impact") or 0)
        LIK = {1:"Rare",2:"Unlikely",3:"Possible",4:"Likely",5:"Almost Certain"}
        IMP = {1:"Negligible",2:"Minor",3:"Moderate",4:"Major",5:"Critical"}

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)

        rows = [
            ("Owner",          r.get("owner") or "—",          None),
            ("Category",       r.get("category") or "—",       None),
            ("Priority",       r.get("priority") or "—",       None),
            ("Source",         r.get("source") or "Manual",    None),
            ("Likelihood",
             f"{lik} — {LIK.get(lik,'')}" if lik else "—",    None),
            ("Impact",
             f"{imp} — {IMP.get(imp,'')}" if imp else "—",     None),
            ("Residual Score",
             str(r.get("residual_score") or "—"),              None),
            ("Review Date",    r.get("review_date") or "—",    None),
        ]
        for i, (k, v, vc) in enumerate(rows):
            grid.addWidget(
                self._L(k, size=8, color=Colors.TEXT_MUTED), i, 0,
                Qt.AlignmentFlag.AlignTop)
            grid.addWidget(
                self._L(v, size=9, color=vc), i, 1,
                Qt.AlignmentFlag.AlignTop)

        vl.addLayout(grid)
        vl.addWidget(self._hdiv())

        # Controls & Mitigation
        vl.addWidget(self._section("Existing Controls"))
        ctrl = r.get("existing_controls") or "None documented"
        ctrl_badge_text = "Weak" if not r.get("existing_controls") else "In Place"
        ctrl_badge_col  = Colors.HIGH if not r.get("existing_controls") \
                          else Colors.SUCCESS_LT
        cb_row = QHBoxLayout()
        cb_row.addWidget(self._L(ctrl, size=9, color=Colors.TEXT_MUTED), 1)
        cb_row.addWidget(self._badge(ctrl_badge_text, ctrl_badge_col))
        vl.addLayout(cb_row)

        if r.get("mitigation"):
            vl.addWidget(self._section("Mitigation Plan"))
            mit_row = QHBoxLayout()
            mit_row.addWidget(
                self._L(r["mitigation"], size=9,
                         color=Colors.TEXT_MUTED), 1)
            mit_row.addWidget(self._badge("Planned", Colors.ACCENT_BLUE))
            vl.addLayout(mit_row)

        if r.get("ai_suggestion"):
            vl.addWidget(self._section("AI Recommendation"))
            vl.addWidget(self._L(
                r["ai_suggestion"], size=9, color=Colors.TEXT_MUTED))

        vl.addStretch()

    def _fill_treatments_col(self, r: dict) -> None:
        vl = self._clear_scroll(self._col_treatments)
        vl.addWidget(self._section("Linked Treatments"))

        try:
            from core.database.db import get_treatments
            treats = [dict(t) for t in get_treatments(r["id"])]
        except Exception:
            treats = []

        if not treats:
            vl.addWidget(self._L("No treatments linked.",
                                   color=Colors.TEXT_DIM, size=9))
        else:
            for t in treats:
                card = QFrame()
                card.setStyleSheet(f"""
                    QFrame {{
                        background: {Colors.BG_CARD};
                        border-radius: {Radius.SM}px;
                        border: 1px solid {Colors.BG_BORDER};
                    }}
                """)
                cl = QVBoxLayout(card)
                cl.setContentsMargins(10, 8, 10, 8)
                cl.setSpacing(4)

                top_row = QHBoxLayout()
                strat = t.get("strategy","—")
                strat_c = {"Mitigate": Colors.ACCENT_BLUE,
                            "Accept": Colors.SUCCESS_LT,
                            "Transfer": Colors.PURPLE_LT,
                            "Avoid": Colors.MEDIUM}.get(strat, Colors.TEXT_MUTED)
                top_row.addWidget(self._badge(strat, strat_c))
                top_row.addStretch()
                st = t.get("status","—")
                st_c2 = {"Approved": Colors.SUCCESS_LT,
                          "In Progress": Colors.ACCENT_BLUE,
                          "Completed": Colors.SUCCESS_LT,
                          "Verified": Colors.SUCCESS_LT}.get(
                              st, Colors.TEXT_MUTED)
                top_row.addWidget(self._L(st, size=8, color=st_c2))
                cl.addLayout(top_row)

                cl.addWidget(self._L(t.get("title","—"), bold=True, size=9))

                if t.get("description"):
                    cl.addWidget(self._L(
                        t["description"][:100], size=8,
                        color=Colors.TEXT_MUTED))

                meta = f"Owner: {t.get('owner','—')}  ·  " \
                       f"Target: {t.get('target_date','—')}"
                cl.addWidget(self._L(meta, size=8, color=Colors.TEXT_DIM))
                vl.addWidget(card)

        vl.addStretch()

    def _fill_frameworks_col(self, r: dict) -> None:
        vl = self._clear_scroll(self._col_frameworks)
        vl.addWidget(self._section("Framework Mapping"))

        rows = [
            ("NIST CSF 2.0",
             f"{r.get('nist_function','—')} › {r.get('nist_category','—')}",
             f"PR.{r.get('nist_subcategory','')}" if r.get("nist_subcategory") else "",
             Colors.FW_NIST),
            ("ISO 27001:2022",
             f"{r.get('iso_domain','—')}",
             r.get("iso_control") or "",
             Colors.FW_ISO),
            ("MITRE ATT&CK",
             r.get("mitre_tactic") or "—",
             r.get("mitre_technique") or "",
             Colors.FW_MITRE),
            ("CIS Controls v8",
             r.get("cis_control") or "—",
             "",
             Colors.FW_CIS),
            ("CIA Triad",
             r.get("cia_component") or "—",
             "",
             Colors.FW_CIA),
        ]

        for fw, main_val, sub_val, color in rows:
            fw_card = QFrame()
            fw_card.setStyleSheet(f"""
                QFrame {{
                    background: {Colors.BG_CARD};
                    border-radius: {Radius.SM}px;
                    border: 1px solid {Colors.BG_BORDER};
                    border-left: 3px solid {color};
                }}
            """)
            fl = QVBoxLayout(fw_card)
            fl.setContentsMargins(10, 6, 10, 6)
            fl.setSpacing(2)

            fw_row = QHBoxLayout()
            badge = self._badge(fw, color)
            badge.setFixedHeight(16)
            fw_row.addWidget(badge)
            fw_row.addStretch()
            fl.addLayout(fw_row)

            fl.addWidget(self._L(main_val, bold=True, size=9,
                                   color=color))
            if sub_val:
                fl.addWidget(self._L(sub_val, size=8,
                                      color=Colors.TEXT_MUTED))
            vl.addWidget(fw_card)

        # Risk tags (from category + priority)
        tags_to_show = [
            r.get("category"), r.get("priority"), r.get("nist_category"),
        ]
        tags = [t for t in tags_to_show if t]
        if tags:
            vl.addWidget(self._hdiv())
            vl.addWidget(self._section("Risk Tags"))
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            for tag in tags[:4]:
                tl = QLabel(f"  {tag}  ")
                tl.setFont(QFont(Fonts.FAMILY, 7))
                tl.setStyleSheet(
                    f"color: {Colors.TEXT_PRIMARY};"
                    f"background: {Colors.BG_BORDER};"
                    f"border-radius: 3px; padding: 1px 4px;")
                tags_row.addWidget(tl)
            tags_row.addStretch()
            vl.addLayout(tags_row)

        vl.addStretch()

    # ── Quick actions ─────────────────────────────────────────────────────────

    def _act_edit(self) -> None:
        if self._sel:
            self.edit_risk_requested.emit(self._sel["id"])

    def _act_add_treatment(self) -> None:
        if self._sel:
            self.add_treatment_requested.emit(self._sel["id"])

    def _act_delete(self) -> None:
        if not self._sel:
            return
        from PySide6.QtWidgets import QMessageBox
        rid   = self._sel["id"]
        title = str(self._sel.get("title","?"))[:60]
        if QMessageBox.question(
                self, "Delete Risk",
                f"Permanently delete:\n\n'{title}'\n\nCannot be undone.",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.Cancel
        ) == QMessageBox.StandardButton.Yes:
            from core.database.db import delete_risk
            delete_risk(rid)
            self._sel = None
            self._det_stack.setCurrentIndex(0)
            self._det_actions.setVisible(False)
            self._det_title.setText("Select a risk to view details")
            self._det_title.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            self.refresh()
            self.data_changed.emit()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Data loading
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def refresh(self) -> None:
        # Guard: don't start a second load if one is already running
        if self._thread is not None and self._thread.isRunning():
            return
        # Reset stale thread reference (shouldn't happen but defensive)
        if self._thread is not None and not self._thread.isRunning():
            self._thread = None
        self._status_lbl.setText("Loading…")
        loader = RegisterLoader(
            search="",
            status=self._f_status.currentText(),
            nist=self._f_nist.currentText(),
            score=self._f_severity.currentText(),
            owner=self._f_owner.currentText(),
        )
        self._thread = QThread()
        loader.moveToThread(self._thread)
        self._thread.started.connect(loader.run)
        loader.finished.connect(self._on_data_loaded)
        loader.error.connect(self._on_error)
        loader.finished.connect(self._thread.quit)
        loader.error.connect(self._thread.quit)
        self._thread.finished.connect(loader.deleteLater)
        self._thread.finished.connect(
            lambda: setattr(self, "_thread", None))
        self._thread.start()
        self._loader = loader

    def _on_data_loaded(self, risks: list, tc_map: dict) -> None:
        self._all = risks
        if self._model is None:
            self._model = RiskTableModel(risks, tc_map)
            self._proxy = RiskFilterProxy()
            self._proxy.setSourceModel(self._model)
            self._table.setModel(self._proxy)
            self._set_col_widths()
            self._proxy.set_search(self._search.text())
        else:
            self._model.refresh(risks, tc_map)
            self._proxy.set_search(self._search.text())

        self._update_count()
        self._update_kpi_strip(risks)
        self._ts_lbl.setText(f"Refreshed: {now_str()}")

        # Repopulate owners
        try:
            owners = ["All"] + sorted(get_owners())
            cur = self._f_owner.currentText()
            self._f_owner.blockSignals(True)
            self._f_owner.clear()
            self._f_owner.addItems(owners)
            idx = self._f_owner.findText(cur)
            self._f_owner.setCurrentIndex(max(0, idx))
            self._f_owner.blockSignals(False)
        except Exception:
            pass

        # Re-select if still exists
        if self._sel:
            still = next(
                (r for r in risks if r.get("id") == self._sel.get("id")),
                None)
            if still:
                self._sel = still
                self._populate_detail(still)

    def _on_error(self, msg: str) -> None:
        self._status_lbl.setText(f"⚠  Error: {msg}")
        self._status_lbl.setStyleSheet(f"color: {Colors.CRITICAL};")

    def _set_col_widths(self) -> None:
        hdr = self._table.horizontalHeader()
        for i, (_, _, w) in enumerate(RISK_COLUMNS):
            if w == 0:
                hdr.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Stretch)
            else:
                hdr.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Fixed)
                self._table.setColumnWidth(i, w)

    def _update_count(self) -> None:
        if self._proxy:
            n = self._proxy.rowCount()
            self._status_lbl.setText(f"Showing 1 to {n} of {n} risks")
            self._status_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED};")

    # ── Filter actions ────────────────────────────────────────────────────────

    def _on_search_changed(self, text: str) -> None:
        if self._proxy:
            self._proxy.set_search(text)
            self._update_count()

    def _on_filter_changed(self, _=None) -> None:
        self.refresh()

    def _clear_filters(self) -> None:
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        for cb in (self._f_status, self._f_nist,
                   self._f_severity, self._f_owner):
            cb.blockSignals(True)
            cb.setCurrentIndex(0)
            cb.blockSignals(False)
        self.refresh()

    # ── Row click ─────────────────────────────────────────────────────────────

    def _on_row_clicked(self, index: QModelIndex) -> None:
        if not index.isValid() or self._proxy is None:
            return
        src  = self._proxy.mapToSource(index)
        risk = self._model.risk_at(src.row())
        if risk:
            self._populate_detail(risk)

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid() or self._proxy is None:
            return
        src  = self._proxy.mapToSource(index)
        risk = self._model.risk_at(src.row())
        if risk:
            self._open_detail(risk["id"])

    def _open_detail(self, rid: int) -> None:
        from ui.risk_detail import RiskDetailDialog
        dlg = RiskDetailDialog(rid, self)
        dlg.risk_deleted.connect(lambda _: (self.refresh(),
                                             self.data_changed.emit()))
        dlg.edit_requested.connect(dlg.accept)
        dlg.edit_requested.connect(self.edit_risk_requested.emit)
        dlg.treatment_added.connect(self.add_treatment_requested.emit)
        dlg.data_changed.connect(self.refresh)
        dlg.exec()

    def _on_risk_deleted(self, rid: int) -> None:
        self.refresh()
        self.data_changed.emit()

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(24)
        w.setStyleSheet(
            f"background: {Colors.BG_DEEP};"
            f"border-top: 1px solid {Colors.BG_BORDER};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(Spacing.XL, 0, Spacing.XL, 0)
        self._status_lbl = QLabel("Loading…")
        self._status_lbl.setFont(Fonts.label_sm())
        self._status_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        hl.addWidget(self._status_lbl)
        hl.addStretch()
        self._ts_lbl = QLabel("")
        self._ts_lbl.setFont(Fonts.label_sm())
        self._ts_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        hl.addWidget(self._ts_lbl)
        return w
