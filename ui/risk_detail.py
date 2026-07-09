"""
ui/risk_detail.py
──────────────────
Risk Detail Dialog — Phase 4.

A QDialog with three tabs:
  Details              — all risk fields (24 rows)
  Framework Intelligence — per-framework mapping with confidence badges
  Treatments           — linked treatment plans with Edit/Delete per row

Action bar at bottom: Delete · Edit · + Add Treatment · Close

Emits signals rather than calling page navigation directly so the
register page can refresh itself after edits.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QTabWidget, QGridLayout,
    QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from core.database.db import (
    get_risk, get_treatments, delete_risk, delete_treatment,
    get_framework_mapping, update_risk,
    LIKELIHOOD_LBL, IMPACT_LBL, NIST_COLORS,
    audit,
)
from core.services.ai_service import get_800_53_recommendations


def _lbl(text: str, font=None,
         color: str = Colors.TEXT_PRIMARY) -> QLabel:
    l = QLabel(str(text or "—"))
    l.setFont(font or Fonts.label())
    l.setStyleSheet(f"color: {color}; border: none;")
    l.setWordWrap(True)
    return l


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"background-color: {Colors.BG_CARD};"
        f"border-radius: {Radius.MD}px;"
        f"border: 1px solid {Colors.BG_BORDER};")
    return f


def _btn(text, color=Colors.BG_BORDER,
         text_color=Colors.TEXT_MUTED) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(32)
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


class RiskDetailDialog(QDialog):
    """
    Modal Risk Detail dialog.

    Signals
    -------
    risk_deleted(int)       : emitted when risk is deleted
    edit_requested(int)     : emitted when Edit is clicked
    treatment_added(int)    : emitted when + Add Treatment is clicked
    data_changed()          : emitted after any treatment delete
    """
    risk_deleted     = Signal(int)
    edit_requested   = Signal(int)
    treatment_added  = Signal(int)
    data_changed     = Signal()

    def __init__(self, rid: int, parent=None):
        super().__init__(parent)
        self.rid = rid
        r = get_risk(rid)
        self._r  = dict(r) if r else None
        if not self._r:
            self.reject()
            return

        sc = int(self._r["risk_score"] or 0)
        sev_col = Colors.severity_color(sc)
        sev_lbl = Colors.severity_label(sc)

        self.setWindowTitle(f"Risk #{rid}  ·  {sev_lbl}")
        self.resize(920, 780)
        self.setMinimumSize(800, 640)
        self.setStyleSheet(
            f"background-color: {Colors.BG_DEEP}; border: none;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Coloured header band
        self._build_header(sc)
        root.addWidget(self._hdr_widget)

        # Score + status strip (just below header)
        strip = QWidget()
        strip.setFixedHeight(48)
        strip.setStyleSheet(
            f"background: {Colors.BG_CARD};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        sl = QHBoxLayout(strip)
        sl.setContentsMargins(Spacing.LG, 6, Spacing.LG, 6)
        sl.setSpacing(Spacing.MD)

        # Score badge
        sc_lbl = QLabel(f"  {sc}  ")
        sc_lbl.setFont(QFont(Fonts.FAMILY, 18, QFont.Weight.Bold))
        sc_lbl.setStyleSheet(
            f"color: white; background: {sev_col};"
            f"border-radius: 6px; padding: 2px 8px;")
        sl.addWidget(sc_lbl)

        sev_tag = QLabel(sev_lbl.upper())
        sev_tag.setFont(QFont(Fonts.FAMILY, 9, QFont.Weight.Bold))
        sev_tag.setStyleSheet(
            f"color: {sev_col}; border: none; letter-spacing: 1px;")
        sl.addWidget(sev_tag)

        # Vertical divider
        d1 = QFrame()
        d1.setFixedWidth(1)
        d1.setFixedHeight(26)
        d1.setStyleSheet(f"background: {Colors.BG_BORDER};")
        sl.addWidget(d1)

        # Status badge
        st = str(self._r.get("status","Open"))
        st_colors = {"Open": Colors.MEDIUM,
                      "In Progress": Colors.ACCENT_BLUE,
                      "Mitigated": Colors.SUCCESS_LT,
                      "Closed": Colors.SUCCESS_LT,
                      "Accepted": Colors.TEXT_MUTED}
        st_c = st_colors.get(st, Colors.TEXT_MUTED)
        st_b = QLabel(f"  {st.upper()}  ")
        st_b.setFont(QFont(Fonts.FAMILY, 8, QFont.Weight.Bold))
        st_b.setStyleSheet(
            f"color: white; background: {st_c};"
            f"border-radius: 4px; padding: 2px 6px;")
        sl.addWidget(st_b)

        owner = str(self._r.get("owner") or "")
        if owner:
            sl.addWidget(QFrame())  # spacer
            d2 = QFrame()
            d2.setFixedWidth(1)
            d2.setFixedHeight(26)
            d2.setStyleSheet(f"background: {Colors.BG_BORDER};")
            sl.addWidget(d2)
            ow_l = QLabel(f"👤  {owner}")
            ow_l.setFont(QFont(Fonts.FAMILY, 9))
            ow_l.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
            sl.addWidget(ow_l)

        sl.addStretch()

        # Inherent → Residual strip
        isc = int(self._r.get("inherent_score") or sc)
        rsc = self._r.get("residual_score") or "—"
        ri_lbl = QLabel(
            f"Inherent: <b style='color:{sev_col}'>{isc}</b>"
            f"  →  Residual: <b>{rsc}</b>")
        ri_lbl.setFont(QFont(Fonts.FAMILY, 9))
        ri_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
        ri_lbl.setTextFormat(Qt.TextFormat.RichText)
        sl.addWidget(ri_lbl)

        root.addWidget(strip)

        # Tab widget
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {Colors.BG_DEEP};
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                padding: 10px 20px;
                border: none;
                border-bottom: 2px solid transparent;
                font-size: 9.5pt;
            }}
            QTabBar::tab:selected {{
                color: {Colors.TEXT_PRIMARY};
                border-bottom: 2px solid {Colors.ACCENT_RED};
                font-weight: bold;
            }}
            QTabBar::tab:hover {{
                color: {Colors.TEXT_PRIMARY};
                background-color: {Colors.BG_CARD2};
            }}
        """)
        tabs.addTab(self._build_details_tab(),         "  Overview  ")
        tabs.addTab(self._build_framework_tab(),       "  Framework Intelligence  ")
        tabs.addTab(self._build_treatments_tab(),      "  Treatments  ")
        tabs.addTab(self._build_cost_tab(),            "  Cost & ROSI  ")
        root.addWidget(tabs, 1)

        # Action bar
        self._build_action_bar()
        root.addWidget(self._action_bar)

    # ── Header band ───────────────────────────────────────────────────────────

    def _build_header(self, sc: int) -> None:
        self._hdr_widget = QFrame()
        self._hdr_widget.setFixedHeight(52)
        bg = Colors.severity_bg(sc)
        self._hdr_widget.setStyleSheet(
            f"background-color: {bg}; border: none;")
        hl = QHBoxLayout(self._hdr_widget)
        hl.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)

        title = QLabel(
            f"  {Colors.severity_label(sc)}  ·  "
            f"Score {sc}  ·  {str(self._r['title'] or '')[:60]}")
        title.setFont(QFont(Fonts.FAMILY, 13, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {Colors.severity_color(sc)}; border: none;")
        hl.addWidget(title, 1)

        if (self._r.get("source") or "Manual") == "AI Analysis":
            ai_lbl = QLabel("◎  AI")
            ai_lbl.setFont(Fonts.label())
            ai_lbl.setStyleSheet(
                f"color: {Colors.PURPLE_LT}; border: none;")
            hl.addWidget(ai_lbl)

    # ── Details tab ───────────────────────────────────────────────────────────

    def _build_details_tab(self) -> QWidget:
        """Modern card-based details tab matching enterprise screenshots."""
        from core.database.lookups import get_mitre_info, cis_display

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"background: {Colors.BG_DEEP}; border: none;")
        inner = QWidget()
        inner.setStyleSheet(f"background: {Colors.BG_DEEP};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(Spacing.LG, Spacing.MD,
                               Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.MD)
        scroll.setWidget(inner)

        r   = self._r
        sc  = int(r.get("risk_score") or 0)
        lik = int(r.get("likelihood") or 1)
        imp = int(r.get("impact") or 1)
        sev_col = Colors.severity_color(sc)

        def _card_label(text):
            l = QLabel(text.upper())
            l.setFont(QFont(Fonts.FAMILY, 7, QFont.Weight.Bold))
            l.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; letter-spacing: 1px; border: none;")
            return l

        def _row(grid, row_i, key, val, val_color=None):
            kl = QLabel(key)
            kl.setFont(Fonts.label_sm())
            kl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            kl.setAlignment(Qt.AlignmentFlag.AlignTop |
                             Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(kl, row_i, 0, Qt.AlignmentFlag.AlignTop)
            vl2 = QLabel(str(val or "—"))
            vl2.setFont(Fonts.label_sm())
            vl2.setStyleSheet(
                f"color: {val_color or Colors.TEXT_PRIMARY}; border: none;")
            vl2.setWordWrap(True)
            grid.addWidget(vl2, row_i, 1)

        def _make_card(*rows_data):
            card = _card()
            cg = QGridLayout(card)
            cg.setContentsMargins(Spacing.LG, Spacing.MD,
                                   Spacing.LG, Spacing.MD)
            cg.setSpacing(6)
            cg.setColumnMinimumWidth(0, 160)
            cg.setColumnStretch(1, 1)
            return card, cg

        # ── Risk Information card ─────────────────────────────────────────────
        vl.addWidget(_card_label("Risk Information"))
        info_card, ig = _make_card()
        _row(ig, 0, "Title",     r.get("title") or "—")
        _row(ig, 1, "Category",  r.get("category") or "—")
        _row(ig, 2, "Likelihood",
             f"{lik} — {LIKELIHOOD_LBL.get(lik,'')}",
             Colors.TEXT_PRIMARY)
        _row(ig, 3, "Impact",
             f"{imp} — {IMPACT_LBL.get(imp,'')}",
             Colors.TEXT_PRIMARY)
        _row(ig, 4, "Inherent Score",
             f"{sc} ({Colors.severity_label(sc)})", sev_col)
        _row(ig, 5, "Residual Score",
             str(r.get("residual_score") or "—"),
             Colors.SUCCESS_LT if r.get("residual_score") else None)
        _row(ig, 6, "Risk Velocity",
             {1:"Slow",2:"Medium",3:"Fast",4:"Immediate"}.get(
                 int(r.get("risk_velocity") or 2), "Medium"))
        _row(ig, 7, "Risk Category",
             r.get("nist_category") or "—")
        _row(ig, 8, "Confidence",  r.get("confidence") or "—")
        _row(ig, 9, "Priority",    r.get("priority") or "—")
        vl.addWidget(info_card)

        # ── NIST CSF 2.0 card ─────────────────────────────────────────────────
        vl.addWidget(_card_label("Framework Mapping"))
        fw_card, fg = _make_card()
        mitre_info = get_mitre_info(r.get("mitre_tactic") or "Not Applicable")
        mitre_id   = mitre_info.get("id","")
        mitre_str  = (f"{mitre_id}  {r.get('mitre_tactic','—')}"
                      if mitre_id and mitre_id != "—"
                      else str(r.get("mitre_tactic") or "—"))
        if r.get("mitre_technique"):
            mitre_str += f"  |  {r['mitre_technique']}"
        _row(fg, 0, "NIST CSF 2.0",
             f"{r.get('nist_function','—')} › {r.get('nist_category','—')}"
             f"  {r.get('nist_subcategory','') or ''}",
             Colors.FW_NIST)
        _row(fg, 1, "ISO 27001:2022",
             f"{r.get('iso_domain','—')}  ·  {r.get('iso_control','') or ''}",
             Colors.FW_ISO)
        _row(fg, 2, "MITRE ATT&CK", mitre_str, Colors.FW_MITRE)
        _row(fg, 3, "CIS Control",
             cis_display(str(r.get("cis_control") or "Not Applicable")),
             Colors.FW_CIS)
        _row(fg, 4, "CIA Component",
             r.get("cia_component") or "—", Colors.FW_CIA)
        vl.addWidget(fw_card)

        # ── Owner / Dates card ────────────────────────────────────────────────
        vl.addWidget(_card_label("Ownership & Dates"))
        od_card, og = _make_card()
        _row(og, 0, "Owner",         r.get("owner") or "—")
        _row(og, 1, "Status",        r.get("status") or "—")
        _row(og, 2, "Review Date",   r.get("review_date") or "—")
        _row(og, 3, "Created",       r.get("date_identified") or "—")
        _row(og, 4, "Last Modified", r.get("date_modified") or "—")
        _row(og, 5, "Last Updated By",
             r.get("last_updated_by") or "—")
        _row(og, 6, "Source",        r.get("source") or "Manual")
        vl.addWidget(od_card)

        # ── Description card ──────────────────────────────────────────────────
        if r.get("description"):
            vl.addWidget(_card_label("Description"))
            desc_card = _card()
            dl = QVBoxLayout(desc_card)
            dl.setContentsMargins(Spacing.LG, Spacing.MD,
                                   Spacing.LG, Spacing.MD)
            desc_lbl = QLabel(str(r["description"]))
            desc_lbl.setFont(Fonts.label())
            desc_lbl.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            desc_lbl.setWordWrap(True)
            dl.addWidget(desc_lbl)
            vl.addWidget(desc_card)

        # ── Controls & Mitigation ─────────────────────────────────────────────
        vl.addWidget(_card_label("Controls & Mitigation"))
        ctrl_card = _card()
        clg = QGridLayout(ctrl_card)
        clg.setContentsMargins(Spacing.LG, Spacing.MD,
                                Spacing.LG, Spacing.MD)
        clg.setSpacing(8)
        clg.setColumnMinimumWidth(0, 160)
        clg.setColumnStretch(1, 1)

        # Existing Controls with coloured badge
        ctrl_val = r.get("existing_controls") or "None documented"
        has_ctrl = bool(r.get("existing_controls"))
        ctrl_badge_c = Colors.SUCCESS_LT if has_ctrl else Colors.HIGH
        ctrl_badge_t = "In Place" if has_ctrl else "Weak"
        clg.addWidget(
            QLabel("Existing Controls"),
            0, 0, Qt.AlignmentFlag.AlignTop)
        clg.itemAt(clg.count()-1).widget().setFont(Fonts.label_sm())
        clg.itemAt(clg.count()-1).widget().setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        ctrl_row = QHBoxLayout()
        ctrl_lbl = QLabel(ctrl_val)
        ctrl_lbl.setFont(Fonts.label_sm())
        ctrl_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        ctrl_lbl.setWordWrap(True)
        ctrl_row.addWidget(ctrl_lbl, 1)
        cb = QLabel(f"  {ctrl_badge_t}  ")
        cb.setFont(QFont(Fonts.FAMILY, 8, QFont.Weight.Bold))
        cb.setStyleSheet(
            f"color: white; background: {ctrl_badge_c};"
            f"border-radius: 4px; padding: 2px 6px;")
        ctrl_row.addWidget(cb)
        clg.addLayout(ctrl_row, 0, 1)

        # Mitigation
        mit_val = r.get("mitigation") or "—"
        has_mit = bool(r.get("mitigation"))
        mit_badge_t = "Planned" if has_mit else "Not Documented"
        mit_badge_c = Colors.ACCENT_BLUE if has_mit else Colors.MEDIUM
        clg.addWidget(QLabel("Mitigation Plan"),
                       1, 0, Qt.AlignmentFlag.AlignTop)
        clg.itemAt(clg.count()-1).widget().setFont(Fonts.label_sm())
        clg.itemAt(clg.count()-1).widget().setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        mit_row = QHBoxLayout()
        mit_lbl = QLabel(mit_val)
        mit_lbl.setFont(Fonts.label_sm())
        mit_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        mit_lbl.setWordWrap(True)
        mit_row.addWidget(mit_lbl, 1)
        mb = QLabel(f"  {mit_badge_t}  ")
        mb.setFont(QFont(Fonts.FAMILY, 8, QFont.Weight.Bold))
        mb.setStyleSheet(
            f"color: white; background: {mit_badge_c};"
            f"border-radius: 4px; padding: 2px 6px;")
        mit_row.addWidget(mb)
        clg.addLayout(mit_row, 1, 1)

        # AI Recommendation + Notes
        if r.get("ai_suggestion"):
            clg.addWidget(QLabel("AI Recommendation"),
                           2, 0, Qt.AlignmentFlag.AlignTop)
            clg.itemAt(clg.count()-1).widget().setFont(Fonts.label_sm())
            clg.itemAt(clg.count()-1).widget().setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            ai_l = QLabel(str(r["ai_suggestion"]))
            ai_l.setFont(Fonts.label_sm())
            ai_l.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            ai_l.setWordWrap(True)
            clg.addWidget(ai_l, 2, 1)

        if r.get("notes"):
            nr = 3 if r.get("ai_suggestion") else 2
            clg.addWidget(QLabel("Notes"),
                           nr, 0, Qt.AlignmentFlag.AlignTop)
            clg.itemAt(clg.count()-1).widget().setFont(Fonts.label_sm())
            clg.itemAt(clg.count()-1).widget().setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            n_l = QLabel(str(r["notes"]))
            n_l.setFont(Fonts.label_sm())
            n_l.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            n_l.setWordWrap(True)
            clg.addWidget(n_l, nr, 1)

        vl.addWidget(ctrl_card)
        vl.addStretch()
        return scroll

    # ── Framework Intelligence tab ────────────────────────────────────────────

    def _build_framework_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl.setSpacing(Spacing.SM)
        scroll.setWidget(inner)

        desc = QLabel(
            "How this risk maps across each supported framework.\n"
            "'Confirmed' = value was explicitly selected.  "
            "'Unmapped' = field left blank or at default.")
        desc.setFont(Fonts.label_sm())
        desc.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        desc.setWordWrap(True)
        vl.addWidget(desc)

        # Framework mappings
        mapping = get_framework_mapping(self._r)
        CONF_COLOR = {
            "Confirmed": Colors.SUCCESS_LT,
            "Suggested": Colors.MEDIUM,
            "Unmapped":  Colors.TEXT_DIM,
        }
        for entry in mapping:
            c_color = CONF_COLOR.get(
                entry["confidence"], Colors.TEXT_MUTED)
            card = _card()
            cl = QHBoxLayout(card)
            cl.setContentsMargins(
                Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            cl.setSpacing(Spacing.MD)

            badge_f = QFrame()
            badge_f.setFixedSize(86, 24)
            badge_f.setStyleSheet(
                f"background-color: {c_color};"
                f"border-radius: {Radius.SM}px; border: none;")
            bl = QHBoxLayout(badge_f)
            bl.setContentsMargins(4, 0, 4, 0)
            bl.setSpacing(0)
            b_lbl = QLabel(entry["confidence"])
            b_lbl.setFont(Fonts.badge())
            b_lbl.setStyleSheet("color: white; border: none;")
            b_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(b_lbl)
            cl.addWidget(badge_f)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            fw_title = QLabel(
                f"{entry['framework']}  ·  {entry['function']}")
            fw_title.setFont(
                QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
            fw_title.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            info_col.addWidget(fw_title)

            if entry["category"] != "—" or entry["control"] != "—":
                meta = QLabel(
                    f"Category: {entry['category']}  ·  "
                    f"Control/Ref: {entry['control']}")
                meta.setFont(Fonts.label_sm())
                meta.setStyleSheet(
                    f"color: {Colors.TEXT_MUTED}; border: none;")
                info_col.addWidget(meta)

            rationale = QLabel(entry["rationale"])
            rationale.setFont(Fonts.label_sm())
            rationale.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none;")
            rationale.setWordWrap(True)
            info_col.addWidget(rationale)

            cl.addLayout(info_col, 1)
            vl.addWidget(card)

        # NIST SP 800-53 Recommendations
        recs = get_800_53_recommendations(dict(self._r), 5)
        vl.addWidget(QLabel())  # spacer
        rec_title = QLabel("NIST SP 800-53 Rev 5 Recommendations")
        rec_title.setFont(Fonts.heading_3())
        rec_title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        vl.addWidget(rec_title)

        for rec in recs:
            rc = _card()
            rl = QHBoxLayout(rc)
            rl.setContentsMargins(
                Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            rl.setSpacing(Spacing.MD)

            conf_color = (Colors.SUCCESS_LT
                          if rec["confidence"] == "Confirmed"
                          else Colors.MEDIUM
                          if rec["confidence"] == "Recommended"
                          else Colors.TEXT_MUTED)
            ctrl_lbl = QLabel(
                f"{rec['control_id']}\n{rec['family']}")
            ctrl_lbl.setFont(
                QFont(Fonts.FAMILY, 10, QFont.Weight.Bold))
            ctrl_lbl.setStyleSheet(
                f"color: {conf_color}; border: none;")
            ctrl_lbl.setFixedWidth(60)
            ctrl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(ctrl_lbl)

            desc_col = QVBoxLayout()
            desc_col.setSpacing(2)
            ctrl_name = QLabel(rec["control_name"])
            ctrl_name.setFont(
                QFont(Fonts.FAMILY, 10, QFont.Weight.Bold))
            ctrl_name.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            desc_col.addWidget(ctrl_name)
            why = QLabel(rec["rationale"])
            why.setFont(Fonts.label_sm())
            why.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            why.setWordWrap(True)
            desc_col.addWidget(why)
            rl.addLayout(desc_col, 1)

            conf_badge = QFrame()
            conf_badge.setFixedSize(90, 22)
            conf_badge.setStyleSheet(
                f"background-color: {conf_color};"
                f"border-radius: {Radius.SM}px; border: none;")
            cbl = QHBoxLayout(conf_badge)
            cbl.setContentsMargins(4, 0, 4, 0)
            cb_lbl = QLabel(rec["confidence"])
            cb_lbl.setFont(Fonts.badge())
            cb_lbl.setStyleSheet("color: white; border: none;")
            cb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cbl.addWidget(cb_lbl)
            rl.addWidget(conf_badge)
            vl.addWidget(rc)

        vl.addStretch()
        return scroll

    # ── Treatments tab ────────────────────────────────────────────────────────

    def _build_treatments_tab(self) -> QWidget:
        self._treat_container = QWidget()
        self._treat_container.setStyleSheet(
            f"background-color: {Colors.BG_DEEP};")
        self._treat_layout = QVBoxLayout(self._treat_container)
        self._treat_layout.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._treat_layout.setSpacing(Spacing.SM)
        self._refresh_treatments()

        scroll = QScrollArea()
        scroll.setWidget(self._treat_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        return scroll

    def _refresh_treatments(self) -> None:
        while self._treat_layout.count():
            item = self._treat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        treatments = get_treatments(self.rid)
        if not treatments:
            empty = QLabel(
                "No treatments logged for this risk.\n"
                "Click '＋ Add Treatment' below to create one.")
            empty.setFont(Fonts.label())
            empty.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._treat_layout.addWidget(empty)
            self._treat_layout.addStretch()
            return

        for t in treatments:
            card = _card()
            card.setStyleSheet(
                f"background-color: {Colors.BG_CARD};"
                f"border-radius: {Radius.MD}px;"
                f"border: 1px solid {Colors.BG_BORDER};")
            vl = QVBoxLayout(card)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(0)

            # Strategy header band
            s_color = Colors.treat_color(t["strategy"])
            hband = QFrame()
            hband.setFixedHeight(30)
            hband.setStyleSheet(
                f"background-color: {s_color};"
                f"border-radius: {Radius.MD}px {Radius.MD}px 0 0;"
                f"border: none;")
            hl = QHBoxLayout(hband)
            hl.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
            title_lbl = QLabel(
                f"  {t['strategy']}  ·  {t['title']}")
            title_lbl.setFont(
                QFont(Fonts.FAMILY, 10, QFont.Weight.Bold))
            title_lbl.setStyleSheet("color: white; border: none;")
            hl.addWidget(title_lbl, 1)
            status_lbl = QLabel(t["status"])
            status_lbl.setFont(Fonts.label_sm_bold())
            status_lbl.setStyleSheet("color: white; border: none;")
            hl.addWidget(status_lbl)
            vl.addWidget(hband)

            # Body grid
            body = QWidget()
            body.setStyleSheet("border: none;")
            gl = QGridLayout(body)
            gl.setContentsMargins(
                Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            gl.setSpacing(4)
            gl.setColumnStretch(1, 1)
            gl.setColumnStretch(3, 1)

            def _tr(r, c, label, value):
                l1 = QLabel(label + ":")
                l1.setFont(Fonts.label_sm())
                l1.setStyleSheet(
                    f"color: {Colors.TEXT_MUTED}; border: none;")
                gl.addWidget(l1, r, c)
                l2 = QLabel(str(value or "—"))
                l2.setFont(Fonts.label_sm())
                l2.setStyleSheet(
                    f"color: {Colors.TEXT_PRIMARY}; border: none;")
                gl.addWidget(l2, r, c + 1)

            _tr(0, 0, "Owner",          t["owner"])
            _tr(0, 2, "Target Date",    t["target_date"] or "—")
            _tr(1, 0, "Residual Target",t["residual_score_target"])
            _tr(1, 2, "Residual Actual",t["residual_score_actual"])

            if t["description"]:
                desc = QLabel(t["description"])
                desc.setFont(Fonts.label_sm())
                desc.setStyleSheet(
                    f"color: {Colors.TEXT_MUTED}; border: none;")
                desc.setWordWrap(True)
                gl.addWidget(desc, 2, 0, 1, 4)

            vl.addWidget(body)

            # Action buttons
            btn_row = QWidget()
            btn_row.setStyleSheet("border: none;")
            bl = QHBoxLayout(btn_row)
            bl.setContentsMargins(
                Spacing.MD, 0, Spacing.MD, Spacing.SM)
            bl.addStretch()
            edit_btn = _btn("Edit", Colors.ACCENT_BLUE, "white")
            edit_btn.setFixedWidth(70)
            del_btn  = _btn("Delete", "#3D1515", Colors.CRITICAL)
            del_btn.setFixedWidth(70)
            tid = t["id"]
            del_btn.clicked.connect(
                lambda checked, t_id=tid:
                self._delete_treatment(t_id))
            bl.addWidget(edit_btn)
            bl.addWidget(del_btn)
            vl.addWidget(btn_row)

            self._treat_layout.addWidget(card)

        self._treat_layout.addStretch()

    def _delete_treatment(self, tid: int) -> None:
        reply = QMessageBox.question(
            self, "Delete Treatment",
            "Delete this treatment plan?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            delete_treatment(tid)
            self._refresh_treatments()
            self.data_changed.emit()

    # ── Action bar ────────────────────────────────────────────────────────────

    def _build_action_bar(self) -> None:
        self._action_bar = QFrame()
        self._action_bar.setFixedHeight(52)
        self._action_bar.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-top: 1px solid {Colors.BG_BORDER};"
            f"border-radius: 0;")
        hl = QHBoxLayout(self._action_bar)
        hl.setContentsMargins(Spacing.LG, Spacing.SM,
                               Spacing.LG, Spacing.SM)
        hl.setSpacing(Spacing.SM)

        del_btn = _btn("🗑  Delete", "#3D1515", Colors.CRITICAL)
        del_btn.clicked.connect(self._delete_risk)
        hl.addWidget(del_btn)

        edit_btn = _btn("✏  Edit", Colors.ACCENT_BLUE, "white")
        edit_btn.clicked.connect(
            lambda: self.edit_requested.emit(self.rid))
        hl.addWidget(edit_btn)

        treat_btn = _btn(
            "＋  Add Treatment", Colors.ACCENT_TEAL, "white")
        treat_btn.clicked.connect(
            lambda: self.treatment_added.emit(self.rid))
        hl.addWidget(treat_btn)

        hl.addStretch()

        close_btn = _btn("Close", Colors.BG_BORDER, Colors.TEXT_MUTED)
        close_btn.clicked.connect(self.accept)
        hl.addWidget(close_btn)

    def _delete_risk(self) -> None:
        reply = QMessageBox.question(
            self, "Delete Risk",
            "Permanently delete this risk and all its treatments?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            delete_risk(self.rid)
            self.risk_deleted.emit(self.rid)
            self.accept()

    # ── Cost Analysis & ROSI Tab ──────────────────────────────────────────────

    def _build_cost_tab(self) -> QWidget:
        """
        Cost & ROSI tab — Treatment Cost Breakdown, Business Impact
        (Cost of Doing Nothing), Cost Comparison, and ROSI calculation.
        All values editable and saved back to the risk record.
        """
        from PySide6.QtWidgets import QLineEdit, QDoubleSpinBox, QSlider

        r = self._r  # already a dict

        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        # ── Helpers ────────────────────────────────────────────────────────────
        def _card():
            f = QFrame()
            f.setStyleSheet(
                f"background: {Colors.BG_CARD};"
                f"border-radius: {Radius.LG}px;"
                f"border: 1px solid {Colors.BG_BORDER};")
            return f

        def _card_title(text, color=Colors.TEXT_PRIMARY):
            lbl = QLabel(text)
            lbl.setFont(QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
            lbl.setStyleSheet(f"color: {color}; border: none;")
            return lbl

        def _lbl(text, color=Colors.TEXT_MUTED):
            l = QLabel(str(text))
            l.setFont(Fonts.label_sm())
            l.setStyleSheet(f"color: {color}; border: none;")
            return l

        def _money_field(val=0.0) -> QLineEdit:
            e = QLineEdit()
            e.setFixedHeight(30)
            e.setText(f"{float(val or 0):.2f}")
            e.setStyleSheet(
                f"background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};"
                f"border: 1px solid {Colors.BG_BORDER};"
                f"border-radius: {Radius.SM}px; padding: 2px 8px;")
            return e

        def _fval(e: QLineEdit) -> float:
            try:
                return max(0.0, float(e.text().replace(",", "").replace("$", "")))
            except Exception:
                return 0.0

        def _fmt(v: float) -> str:
            return f"${v:,.0f}"

        def _divider():
            d = QFrame()
            d.setFrameShape(QFrame.Shape.HLine)
            d.setStyleSheet(
                f"background: {Colors.BG_BORDER}; border: none; max-height: 1px;")
            return d

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 0 — Enterprise Preset Selector
        # Presets based on IBM Cost of a Data Breach Report 2024
        # Users can apply a preset as a starting point and customise
        # ─────────────────────────────────────────────────────────────────────
        c0 = _card()
        g0 = QVBoxLayout(c0)
        g0.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        g0.setSpacing(Spacing.SM)

        hdr0 = QHBoxLayout()
        hdr0.addWidget(_card_title("Industry Benchmark Presets",
                                    Colors.ACCENT_BLUE))
        g0.addLayout(hdr0)
        g0.addWidget(_lbl(
            "Select an organisation size to populate industry-average cost estimates "
            "based on the IBM Cost of a Data Breach Report 2024. "
            "Adjust all values to match your organisation — these are starting points only.",
            color=Colors.TEXT_MUTED))

        # ── Preset definitions (IBM 2024 benchmarks) ─────────────────────────
        # Sources:
        #   IBM Cost of a Data Breach 2024 — global avg $4.88M, SME avg $4.5M
        #   US average $9.36M, downtime avg $5,600/min (Gartner)
        #   GDPR max fine 4% global turnover; avg enforcement ~$1.5M SME
        #   Ransomware recovery avg $2.73M (Sophos 2024)
        # ── Preset data — benchmarks from IBM 2024, Gartner, Sophos 2024 ────────
        # Keys match EXACTLY the Settings → Organisation → Organisation Size values
        _PRESETS = {
            # < 50 employees — lean team, limited budget, mostly external support
            # IBM 2024 SME breach avg ~$4.5M; scaled down for micro-organisations
            "Small (< 50 employees)": {
                "labour_cost":            2500,
                "software_cost":          1500,
                "hardware_cost":           500,
                "consulting_cost":        4000,
                "training_cost":           800,
                "licensing_cost":         1000,
                "maintenance_cost":        500,
                "misc_cost":               200,
                "regulatory_fine_est":   20000,
                "breach_cost_est":        80000,
                "downtime_cost_est":      12000,
                "lost_revenue_est":       18000,
                "recovery_cost_est":      15000,
                "legal_cost_est":          8000,
                "reputation_cost_est":    10000,
                "customer_loss_est":       6000,
                "productivity_loss_est":   4000,
                "risk_reduction_pct":        70,
            },
            # 50–500 employees — part-time security, mostly managed services
            # IBM 2024 global SME average scaled to lower end
            "Medium (50–500 employees)": {
                "labour_cost":            5000,
                "software_cost":          3000,
                "hardware_cost":          1000,
                "consulting_cost":        8000,
                "training_cost":          1500,
                "licensing_cost":         2000,
                "maintenance_cost":       1000,
                "misc_cost":               500,
                "regulatory_fine_est":    50000,
                "breach_cost_est":       180000,
                "downtime_cost_est":      30000,
                "lost_revenue_est":       45000,
                "recovery_cost_est":      40000,
                "legal_cost_est":         22000,
                "reputation_cost_est":    28000,
                "customer_loss_est":      18000,
                "productivity_loss_est":  12000,
                "risk_reduction_pct":        75,
            },
            # 500–5,000 employees — dedicated security team, mixed tooling
            # IBM 2024 global average $4.88M
            "Large (500–5,000 employees)": {
                "labour_cost":           18000,
                "software_cost":         12000,
                "hardware_cost":          5000,
                "consulting_cost":       20000,
                "training_cost":          4000,
                "licensing_cost":         8000,
                "maintenance_cost":       5000,
                "misc_cost":              2000,
                "regulatory_fine_est":  250000,
                "breach_cost_est":       680000,
                "downtime_cost_est":     125000,
                "lost_revenue_est":      185000,
                "recovery_cost_est":     155000,
                "legal_cost_est":         88000,
                "reputation_cost_est":   105000,
                "customer_loss_est":      68000,
                "productivity_loss_est":  50000,
                "risk_reduction_pct":        80,
            },
            # 5,000+ employees — mature programme, enterprise tooling
            # IBM 2024 US average $9.36M; Sophos ransomware avg $2.73M
            "Enterprise (5,000+ employees)": {
                "labour_cost":           85000,
                "software_cost":         60000,
                "hardware_cost":         25000,
                "consulting_cost":       75000,
                "training_cost":         15000,
                "licensing_cost":        35000,
                "maintenance_cost":      20000,
                "misc_cost":              8000,
                "regulatory_fine_est": 1200000,
                "breach_cost_est":     3500000,
                "downtime_cost_est":    875000,
                "lost_revenue_est":    1250000,
                "recovery_cost_est":    775000,
                "legal_cost_est":       460000,
                "reputation_cost_est":  620000,
                "customer_loss_est":    420000,
                "productivity_loss_est":260000,
                "risk_reduction_pct":        85,
            },
        }

        def _apply_preset(preset_data):
            """Apply a preset to all cost/impact fields and refresh totals."""
            for key, val in preset_data.items():
                if key == "risk_reduction_pct":
                    self._rr_slider.setValue(int(val))
                elif key in self._cost_fields:
                    self._cost_fields[key].setText(f"{float(val):.2f}")
                elif key in self._impact_fields:
                    self._impact_fields[key].setText(f"{float(val):.2f}")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.SM)
        for preset_name, preset_data in _PRESETS.items():
            btn = QPushButton(preset_name)
            btn.setFont(Fonts.label_sm())
            btn.setFixedHeight(48)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.BG_CARD2};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.BG_BORDER};
                    border-radius: {Radius.SM}px;
                    padding: 4px 12px;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background: {Colors.ACCENT_BLUE};
                    color: white;
                    border: 1px solid {Colors.ACCENT_BLUE};
                }}
            """)
            # Capture preset_data in closure
            btn.clicked.connect(
                lambda checked, pd=preset_data: _apply_preset(pd))
            btn_row.addWidget(btn)

        g0.addLayout(btn_row)
        # Auto-detect and apply the right preset from org settings
        # so fields are pre-populated when the tab opens
        try:
            from core.database.db import get_organisation_scope, load_settings
            _scope    = get_organisation_scope() or {}
            _settings = load_settings() or {}
            _org_size = (_scope.get("organisation_size","")
                         or _settings.get("organisation_size","")).lower()
            _has_cost = any(float(r.get(k) or 0) > 0
                           for k in ("labour_cost","software_cost",
                                     "total_treatment_cost","total_business_impact"))

            # Only auto-apply if no cost data has been entered yet
            if not _has_cost:
                # Match against exact Settings dropdown values
                if "Enterprise" in _org_size or "5,000+" in _org_size:
                    _auto_preset = _PRESETS["Enterprise (5,000+ employees)"]
                elif "Large" in _org_size or "500–5,000" in _org_size:
                    _auto_preset = _PRESETS["Large (500–5,000 employees)"]
                elif "Medium" in _org_size or "50–500" in _org_size:
                    _auto_preset = _PRESETS["Medium (50–500 employees)"]
                else:
                    _auto_preset = _PRESETS["Small (< 50 employees)"]
                # Schedule auto-apply after widget construction completes
                from PySide6.QtCore import QTimer as _QT
                _QT.singleShot(0, lambda pd=_auto_preset: _apply_preset(pd))
        except Exception:
            pass  # Non-critical — user can manually select

        g0.addWidget(_lbl(
            "Source: IBM Cost of a Data Breach Report 2024  ·  "
            "Gartner Downtime Cost Analysis 2024  ·  Sophos Ransomware Report 2024  ·  "
            "Values are industry averages — update to match your specific context.",
            color=Colors.TEXT_DIM))
        vl.addWidget(c0)

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 1 — Treatment Cost Breakdown
        # ─────────────────────────────────────────────────────────────────────
        c1 = _card()
        g1 = QGridLayout(c1)
        g1.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        g1.setSpacing(Spacing.SM)
        g1.setColumnStretch(1, 1)
        g1.addWidget(_card_title("Treatment Cost Breakdown",
                                  Colors.ACCENT_BLUE), 0, 0, 1, 3)
        g1.addWidget(_lbl("Enter estimated costs for each component:"), 1, 0, 1, 3)

        cost_fields_def = [
            ("labour_cost",       "Labour Cost",       "Staff time and internal hours"),
            ("software_cost",     "Software",          "Licences, tools, subscriptions"),
            ("hardware_cost",     "Hardware",          "Devices, infrastructure, equipment"),
            ("consulting_cost",   "Consulting",        "External consultants or specialists"),
            ("training_cost",     "Training",          "Staff training and awareness"),
            ("licensing_cost",    "Licensing",         "Ongoing product or service licences"),
            ("maintenance_cost",  "Maintenance",       "Ongoing maintenance and support"),
            ("misc_cost",         "Miscellaneous",     "Other costs"),
        ]

        self._cost_fields = {}
        for i, (key, label, hint) in enumerate(cost_fields_def, 2):
            g1.addWidget(_lbl(label), i, 0)
            e = _money_field(r.get(key, 0))
            e.setToolTip(hint)
            self._cost_fields[key] = e
            g1.addWidget(e, i, 1)
            g1.addWidget(_lbl(f"  {hint}", Colors.TEXT_DIM), i, 2)

        g1.addWidget(_divider(), len(cost_fields_def) + 2, 0, 1, 3)

        self._total_cost_lbl = QLabel(_fmt(r.get("total_treatment_cost", 0)))
        self._total_cost_lbl.setFont(QFont(Fonts.FAMILY, 20, QFont.Weight.Bold))
        self._total_cost_lbl.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE}; border: none;")
        g1.addWidget(_lbl("Total Treatment Cost"), len(cost_fields_def) + 3, 0)
        g1.addWidget(self._total_cost_lbl, len(cost_fields_def) + 3, 1)

        # Auto-update total as fields change
        def _update_cost_total():
            total = sum(_fval(e) for e in self._cost_fields.values())
            self._total_cost_lbl.setText(_fmt(total))
            self._update_comparison()

        for e in self._cost_fields.values():
            e.textChanged.connect(_update_cost_total)

        vl.addWidget(c1)

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 2 — Business Impact (Cost of Doing Nothing)
        # ─────────────────────────────────────────────────────────────────────
        c2 = _card()
        g2 = QGridLayout(c2)
        g2.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        g2.setSpacing(Spacing.SM)
        g2.setColumnStretch(1, 1)
        g2.addWidget(_card_title("Business Impact — Cost of Doing Nothing",
                                  Colors.CRITICAL), 0, 0, 1, 3)
        g2.addWidget(_lbl(
            "Estimate the financial impact if this risk is not treated:"),
            1, 0, 1, 3)

        impact_fields_def = [
            ("regulatory_fine_est",   "Regulatory Fines",    "GDPR, FCA, PCI-DSS, HIPAA or sector penalties"),
            ("breach_cost_est",       "Data Breach Cost",    "Notification, forensics, remediation costs"),
            ("downtime_cost_est",     "Downtime Cost",       "Revenue lost per hour × estimated outage hours"),
            ("lost_revenue_est",      "Lost Revenue",        "Direct business revenue impact"),
            ("recovery_cost_est",     "Recovery Cost",       "IR, restoration, rebuilding systems"),
            ("legal_cost_est",        "Legal Cost",          "Litigation, regulatory defence, settlements"),
            ("reputation_cost_est",   "Reputation Damage",   "Brand value loss, market cap impact"),
            ("customer_loss_est",     "Customer Loss",       "Customer churn × customer lifetime value"),
            ("productivity_loss_est", "Productivity Loss",   "Staff downtime, incident response hours"),
        ]

        self._impact_fields = {}
        for i, (key, label, hint) in enumerate(impact_fields_def, 2):
            g2.addWidget(_lbl(label), i, 0)
            e = _money_field(r.get(key, 0))
            e.setToolTip(hint)
            self._impact_fields[key] = e
            g2.addWidget(e, i, 1)
            g2.addWidget(_lbl(f"  {hint}", Colors.TEXT_DIM), i, 2)

        g2.addWidget(_divider(), len(impact_fields_def) + 2, 0, 1, 3)

        self._total_impact_lbl = QLabel(_fmt(r.get("total_business_impact", 0)))
        self._total_impact_lbl.setFont(QFont(Fonts.FAMILY, 20, QFont.Weight.Bold))
        self._total_impact_lbl.setStyleSheet(
            f"color: {Colors.CRITICAL}; border: none;")
        g2.addWidget(_lbl("Total Business Impact"), len(impact_fields_def) + 3, 0)
        g2.addWidget(self._total_impact_lbl, len(impact_fields_def) + 3, 1)

        def _update_impact_total():
            total = sum(_fval(e) for e in self._impact_fields.values())
            self._total_impact_lbl.setText(_fmt(total))
            self._update_comparison()

        for e in self._impact_fields.values():
            e.textChanged.connect(_update_impact_total)

        vl.addWidget(c2)

        # ─────────────────────────────────────────────────────────────────────
        # SECTION 3 — Cost Comparison & ROSI
        # ─────────────────────────────────────────────────────────────────────
        c3 = _card()
        g3 = QGridLayout(c3)
        g3.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        g3.setSpacing(Spacing.SM)
        g3.setColumnStretch(0, 1)
        g3.setColumnStretch(1, 1)
        g3.setColumnStretch(2, 1)
        g3.addWidget(_card_title("Cost Comparison & ROSI",
                                  Colors.SUCCESS_LT), 0, 0, 1, 3)

        # Three prominent comparison boxes
        def _big_box(label, val_lbl_attr, color, bg, col):
            box = QFrame()
            box.setStyleSheet(
                f"background: {bg}; border-radius: {Radius.MD}px; border: none;")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(Spacing.MD, Spacing.MD,
                                   Spacing.MD, Spacing.MD)
            bl.setSpacing(4)
            title = QLabel(label)
            title.setFont(Fonts.label_sm())
            title.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(title)
            val = QLabel("$0")
            val.setFont(QFont(Fonts.FAMILY, 18, QFont.Weight.Bold))
            val.setStyleSheet(f"color: {color}; border: none;")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(val)
            setattr(self, val_lbl_attr, val)
            g3.addWidget(box, 1, col)

        _big_box("Treatment Cost",     "_cmp_cost_lbl",
                 Colors.ACCENT_BLUE, Colors.BG_CARD2, 0)
        _big_box("Potential Business Loss", "_cmp_impact_lbl",
                 Colors.CRITICAL, Colors.BG_CRITICAL, 1)
        _big_box("Projected Savings",  "_cmp_savings_lbl",
                 Colors.SUCCESS_LT, Colors.BG_CARD2, 2)

        # ROSI row
        rosi_row = QHBoxLayout()
        self._rosi_lbl = QLabel("ROSI: — %")
        self._rosi_lbl.setFont(QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        self._rosi_lbl.setStyleSheet(
            f"color: {Colors.SUCCESS_LT}; border: none;")
        rosi_row.addWidget(self._rosi_lbl)

        self._rosi_reduction_lbl = QLabel("Risk Reduction: 80%")
        self._rosi_reduction_lbl.setFont(Fonts.label_sm())
        self._rosi_reduction_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        rosi_row.addStretch()
        rosi_row.addWidget(self._rosi_reduction_lbl)
        g3.addLayout(rosi_row, 2, 0, 1, 3)

        # Executive recommendation
        self._exec_rec_lbl = QLabel("")
        self._exec_rec_lbl.setFont(Fonts.label_sm())
        self._exec_rec_lbl.setWordWrap(True)
        self._exec_rec_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;"
            f"background: {Colors.BG_CARD2};"
            f"border-radius: {Radius.SM}px; padding: 8px;")
        g3.addWidget(self._exec_rec_lbl, 3, 0, 1, 3)

        # Risk reduction slider
        slider_row = QHBoxLayout()
        slider_row.addWidget(_lbl("Assumed Risk Reduction %:"))
        self._rr_slider = QSlider(Qt.Orientation.Horizontal)
        self._rr_slider.setRange(10, 100)
        self._rr_slider.setValue(int(r.get("risk_reduction_pct") or 80))
        self._rr_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background: {Colors.BG_BORDER};"
            f"height: 6px; border-radius: 3px; }}"
            f"QSlider::handle:horizontal {{ background: {Colors.ACCENT_BLUE};"
            f"width: 16px; height: 16px; margin: -5px 0;"
            f"border-radius: 8px; }}"
            f"QSlider::sub-page:horizontal {{ background: {Colors.ACCENT_BLUE};"
            f"border-radius: 3px; }}")
        self._rr_slider.valueChanged.connect(self._update_comparison)
        slider_row.addWidget(self._rr_slider, 1)
        self._rr_val_lbl = QLabel(f"{int(r.get('risk_reduction_pct') or 80)}%")
        self._rr_val_lbl.setFont(Fonts.label_sm_bold())
        self._rr_val_lbl.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE}; border: none;")
        slider_row.addWidget(self._rr_val_lbl)
        g3.addLayout(slider_row, 4, 0, 1, 3)

        # Save button
        save_btn = QPushButton("💾  Save Cost Analysis")
        save_btn.setFont(Fonts.label_sm_bold())
        save_btn.setFixedHeight(36)
        save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        save_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.ACCENT_BLUE}; color: white;"
            f"border: none; border-radius: {Radius.SM}px; padding: 0 16px; }}")
        save_btn.clicked.connect(self._save_cost_analysis)
        g3.addWidget(save_btn, 5, 0, 1, 3)

        self._save_cost_status = QLabel("")
        self._save_cost_status.setFont(Fonts.label_sm())
        self._save_cost_status.setStyleSheet(
            f"color: {Colors.SUCCESS_LT}; border: none;")
        g3.addWidget(self._save_cost_status, 6, 0, 1, 3)

        vl.addWidget(c3)
        vl.addStretch()

        # Initialise comparison display
        self._update_comparison()

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _update_comparison(self):
        """Recalculate ROSI and comparison labels from current field values."""
        try:
            from PySide6.QtWidgets import QLineEdit

            def _fval(e):
                try:
                    return max(0.0, float(
                        e.text().replace(",", "").replace("$", "")))
                except Exception:
                    return 0.0

            def _fmt(v):
                return f"${v:,.0f}"

            ttc = sum(_fval(e) for e in self._cost_fields.values())
            tbi = sum(_fval(e) for e in self._impact_fields.values())
            rrp = self._rr_slider.value()
            self._rr_val_lbl.setText(f"{rrp}%")

            exp_loss = tbi * (rrp / 100)
            savings  = exp_loss - ttc
            rosi     = ((exp_loss - ttc) / ttc * 100) if ttc > 0 else 0.0

            self._cmp_cost_lbl.setText(_fmt(ttc))
            self._cmp_impact_lbl.setText(_fmt(tbi))
            self._cmp_savings_lbl.setText(_fmt(max(0, savings)))
            self._rosi_lbl.setText(
                f"ROSI: {rosi:+.0f}%  |  "
                f"Expected Loss Avoided: {_fmt(exp_loss)}")
            self._rosi_reduction_lbl.setText(
                f"Risk Reduction Assumption: {rrp}%")

            # Executive recommendation
            if ttc == 0 and tbi == 0:
                rec = "Enter treatment costs and business impact estimates above to generate the executive recommendation."
                rec_color = Colors.TEXT_MUTED
            elif ttc == 0:
                rec = f"⚠  No treatment costs entered. Estimated business impact if untreated: {_fmt(tbi)}. Enter treatment costs to calculate ROSI."
                rec_color = Colors.MEDIUM
            elif tbi == 0:
                rec = "⚠  No business impact estimated. Enter potential costs (regulatory fines, downtime, etc.) to generate a meaningful ROSI."
                rec_color = Colors.MEDIUM
            elif rosi >= 500:
                rec = (f"✅  STRONGLY RECOMMENDED: Treatment cost {_fmt(ttc)} represents only "
                       f"{ttc/tbi*100:.1f}% of estimated business impact {_fmt(tbi)}. "
                       f"Expected savings: {_fmt(savings)}. ROSI of {rosi:.0f}% makes this "
                       f"one of the highest-value security investments available.")
                rec_color = Colors.SUCCESS_LT
            elif rosi >= 100:
                rec = (f"✅  RECOMMENDED: Treatment cost {_fmt(ttc)} vs. estimated exposure {_fmt(tbi)}. "
                       f"Expected savings: {_fmt(savings)}. ROSI of {rosi:.0f}% — "
                       f"remediation is financially justified. Prioritise this treatment.")
                rec_color = Colors.SUCCESS_LT
            elif rosi >= 0:
                rec = (f"⚠  CONSIDER: Treatment cost {_fmt(ttc)} delivers an estimated saving of "
                       f"{_fmt(savings)} (ROSI {rosi:.0f}%). Remediation is justified but should "
                       f"be weighed against other investment priorities.")
                rec_color = Colors.MEDIUM
            else:
                rec = (f"❌  ACCEPT / TRANSFER: Treatment cost {_fmt(ttc)} exceeds expected risk "
                       f"exposure {_fmt(exp_loss)} (ROSI {rosi:.0f}%). Consider risk acceptance, "
                       f"transfer (insurance), or a lower-cost mitigation approach.")
                rec_color = Colors.CRITICAL

            self._exec_rec_lbl.setText(rec)
            self._exec_rec_lbl.setStyleSheet(
                f"color: {rec_color}; border: none;"
                f"background: {Colors.BG_CARD2};"
                f"border-radius: {Radius.SM}px; padding: 10px;")
        except AttributeError:
            pass  # Fields not yet built

    def _save_cost_analysis(self):
        """Save all cost/ROSI fields back to the risk record."""
        def _fval(e):
            try:
                return max(0.0, float(
                    e.text().replace(",", "").replace("$", "")))
            except Exception:
                return 0.0

        ttc = sum(_fval(e) for e in self._cost_fields.values())
        tbi = sum(_fval(e) for e in self._impact_fields.values())
        rrp = float(self._rr_slider.value())
        exp_loss = tbi * (rrp / 100)
        rosi     = ((exp_loss - ttc) / ttc * 100) if ttc > 0 else 0.0
        savings  = exp_loss - ttc

        cost_data = {k: _fval(e) for k, e in self._cost_fields.items()}
        impact_data = {k: _fval(e) for k, e in self._impact_fields.items()}

        # Build minimal data dict for update_risk — carry existing fields
        data = dict(self._r)
        data.update(cost_data)
        data.update(impact_data)
        data["total_treatment_cost"]  = ttc
        data["total_business_impact"] = tbi
        data["risk_reduction_pct"]    = rrp
        data["rosi_pct"]              = rosi
        data["projected_savings"]     = savings

        try:
            update_risk(self.rid, data)
            # Refresh local cache
            from core.database.db import get_risk as _gr
            r2 = _gr(self.rid)
            if r2:
                self._r = dict(r2)
            self._save_cost_status.setText("✅  Saved")
            self.data_changed.emit()
        except Exception as e:
            self._save_cost_status.setText(f"⚠  {e}")
