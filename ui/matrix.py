"""
ui/matrix.py
─────────────
Risk Matrix Page — Phase 6 migration.

A true 5×5 QPainter-drawn heat map.
Each cell is a styled QPushButton with severity colour fill.
Clicking a cell opens a CellRisksDialog listing all risks at
that likelihood × impact coordinate — clicking any listed risk
opens the full RiskDetailDialog.

Layout (Image 5):
  Page header (title + Export + Refresh)
  Legend bar (LOW / MEDIUM / HIGH / CRITICAL)
  5×5 matrix grid with axis labels
  Note: "Score = Likelihood × Impact · (n) = risks at this cell"
  Footer: three info cards (How to read / Color guide / Take action)
"""

from __future__ import annotations
import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QDialog,
    QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, QTimer
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from core.database.db import get_db, today


# ── Helpers ───────────────────────────────────────────────────────────────────

IMP_LABELS = {1: "Negligible", 2: "Minor", 3: "Moderate",
              4: "Major",      5: "Critical"}
LIK_LABELS = {1: "Rare",      2: "Unlikely", 3: "Possible",
              4: "Likely",     5: "Almost Certain"}


def _severity_color(score: int) -> str:
    if score >= 15: return Colors.CRITICAL
    if score >= 10: return Colors.HIGH
    if score >= 5:  return Colors.MEDIUM
    return Colors.LOW


def _lbl(text, font=None, color=Colors.TEXT_MUTED,
         align=Qt.AlignmentFlag.AlignLeft) -> QLabel:
    l = QLabel(str(text))
    l.setFont(font or Fonts.label_sm())
    l.setStyleSheet(f"color: {color}; background: transparent; border: none;")
    l.setAlignment(align)
    return l


# ── Matrix data loader ────────────────────────────────────────────────────────

class MatrixLoader(QObject):
    """Load risk counts per (likelihood, impact) cell off the UI thread."""
    finished = Signal(object)  # dict — use object for cross-thread safety
    error    = Signal(str)

    def run(self) -> None:
        try:
            counts = {}
            with get_db() as conn:
                for lik in range(1, 6):
                    for imp in range(1, 6):
                        c = conn.execute(
                            "SELECT COUNT(*) FROM risks "
                            "WHERE likelihood=? AND impact=?",
                            (lik, imp)).fetchone()[0]
                        counts[(lik, imp)] = c
            self.finished.emit(counts)
        except Exception as e:
            self.error.emit(str(e))


# ── Cell risks popup ──────────────────────────────────────────────────────────

