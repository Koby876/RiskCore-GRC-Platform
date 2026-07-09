"""
ui/framework_intelligence.py
─────────────────────────────
Framework Intelligence — dynamically generated from the Risk Register.

Displays per-framework coverage, maturity, missing controls,
recommendations, and risk trends for all 5 frameworks.
"""

from __future__ import annotations
from collections import Counter

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QTabWidget, QProgressBar, QGridLayout,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from core.database.db import get_risks, NIST_FUNCTIONS, NIST_CATEGORIES, NIST_COLORS
from core.database.lookups import (
    get_cis_info, get_mitre_info, CIS_CONTROL_DATA, MITRE_TACTIC_DATA
)


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"background-color: {Colors.BG_CARD};"
        f"border-radius: {Radius.LG}px;"
        f"border: 1px solid {Colors.BG_BORDER};")
    return f


def _lbl(text, font=None, color=Colors.TEXT_MUTED) -> QLabel:
    l = QLabel(str(text))
    l.setFont(font or Fonts.label_sm())
    l.setStyleSheet(f"color: {color}; border: none;")
    l.setWordWrap(True)
    return l


def _bar(pct: int, color: str, height: int = 8) -> QProgressBar:
    b = QProgressBar()
    b.setRange(0, 100)
    b.setValue(max(0, min(100, pct)))
    b.setTextVisible(False)
    b.setFixedHeight(height)
    b.setStyleSheet(f"""
        QProgressBar {{
            background-color: {Colors.BG_BORDER};
            border-radius: 4px; border: none;
        }}
        QProgressBar::chunk {{
            background-color: {color};
            border-radius: 4px;
        }}
    """)
    return b


def _section_title(text: str, color: str = Colors.TEXT_PRIMARY) -> QLabel:
    l = QLabel(text)
    l.setFont(QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
    l.setStyleSheet(f"color: {color}; border: none;")
    return l


def _rec_card(text: str, priority: str = "Medium") -> QFrame:
    """Recommendation card with priority colour."""
    colors = {"High": Colors.HIGH, "Medium": Colors.MEDIUM,
               "Low": Colors.LOW, "Critical": Colors.CRITICAL}
    c = colors.get(priority, Colors.ACCENT_BLUE)
    f = QFrame()
    f.setStyleSheet(
        f"background-color: {Colors.BG_CARD2};"
        f"border-radius: {Radius.SM}px;"
        f"border-left: 3px solid {c};"
        f"border-top: none; border-right: none; border-bottom: none;")
    hl = QHBoxLayout(f)
    hl.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.SM, Spacing.XS)
    hl.setSpacing(Spacing.SM)
    dot = QLabel("▸")
    dot.setFont(Fonts.label_sm())
    dot.setStyleSheet(f"color: {c}; border: none;")
    hl.addWidget(dot)
    lbl = _lbl(text, color=Colors.TEXT_PRIMARY)
    hl.addWidget(lbl, 1)
    pri = QLabel(priority)
    pri.setFont(Fonts.badge())
    pri.setStyleSheet(
        f"background-color: {c}; color: white; "
        f"border-radius: 3px; padding: 2px 6px; border: none;")
    pri.setFixedHeight(18)
    hl.addWidget(pri)
    return f


# ── Worker ────────────────────────────────────────────────────────────────────

class FwWorker(QObject):
    finished = Signal(object)
    error    = Signal(str)

    def run(self) -> None:
        try:
            risks = [dict(r) for r in get_risks()]
            self.finished.emit(risks)
        except Exception as e:
            self.error.emit(str(e))


# ── Framework Intelligence Page ───────────────────────────────────────────────

