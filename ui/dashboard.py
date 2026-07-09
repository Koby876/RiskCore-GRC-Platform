"""
ui/dashboard.py — RiskCore Enterprise Dashboard

Thread safety rules applied here:
- refresh() is guarded: if a thread is already running it is ignored.
- The QThread is parented to self so Qt owns it and won't GC it.
- Worker is parented to the thread so it moves and cleans up correctly.
- finished → thread.quit → thread.deleteLater → worker.deleteLater
- self._thread is set to None after cleanup so re-entrant calls are safe.
- __init__ does NOT call refresh() directly — main_window calls it after
  navigate(), which happens after app.exec() is entered.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QPushButton, QSizePolicy,
    QGridLayout, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from widgets.cards import (
    KpiCard, FwCoverageRow, Divider,
)
from core.database.db import (
    get_stats, get_risks, get_organisation_scope,
    get_pipeline_treatments, get_db, today, now_str,
    NIST_FUNCTIONS, days_until, NIST_COLORS, TREAT_COLORS,
)
from core.services.ai_service import build_framework_coverage_report


class DashboardDataWorker(QObject):
    """Loads all dashboard data off the UI thread."""
    finished = Signal(object)  # dict — use object for cross-thread safety
    error    = Signal(str)

    def run(self) -> None:
        import traceback as _tb
        try:
            stats    = get_stats()
            risks    = get_risks()
            scope    = get_organisation_scope()
            pipeline = get_pipeline_treatments()
            cov      = build_framework_coverage_report([dict(r) for r in risks])

            nist_dist = {}
            with get_db() as conn:
                for fn in NIST_FUNCTIONS:
                    cnt = conn.execute(
                        "SELECT COUNT(*) FROM risks WHERE nist_function=?",
                        (fn,)).fetchone()[0]
                    avg = conn.execute(
                        "SELECT AVG(COALESCE(risk_score,0)) FROM risks "
                        "WHERE nist_function=?", (fn,)).fetchone()[0]
                    nist_dist[fn] = {"count": cnt, "avg": round(avg or 0, 1)}

            # Convert to dicts — sqlite3.Row can't pass through Qt Signal(dict)
            risks_dicts = [dict(r) for r in risks]
            top_risks = sorted(
                risks_dicts,
                key=lambda r: int(r.get("risk_score") or 0),
                reverse=True)[:8]

            with get_db() as conn:
                logs = conn.execute(
                    "SELECT timestamp, action, detail "
                    "FROM audit_log ORDER BY id DESC LIMIT 8"
                ).fetchall()
                tc_map = {}
                for row in conn.execute(
                    "SELECT risk_id, COUNT(*) as c FROM treatments "
                    "WHERE status NOT IN ('Ineffective') GROUP BY risk_id"):
                    tc_map[str(row["risk_id"])] = row["c"]  # str key for Qt Signal

            self.finished.emit({
                "stats":      stats,
                "scope":      scope,
                "pipeline":   pipeline,
                "cov":        cov,
                "nist_dist":  nist_dist,
                "top_risks":  top_risks,
                "logs":       logs,
                "tc_map":     tc_map,
                "risk_count": len(risks),
            })
        except Exception as e:
            import traceback as _tb
            print("[DashboardWorker] EXCEPTION:", flush=True)
            _tb.print_exc()
            self.error.emit(str(e))


class DashboardPage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._exec_summary  = None
        self._thread: QThread | None = None   # None = no thread running
        self._setup_ui()
        # Do NOT call refresh() here — main_window calls it after navigate()

    def set_exec_summary(self, summary: dict | None) -> None:
        self._exec_summary = summary

    def refresh(self) -> None:
        """Start background data load. Ignored if already loading."""
        if self._thread is not None and self._thread.isRunning():
            return  # already loading — do not start a second thread
        if self._thread is not None and not self._thread.isRunning():
            self._thread = None  # clear stale reference

        # Parent the thread to self so Qt owns the lifetime
        self._thread = QThread()
        self._worker = DashboardDataWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_data_loaded)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_done)

        self._thread.start()

    def _on_thread_done(self) -> None:
        self._thread = None

    # ── UI setup ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._content.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        scroll.setWidget(self._content)
        root.addWidget(scroll)

        self._main_layout = QVBoxLayout(self._content)
        self._main_layout.setContentsMargins(
            Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        self._main_layout.setSpacing(Spacing.MD)

        loading = QLabel("Loading dashboard...")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 14pt;")
        self._main_layout.addWidget(loading)

    def _clear_content(self) -> None:
        while self._main_layout.count():
            item = self._main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ── Data loaded ───────────────────────────────────────────────

    def _on_data_loaded(self, data: dict) -> None:
        self._clear_content()
        self._build_header(data)
        self._build_risk_kpis(data["stats"])
        self._build_treatment_kpis(data["stats"])
        self._build_middle_row(data)
        self._build_lower_row(data)
        if self._exec_summary:
            self._build_exec_intel(self._exec_summary, data["stats"])
        self._build_bottom_row(data)
        self._main_layout.addStretch()

    def _on_error(self, msg: str) -> None:
        print(f"[Dashboard] error: {msg}", flush=True)
        self._clear_content()
        lbl = QLabel(f"⚠  Dashboard error: {msg}")
        lbl.setStyleSheet(f"color: {Colors.CRITICAL}; font-size: 11pt;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(lbl)

    # ── Header ────────────────────────────────────────────────────

    def _build_header(self, data: dict) -> None:
        scope   = data.get("scope")
        org     = scope.get("organisation_name", "RiskCore") if scope else "RiskCore"
        assess  = scope.get("assessment_name", "") if scope else ""
        posture = data["cov"].get("posture", "Unknown")

        hdr = QFrame()
        hdr.setStyleSheet(
            f"background-color: {Colors.BG_SIDEBAR};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)

        brand_row = QHBoxLayout()
        import os as _os, sys as _sys
        from PySide6.QtGui import QPixmap
        _cands = []
        if hasattr(_sys, "_MEIPASS"):
            _cands.append(_os.path.join(_sys._MEIPASS, "assets", "images", "riskcore_logo.png"))
        _cands.append(_os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            "..", "assets", "images", "riskcore_logo.png"))
        _cands.append(_os.path.join(
            _os.path.dirname(_sys.executable),
            "assets", "images", "riskcore_logo.png"))
        _cands.append(_os.path.join(
            _os.path.dirname(_sys.executable),
            "_internal", "assets", "images", "riskcore_logo.png"))
        _lp = next((p for p in _cands if _os.path.exists(p)), None)
        if _lp:
            hex_lbl = QLabel()
            _pix = QPixmap(_lp).scaled(
                32, 32,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            hex_lbl.setPixmap(_pix)
            hex_lbl.setFixedSize(32, 32)
        else:
            hex_lbl = QLabel("⬡")
            hex_lbl.setFont(QFont(Fonts.FAMILY, 16))
            hex_lbl.setStyleSheet(f"color: {Colors.ACCENT_RED};")
        brand_row.addWidget(hex_lbl)
        brand_name = QLabel("  RiskCore")
        brand_name.setFont(QFont(Fonts.FAMILY, 13, QFont.Weight.Bold))
        brand_name.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        brand_row.addWidget(brand_name)
        brand_row.addStretch()
        hl.addLayout(brand_row)

        meta_parts = [assess, org, today()] if assess else [org, today()]
        meta_parts += ["NIST CSF 2.0", "ISO/IEC 27001:2022",
                       "MITRE ATT&CK", "CIS Controls v8", "CIA Triad"]
        meta = QLabel("  ·  ".join(meta_parts))
        meta.setFont(Fonts.label_sm())
        meta.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        hl.addWidget(meta, 1)

        p_color = {
            "Critical": Colors.CRITICAL, "High": Colors.HIGH,
            "Medium": Colors.MEDIUM, "Low": Colors.LOW,
        }.get(posture, Colors.TEXT_MUTED)
        p_lbl = QLabel(posture)
        p_lbl.setFont(QFont(Fonts.FAMILY, 10, QFont.Weight.Bold))
        p_lbl.setStyleSheet(f"color: {p_color};")
        hl.addWidget(p_lbl)

        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px; padding: 5px 14px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)

        self._main_layout.addWidget(hdr)

    # ── KPI rows ──────────────────────────────────────────────────

    def _kpi_grid(self, items: list) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        for title, value, sub, icon, color, bg in items:
            card = KpiCard(title=title, value=value, sub=sub,
                           icon=icon, value_color=color, bg_color=bg)
            card.setMinimumHeight(100)
            layout.addWidget(card)
        return row

    def _build_risk_kpis(self, s: dict) -> None:
        items = [
            ("Total Risks", s["total"], "in register",
             "▣", Colors.TEXT_PRIMARY, None),
            ("Critical", s["critical"], "score ≥ 15",
             "⊘", Colors.CRITICAL,
             Colors.BG_CRITICAL if s["critical"] else None),
            ("High", s["high"], "score 10–14",
             "↑", Colors.HIGH,
             Colors.BG_HIGH if s["high"] else None),
            ("Open", s["open"], "unresolved",
             "◉", Colors.MEDIUM, None),
            ("Overdue Review", s["overdue"], "past review date",
             "⏱", Colors.CRITICAL if s["overdue"] else Colors.TEXT_MUTED,
             Colors.BG_CRITICAL if s["overdue"] else None),
            ("AI Sourced", s["ai_sourced"], "from PDF",
             "◎", Colors.PURPLE_LT, None),
        ]
        self._main_layout.addWidget(self._kpi_grid(items))

    def _build_treatment_kpis(self, s: dict) -> None:
        items = [
            ("Total Treatments", s["treat_total"], "logged",
             "✓", Colors.SUCCESS_LT, None),
            ("Overdue Treatments", s["treat_overdue"], "past target date",
             "⚠", Colors.CRITICAL if s["treat_overdue"] else Colors.TEXT_MUTED,
             Colors.BG_CRITICAL if s["treat_overdue"] else None),
            ("Verify Queue", s["treat_verify"], "Completed → Verify",
             "◈", Colors.MEDIUM if s["treat_verify"] else Colors.TEXT_MUTED, None),
            ("Untreated High+", s["no_treatment"], "score ≥ 10, no plan",
             "⊗", Colors.HIGH if s["no_treatment"] else Colors.TEXT_MUTED,
             Colors.BG_HIGH if s["no_treatment"] else None),
        ]
        self._main_layout.addWidget(self._kpi_grid(items))

    # ── Middle row ────────────────────────────────────────────────

    def _build_middle_row(self, data: dict) -> None:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.MD)
        hl.addWidget(self._build_nist_card(data), 5)
        hl.addWidget(self._build_severity_card(data), 4)
        hl.addWidget(self._build_pipeline_card(data), 3)
        self._main_layout.addWidget(row)

    def _build_nist_card(self, data: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        title = QLabel("Risk Distribution by NIST CSF 2.0 Function")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        total_safe = max(data["stats"]["total"], 1)
        for fn in NIST_FUNCTIONS:
            fn_data = data["nist_dist"].get(fn, {"count": 0, "avg": 0})
            cnt   = fn_data["count"]
            avg   = fn_data["avg"]
            color = NIST_COLORS.get(fn, Colors.ACCENT_BLUE)

            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(Spacing.SM)

            fn_lbl = QLabel(fn)
            fn_lbl.setFont(QFont(Fonts.FAMILY, 9, QFont.Weight.Bold))
            fn_lbl.setStyleSheet(f"color: {color};")
            fn_lbl.setFixedWidth(68)
            row_l.addWidget(fn_lbl)

            bar = QProgressBar()
            bar.setRange(0, total_safe)
            bar.setValue(cnt)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {Colors.BG_BORDER};
                    border-radius: 4px; border: none;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 4px;
                }}
            """)
            row_l.addWidget(bar, 1)

            stat_lbl = QLabel(f"{cnt} risks · avg {avg}")
            stat_lbl.setFont(Fonts.label_sm())
            stat_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            stat_lbl.setFixedWidth(100)
            stat_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_l.addWidget(stat_lbl)

            vl.addWidget(row_w)

        vl.addStretch()
        return card

    def _build_severity_card(self, data: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        title = QLabel("Risks by Severity")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        dist  = data["cov"]["chart_data"]["risk_distribution"]
        total = max(sum(dist.values()), 1)
        n     = data["stats"]["total"]

        centre = QFrame()
        centre.setFixedSize(90, 90)
        centre.setStyleSheet(
            f"background-color: {Colors.BG_CARD2};"
            f"border-radius: 45px; border: none;")
        cl = QVBoxLayout(centre)
        cl.setContentsMargins(0, 0, 0, 0)
        num_lbl = QLabel(str(n))
        num_lbl.setFont(QFont(Fonts.FAMILY, 26, QFont.Weight.Bold))
        num_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(num_lbl)
        tot_lbl = QLabel("Total")
        tot_lbl.setFont(Fonts.label_sm())
        tot_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        tot_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(tot_lbl)
        vl.addWidget(centre, 0, Qt.AlignmentFlag.AlignHCenter)

        for label, key, color in [
            ("Critical", "Critical", Colors.CRITICAL),
            ("High",     "High",     Colors.HIGH),
            ("Medium",   "Medium",   Colors.MEDIUM),
            ("Low",      "Low",      Colors.LOW),
        ]:
            cnt = dist.get(key, 0)
            pct = int(cnt / total * 100)
            sr  = QWidget()
            sl  = QHBoxLayout(sr)
            sl.setContentsMargins(0, 2, 0, 2)
            sl.setSpacing(Spacing.SM)

            dot = QFrame()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
            sl.addWidget(dot)

            name_lbl = QLabel(label)
            name_lbl.setFont(Fonts.label_sm())
            name_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            name_lbl.setFixedWidth(55)
            sl.addWidget(name_lbl)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(pct)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {Colors.BG_BORDER};
                    border-radius: 4px; border: none;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 4px;
                }}
            """)
            sl.addWidget(bar, 1)

            cnt_lbl = QLabel(f"{cnt}  ({pct}%)")
            cnt_lbl.setFont(Fonts.label_sm())
            cnt_lbl.setStyleSheet(f"color: {color};")
            cnt_lbl.setFixedWidth(60)
            cnt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            sl.addWidget(cnt_lbl)
            vl.addWidget(sr)

        vl.addStretch()
        return card

    def _build_pipeline_card(self, data: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        title = QLabel("Treatment Pipeline")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        pipeline = data["pipeline"]
        if not pipeline:
            empty = QLabel("No active treatments")
            empty.setFont(Fonts.label())
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.addWidget(empty)
        else:
            for t in pipeline[:6]:
                tr = QFrame()
                tr.setStyleSheet(
                    f"background-color: {Colors.BG_CARD2};"
                    f"border-radius: {Radius.SM}px; border: none;")
                tl = QHBoxLayout(tr)
                tl.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
                tl.setSpacing(Spacing.SM)

                s_color  = TREAT_COLORS.get(t["strategy"], Colors.ACCENT_BLUE)
                badge_f  = QFrame()
                badge_f.setFixedSize(58, 20)
                badge_f.setStyleSheet(
                    f"background-color: {s_color}; border-radius: 4px; border: none;")
                badge_l  = QHBoxLayout(badge_f)
                badge_l.setContentsMargins(4, 0, 4, 0)
                badge_txt = QLabel(t["strategy"][:7])
                badge_txt.setFont(Fonts.badge())
                badge_txt.setStyleSheet("color: white; border: none;")
                badge_l.addWidget(badge_txt)
                tl.addWidget(badge_f)

                title_lbl = QLabel((t["title"] or "")[:28])
                title_lbl.setFont(Fonts.label_sm())
                title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
                tl.addWidget(title_lbl, 1)

                d = days_until(t["target_date"])
                if d is not None:
                    d_txt = (f"{abs(d)}d overdue" if d < 0
                             else f"{d}d left" if d <= 7 else f"{d}d")
                    d_col = (Colors.CRITICAL if d < 0
                             else Colors.MEDIUM if d <= 7 else Colors.TEXT_MUTED)
                    d_lbl = QLabel(d_txt)
                    d_lbl.setFont(Fonts.label_sm())
                    d_lbl.setStyleSheet(f"color: {d_col};")
                    tl.addWidget(d_lbl)

                vl.addWidget(tr)

        vl.addStretch()

        view_btn = QPushButton("View All Treatments →")
        view_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.ACCENT_RED};
                border: 1px solid {Colors.ACCENT_RED};
                border-radius: {Radius.SM}px; padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT_RED}; color: white;
            }}
        """)
        view_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        view_btn.clicked.connect(lambda: self.navigate.emit("treatments"))
        vl.addWidget(view_btn)
        return card

    # ── Lower row ─────────────────────────────────────────────────

    def _build_lower_row(self, data: dict) -> None:
        row = QWidget()
        hl  = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.MD)
        hl.addWidget(self._build_top_risks_card(data), 3)
        hl.addWidget(self._build_fw_coverage_card(data), 2)
        self._main_layout.addWidget(row)

    def _build_top_risks_card(self, data: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(2)

        title = QLabel("Top Critical Risks")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        hdr_row = QFrame()
        hdr_row.setStyleSheet(
            f"background-color: {Colors.BG_BORDER}; border-radius: 0px;")
        hdr_l = QHBoxLayout(hdr_row)
        hdr_l.setContentsMargins(Spacing.SM, 4, Spacing.SM, 4)
        hdr_l.setSpacing(0)
        for h, w in [("Risk", 0), ("Score", 60),
                      ("Owner", 110), ("NIST", 90), ("Status", 70)]:
            lbl = QLabel(h)
            lbl.setFont(Fonts.label_sm_bold())
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
            if w:
                lbl.setFixedWidth(w)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hdr_l.addWidget(lbl)
            else:
                hdr_l.addWidget(lbl, 1)
        vl.addWidget(hdr_row)

        for i, r in enumerate(data["top_risks"]):
            sc = int(r["risk_score"] or 0)
            bg = Colors.BG_CARD if i % 2 == 0 else Colors.BG_CARD2
            rr = QFrame()
            rr.setStyleSheet(f"background-color: {bg}; border: none;")
            rl = QHBoxLayout(rr)
            rl.setContentsMargins(Spacing.SM, 6, Spacing.SM, 6)
            rl.setSpacing(0)

            t_lbl = QLabel(str(r["title"] or "")[:38])
            t_lbl.setFont(Fonts.label())
            t_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; border: none;")
            rl.addWidget(t_lbl, 1)

            sc_lbl = QLabel(str(sc))
            sc_lbl.setFixedWidth(60)
            sc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sc_lbl.setFont(Fonts.label_bold())
            sc_lbl.setStyleSheet(
                f"color: {Colors.severity_color(sc)}; border: none;")
            rl.addWidget(sc_lbl)

            ow_lbl = QLabel(str(r["owner"] or "—")[:14])
            ow_lbl.setFixedWidth(110)
            ow_lbl.setFont(Fonts.label_sm())
            ow_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
            rl.addWidget(ow_lbl)

            nist_fn = r["nist_function"] or "—"
            nist_lbl = QLabel(nist_fn[:10])
            nist_lbl.setFixedWidth(90)
            nist_lbl.setFont(Fonts.label_sm())
            nist_lbl.setStyleSheet(
                f"color: {NIST_COLORS.get(nist_fn, Colors.TEXT_MUTED)}; border: none;")
            rl.addWidget(nist_lbl)

            status  = r["status"] or "—"
            st_col  = (Colors.MEDIUM if status == "Open" else
                       Colors.SUCCESS_LT if status in ("Mitigated","Closed")
                       else Colors.TEXT_MUTED)
            st_lbl  = QLabel(status[:8])
            st_lbl.setFixedWidth(70)
            st_lbl.setFont(Fonts.label_sm_bold())
            st_lbl.setStyleSheet(f"color: {st_col}; border: none;")
            rl.addWidget(st_lbl)

            vl.addWidget(rr)

        vl.addStretch()
        return card

    def _build_fw_coverage_card(self, data: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        title = QLabel("Framework Coverage")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        for fw_name, fw_data in data["cov"]["per_framework"].items():
            vl.addWidget(FwCoverageRow(
                framework=fw_name,
                pct=fw_data["coverage_pct"],
                confirmed=fw_data["confirmed"],
                total=fw_data["total"],
            ))

        hi = data["cov"].get("health_insights", {})
        needs_review = hi.get("frameworks_needing_review", [])
        if needs_review:
            warn = QLabel("⚠  Needs attention: " + ", ".join(needs_review))
            warn.setFont(Fonts.label_sm())
            warn.setStyleSheet(f"color: {Colors.MEDIUM}; border: none;")
            warn.setWordWrap(True)
            vl.addWidget(warn)

        vl.addStretch()

        fw_btn = QPushButton("View Framework Intelligence →")
        fw_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.ACCENT_BLUE};
                border: 1px solid {Colors.ACCENT_BLUE};
                border-radius: {Radius.SM}px; padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT_BLUE}; color: white;
            }}
        """)
        fw_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        fw_btn.clicked.connect(lambda: self.navigate.emit("framework"))
        vl.addWidget(fw_btn)
        return card

    # ── Executive intel ───────────────────────────────────────────

    def _build_exec_intel(self, es: dict, stats: dict) -> None:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        title = QLabel("Executive Intelligence  ·  from last AI analysis")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        grid = QWidget()
        gl   = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(Spacing.SM)
        gl.setColumnStretch(0, 1)
        gl.setColumnStretch(1, 1)

        posture = es.get("posture", "Unknown")
        p_color = {
            "Critical": Colors.CRITICAL, "High": Colors.HIGH,
            "Medium": Colors.MEDIUM, "Low": Colors.LOW,
        }.get(posture, Colors.TEXT_MUTED)

        def _cell(row, col, label, value, color):
            f2 = QFrame()
            f2.setStyleSheet(
                f"background-color: {Colors.BG_CARD2};"
                f"border-radius: {Radius.SM}px; border: none;")
            fl = QHBoxLayout(f2)
            fl.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            fl.setSpacing(Spacing.SM)
            l1 = QLabel(label)
            l1.setFont(Fonts.label_sm())
            l1.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
            l1.setFixedWidth(130)
            fl.addWidget(l1)
            v1 = QLabel(str(value or "—")[:100])
            v1.setFont(Fonts.label_sm())
            v1.setStyleSheet(f"color: {color}; border: none;")
            v1.setWordWrap(True)
            fl.addWidget(v1, 1)
            gl.addWidget(f2, row, col)

        _cell(0, 0, "Risk Posture",       posture,                      p_color)
        _cell(0, 1, "Posture Explanation", es.get("posture_explanation",""), Colors.TEXT_PRIMARY)
        _cell(1, 0, "Strongest Areas",    es.get("strongest_areas",""), Colors.SUCCESS_LT)
        _cell(1, 1, "Weakest Areas",      es.get("weakest_areas",""),   Colors.CRITICAL)

        priorities = es.get("immediate_priorities", [])
        recommendations = es.get("strategic_recommendations", [])
        if priorities:
            _cell(2, 0, "Immediate Priority", priorities[0], Colors.HIGH)
        if recommendations:
            _cell(2, 1, "Strategic Recommendation", recommendations[0], Colors.ACCENT_BLUE)

        vl.addWidget(grid)
        self._main_layout.addWidget(card)

    # ── Bottom row ────────────────────────────────────────────────

    def _build_bottom_row(self, data: dict) -> None:
        row = QWidget()
        hl  = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.MD)
        hl.addWidget(self._build_activity_card(data), 2)
        hl.addWidget(self._build_quick_actions(), 1)
        self._main_layout.addWidget(row)

    def _build_activity_card(self, data: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(4)

        title = QLabel("Recent Activity")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        ACTION_META = {
            "CREATE":           ("◉", Colors.MEDIUM,     "Risk Created"),
            "UPDATE":           ("✏", Colors.ACCENT_BLUE, "Risk Updated"),
            "DELETE":           ("✕", Colors.CRITICAL,    "Risk Deleted"),
            "TREATMENT_CREATE": ("◈", Colors.ACCENT_TEAL, "Treatment Created"),
            "TREATMENT_UPDATE": ("◈", Colors.ACCENT_CYAN, "Treatment Updated"),
            "TREATMENT_DELETE": ("◈", Colors.HIGH,        "Treatment Deleted"),
            "AI_ANALYSIS":      ("◎", Colors.PURPLE_LT,   "AI Analysis"),
            "AI_APPROVE":       ("✓", Colors.SUCCESS_LT,  "AI Approved"),
            "EXPORT_PDF":       ("↗", Colors.ACCENT_BLUE, "PDF Generated"),
            "DB_BACKUP":        ("◧", Colors.ACCENT_BLUE, "Database Backup"),
            "APP_START":        ("⬡", Colors.TEXT_DIM,    "App Started"),
            "ORG_SCOPE_SAVE":   ("⊙", Colors.ACCENT_TEAL, "Scope Updated"),
        }

        logs = data.get("logs", [])
        if not logs:
            empty = QLabel("No activity recorded yet.")
            empty.setFont(Fonts.label())
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            vl.addWidget(empty)
        else:
            for lg in logs:
                action = lg["action"]
                icon, color, label = ACTION_META.get(
                    action, ("·", Colors.TEXT_DIM,
                             action.replace("_"," ").title()))
                ts = (lg["timestamp"] or "")[:16].replace("T", " ")

                ar = QWidget()
                al = QHBoxLayout(ar)
                al.setContentsMargins(0, 2, 0, 2)
                al.setSpacing(Spacing.SM)

                dot = QLabel(icon)
                dot.setFont(QFont(Fonts.FAMILY, 10))
                dot.setStyleSheet(f"color: {color}; border: none;")
                dot.setFixedWidth(16)
                al.addWidget(dot)

                action_lbl = QLabel(label)
                action_lbl.setFont(Fonts.label_sm_bold())
                action_lbl.setStyleSheet(f"color: {color}; border: none;")
                action_lbl.setFixedWidth(140)
                al.addWidget(action_lbl)

                detail_lbl = QLabel((lg["detail"] or "—")[:50])
                detail_lbl.setFont(Fonts.label_sm())
                detail_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
                al.addWidget(detail_lbl, 1)

                ts_lbl = QLabel(ts)
                ts_lbl.setFont(Fonts.label_sm())
                ts_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; border: none;")
                al.addWidget(ts_lbl)

                vl.addWidget(ar)

        vl.addStretch()
        audit_btn = QPushButton("View Full Audit Log →")
        audit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED}; border: none;
                font-size: 9pt; text-align: right;
            }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        audit_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        audit_btn.clicked.connect(lambda: self.navigate.emit("audit"))
        vl.addWidget(audit_btn, alignment=Qt.AlignmentFlag.AlignRight)
        return card

    def _build_quick_actions(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)

        title = QLabel("Quick Actions")
        title.setFont(Fonts.heading_3())
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)

        actions = [
            ("+ New Risk",            Colors.ACCENT_RED,  "add"),
            ("◎ Run AI Analysis",     Colors.PURPLE_LT,   "ai"),
            ("↗ Generate PDF Report", Colors.ACCENT_BLUE, "export"),
            ("≡ View Risk Register",  Colors.BG_BORDER,   "register"),
            ("◈ Manage Treatments",   Colors.ACCENT_TEAL, "treatments"),
            ("⊞ Risk Matrix",         Colors.BG_BORDER,   "matrix"),
            ("⊙ Audit Log",           Colors.BG_BORDER,   "audit"),
            ("⚙ Settings",           Colors.BG_BORDER,   "settings"),
        ]
        for label, color, page in actions:
            btn = QPushButton(label)
            text_color = "white" if color != Colors.BG_BORDER else Colors.TEXT_MUTED
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: {text_color}; border: none;
                    border-radius: {Radius.SM}px;
                    padding: 7px 12px; text-align: left; font-size: 11pt;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BG_CARD2};
                    color: {Colors.TEXT_PRIMARY};
                }}
            """)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(lambda checked, p=page: self.navigate.emit(p))
            vl.addWidget(btn)

        vl.addStretch()
        return card
