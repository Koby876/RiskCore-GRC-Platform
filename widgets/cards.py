"""
ui/widgets/cards.py
────────────────────
Reusable card widgets for the RiskCore Enterprise Design System.

Every page consumes these. No page builds its own card layout.
"""

from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QSizePolicy, QProgressBar,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QFont

from assets.themes.design_system import Colors, Fonts, Spacing, Radius


# ── Utility: set QSS property and refresh ────────────────────────────────────

def _set_class(widget: QWidget, cls: str) -> None:
    widget.setProperty("class", cls)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# ── Card frame base ───────────────────────────────────────────────────────────

class Card(QFrame):
    """Standard card container — dark background, rounded corners, border."""
    def __init__(self, parent=None, variant: str = "card"):
        super().__init__(parent)
        self.setProperty("class", variant)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def inner_layout(self) -> QVBoxLayout:
        return self._layout


class Card2(Card):
    """Alternate card — slightly lighter background."""
    def __init__(self, parent=None):
        super().__init__(parent, variant="card2")


# ── KPI Card ─────────────────────────────────────────────────────────────────

class KpiCard(QFrame):
    """
    Executive KPI card — clean enterprise style.

    +─────────────────────────────+
    │  TITLE               ICON   │  ← coloured top accent bar
    │                             │
    │         VALUE (32pt)        │  ← centred, bold, colour-coded
    │                             │
    │       sub-text (muted)      │  ← centred below
    +─────────────────────────────+

    Design principles:
    - Minimal borders — 1px only, no visual noise
    - Coloured top accent bar (3px) identifies severity at a glance
    - Value centred and prominent (not left-aligned)
    - Title uppercase, muted — label not header
    - Clickable with hand cursor and hover tint
    """
    clicked = Signal()

    def __init__(
        self,
        title: str,
        value: str,
        sub: str = "",
        icon: str = "",
        value_color: str = Colors.TEXT_PRIMARY,
        bg_color: str = None,
        clickable: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.setFrameShape(QFrame.Shape.NoFrame)

        # Card background + border
        bg = bg_color or Colors.BG_CARD
        self.setStyleSheet(
            f"QFrame[class='card'] {{"
            f"  background-color: {bg};"
            f"  border-radius: {Radius.MD}px;"
            f"  border: 1px solid {Colors.BG_BORDER};"
            f"}}"
        )

        if clickable:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Coloured top accent bar (3px) — severity at a glance
        accent = QFrame()
        accent.setFixedHeight(3)
        accent.setStyleSheet(
            f"background: {value_color}; border: none;"
            f"border-radius: 0px;")
        layout.addWidget(accent)

        # Content area
        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.MD)
        cl.setSpacing(2)

        # Title row (left) + icon (right)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        title_lbl = QLabel(title.upper())
        title_lbl.setFont(QFont(Fonts.FAMILY, 7, QFont.Weight.Bold))
        title_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;"
            f"letter-spacing: 1px;")
        top.addWidget(title_lbl, 1)
        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setFont(Fonts.label_sm())
            icon_lbl.setStyleSheet(
                f"color: {value_color}; border: none;")
            top.addWidget(icon_lbl)
        cl.addLayout(top)

        # Spacer above value
        cl.addSpacing(4)

        # Value — large, centred, bold
        self._value_lbl = QLabel(str(value))
        self._value_lbl.setFont(Fonts.kpi_value())
        self._value_lbl.setStyleSheet(
            f"color: {value_color}; border: none;")
        self._value_lbl.setAlignment(
            Qt.AlignmentFlag.AlignHCenter)
        cl.addWidget(self._value_lbl)

        # Sub text — centred, muted
        if sub:
            sub_lbl = QLabel(sub)
            sub_lbl.setFont(QFont(Fonts.FAMILY, 7))
            sub_lbl.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none;")
            sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cl.addWidget(sub_lbl)

        cl.addStretch()
        layout.addWidget(content, 1)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(100)

    def set_value(self, value: str) -> None:
        self._value_lbl.setText(str(value))

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


# ── Section Header ────────────────────────────────────────────────────────────

class SectionHeader(QWidget):
    """
    Card section header with title and optional subtitle.
    Used at the top of every card panel.
    """
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.SM)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(Fonts.heading_3())
        title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setFont(Fonts.label_sm())
            sub_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            layout.addWidget(sub_lbl)


# ── Page Header ───────────────────────────────────────────────────────────────

