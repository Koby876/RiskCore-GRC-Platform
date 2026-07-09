"""
widgets/navigation.py
─────────────────────
RiskCore Enterprise Sidebar Navigation — v1.5

Enterprise-grade sidebar with:
  - Brand mark + version
  - Section groups with icons, full-width dividers, breathing space
  - Navigation buttons with active highlight
  - Framework status pills (compact)
  - Org name sync via settings_saved signal
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap, QColor, QPainter, QPen

from assets.themes.design_system import Colors, Fonts, Spacing, Radius


# ── Section metadata ──────────────────────────────────────────────────────────
_SECTION_ICONS = {
    "OVERVIEW":        "▣",
    "RISK MANAGEMENT": "⬡",
    "ANALYSIS":        "◎",
    "REPORTING":       "↗",
    "ADMINISTRATION":  "⚙",
}


class NavButton(QPushButton):
    """Single sidebar navigation button — left-aligned, icon + label."""

    def __init__(self, icon: str, label: str, page_key: str, parent=None):
        super().__init__(parent)
        self.page_key = page_key
        self.setText(f"  {icon}   {label}")
        self.setFont(Fonts.label())
        self.setFixedHeight(34)
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)

    def _apply_style(self, active: bool) -> None:
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.ACCENT_RED};
                    color: white;
                    border: none;
                    border-radius: {Radius.SM}px;
                    padding: 5px 12px;
                    text-align: left;
                    font-weight: bold;
                    font-size: 10pt;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Colors.TEXT_MUTED};
                    border: none;
                    border-radius: {Radius.SM}px;
                    padding: 5px 12px;
                    text-align: left;
                    font-size: 10pt;
                }}
                QPushButton:hover {{
                    background-color: {Colors.BG_BORDER};
                    color: {Colors.TEXT_PRIMARY};
                }}
            """)

    def set_active(self, active: bool) -> None:
        self._apply_style(active)


class _SectionHeader(QWidget):
    """
    Full-width section divider — enterprise style.

    Layout:
      ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔  (thin blue top line)
       ICON  SECTION LABEL
    """

    def __init__(self, section: str, first: bool = False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 8 if not first else 4, 0, 2)
        vl.setSpacing(0)

        # Full-width accent line
        if not first:
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(
                f"background: {Colors.ACCENT_BLUE};"
                f"border: none; opacity: 0.4;")
            vl.addWidget(line)

        vl.addSpacing(4)

        # Icon + label row
        row = QHBoxLayout()
        row.setContentsMargins(10, 0, 8, 0)
        row.setSpacing(5)

        icon_char = _SECTION_ICONS.get(section, "·")
        icon_lbl = QLabel(icon_char)
        icon_lbl.setFont(QFont(Fonts.FAMILY, 9))
        icon_lbl.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE}; border: none;")
        row.addWidget(icon_lbl)

        sec_lbl = QLabel(section)
        sec_lbl.setFont(QFont(Fonts.FAMILY, 7, QFont.Weight.Bold))
        sec_lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; border: none;"
            f"letter-spacing: 1px;")
        row.addWidget(sec_lbl, 1)
        vl.addLayout(row)