class CellRisksDialog(QDialog):
    """
    Lists all risks at a specific likelihood × impact cell.
    Clicking a risk row opens RiskDetailDialog.
    """
    def __init__(self, lik: int, imp: int, score: int,
                 parent=None):
        super().__init__(parent)
        self._lik   = lik
        self._imp   = imp
        self._score = score

        with get_db() as conn:
            self._risks = [dict(r) for r in conn.execute(
                "SELECT * FROM risks "
                "WHERE likelihood=? AND impact=?",
                (lik, imp)).fetchall()]

        color = _severity_color(score)
        n     = len(self._risks)
        self.setWindowTitle(f"Score {score} — {n} risk(s)")
        self.resize(660, 440)
        self.setStyleSheet(
            f"background-color: {Colors.BG_DEEP}; border: none;")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD,
                                Spacing.LG, Spacing.MD)
        root.setSpacing(Spacing.SM)

        # Header
        hdr = QHBoxLayout()
        t = QLabel(
            f"{n} risk(s) at score {score}  "
            f"(L{lik} × I{imp})")
        t.setFont(QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        t.setStyleSheet(f"color: {color};")
        hdr.addWidget(t)
        hdr.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(30)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px; padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        hdr.addWidget(close_btn)
        root.addLayout(hdr)

        hint = _lbl("Click a risk to view full details",
                    color=Colors.TEXT_MUTED)
        root.addWidget(hint)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        for i, r in enumerate(self._risks):
            sc   = int(r["risk_score"] or 0)
            bg   = Colors.BG_CARD if i % 2 == 0 else Colors.BG_CARD2
            row  = QFrame()
            row.setStyleSheet(
                f"background-color: {bg};"
                f"border-radius: {Radius.SM}px; border: none;")
            row.setCursor(
                QCursor(Qt.CursorShape.PointingHandCursor))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(Spacing.SM, 6, Spacing.SM, 6)
            rl.setSpacing(Spacing.SM)

            sev = QLabel(Colors.severity_label(sc))
            sev.setFont(Fonts.label_sm_bold())
            sev.setStyleSheet(
                f"color: {Colors.severity_color(sc)};"
                f"border: none;")
            sev.setFixedWidth(68)
            rl.addWidget(sev)

            title = QLabel(str(r["title"] or "Untitled"))
            title.setFont(Fonts.label())
            title.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            rl.addWidget(title, 1)

            st_color = (Colors.MEDIUM
                        if r["status"] == "Open"
                        else Colors.SUCCESS_LT
                        if r["status"] in ("Mitigated", "Closed")
                        else Colors.TEXT_MUTED)
            status = QLabel(str(r["status"] or "—"))
            status.setFont(Fonts.label_sm())
            status.setStyleSheet(
                f"color: {st_color}; border: none;")
            status.setFixedWidth(70)
            rl.addWidget(status)

            owner = QLabel(str(r["owner"] or "Unassigned"))
            owner.setFont(Fonts.label_sm())
            owner.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            owner.setFixedWidth(110)
            rl.addWidget(owner)

            # Click opens risk detail
            rid = r["id"]
            row.mousePressEvent = (
                lambda e, r_id=rid: self._open_detail(r_id))
            vl.addWidget(row)

        vl.addStretch()

    def _open_detail(self, rid: int) -> None:
        from ui.risk_detail import RiskDetailDialog
        dlg = RiskDetailDialog(rid, self)
        dlg.exec()


# ── Risk Matrix Page ──────────────────────────────────────────────────────────

class RiskMatrixPage(QWidget):
    """
    Risk Matrix — 5×5 heat map grid.

    Signals
    -------
    navigate(str) : page navigation request
    """
    navigate = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts: dict = {}
        self._cell_btns: dict = {}
        self._thread: QThread | None = None
        self._setup_ui()
        QTimer.singleShot(100, self._load)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_legend())

        # Scrollable body (matrix + note + footer)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(
            Spacing.XL, Spacing.MD, Spacing.XL, Spacing.XL)
        self._body_layout.setSpacing(Spacing.MD)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self._build_matrix_grid()
        self._body_layout.addWidget(self._build_note())
        self._body_layout.addWidget(self._build_footer())
        self._body_layout.addStretch()

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, Spacing.LG, Spacing.XL, Spacing.SM)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("⊞  Risk Matrix")
        t.setFont(Fonts.heading_1())
        t.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(t)
        s = QLabel(
            "5×5 heat map  ·  NIST SP 800-30  "
            "·  Click a cell to see risks")
        s.setFont(Fonts.label())
        s.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        col.addWidget(s)
        hl.addLayout(col)
        hl.addStretch()

        export_btn = QPushButton("↗  Export Matrix")
        export_btn.setFixedHeight(34)
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px;
                padding: 0 14px; font-size: 11pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        export_btn.clicked.connect(
            lambda: self.navigate.emit("export"))
        hl.addWidget(export_btn)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedSize(36, 34)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px; font-size: 14pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        refresh_btn.clicked.connect(self._load)
        hl.addWidget(refresh_btn)
        return w

    def _build_legend(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(Spacing.XL, 0, Spacing.XL, 0)
        for text, color in [
            ("●  LOW  1–4",       Colors.LOW),
            ("●  MEDIUM  5–9",    Colors.MEDIUM),
            ("●  HIGH  10–14",    Colors.HIGH),
            ("●  CRITICAL  15–25",Colors.CRITICAL),
        ]:
            l = QLabel(text)
            l.setFont(QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {color};")
            hl.addWidget(l)
            hl.addSpacing(Spacing.XL)
        hl.addStretch()
        return bar

    def _build_matrix_grid(self) -> None:
        # Load org size to drive benchmark tooltips on cells
        try:
            from core.database.db import get_organisation_scope, load_settings
            _scope    = get_organisation_scope() or {}
            _settings = load_settings() or {}
            _org_size = (_scope.get("organisation_size","")
                         or _settings.get("organisation_size",""))
        except Exception:
            _org_size = ""

        # Industry benchmark financial impact ranges by org size
        # Sources: IBM Cost of a Data Breach 2024, Gartner, Sophos 2024
        # Match against exact Settings dropdown values
        if "Enterprise" in _org_size:     # Enterprise (5,000+ employees)
            _benchmarks = {
                "Critical": ("$2.5M – $9.4M",  "IBM 2024 US avg $9.36M"),
                "High":     ("$800K – $2.5M",   "Gartner enterprise estimate"),
                "Medium":   ("$150K – $800K",   "Industry avg mid-tier incident"),
                "Low":      ("$10K – $150K",    "Minor incident cost estimate"),
            }
            _size_label = "Enterprise (5,000+ employees)"
        elif "Large" in _org_size:        # Large (500–5,000 employees)
            _benchmarks = {
                "Critical": ("$800K – $2.5M",   "IBM 2024 global avg $4.88M"),
                "High":     ("$250K – $800K",   "Scaled to organisation size"),
                "Medium":   ("$50K – $250K",    "Industry avg mid-tier incident"),
                "Low":      ("$5K – $50K",      "Minor incident cost estimate"),
            }
            _size_label = "Large (500–5,000 employees)"
        elif "Medium" in _org_size:       # Medium (50–500 employees)
            _benchmarks = {
                "Critical": ("$150K – $500K",   "IBM 2024 SME avg scaled"),
                "High":     ("$50K – $150K",    "Scaled SME incident estimate"),
                "Medium":   ("$10K – $50K",     "SME mid-tier incident estimate"),
                "Low":      ("$1K – $10K",      "Minor SME incident estimate"),
            }
            _size_label = "Medium (50–500 employees)"
        else:                             # Small (< 50 employees) — default
            _benchmarks = {
                "Critical": ("$20K – $80K",     "IBM 2024 micro-org scaled"),
                "High":     ("$8K – $20K",      "Scaled micro-org estimate"),
                "Medium":   ("$2K – $8K",       "Micro-org incident estimate"),
                "Low":      ("$200 – $2K",      "Minor micro-org estimate"),
            }
            _size_label = "Small (< 50 employees)"

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        gl = QGridLayout(container)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(4)

        # IMPACT → label (row 0, spans columns 2-6)
        impact_lbl = _lbl(
            "IMPACT  →",
            font=QFont(Fonts.FAMILY, 10, QFont.Weight.Bold),
            color=Colors.TEXT_MUTED,
            align=Qt.AlignmentFlag.AlignCenter)
        gl.addWidget(impact_lbl, 0, 2, 1, 5)

        # Column headers (row 1)
        for ci, imp in enumerate(range(1, 6)):
            lbl = _lbl(
                f"{IMP_LABELS[imp]}\n({imp})",
                font=QFont(Fonts.FAMILY, 9),
                color=Colors.TEXT_MUTED,
                align=Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(115)
            gl.addWidget(lbl, 1, ci + 2)

        # LIKELIHOOD label (column 0, rows 2-6)
        lik_lbl = _lbl(
            "L\nI\nK\nE\nL\nI\nH\nO\nO\nD",
            font=QFont(Fonts.FAMILY, 9, QFont.Weight.Bold),
            color=Colors.TEXT_MUTED,
            align=Qt.AlignmentFlag.AlignCenter)
        gl.addWidget(lik_lbl, 2, 0, 5, 1)

        # Row labels + cells
        for ri, lik in enumerate(range(5, 0, -1)):
            row_lbl = _lbl(
                f"{LIK_LABELS[lik]}\n({lik})",
                font=QFont(Fonts.FAMILY, 9),
                color=Colors.TEXT_MUTED,
                align=Qt.AlignmentFlag.AlignRight |
                      Qt.AlignmentFlag.AlignVCenter)
            row_lbl.setFixedWidth(100)
            gl.addWidget(row_lbl, ri + 2, 1)

            for ci, imp in enumerate(range(1, 6)):
                sc    = lik * imp
                color = _severity_color(sc)
                sev_name = ("Critical" if sc >= 15
                             else "High" if sc >= 10
                             else "Medium" if sc >= 5 else "Low")
                bench = _benchmarks.get(sev_name, ("—", ""))
                btn   = QPushButton(str(sc))
                btn.setFixedSize(115, 66)
                btn.setFont(
                    QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
                btn.setCursor(
                    QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        color: white;
                        border: none;
                        border-radius: {Radius.SM}px;
                        font-size: 14pt;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: white;
                        color: {color};
                    }}
                """)
                btn.setToolTip(
                    f"Score: {sc}  ({sev_name})\n"
                    f"Likelihood: {lik}  ·  Impact: {imp}\n"
                    f"─────────────────────────\n"
                    f"Estimated Financial Exposure:\n"
                    f"{bench[0]}\n"
                    f"Source: {bench[1]}\n"
                    f"Organisation: {_size_label}\n"
                    f"─────────────────────────\n"
                    f"Click to view risks at this score"
                )
                btn.clicked.connect(
                    lambda checked, l=lik, i=imp, s=sc:
                    self._on_cell_click(l, i, s))
                self._cell_btns[(lik, imp)] = btn
                gl.addWidget(btn, ri + 2, ci + 2)

        self._body_layout.addWidget(
            container,
            alignment=Qt.AlignmentFlag.AlignHCenter)
        self._grid_container = container

    def _build_note(self) -> QLabel:
        l = QLabel(
            "Score = Likelihood × Impact  ·  "
            "(n) = risks logged at this cell")
        l.setFont(Fonts.label_sm())
        l.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return l

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        gl = QGridLayout(footer)
        gl.setContentsMargins(
            Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        gl.setSpacing(Spacing.SM)
        gl.setColumnStretch(0, 1)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(2, 1)

        for col, (icon, title, body) in enumerate([
            ("⊘", "How to read",
             "Multiply the Likelihood by Impact "
             "to get the inherent risk score."),
            ("ⓘ", "Color guide",
             "Green = Low (1–4)   Yellow = Medium (5–9)\n"
             "Orange = High (10–14)   Red = Critical (15–25)"),
            ("◎", "Take action",
             "Click any cell to view the risks and "
             "recommended treatments at that score."),
        ]):
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {Colors.BG_CARD2};"
                f"border-radius: {Radius.MD}px; border: none;")
            vl = QVBoxLayout(card)
            vl.setContentsMargins(
                Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            vl.setSpacing(4)
            t_lbl = QLabel(f"{icon}  {title}")
            t_lbl.setFont(
                QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
            t_lbl.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            vl.addWidget(t_lbl)
            b_lbl = QLabel(body)
            b_lbl.setFont(Fonts.label_sm())
            b_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            b_lbl.setWordWrap(True)
            vl.addWidget(b_lbl)
            gl.addWidget(card, 0, col)
        return footer

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if self._thread is not None and not self._thread.isRunning():
            self._thread = None  # clear stale reference
        self._thread = QThread()
        self._loader = MatrixLoader()
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.finished.connect(self._on_loaded)
        self._loader.error.connect(
            lambda e: print(f"Matrix error: {e}"))
        self._loader.finished.connect(self._thread.quit)
        self._loader.error.connect(self._thread.quit)
        self._thread.finished.connect(self._loader.deleteLater)
        self._thread.finished.connect(
            lambda: setattr(self, '_thread', None))
        self._thread.start()

    def _on_loaded(self, counts: dict) -> None:
        self._counts = counts
        for (lik, imp), btn in self._cell_btns.items():
            sc  = lik * imp
            cnt = counts.get((lik, imp), 0)
            btn.setText(
                f"{sc}\n({cnt})" if cnt else str(sc))
            # Brighten cells with risks
            color = _severity_color(sc)
            if cnt:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        color: white;
                        border: 2px solid white;
                        border-radius: {Radius.SM}px;
                        font-size: 12pt; font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: white;
                        color: {color};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        color: rgba(255,255,255,0.6);
                        border: none;
                        border-radius: {Radius.SM}px;
                        font-size: 14pt; font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: white;
                        color: {color};
                    }}
                """)

    # ── Cell click ────────────────────────────────────────────────────────────

    def _on_cell_click(self, lik: int, imp: int,
                        score: int) -> None:
        cnt = self._counts.get((lik, imp), 0)
        if cnt == 0:
            QMessageBox.information(
                self, "Risk Matrix",
                f"Score {score} "
                f"(L{lik} × I{imp}): "
                f"No risks logged at this cell.")
            return
        dlg = CellRisksDialog(lik, imp, score, self)
        dlg.exec()