class FrameworkIntelligencePage(QWidget):
    navigate = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._risks: list[dict] = []
        self._thread: QThread | None = None
        self._worker: FwWorker | None = None
        self._setup_ui()

    def refresh(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if self._thread is not None and not self._thread.isRunning():
            self._thread = None  # clear stale reference
        self._thread = QThread()
        self._worker = FwWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(lambda e: print(f"[FwIntel] error: {e}"))
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(lambda: setattr(self, '_thread', None))
        self._thread.start()

    def _on_loaded(self, risks: list) -> None:
        self._risks = risks
        self._rebuild_tabs()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.SM)
        col = QVBoxLayout()
        t = QLabel("◈  Framework Intelligence")
        t.setFont(Fonts.heading_1())
        t.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        col.addWidget(t)
        s = QLabel("Dynamic GRC intelligence derived from your Risk Register")
        s.setFont(Fonts.label())
        s.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        col.addWidget(s)
        hl.addLayout(col)
        hl.addStretch()
        refresh_btn = QPushButton("⟳  Refresh")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
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
        root.addWidget(hdr)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {Colors.BG_DEEP};
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                padding: 8px 20px; border: none;
                border-bottom: 2px solid transparent;
                font-size: 10pt;
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
        root.addWidget(self._tabs, 1)

        # Placeholder tabs
        self._tab_placeholders = [
            ("NIST CSF 2.0",       Colors.FW_NIST),
            ("ISO 27001:2022",     Colors.FW_ISO),
            ("MITRE ATT&CK",      Colors.FW_MITRE),
            ("CIS Controls v8",   Colors.FW_CIS),
            ("CIA Triad",         Colors.FW_CIA),
            ("Recommendations",   Colors.ACCENT_RED),
        ]
        for name, color in self._tab_placeholders:
            w = QWidget()
            vl = QVBoxLayout(w)
            lbl = QLabel("Loading...")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            vl.addStretch()
            vl.addWidget(lbl)
            vl.addStretch()
            self._tabs.addTab(w, name)

    def _rebuild_tabs(self) -> None:
        while self._tabs.count():
            self._tabs.removeTab(0)
        risks = self._risks
        self._tabs.addTab(self._build_nist_tab(risks),     "NIST CSF 2.0")
        self._tabs.addTab(self._build_iso_tab(risks),      "ISO 27001:2022")
        self._tabs.addTab(self._build_mitre_tab(risks),    "MITRE ATT&CK")
        self._tabs.addTab(self._build_cis_tab(risks),      "CIS Controls v8")
        self._tabs.addTab(self._build_cia_tab(risks),      "CIA Triad")
        self._tabs.addTab(self._build_recs_tab(risks),     "Recommendations")

    def _scrolled(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(Spacing.XL, Spacing.MD, Spacing.XL, Spacing.XL)
        vl.setSpacing(Spacing.MD)
        vl.addWidget(widget)
        vl.addStretch()
        scroll.setWidget(inner)
        return scroll

    # ── NIST CSF 2.0 ─────────────────────────────────────────────────────────

    def _build_nist_tab(self, risks: list) -> QWidget:
        """
        NIST CSF 2.0 — Executive briefing per function.
        Shows: coverage %, risk count, top risks, missing categories,
        what it means for the business, and specific action items.
        """
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        total = len(risks) or 1

        # Executive overview card
        fn_counts = {fn: sum(1 for r in risks
                             if r.get("nist_function") == fn)
                     for fn in NIST_FUNCTIONS}
        unmapped = sum(1 for r in risks if not r.get("nist_function"))

        ov = _card()
        ovl = QVBoxLayout(ov)
        ovl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        ovl.setSpacing(Spacing.SM)
        ovl.addWidget(_section_title("NIST Cybersecurity Framework 2.0 — Coverage Overview",
                                     Colors.FW_NIST))
        covered_fns = sum(1 for c in fn_counts.values() if c > 0)
        ovl.addWidget(_lbl(
            f"{covered_fns} of 6 functions covered across {len(risks)} risk(s). "
            + (f"{unmapped} risk(s) not yet mapped to NIST CSF."
               if unmapped else "All risks mapped to NIST CSF functions."),
            color=Colors.TEXT_PRIMARY))

        fn_descriptions = {
            "Govern":   ("Sets the strategic direction for cybersecurity. Risks here indicate "
                         "gaps in policy, governance structures, roles, or cyber risk management strategy."),
            "Identify": ("Understanding your assets, data, and risks. Gaps mean the organisation "
                         "may not know what it has or what is at risk."),
            "Protect":  ("Implementing safeguards to prevent or limit cyber events. "
                         "The largest risk cluster here indicates your greatest control gaps."),
            "Detect":   ("Identifying cybersecurity events. Risks here mean threats may go "
                         "undetected — increasing dwell time and breach severity."),
            "Respond":  ("Taking action following a detected event. Gaps here mean the organisation "
                         "may not respond effectively, increasing damage and recovery time."),
            "Recover":  ("Restoring capabilities after an event. Gaps here risk extended downtime "
                         "and revenue loss. Prioritise BCP and DR plans."),
        }

        fn_actions = {
            "Govern":   "Review and update the cybersecurity policy, assign risk owners, and establish a GRC committee.",
            "Identify": "Conduct an asset inventory, classify data, and complete a full risk assessment.",
            "Protect":  "Implement or verify: MFA, patch management, access controls, and security awareness training.",
            "Detect":   "Deploy SIEM/EDR, enable alerting, and test detection capabilities quarterly.",
            "Respond":  "Develop and test an Incident Response Plan. Define escalation paths and communication protocols.",
            "Recover":  "Test backup restoration, document RTO/RPO targets, and conduct BCP exercises.",
        }

        for fn in NIST_FUNCTIONS:
            fn_risks = [r for r in risks if r.get("nist_function") == fn]
            fn_count = len(fn_risks)
            pct      = int(fn_count / total * 100) if total else 0
            color    = NIST_COLORS.get(fn, Colors.ACCENT_BLUE)

            card = _card()
            cl   = QVBoxLayout(card)
            cl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            cl.setSpacing(Spacing.SM)

            # Header
            hr = QHBoxLayout()
            fn_lbl = QLabel(fn)
            fn_lbl.setFont(QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
            fn_lbl.setStyleSheet(f"color: {color}; border: none;")
            hr.addWidget(fn_lbl)
            hr.addStretch()

            status_txt = ("✓ Covered" if fn_count > 0
                          else "○ No risks mapped")
            status_lbl = QLabel(status_txt)
            status_lbl.setFont(Fonts.label_sm_bold())
            status_lbl.setStyleSheet(
                f"color: {Colors.SUCCESS_LT if fn_count else Colors.TEXT_DIM};"
                f"border: none;")
            hr.addWidget(status_lbl)

            cnt_lbl = QLabel(f"  {fn_count} risk{'s' if fn_count != 1 else ''}"
                             f"  ({pct}%)")
            cnt_lbl.setFont(Fonts.label_sm())
            cnt_lbl.setStyleSheet(f"color: {color}; border: none;")
            hr.addWidget(cnt_lbl)
            cl.addLayout(hr)
            cl.addWidget(_bar(pct, color, 10))

            # What this means
            cl.addWidget(_lbl(fn_descriptions.get(fn, ""),
                              color=Colors.TEXT_PRIMARY))

            # Top risks in this function
            top = sorted(fn_risks,
                         key=lambda r: int(r.get("risk_score") or 0),
                         reverse=True)[:3]
            if top:
                top_lbl = _lbl(
                    "Top risks: " + "  ·  ".join(
                        f"{r['title'][:35]} (score {r.get('risk_score',0)})"
                        for r in top),
                    color=Colors.TEXT_MUTED)
                cl.addWidget(top_lbl)

            # Categories covered vs missing
            cats_covered = set(r.get("nist_category", "") for r in fn_risks
                               if r.get("nist_category"))
            all_cats = NIST_CATEGORIES.get(fn, [])
            missing  = [c for c in all_cats if c not in cats_covered]

            if cats_covered:
                cl.addWidget(_lbl("✓  " + "  ·  ".join(sorted(cats_covered)),
                                  color=Colors.SUCCESS_LT))
            if missing:
                cl.addWidget(_lbl("⚠  Not yet covered: " + "  ·  ".join(missing),
                                  color=Colors.MEDIUM))

            # Action required
            action_box = QFrame()
            action_box.setStyleSheet(
                f"background: {Colors.BG_CARD2}; border-radius: {Radius.SM}px;"
                f"border: none;")
            al = QVBoxLayout(action_box)
            al.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            al.addWidget(_lbl(f"▸  {fn_actions.get(fn, '')}",
                              color=Colors.TEXT_PRIMARY))
            cl.addWidget(action_box)

            ovl.addWidget(card)

        if unmapped:
            ovl.addWidget(_rec_card(
                f"{unmapped} risk(s) not mapped to NIST CSF 2.0. "
                f"Open each risk and assign a NIST function to improve coverage reporting.",
                "Medium"))

        vl.addWidget(ov)
        return self._scrolled(container)

    # ── ISO 27001:2022 ────────────────────────────────────────────────────────

    def _build_iso_tab(self, risks: list) -> QWidget:
        """ISO 27001:2022 — Executive domain briefing with gap analysis."""
        from collections import Counter
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        iso_counts = Counter(r.get("iso_domain", "") for r in risks
                             if r.get("iso_domain"))
        total = len(risks) or 1
        mapped = sum(1 for r in risks if r.get("iso_domain"))
        cov_pct = int(mapped / total * 100)

        ov = _card()
        ovl = QVBoxLayout(ov)
        ovl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        ovl.setSpacing(Spacing.SM)
        ovl.addWidget(_section_title(
            "ISO/IEC 27001:2022 — Domain Coverage", Colors.FW_ISO))
        ovl.addWidget(_lbl(
            f"{mapped} of {total} risks mapped to ISO 27001:2022 domains "
            f"({cov_pct}% mapping coverage). "
            "ISO 27001 is the international standard for information security "
            "management — alignment demonstrates board-level security governance.",
            color=Colors.TEXT_PRIMARY))
        ovl.addWidget(_bar(cov_pct, Colors.FW_ISO, 10))

        domain_info = {
            "A.5 Organisational Controls": {
                "desc": "Policies, roles, responsibilities, and asset management.",
                "count": 37,
                "action": "Ensure cybersecurity policy is documented, approved by leadership, and reviewed annually.",
            },
            "A.6 People Controls": {
                "desc": "Personnel security — screening, training, offboarding.",
                "count": 8,
                "action": "Implement security awareness training, background checks, and clear offboarding procedures.",
            },
            "A.7 Physical Controls": {
                "desc": "Physical security of facilities and equipment.",
                "count": 14,
                "action": "Review physical access controls, CCTV, clean desk policy, and equipment disposal procedures.",
            },
            "A.8 Technological Controls": {
                "desc": "Technical controls: access management, encryption, vulnerability management, logging.",
                "count": 34,
                "action": "Prioritise MFA, patch management, privileged access management, and security monitoring.",
            },
        }

        for domain, info in domain_info.items():
            count = iso_counts.get(domain, 0)
            pct   = int(count / total * 100) if total else 0
            dom_risks = [r for r in risks if r.get("iso_domain") == domain]

            card = _card()
            cl   = QVBoxLayout(card)
            cl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            cl.setSpacing(Spacing.SM)

            hr = QHBoxLayout()
            d_lbl = QLabel(domain)
            d_lbl.setFont(QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
            d_lbl.setStyleSheet(f"color: {Colors.FW_ISO}; border: none;")
            hr.addWidget(d_lbl)
            hr.addStretch()
            c_lbl = QLabel(f"{count} risk{'s' if count != 1 else ''}  ({pct}%)")
            c_lbl.setFont(Fonts.label_sm())
            c_lbl.setStyleSheet(f"color: {Colors.FW_ISO}; border: none;")
            hr.addWidget(c_lbl)
            cl.addLayout(hr)
            cl.addWidget(_bar(pct, Colors.FW_ISO))
            cl.addWidget(_lbl(info["desc"], color=Colors.TEXT_PRIMARY))

            # Top risks
            top = sorted(dom_risks,
                         key=lambda r: int(r.get("risk_score") or 0),
                         reverse=True)[:3]
            if top:
                cl.addWidget(_lbl(
                    "Risks: " + "  ·  ".join(
                        f"{r['title'][:35]} ({r.get('risk_score',0)})"
                        for r in top),
                    color=Colors.TEXT_MUTED))

            # Controls mapped
            controls = [r.get("iso_control", "") for r in dom_risks
                        if r.get("iso_control")]
            if controls:
                cl.addWidget(_lbl(
                    f"Controls referenced: {', '.join(sorted(set(controls))[:6])}",
                    color=Colors.SUCCESS_LT))

            # Action
            ab = QFrame()
            ab.setStyleSheet(f"background: {Colors.BG_CARD2}; border-radius:"
                             f"{Radius.SM}px; border: none;")
            al = QVBoxLayout(ab)
            al.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            al.addWidget(_lbl(f"▸  {info['action']}", color=Colors.TEXT_PRIMARY))
            cl.addWidget(ab)
            ovl.addWidget(card)

        unmapped_iso = sum(1 for r in risks if not r.get("iso_domain"))
        if unmapped_iso:
            ovl.addWidget(_rec_card(
                f"{unmapped_iso} risk(s) not mapped to ISO 27001:2022. "
                f"Map each risk to an Annex A domain to support ISO certification or gap assessment.",
                "Medium"))

        vl.addWidget(ov)
        return self._scrolled(container)

    # ── MITRE ATT&CK ─────────────────────────────────────────────────────────

    def _build_mitre_tab(self, risks: list) -> QWidget:
        """MITRE ATT&CK — Threat actor perspective with detection gaps."""
        from collections import Counter
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        mitre_counts = Counter(
            r.get("mitre_tactic", "") for r in risks
            if r.get("mitre_tactic") and
               r.get("mitre_tactic") != "Not Applicable")
        mapped = sum(mitre_counts.values())
        total  = len(risks) or 1

        ov = _card()
        ovl = QVBoxLayout(ov)
        ovl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        ovl.setSpacing(Spacing.SM)
        ovl.addWidget(_section_title(
            "MITRE ATT&CK — Adversary Tactic Coverage", Colors.FW_MITRE))
        ovl.addWidget(_lbl(
            f"{len(mitre_counts)} of 14 ATT&CK tactics represented across "
            f"{mapped} risk(s). "
            "MITRE ATT&CK maps your risks to real-world adversary behaviour — "
            "helping prioritise defences against the most likely attack paths.",
            color=Colors.TEXT_PRIMARY))

        all_tactics = [
            "Reconnaissance", "Resource Development", "Initial Access",
            "Execution", "Persistence", "Privilege Escalation",
            "Defense Evasion", "Credential Access", "Discovery",
            "Lateral Movement", "Collection", "Command & Control",
            "Exfiltration", "Impact",
        ]
        covered_tactics = set(mitre_counts.keys())
        missing_tactics = [t for t in all_tactics if t not in covered_tactics]

        tactic_actions = {
            "Reconnaissance":     "Review public attack surface — patch internet-facing systems, reduce exposed services.",
            "Resource Development": "Threat intel feeds recommended. Monitor for spoofed domains and fake infrastructure.",
            "Initial Access":     "Enforce MFA, patch VPNs/remote access, implement email filtering.",
            "Execution":          "Application whitelisting, disable macros, endpoint detection (EDR).",
            "Persistence":        "Review scheduled tasks, startup items, and privileged accounts regularly.",
            "Privilege Escalation": "Implement least privilege, separate admin accounts, monitor privilege use.",
            "Defense Evasion":    "SIEM tuning, integrity monitoring, and hardened logging configuration.",
            "Credential Access":  "MFA everywhere, password manager policy, monitor failed logins.",
            "Discovery":          "Network segmentation, internal scanning alerts, honeypots.",
            "Lateral Movement":   "Micro-segmentation, jump servers, privileged session management.",
            "Collection":         "DLP tools, classify sensitive data, monitor bulk file access.",
            "Command & Control":  "DNS filtering, proxy inspection, block known C2 infrastructure.",
            "Exfiltration":       "DLP monitoring, block unapproved cloud storage, alert on large transfers.",
            "Impact":             "Immutable backups, offline copies, tested incident response plan.",
        }

        if mitre_counts:
            for tactic, count in sorted(mitre_counts.items(),
                                        key=lambda x: x[1], reverse=True):
                tactic_risks = [r for r in risks if r.get("mitre_tactic") == tactic]
                try:
                    info = get_mitre_info(tactic)
                    tactic_id = info.get("id", "")
                    tactic_desc = info.get("desc", "")
                except Exception:
                    tactic_id = ""
                    tactic_desc = ""

                card = _card()
                cl   = QVBoxLayout(card)
                cl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
                cl.setSpacing(Spacing.SM)

                hr = QHBoxLayout()
                id_lbl = QLabel(f"{tactic_id}  {tactic}" if tactic_id else tactic)
                id_lbl.setFont(QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
                id_lbl.setStyleSheet(f"color: {Colors.FW_MITRE}; border: none;")
                hr.addWidget(id_lbl)
                hr.addStretch()
                c_lbl = QLabel(f"{count} risk{'s' if count != 1 else ''}")
                c_lbl.setFont(Fonts.label_sm_bold())
                c_lbl.setStyleSheet(f"color: {Colors.FW_MITRE}; border: none;")
                hr.addWidget(c_lbl)
                cl.addLayout(hr)

                pct = int(count / total * 100)
                cl.addWidget(_bar(pct, Colors.FW_MITRE))
                if tactic_desc:
                    cl.addWidget(_lbl(tactic_desc, color=Colors.TEXT_PRIMARY))

                top = sorted(tactic_risks,
                             key=lambda r: int(r.get("risk_score") or 0),
                             reverse=True)[:3]
                if top:
                    cl.addWidget(_lbl(
                        "Risks: " + "  ·  ".join(
                            f"{r['title'][:35]} ({r.get('risk_score',0)})"
                            for r in top),
                        color=Colors.TEXT_MUTED))

                # Detection and mitigation action
                action = tactic_actions.get(tactic, "")
                if action:
                    ab = QFrame()
                    ab.setStyleSheet(f"background: {Colors.BG_CARD2};"
                                     f"border-radius: {Radius.SM}px; border: none;")
                    al = QVBoxLayout(ab)
                    al.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
                    al.addWidget(_lbl(f"▸  {action}", color=Colors.TEXT_PRIMARY))
                    cl.addWidget(ab)

                ovl.addWidget(card)

        if missing_tactics:
            miss_card = _card()
            mcl = QVBoxLayout(miss_card)
            mcl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            mcl.setSpacing(Spacing.SM)
            mcl.addWidget(_section_title("Tactics Not Yet in Register", Colors.TEXT_MUTED))
            mcl.addWidget(_lbl(
                "These ATT&CK tactics have no risks mapped. This may indicate "
                "coverage gaps or that these attack vectors have not yet been assessed:",
                color=Colors.TEXT_PRIMARY))
            for t in missing_tactics:
                action = tactic_actions.get(t, "")
                mcl.addWidget(_lbl(
                    f"○  {t}" + (f" — {action}" if action else ""),
                    color=Colors.TEXT_DIM))
            ovl.addWidget(miss_card)

        if not mitre_counts:
            ovl.addWidget(_rec_card(
                "No risks mapped to MITRE ATT&CK tactics. "
                "Map each risk to a tactic to understand your exposure to real-world attack patterns.",
                "High"))

        vl.addWidget(ov)
        return self._scrolled(container)

    # ── CIS Controls v8 ──────────────────────────────────────────────────────

    def _build_cis_tab(self, risks: list) -> QWidget:
        """CIS Controls v8 — Full control names, IG grouping, gap analysis."""
        from collections import Counter
        import re as _re

        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        def _cis_key(val):
            if not val or val in ("Not Applicable", ""):
                return "Not Applicable"
            m = _re.match(r"(CIS-\d+)", str(val))
            return m.group(1) if m else val

        cis_counts = Counter(
            _cis_key(r.get("cis_control", "Not Applicable")) for r in risks)
        covered = {k for k in cis_counts
                   if k not in ("Not Applicable", "", None)}
        total_cis = 18
        cov_pct   = int(len(covered) / total_cis * 100)

        ov = _card()
        ovl = QVBoxLayout(ov)
        ovl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        ovl.setSpacing(Spacing.SM)
        ovl.addWidget(_section_title(
            f"CIS Controls v8 — {len(covered)} of 18 Controls Covered ({cov_pct}%)",
            Colors.FW_CIS))
        ovl.addWidget(_lbl(
            "CIS Controls v8 provides 18 prioritised safeguards organised into "
            "Implementation Groups (IG1=Essential, IG2=Advanced, IG3=Expert). "
            "Start with IG1 — these controls prevent the majority of common attacks.",
            color=Colors.TEXT_PRIMARY))
        ovl.addWidget(_bar(cov_pct, Colors.FW_CIS, 12))

        for ig in ("IG1", "IG2", "IG3"):
            ig_controls = {k: v for k, v in CIS_CONTROL_DATA.items()
                           if v.get("ig") == ig and k != "Not Applicable"}
            ig_covered  = [c for c in ig_controls if c in covered]
            ig_missing  = [c for c in ig_controls if c not in covered]
            ig_pct = int(len(ig_covered) / len(ig_controls) * 100) if ig_controls else 0

            ig_desc = {
                "IG1": "Essential — Basic cyber hygiene that every organisation must implement.",
                "IG2": "Advanced — For organisations managing sensitive data or critical services.",
                "IG3": "Expert — For organisations managing critical infrastructure or high-value targets.",
            }

            ig_card = _card()
            il = QVBoxLayout(ig_card)
            il.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            il.setSpacing(Spacing.SM)

            hr = QHBoxLayout()
            ig_title = QLabel(f"Implementation Group {ig[-1]}  ({ig})")
            ig_title.setFont(QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
            ig_title.setStyleSheet(f"color: {Colors.FW_CIS}; border: none;")
            hr.addWidget(ig_title)
            hr.addStretch()
            ig_cov_lbl = QLabel(f"{len(ig_covered)}/{len(ig_controls)} controls  ({ig_pct}%)")
            ig_cov_lbl.setFont(Fonts.label_sm_bold())
            ig_cov_lbl.setStyleSheet(f"color: {Colors.FW_CIS}; border: none;")
            hr.addWidget(ig_cov_lbl)
            il.addLayout(hr)
            il.addWidget(_bar(ig_pct, Colors.FW_CIS))
            il.addWidget(_lbl(ig_desc.get(ig, ""), color=Colors.TEXT_PRIMARY))
            ovl.addWidget(ig_card)

            for key, info in ig_controls.items():
                count = cis_counts.get(key, 0)
                card  = _card()
                cl    = QVBoxLayout(card)
                cl.setContentsMargins(Spacing.LG, Spacing.SM, Spacing.LG, Spacing.SM)
                cl.setSpacing(4)
                hr2 = QHBoxLayout()

                status_icon = "✓" if count else "○"
                status_color = Colors.SUCCESS_LT if count else Colors.TEXT_DIM
                icon_lbl = QLabel(status_icon)
                icon_lbl.setFont(QFont(Fonts.FAMILY, 12))
                icon_lbl.setStyleSheet(f"color: {status_color}; border: none;")
                icon_lbl.setFixedWidth(20)
                hr2.addWidget(icon_lbl)

                t_lbl = QLabel(f"{key}  ·  {info['title']}")
                t_lbl.setFont(QFont(Fonts.FAMILY, 10, QFont.Weight.Bold))
                t_lbl.setStyleSheet(
                    f"color: {Colors.TEXT_PRIMARY if count else Colors.TEXT_MUTED};"
                    f"border: none;")
                hr2.addWidget(t_lbl, 1)

                if count:
                    cnt_lbl = QLabel(f"{count} risk{'s' if count != 1 else ''}")
                    cnt_lbl.setFont(Fonts.label_sm_bold())
                    cnt_lbl.setStyleSheet(f"color: {Colors.FW_CIS}; border: none;")
                    hr2.addWidget(cnt_lbl)

                cl.addLayout(hr2)
                cl.addWidget(_lbl(info.get("desc", ""), color=Colors.TEXT_DIM))
                ovl.addWidget(card)

        vl.addWidget(ov)
        return self._scrolled(container)

    # ── CIA Triad ─────────────────────────────────────────────────────────────

    def _build_cia_tab(self, risks: list) -> QWidget:
        """CIA Triad — Executive briefing with business context per component."""
        from collections import Counter
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        cia_counts = Counter(
            r.get("cia_component", "Unmapped") for r in risks)
        total = len(risks) or 1

        ov = _card()
        ovl = QVBoxLayout(ov)
        ovl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        ovl.setSpacing(Spacing.SM)
        ovl.addWidget(_section_title("CIA Triad — Risk Distribution", Colors.FW_CIA))
        ovl.addWidget(_lbl(
            "The CIA Triad (Confidentiality, Integrity, Availability) is the "
            "foundational model for categorising security risk. "
            "Understanding distribution across these pillars guides investment "
            "prioritisation and board communication.",
            color=Colors.TEXT_PRIMARY))

        cia_info = [
            ("Confidentiality", Colors.ACCENT_BLUE, "🔒",
             "Protecting data from unauthorised access or disclosure.",
             "Business impact: regulatory fines (GDPR), reputational damage, "
             "loss of customer trust, competitive disadvantage.",
             "Review access controls, encryption at rest/in transit, data classification, "
             "and DLP tools. Ensure only authorised personnel access sensitive data."),
            ("Integrity", Colors.SUCCESS_LT, "✓",
             "Ensuring data accuracy and preventing unauthorised modification.",
             "Business impact: corrupted financial records, operational errors, "
             "loss of confidence in data-driven decisions.",
             "Implement integrity monitoring, change management controls, "
             "digital signatures, and database activity monitoring."),
            ("Availability", Colors.MEDIUM, "◉",
             "Ensuring systems and data are accessible when needed.",
             "Business impact: revenue loss from downtime, SLA penalties, "
             "customer churn, reputational damage.",
             "Prioritise BCP/DR, backup testing, redundant systems, "
             "DDoS mitigation, and uptime monitoring."),
            ("All Three", Colors.FW_CIA, "⬡",
             "Risks affecting all three CIA components simultaneously.",
             "Business impact: maximum exposure — ransomware, insider threats, "
             "and major breaches typically affect all three.",
             "These risks require the highest priority treatment. "
             "Consider immediate escalation and dedicated incident response planning."),
        ]

        for component, color, icon, desc, biz_impact, action in cia_info:
            count = cia_counts.get(component, 0)
            pct   = int(count / total * 100)
            comp_risks = [r for r in risks if r.get("cia_component") == component]

            card = _card()
            cl   = QVBoxLayout(card)
            cl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            cl.setSpacing(Spacing.SM)

            hr = QHBoxLayout()
            ic = QLabel(icon)
            ic.setFont(QFont(Fonts.FAMILY, 14))
            ic.setStyleSheet(f"color: {color}; border: none;")
            ic.setFixedWidth(24)
            hr.addWidget(ic)
            c_title = QLabel(component)
            c_title.setFont(QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
            c_title.setStyleSheet(f"color: {color}; border: none;")
            hr.addWidget(c_title)
            hr.addStretch()
            c_count = QLabel(f"{count} risk{'s' if count != 1 else ''}  ({pct}%)")
            c_count.setFont(Fonts.label_sm_bold())
            c_count.setStyleSheet(f"color: {color}; border: none;")
            hr.addWidget(c_count)
            cl.addLayout(hr)
            cl.addWidget(_bar(pct, color))

            cl.addWidget(_lbl(desc, color=Colors.TEXT_PRIMARY))
            if biz_impact:
                cl.addWidget(_lbl(f"📊  {biz_impact}", color=Colors.TEXT_MUTED))

            top = sorted(comp_risks,
                         key=lambda r: int(r.get("risk_score") or 0),
                         reverse=True)[:3]
            if top:
                cl.addWidget(_lbl(
                    "Top risks: " + "  ·  ".join(
                        f"{r['title'][:35]} ({r.get('risk_score',0)})"
                        for r in top),
                    color=Colors.TEXT_DIM))

            if action:
                ab = QFrame()
                ab.setStyleSheet(f"background: {Colors.BG_CARD2};"
                                 f"border-radius: {Radius.SM}px; border: none;")
                al = QVBoxLayout(ab)
                al.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
                al.addWidget(_lbl(f"▸  {action}", color=Colors.TEXT_PRIMARY))
                cl.addWidget(ab)

            ovl.addWidget(card)

        # Unmapped
        unmapped_cia = sum(1 for r in risks
                           if not r.get("cia_component") or
                           r.get("cia_component") == "Unmapped")
        if unmapped_cia:
            ovl.addWidget(_rec_card(
                f"{unmapped_cia} risk(s) not mapped to a CIA component. "
                f"Map each risk to Confidentiality, Integrity, or Availability "
                f"to complete the impact analysis.",
                "Low"))

        vl.addWidget(ov)
        return self._scrolled(container)

    # ── Recommendations ───────────────────────────────────────────────────────

    def _build_recs_tab(self, risks: list) -> QWidget:
        container = QWidget()
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(Spacing.MD)

        if not risks:
            card = _card()
            cl   = QVBoxLayout(card)
            cl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            cl.addWidget(_lbl(
                "Add risks to the register to generate recommendations.",
                color=Colors.TEXT_MUTED))
            vl.addWidget(card)
            return self._scrolled(container)

        recs = self._generate_recommendations(risks)
        for priority in ("Critical", "High", "Medium", "Low"):
            pr_recs = [r for r in recs if r["priority"] == priority]
            if not pr_recs:
                continue
            priority_colors = {
                "Critical": Colors.CRITICAL, "High": Colors.HIGH,
                "Medium": Colors.MEDIUM,     "Low": Colors.LOW,
            }
            pc = priority_colors.get(priority, Colors.ACCENT_BLUE)

            card = _card()
            cl   = QVBoxLayout(card)
            cl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            cl.setSpacing(Spacing.SM)

            hdr = QHBoxLayout()
            p_lbl = QLabel(f"{priority} Priority")
            p_lbl.setFont(QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
            p_lbl.setStyleSheet(f"color: {pc}; border: none;")
            hdr.addWidget(p_lbl)
            hdr.addStretch()
            cnt = QLabel(f"{len(pr_recs)} recommendation{'s' if len(pr_recs) != 1 else ''}")
            cnt.setFont(Fonts.label_sm())
            cnt.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none;")
            hdr.addWidget(cnt)
            cl.addLayout(hdr)

            for rec in pr_recs:
                cl.addWidget(_rec_card(rec["text"], priority))

            vl.addWidget(card)

        return self._scrolled(container)

    def _generate_recommendations(self, risks: list) -> list:
        """Generate intelligent recommendations from the risk register."""
        recs = []
        titles = " ".join(
            (r.get("title", "") + " " + r.get("description", "")).lower()
            for r in risks)
        crit_count   = sum(1 for r in risks if int(r.get("risk_score") or 0) >= 15)
        unmapped_nist = sum(1 for r in risks if not r.get("nist_function"))

        if crit_count > 0:
            recs.append({"priority": "Critical",
                         "text": f"{crit_count} critical risk{'s' if crit_count>1 else ''} "
                                 f"(score ≥ 15) require immediate treatment plans. "
                                 f"Assign owners and target dates this week."})

        if any(w in titles for w in
               ("mfa", "multi-factor", "authenticat", "password",
                "credential", "brute force")):
            recs.append({"priority": "High",
                         "text": "Credential and authentication risks detected. "
                                 "Implement Multi-Factor Authentication for all privileged accounts."})

        if any(w in titles for w in
               ("patch", "update", "vulnerability", "cve", "unpatched")):
            recs.append({"priority": "High",
                         "text": "Patch management risks present. "
                                 "Deploy a centralised patch management solution "
                                 "and establish a monthly patching cadence."})

        if any(w in titles for w in
               ("backup", "recovery", "restore", "rto", "rpo", "disaster")):
            recs.append({"priority": "High",
                         "text": "Data recovery risks identified. "
                                 "Test backup restoration quarterly "
                                 "and document RTO/RPO targets."})

        if any(w in titles for w in
               ("firewall", "network", "perimeter", "segmentation", "dmz")):
            recs.append({"priority": "Medium",
                         "text": "Network security risks present. "
                                 "Review firewall rules quarterly "
                                 "and implement network segmentation."})

        if any(w in titles for w in
               ("vendor", "third.party", "supplier", "supply chain")):
            recs.append({"priority": "Medium",
                         "text": "Vendor/supply chain risks identified. "
                                 "Conduct annual vendor security assessments "
                                 "and review SLAs."})

        if any(w in titles for w in
               ("phish", "email", "social engineer", "awareness", "training")):
            recs.append({"priority": "Medium",
                         "text": "Social engineering risks present. "
                                 "Implement regular security awareness training "
                                 "and phishing simulations."})

        if any(w in titles for w in
               ("ransomware", "encrypt", "malware", "virus", "worm")):
            recs.append({"priority": "Critical",
                         "text": "Malware/ransomware risks identified. "
                                 "Deploy endpoint detection and response (EDR) "
                                 "and maintain offline, immutable backups."})

        if any(w in titles for w in
               ("insider", "privilege", "access control", "least privilege")):
            recs.append({"priority": "High",
                         "text": "Insider threat and access control risks present. "
                                 "Implement principle of least privilege and "
                                 "conduct quarterly access reviews."})

        if any(w in titles for w in
               ("gdpr", "data protection", "pii", "personal data", "privacy")):
            recs.append({"priority": "High",
                         "text": "Data protection and privacy risks identified. "
                                 "Review GDPR compliance posture "
                                 "and conduct a data mapping exercise."})

        if unmapped_nist > 0:
            recs.append({"priority": "Low",
                         "text": f"{unmapped_nist} risk{'s' if unmapped_nist>1 else ''} "
                                 f"not mapped to NIST CSF 2.0. "
                                 f"Complete framework mapping to improve "
                                 f"coverage reporting."})

        if len(recs) < 3:
            recs.append({"priority": "Medium",
                         "text": "Review all High and Critical risks monthly "
                                 "to ensure treatment plans remain on track."})
            recs.append({"priority": "Low",
                         "text": "Schedule a quarterly GRC review to assess "
                                 "risk posture changes and update the risk register."})

        return recs

    def _scrolled(self, widget: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidget(widget)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setStyleSheet("border: none; background: transparent;")
        sa.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return sa
