"""
ui/audit_log.py
────────────────
Audit Log / Activity Center — Phase 6 migration.

Matches Image 2 layout:
  KPI strip (6 cards: total, risk changes, treatment activity,
             AI activity, reports, failed ops)
  Two-column body:
    Left  — filter sidebar (All Activity / Risk Changes / Treatment /
             AI Activity / Reports / Settings / System) with counts
    Right — scrollable activity timeline (dot + timestamp + label +
             detail + status tag)

All DB queries run on a QThread. The timeline reloads instantly
when a filter is clicked.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from core.database.db import get_db, today, now_str


# ── Background loader ─────────────────────────────────────────────────────────

class AuditLoader(QObject):
    finished = Signal(object, object)  # list, dict — cross-thread safe
    error    = Signal(str)

    WHERE = {
        "All":       "",
        "RISK":      "WHERE action IN ('CREATE','UPDATE','DELETE')",
        "TREATMENT": ("WHERE action LIKE 'TREATMENT%' "
                      "OR action='RESIDUAL_SYNC'"),
        "AI":        "WHERE action LIKE 'AI%'",
        "EXPORT":    "WHERE action LIKE 'EXPORT%'",
        "SETTINGS":  ("WHERE action LIKE '%SCOPE%' "
                      "OR action LIKE '%SETTINGS%'"),
        "SYSTEM":    ("WHERE action IN ('APP_START','DB_BACKUP',"
                      "'DB_RESTORE','SCHEMA_MIGRATION')"),
    }

    def __init__(self, key: str = "All"):
        super().__init__()
        self._key = key

    def run(self) -> None:
        try:
            with get_db() as conn:
                where = self.WHERE.get(self._key, "")
                rows = [dict(r) for r in conn.execute(
                    f"SELECT * FROM audit_log {where} "
                    f"ORDER BY id DESC LIMIT 200").fetchall()]
                # Group counts for sidebar
                counts = {
                    "All": conn.execute(
                        "SELECT COUNT(*) FROM audit_log"
                    ).fetchone()[0],
                    "RISK": conn.execute(
                        "SELECT COUNT(*) FROM audit_log "
                        "WHERE action IN ('CREATE','UPDATE','DELETE')"
                    ).fetchone()[0],
                    "TREATMENT": conn.execute(
                        "SELECT COUNT(*) FROM audit_log "
                        "WHERE action LIKE 'TREATMENT%' "
                        "OR action='RESIDUAL_SYNC'"
                    ).fetchone()[0],
                    "AI": conn.execute(
                        "SELECT COUNT(*) FROM audit_log "
                        "WHERE action LIKE 'AI%'"
                    ).fetchone()[0],
                    "EXPORT": conn.execute(
                        "SELECT COUNT(*) FROM audit_log "
                        "WHERE action LIKE 'EXPORT%'"
                    ).fetchone()[0],
                    "SETTINGS": conn.execute(
                        "SELECT COUNT(*) FROM audit_log "
                        "WHERE action LIKE '%SCOPE%' "
                        "OR action LIKE '%SETTINGS%'"
                    ).fetchone()[0],
                    "SYSTEM": conn.execute(
                        "SELECT COUNT(*) FROM audit_log "
                        "WHERE action IN ('APP_START','DB_BACKUP',"
                        "'DB_RESTORE','SCHEMA_MIGRATION')"
                    ).fetchone()[0],
                }
            self.finished.emit(rows, counts)
        except Exception as e:
            self.error.emit(str(e))


# ── Action metadata ───────────────────────────────────────────────────────────

ACTION_META = {
    "CREATE":           ("◉", Colors.MEDIUM,     "Risk Created",        ("Risk",       Colors.MEDIUM)),
    "UPDATE":           ("✏", Colors.ACCENT_BLUE, "Risk Updated",        ("Risk",       Colors.MEDIUM)),
    "DELETE":           ("✕", Colors.CRITICAL,    "Risk Deleted",        ("Risk",       Colors.CRITICAL)),
    "TREATMENT_CREATE": ("◈", Colors.ACCENT_TEAL, "Treatment Created",   ("Treatment",  Colors.ACCENT_TEAL)),
    "TREATMENT_UPDATE": ("◈", Colors.ACCENT_CYAN, "Treatment Updated",   ("Treatment",  Colors.ACCENT_TEAL)),
    "TREATMENT_DELETE": ("◈", Colors.HIGH,        "Treatment Deleted",   ("Treatment",  Colors.HIGH)),
    "RESIDUAL_SYNC":    ("↓", Colors.SUCCESS_LT,  "Residual Synced",     None),
    "AI_ANALYSIS":      ("◎", Colors.PURPLE_LT,   "AI Analysis",         ("AI",         Colors.PURPLE_LT)),
    "AI_APPROVE":       ("✓", Colors.SUCCESS_LT,  "AI Approved",         ("AI",         Colors.SUCCESS_LT)),
    "EXPORT_PDF":       ("↗", Colors.ACCENT_BLUE, "PDF Generated",       ("Report",     Colors.ACCENT_BLUE)),
    "EXPORT_CSV":       ("↗", Colors.SUCCESS_LT,  "CSV Exported",        ("Export",     Colors.SUCCESS_LT)),
    "DB_BACKUP":        ("◧", Colors.ACCENT_BLUE, "Database Backup",     ("System",     Colors.TEXT_DIM)),
    "DB_RESTORE":       ("◧", Colors.MEDIUM,      "Database Restored",   ("System",     Colors.TEXT_DIM)),
    "APP_START":        ("⬡", Colors.TEXT_DIM,    "App Started",         None),
    "ORG_SCOPE_SAVE":   ("⊙", Colors.ACCENT_TEAL, "Scope Updated",       ("Settings",   Colors.ACCENT_TEAL)),
    "SCHEMA_MIGRATION": ("⚙", Colors.TEXT_DIM,    "Schema Migration",    None),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lbl(text, font=None, color=Colors.TEXT_MUTED) -> QLabel:
    l = QLabel(str(text))
    l.setFont(font or Fonts.label_sm())
    l.setStyleSheet(f"color: {color}; border: none;")
    return l


# ── Audit Log Page ────────────────────────────────────────────────────────────

class AuditLogPage(QWidget):
    """
    Activity Center — full audit log page.

    Signals
    -------
    navigate(str) : page navigation request
    """
    navigate = Signal(str)

    FILTER_GROUPS = [
        ("All Activity",       "All"),
        ("Risk Changes",       "RISK"),
        ("Treatment Activity", "TREATMENT"),
        ("AI Activity",        "AI"),
        ("Reports",            "EXPORT"),
        ("Settings",           "SETTINGS"),
        ("System",             "SYSTEM"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_filter = "All"
        self._filter_btns: dict[str, QPushButton] = {}
        self._thread: QThread | None = None
        self._setup_ui()
        QTimer.singleShot(100, self.refresh)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_kpi_strip())

        # Two-column body
        body = QWidget()
        body.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(body)
        hl.setContentsMargins(
            Spacing.XL, Spacing.MD, Spacing.XL, Spacing.XL)
        hl.setSpacing(Spacing.MD)

        hl.addWidget(self._build_filter_panel(), 1)
        hl.addWidget(self._build_timeline_panel(), 3)

        root.addWidget(body, 1)

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(
            Spacing.XL, Spacing.LG, Spacing.XL, Spacing.SM)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("⊙  Activity Center")
        t.setFont(Fonts.heading_1())
        t.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(t)
        s = QLabel(
            "Real-time audit trail  ·  Compliance intelligence  "
            "·  ISO/IEC 27001:2022 A.8 compliant")
        s.setFont(Fonts.label())
        s.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        col.addWidget(s)
        hl.addLayout(col)
        hl.addStretch()

        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px; padding: 0 14px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)
        return w

    def _build_kpi_strip(self) -> QWidget:
        self._kpi_strip = QWidget()
        self._kpi_strip.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(self._kpi_strip)
        hl.setContentsMargins(
            Spacing.XL, 0, Spacing.XL, Spacing.SM)
        hl.setSpacing(Spacing.SM)

        self._kpi_vals: dict[str, QLabel] = {}
        specs = [
            ("total",    "◉", "0", "Total Records",       Colors.TEXT_PRIMARY),
            ("risk",     "⊘", "0", "Risk Changes",        Colors.MEDIUM),
            ("treat",    "◈", "0", "Treatment Activity",  Colors.ACCENT_TEAL),
            ("ai",       "◎", "0", "AI Activity",         Colors.PURPLE_LT),
            ("export",   "↗", "0", "Reports Generated",   Colors.ACCENT_BLUE),
            ("system",   "⚙", "0", "System Events",       Colors.TEXT_DIM),
        ]
        for key, icon, val, label, color in specs:
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {Colors.BG_CARD};"
                f"border-radius: {Radius.LG}px;"
                f"border: 1px solid {Colors.BG_BORDER};")
            vl = QVBoxLayout(card)
            vl.setContentsMargins(
                Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
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

            sub_lbl = _lbl(label)
            vl.addWidget(sub_lbl)

            self._kpi_vals[key] = val_lbl
            hl.addWidget(card)
        return self._kpi_strip

    def _build_filter_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(
            Spacing.SM, Spacing.MD, Spacing.SM, Spacing.MD)
        vl.setSpacing(2)

        t = QLabel("Filter Activity")
        t.setFont(QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
        t.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        vl.addWidget(t)

        for label, key in self.FILTER_GROUPS:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)

            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setCursor(
                QCursor(Qt.CursorShape.PointingHandCursor))
            self._style_filter_btn(btn, key == "All")
            btn.clicked.connect(
                lambda checked, k=key: self._set_filter(k))
            rl.addWidget(btn, 1)

            # Count badge
            cnt_lbl = QLabel("—")
            cnt_lbl.setFont(Fonts.label_sm())
            cnt_lbl.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none;")
            cnt_lbl.setFixedWidth(34)
            cnt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            rl.addWidget(cnt_lbl)

            self._filter_btns[key] = (btn, cnt_lbl)
            vl.addWidget(row)

        vl.addStretch()
        return panel

    def _style_filter_btn(self, btn: QPushButton,
                           active: bool) -> None:
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.ACCENT_RED};
                    color: white; border: none;
                    border-radius: {Radius.SM}px;
                    padding: 0 10px; text-align: left;
                    font-size: 10pt; font-weight: bold;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Colors.TEXT_MUTED}; border: none;
                    border-radius: {Radius.SM}px;
                    padding: 0 10px; text-align: left;
                    font-size: 10pt;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BG_BORDER};
                    color: {Colors.TEXT_PRIMARY};
                }}
            """)

    def _build_timeline_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Timeline header
        hdr = QWidget()
        hdr.setFixedHeight(44)
        hdr.setStyleSheet("border: none;")
        hhl = QHBoxLayout(hdr)
        hhl.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        title = QLabel("Recent Activity")
        title.setFont(
            QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        hhl.addWidget(title)
        hhl.addStretch()

        live_f = QFrame()
        live_f.setFixedHeight(24)
        live_f.setStyleSheet(
            f"background-color: #0D3321;"
            f"border-radius: {Radius.SM}px; border: none;")
        ll = QHBoxLayout(live_f)
        ll.setContentsMargins(8, 0, 8, 0)
        live_lbl = QLabel("● Live")
        live_lbl.setFont(Fonts.label_sm())
        live_lbl.setStyleSheet(
            f"color: {Colors.SUCCESS_LT}; border: none;")
        ll.addWidget(live_lbl)
        hhl.addWidget(live_f)
        vl.addWidget(hdr)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._timeline_inner = QWidget()
        self._timeline_inner.setStyleSheet("border: none;")
        self._timeline_layout = QVBoxLayout(
            self._timeline_inner)
        self._timeline_layout.setContentsMargins(0, 0, 0, 0)
        self._timeline_layout.setSpacing(1)
        scroll.setWidget(self._timeline_inner)
        vl.addWidget(scroll, 1)
        return panel

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if self._thread is not None and not self._thread.isRunning():
            self._thread = None  # clear stale reference
        self._thread = QThread()
        self._loader = AuditLoader(self._current_filter)
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.finished.connect(self._on_loaded)
        self._loader.error.connect(
            lambda e: print(f"Audit error: {e}"))
        self._loader.finished.connect(self._thread.quit)
        self._loader.error.connect(self._thread.quit)
        self._thread.finished.connect(self._loader.deleteLater)
        self._thread.finished.connect(
            lambda: setattr(self, '_thread', None))
        self._thread.start()

    def _on_loaded(self, rows: list, counts: dict) -> None:
        # Update KPI strip
        self._kpi_vals["total"].setText(str(counts.get("All",0)))
        self._kpi_vals["risk"].setText(str(counts.get("RISK",0)))
        self._kpi_vals["treat"].setText(
            str(counts.get("TREATMENT",0)))
        self._kpi_vals["ai"].setText(str(counts.get("AI",0)))
        self._kpi_vals["export"].setText(
            str(counts.get("EXPORT",0)))
        self._kpi_vals["system"].setText(
            str(counts.get("SYSTEM",0)))

        # Update filter counts
        for key, (btn, cnt_lbl) in self._filter_btns.items():
            cnt_lbl.setText(str(counts.get(key, "—")))

        # Rebuild timeline
        while self._timeline_layout.count():
            item = self._timeline_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            empty = _lbl(
                "No activity recorded for this filter.",
                font=Fonts.label(), color=Colors.TEXT_MUTED)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._timeline_layout.addWidget(empty)
            self._timeline_layout.addStretch()
            return

        for i, lg in enumerate(rows):
            action = lg.get("action", "")
            meta   = ACTION_META.get(action)
            if meta:
                icon, color, label, tag_info = meta
            else:
                icon  = "·"
                color = Colors.TEXT_DIM
                label = action.replace("_", " ").title()
                tag_info = None

            ts = (lg.get("timestamp") or "")[:16].replace("T", " ")
            bg = Colors.BG_CARD2 if i % 2 == 0 else "transparent"

            row = QFrame()
            row.setStyleSheet(
                f"background-color: {bg}; border: none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(Spacing.MD, 6, Spacing.MD, 6)
            rl.setSpacing(Spacing.SM)

            # Dot
            dot = QLabel(icon)
            dot.setFont(QFont(Fonts.FAMILY, 10))
            dot.setStyleSheet(
                f"color: {color}; border: none;")
            dot.setFixedWidth(16)
            rl.addWidget(dot)

            # Timestamp
            ts_lbl = _lbl(ts)
            ts_lbl.setFixedWidth(115)
            rl.addWidget(ts_lbl)

            # Action label
            act_lbl = QLabel(label)
            act_lbl.setFont(Fonts.label_sm_bold())
            act_lbl.setStyleSheet(
                f"color: {color}; border: none;")
            act_lbl.setFixedWidth(140)
            rl.addWidget(act_lbl)

            # Detail
            detail = QLabel(
                (lg.get("detail") or "—")[:70])
            detail.setFont(Fonts.label_sm())
            detail.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            rl.addWidget(detail, 1)

            # Status tag
            if tag_info:
                tag_label, tag_color = tag_info
                tf = QFrame()
                tf.setFixedHeight(20)
                tf.setStyleSheet(
                    f"background-color: {tag_color};"
                    f"border-radius: {Radius.SM}px; border: none;")
                tl = QHBoxLayout(tf)
                tl.setContentsMargins(6, 0, 6, 0)
                t_lbl = QLabel(tag_label)
                t_lbl.setFont(Fonts.badge())
                t_lbl.setStyleSheet("color: white; border: none;")
                tl.addWidget(t_lbl)
                rl.addWidget(tf)

            self._timeline_layout.addWidget(row)

        self._timeline_layout.addStretch()

    # ── Filter switching ──────────────────────────────────────────────────────

    def _set_filter(self, key: str) -> None:
        self._current_filter = key
        for k, (btn, _) in self._filter_btns.items():
            self._style_filter_btn(btn, k == key)
        self.refresh()