class FwPill(QPushButton):
    """
    Framework status badge — compact row showing name + coverage indicator.
    Clickable: opens Framework Intelligence page.
    Displays: name left, coverage % or ✓ right.
    """
    clicked_fw = Signal()

    def __init__(self, name: str, color: str, parent=None):
        super().__init__(parent)
        self._name  = name
        self._color = color
        self._pct   = None  # None = not yet loaded
        self._update_display()
        self.setFixedHeight(18)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Click to open Framework Intelligence — {name}")
        self.clicked.connect(self.clicked_fw)

    def _update_display(self):
        pct_txt = f"  {self._pct}%" if self._pct is not None else "  ✓"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._color};
                color: white;
                border: none;
                border-radius: 3px;
                padding: 1px 6px;
                text-align: left;
                font-family: "Segoe UI";
                font-size: 7pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.85;
            }}
        """)
        # name left + status right using fixed-width trick
        self.setText(f"{self._name}   {pct_txt}")

    def set_coverage(self, pct: int | None) -> None:
        """Update coverage indicator. pct=None shows ✓, int shows N%."""
        self._pct = pct
        self._update_display()


class Sidebar(QWidget):
    """
    Full sidebar widget.

    Signals
    -------
    page_requested(str) : page navigation request
    """
    page_requested = Signal(str)

    NAV_ITEMS = [
        # (section, icon, label, page_key)
        ("OVERVIEW",         "▣",  "Dashboard",       "dashboard"),
        ("RISK MANAGEMENT",  "≡",  "Risk Register",   "register"),
        ("RISK MANAGEMENT",  "+",  "Add Risk",        "add"),
        ("RISK MANAGEMENT",  "◈",  "Treatments",      "treatments"),
        ("RISK MANAGEMENT",  "⊞",  "Risk Matrix",     "matrix"),
        ("ANALYSIS",         "◎",  "AI Analysis",     "ai"),
        ("ANALYSIS",         "◉",  "Framework Intel", "framework"),
        ("REPORTING",        "↗",  "Export Report",   "export"),
        ("REPORTING",        "⊙",  "Audit Log",       "audit"),
        ("ADMINISTRATION",   "⚙",  "Settings",        "settings"),
    ]

    FW_PILLS = [
        ("NIST CSF 2.0",    Colors.FW_NIST),
        ("ISO 27001:2022",  Colors.FW_ISO),
        ("MITRE ATT&CK",    Colors.FW_MITRE),
        ("CIS Controls v8", Colors.FW_CIS),
        ("CIA Triad",       Colors.FW_CIA),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(230)
        self.setStyleSheet(
            f"background-color: {Colors.BG_SIDEBAR};"
            f"border-right: 1px solid {Colors.BG_BORDER};")

        self._buttons: dict[str, NavButton] = {}
        self._current_page: str = "dashboard"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Brand ─────────────────────────────────────────────────────
        brand_w = QWidget()
        brand_w.setFixedHeight(68)
        brand_l = QHBoxLayout(brand_w)
        brand_l.setContentsMargins(Spacing.LG, Spacing.MD,
                                    Spacing.LG, Spacing.MD)

        import os as _os, sys as _sys
        # Find logo: try PyInstaller paths first, then dev path
        _cands = []
        if hasattr(_sys, "_MEIPASS"):
            _cands.append(_os.path.join(_sys._MEIPASS,
                "assets", "images", "riskcore_logo.png"))
        _cands.append(_os.path.join(
            _os.path.dirname(_sys.executable),
            "_internal", "assets", "images", "riskcore_logo.png"))
        _cands.append(_os.path.join(
            _os.path.dirname(_sys.executable),
            "assets", "images", "riskcore_logo.png"))
        _cands.append(_os.path.normpath(_os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)),
            "..", "assets", "images", "riskcore_logo.png")))
        _logo = next((p for p in _cands if _os.path.exists(p)), None)

        if _logo:
            from PySide6.QtGui import QPixmap
            _pix = QPixmap(_logo)
            if not _pix.isNull():
                hex_lbl = QLabel()
                hex_lbl.setPixmap(_pix.scaled(
                    38, 38,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                hex_lbl.setFixedSize(38, 38)
                hex_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hex_lbl.setStyleSheet("border: none; background: transparent;")
            else:
                _logo = None  # pixmap failed, fall through to text

        if not _logo:
            hex_lbl = QLabel("⬡")
            hex_lbl.setFont(QFont(Fonts.FAMILY, 28, QFont.Weight.Bold))
            hex_lbl.setStyleSheet(f"color: {Colors.ACCENT_RED}; border: none;")
            hex_lbl.setFixedSize(38, 38)
            hex_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_l.addWidget(hex_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        name_lbl = QLabel("RiskCore")
        name_lbl.setFont(QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        name_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        text_col.addWidget(name_lbl)
        ver_lbl = QLabel("GRC Platform  v1.5")
        ver_lbl.setFont(QFont(Fonts.FAMILY, 7))
        ver_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        text_col.addWidget(ver_lbl)

        brand_l.addLayout(text_col)
        brand_l.addStretch()
        layout.addWidget(brand_w)

        # Brand bottom divider — solid blue accent
        brand_div = QFrame()
        brand_div.setFixedHeight(2)
        brand_div.setStyleSheet(
            f"background: {Colors.ACCENT_BLUE}; border: none;")
        layout.addWidget(brand_div)

        # ── Navigation ────────────────────────────────────────────────
        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(Spacing.SM, Spacing.SM,
                                       Spacing.SM, Spacing.SM)
        nav_layout.setSpacing(2)

        current_section = None
        for i, (section, icon, label, key) in enumerate(self.NAV_ITEMS):
            if section != current_section:
                current_section = section
                is_first = (i == 0)
                nav_layout.addWidget(
                    _SectionHeader(section, first=is_first))
                # Extra 2px breathing room after section header
                nav_layout.addSpacing(2)

            btn = NavButton(icon, label, key)
            btn.clicked.connect(
                lambda checked, k=key: self._on_nav(k))
            nav_layout.addWidget(btn)
            self._buttons[key] = btn

        nav_layout.addStretch()
        layout.addWidget(nav_container, 1)

        # ── Framework pills ───────────────────────────────────────────
        fw_div = QFrame()
        fw_div.setFixedHeight(1)
        fw_div.setStyleSheet(
            f"background: {Colors.BG_BORDER}; border: none;")
        layout.addWidget(fw_div)

        pills_w = QWidget()
        pills_w.setStyleSheet("background: transparent;")
        pills_l = QVBoxLayout(pills_w)
        pills_l.setContentsMargins(Spacing.SM, 5, Spacing.SM, 5)
        pills_l.setSpacing(2)
        self._fw_pills: dict[str, FwPill] = {}
        for name, color in self.FW_PILLS:
            pill = FwPill(name, color)
            pill.clicked_fw.connect(
                lambda: self._on_nav("framework"))
            pills_l.addWidget(pill)
            self._fw_pills[name] = pill
        layout.addWidget(pills_w)

        # ── AI pending badge ──────────────────────────────────────────
        bot_div = QFrame()
        bot_div.setFixedHeight(1)
        bot_div.setStyleSheet(
            f"background: {Colors.BG_BORDER}; border: none;")
        layout.addWidget(bot_div)

        self._ai_badge = QLabel("")
        self._ai_badge.setFont(QFont(Fonts.FAMILY, 9))
        self._ai_badge.setStyleSheet(
            f"color: {Colors.MEDIUM}; padding: 5px 14px;")
        self._ai_badge.setVisible(False)
        layout.addWidget(self._ai_badge)

        self._set_active("dashboard")

    # ── Public API ────────────────────────────────────────────────────

    def _on_nav(self, page_key: str) -> None:
        self._set_active(page_key)
        self.page_requested.emit(page_key)

    def _set_active(self, page_key: str) -> None:
        self._current_page = page_key
        for key, btn in self._buttons.items():
            btn.set_active(key == page_key)

    def set_active_page(self, page_key: str) -> None:
        self._set_active(page_key)

    def update_fw_coverage(self, coverage: dict) -> None:
        """
        Update framework badge coverage indicators.
        coverage = {"NIST CSF 2.0": 75, "ISO 27001:2022": None, ...}
        None = fully covered (shows ✓), int = percentage.
        """
        for name, pill in self._fw_pills.items():
            pct = coverage.get(name)
            pill.set_coverage(pct)

    def set_ai_pending(self, count: int) -> None:
        if count > 0:
            self._ai_badge.setText(f"◎  {count} risks pending review")
            self._ai_badge.setVisible(True)
        else:
            self._ai_badge.setVisible(False)