class PageHeader(QWidget):
    """
    Standardised page header — large title, subtitle, optional right-side
    action buttons.

    Usage:
        hdr = PageHeader("Risk Register",
                         "All risks  ·  Click a row to view")
        hdr.add_action(btn)
    """
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(Fonts.heading_1())
        title_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        text_col.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setFont(Fonts.label())
            sub_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            text_col.addWidget(sub_lbl)

        self._layout.addLayout(text_col)
        self._layout.addStretch()

        self._actions = QHBoxLayout()
        self._actions.setSpacing(Spacing.SM)
        self._layout.addLayout(self._actions)

    def add_action(self, widget: QWidget) -> None:
        self._actions.addWidget(widget)


# ── Framework Coverage Bar ────────────────────────────────────────────────────

class FwCoverageRow(QWidget):
    """
    Single framework coverage row:
    [Name label]  [progress bar]  [pct%]
    """
    def __init__(
        self,
        framework: str,
        pct: float,
        confirmed: int,
        total: int,
        parent=None,
    ):
        super().__init__(parent)
        color = Colors.fw_color(framework)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(Spacing.SM)

        # Short name
        short = {
            "NIST CSF 2.0":       "NIST CSF 2.0",
            "ISO/IEC 27001:2022": "ISO 27001",
            "MITRE ATT&CK":       "MITRE",
            "CIS Controls v8":    "CIS v8",
            "CIA Triad":          "CIA Triad",
        }.get(framework, framework[:12])

        lbl = QLabel(short)
        lbl.setFont(Fonts.label_sm_bold())
        lbl.setStyleSheet(f"color: {color};")
        lbl.setFixedWidth(80)
        layout.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(pct))
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG_BORDER};
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(bar, 1)

        pct_lbl = QLabel(f"{pct:.0f}%")
        pct_lbl.setFont(Fonts.label_sm_bold())
        pct_lbl.setStyleSheet(f"color: {color};")
        pct_lbl.setFixedWidth(36)
        pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(pct_lbl)


# ── Severity Badge ────────────────────────────────────────────────────────────

class SeverityBadge(QLabel):
    """Compact coloured pill showing score label (CRITICAL / HIGH / etc.)"""
    def __init__(self, score: int, parent=None):
        super().__init__(parent)
        label = Colors.severity_label(score)
        color = Colors.severity_color(score)
        self.setText(f" {label} ")
        self.setFont(Fonts.badge())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: {Radius.SM}px;
                padding: 2px 6px;
            }}
        """)
        self.setFixedHeight(20)


# ── Strategy Badge ────────────────────────────────────────────────────────────

class StrategyBadge(QLabel):
    """Coloured pill for treatment strategy."""
    def __init__(self, strategy: str, parent=None):
        super().__init__(parent)
        color = Colors.treat_color(strategy)
        self.setText(f" {strategy[:8]} ")
        self.setFont(Fonts.badge())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: {Radius.SM}px;
                padding: 2px 4px;
            }}
        """)
        self.setFixedHeight(20)


# ── NIST Function Badge ───────────────────────────────────────────────────────

class NistBadge(QLabel):
    """Coloured pill for NIST CSF 2.0 function."""
    def __init__(self, function: str, parent=None):
        super().__init__(parent)
        color = Colors.nist_color(function)
        self.setText(f" {function} ")
        self.setFont(Fonts.badge())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: {Radius.SM}px;
                padding: 2px 6px;
            }}
        """)
        self.setFixedHeight(20)


# ── Status Badge ──────────────────────────────────────────────────────────────

class StatusBadge(QLabel):
    """Status pill (Open / Mitigated / Closed)."""
    STATUS_COLORS = {
        "Open":       Colors.MEDIUM,
        "In Progress":Colors.ACCENT_BLUE,
        "Mitigated":  Colors.SUCCESS_LT,
        "Accepted":   Colors.TEXT_MUTED,
        "Closed":     Colors.TEXT_DIM,
    }
    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        color = self.STATUS_COLORS.get(status, Colors.TEXT_MUTED)
        self.setText(f" {status} ")
        self.setFont(Fonts.badge())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: {Radius.SM}px;
                padding: 2px 6px;
            }}
        """)
        self.setFixedHeight(20)


# ── Divider ───────────────────────────────────────────────────────────────────

class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(
            f"background-color: {Colors.BG_BORDER}; max-height: 1px;")
