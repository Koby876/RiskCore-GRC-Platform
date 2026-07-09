"""
ui/widgets/components.py
─────────────────────────
RiskCore Enterprise Widget Library — complete component set.

Every page imports from here. Nothing is reinvented in page files.

Widgets
-------
ExecutiveCard       — large card with icon, headline, body, optional action
ChartCard           — card with a title bar, chart-area placeholder,
                      and a reusable bar/donut chart made of QFrame strips
SectionHeader       — section title with optional subtitle and rule
StatusBadge         — severity / status / treatment-status coloured pill
FrameworkBadge      — framework-specific coloured pill (NIST / ISO / MITRE…)
Timeline            — scrollable activity-timeline widget
FilterBar           — standardised horizontal filter row (dropdowns + search)
SearchPanel         — standalone search + clear button
EmptyState          — centred icon + title + body + optional action cards
LoadingOverlay      — semi-transparent "Loading…" overlay over any widget
Toast               — slide-in notification banner (auto-dismisses)
ConfirmationDialog  — modal confirm/cancel with title, body, button labels

All widgets consume tokens from design_system.py exclusively.
"""

from __future__ import annotations
from typing import Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QDialog, QGraphicsOpacityEffect,
    QSizePolicy, QLineEdit, QComboBox, QLayout,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation,
    QEasingCurve, QSize, QPoint,
)
from PySide6.QtGui import QFont, QColor, QCursor, QPainter

from assets.themes.design_system import Colors, Fonts, Spacing, Radius


# ── Internal helpers ──────────────────────────────────────────────────────────

def _styled_btn(text: str, color: str = Colors.BG_BORDER,
                text_color: str = Colors.TEXT_MUTED,
                height: int = 32) -> QPushButton:
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
        QPushButton:disabled {{
            background-color: {Colors.BG_BORDER};
            color: {Colors.TEXT_DIM};
        }}
    """)
    return b


def _card_frame(bg: str = Colors.BG_CARD) -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"background-color: {bg};"
        f"border-radius: {Radius.LG}px;"
        f"border: 1px solid {Colors.BG_BORDER};")
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  ExecutiveCard
# ══════════════════════════════════════════════════════════════════════════════

class ExecutiveCard(QFrame):
    """
    Large executive summary card.

    +─────────────────────────────────────────────────────+
    │  ICON   HEADLINE                                     │
    │         Body text (wraps)                            │
    │                                        [Action btn]  │
    +─────────────────────────────────────────────────────+

    Parameters
    ----------
    icon          : unicode glyph
    headline      : bold title text
    body          : body paragraph (wraps)
    accent_color  : left border + icon colour
    action_label  : optional button label
    action_cmd    : callable for action button
    """
    action_clicked = Signal()

    def __init__(self, icon: str = "", headline: str = "",
                 body: str = "", accent_color: str = Colors.ACCENT_BLUE,
                 action_label: str = "", action_cmd: Callable = None,
                 parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};"
            f"border-left: 4px solid {accent_color};")

        root = QHBoxLayout(self)
        root.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.setSpacing(Spacing.MD)

        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont(Fonts.FAMILY, 22))
            icon_lbl.setStyleSheet(
                f"color: {accent_color}; border: none;")
            icon_lbl.setFixedWidth(36)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
            root.addWidget(icon_lbl)

        col = QVBoxLayout()
        col.setSpacing(Spacing.XS)
        if headline:
            hl = QLabel(headline)
            hl.setFont(QFont(Fonts.FAMILY, 12, QFont.Weight.Bold))
            hl.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; border: none;")
            col.addWidget(hl)
        if body:
            bl = QLabel(body)
            bl.setFont(Fonts.label())
            bl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            bl.setWordWrap(True)
            col.addWidget(bl)
        root.addLayout(col, 1)

        if action_label:
            btn = _styled_btn(action_label, Colors.BG_BORDER,
                              Colors.TEXT_MUTED, 30)
            def _cmd():
                self.action_clicked.emit()
                if action_cmd:
                    action_cmd()
            btn.clicked.connect(_cmd)
            root.addWidget(btn,
                           alignment=Qt.AlignmentFlag.AlignVCenter)


# ══════════════════════════════════════════════════════════════════════════════
#  ChartCard
# ══════════════════════════════════════════════════════════════════════════════

class BarChartRow(QWidget):
    """
    A single horizontal bar row:  [label]  [████░░░░]  [value]
    Used inside ChartCard to compose bar charts without external libs.
    """
    def __init__(self, label: str, value: int, maximum: int,
                 color: str = Colors.ACCENT_BLUE,
                 value_text: str = "", parent=None):
        super().__init__(parent)
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 2, 0, 2)
        hl.setSpacing(Spacing.SM)

        lbl = QLabel(label)
        lbl.setFont(Fonts.label_sm())
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        lbl.setFixedWidth(80)
        hl.addWidget(lbl)

        track = QFrame()
        track.setFixedHeight(8)
        track.setStyleSheet(
            f"background-color: {Colors.BG_BORDER};"
            f"border-radius: 4px; border: none;")
        track_layout = QHBoxLayout(track)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(0)

        pct = min(value / max(maximum, 1), 1.0)
        fill = QFrame()
        fill.setFixedHeight(8)
        fill.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed)
        fill.setStyleSheet(
            f"background-color: {color};"
            f"border-radius: 4px; border: none;")
        track_layout.addWidget(fill)
        track_layout.addStretch()
        hl.addWidget(track, 1)

        # Resize fill proportionally when track resizes
        self._fill  = fill
        self._pct   = pct
        self._track = track

        val_lbl = QLabel(value_text or str(value))
        val_lbl.setFont(Fonts.label_sm_bold())
        val_lbl.setStyleSheet(f"color: {color}; border: none;")
        val_lbl.setFixedWidth(40)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(val_lbl)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = int(self._track.width() * self._pct)
        self._fill.setFixedWidth(max(w, 0))


class ChartCard(QFrame):
    """
    Card with title bar + slot for chart content.

    Usage:
        card = ChartCard("Risk Distribution")
        card.add_row("Critical", 4, 10, Colors.CRITICAL)
        card.add_row("High",     3, 10, Colors.HIGH)
    """
    def __init__(self, title: str, subtitle: str = "",
                 parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-radius: {Radius.LG}px;"
            f"border: 1px solid {Colors.BG_BORDER};")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._layout.setSpacing(Spacing.SM)

        t = QLabel(title)
        t.setFont(Fonts.heading_3())
        t.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        self._layout.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setFont(Fonts.label_sm())
            s.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            self._layout.addWidget(s)

    def add_row(self, label: str, value: int,
                maximum: int, color: str = Colors.ACCENT_BLUE,
                value_text: str = "") -> None:
        self._layout.addWidget(
            BarChartRow(label, value, maximum,
                        color, value_text))

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_stretch(self) -> None:
        self._layout.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
#  SectionHeader (enhanced)
# ══════════════════════════════════════════════════════════════════════════════

class SectionHeader(QWidget):
    """
    Section title with optional subtitle and horizontal rule.
    Replaces the basic version in cards.py for page-level use.
    """
    def __init__(self, title: str, subtitle: str = "",
                 show_rule: bool = False, parent=None):
        super().__init__(parent)
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, Spacing.SM, 0, Spacing.XS)
        vl.setSpacing(2)

        t = QLabel(title)
        t.setFont(Fonts.heading_2())
        t.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        vl.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setFont(Fonts.label())
            s.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            vl.addWidget(s)

        if show_rule:
            rule = QFrame()
            rule.setFrameShape(QFrame.Shape.HLine)
            rule.setStyleSheet(
                f"background-color: {Colors.ACCENT_RED};"
                f"max-height: 2px; border: none;")
            vl.addWidget(rule)


# ══════════════════════════════════════════════════════════════════════════════
#  StatusBadge (enhanced — all status types)
# ══════════════════════════════════════════════════════════════════════════════

class StatusBadge(QLabel):
    """
    Coloured pill badge for any status or severity value.

    Handles:
      • risk severity  (Critical / High / Medium / Low)
      • risk status    (Open / In Progress / Mitigated / Closed)
      • treatment status (Draft / Approved / In Progress / Completed / Verified)
      • confidence     (High / Medium / Low)
      • posture        (Critical / High / Medium / Low)
    """
    _MAP = {
        # Severity
        "CRITICAL":    (Colors.CRITICAL,    "white"),
        "HIGH":        (Colors.HIGH,        "white"),
        "MEDIUM":      (Colors.MEDIUM,      "black"),
        "LOW":         (Colors.LOW,         "white"),
        # Risk status
        "Open":        (Colors.MEDIUM,      "black"),
        "In Progress": (Colors.ACCENT_BLUE, "white"),
        "Mitigated":   (Colors.SUCCESS_LT,  "white"),
        "Accepted":    (Colors.TEXT_MUTED,  "white"),
        "Closed":      (Colors.TEXT_DIM,    "white"),
        # Treatment status
        "Draft":       (Colors.TEXT_MUTED,  "white"),
        "Approved":    (Colors.ACCENT_BLUE, "white"),
        "Completed":   (Colors.ACCENT_CYAN, "white"),
        "Verified":    (Colors.SUCCESS_LT,  "white"),
        "Ineffective": (Colors.CRITICAL,    "white"),
        # Confidence
        "High":        (Colors.SUCCESS_LT,  "white"),
        "Medium":      (Colors.MEDIUM,      "black"),
        "Unknown":     (Colors.TEXT_DIM,    "white"),
        # Posture
        "Critical":    (Colors.CRITICAL,    "white"),
    }

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        bg, fg = self._MAP.get(status, (Colors.BG_BORDER,
                                         Colors.TEXT_MUTED))
        self.setText(f" {status} ")
        self.setFont(Fonts.badge())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: {Radius.SM}px;
                padding: 2px 6px;
                border: none;
            }}
        """)
        self.setFixedHeight(20)


# ══════════════════════════════════════════════════════════════════════════════
#  FrameworkBadge
# ══════════════════════════════════════════════════════════════════════════════

class FrameworkBadge(QLabel):
    """
    Framework-specific coloured pill.
    Colour is keyed to the framework name from the design system.
    """
    _SHORT = {
        "NIST CSF 2.0":       "NIST CSF 2.0",
        "ISO/IEC 27001:2022": "ISO 27001",
        "MITRE ATT&CK":       "MITRE ATT&CK",
        "CIS Controls v8":    "CIS v8",
        "CIA Triad":          "CIA Triad",
    }

    def __init__(self, framework: str, short: bool = True,
                 parent=None):
        super().__init__(parent)
        color = Colors.fw_color(framework)
        label = (self._SHORT.get(framework, framework[:12])
                 if short else framework)
        self.setText(f" {label} ")
        self.setFont(Fonts.badge())
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: {Radius.SM}px;
                padding: 2px 6px;
                border: none;
            }}
        """)
        self.setFixedHeight(20)


# ══════════════════════════════════════════════════════════════════════════════
#  Timeline
# ══════════════════════════════════════════════════════════════════════════════

class TimelineItem:
    """Data container for a single timeline entry."""
    __slots__ = ("icon", "color", "label", "detail",
                 "timestamp", "tag", "tag_color")

    def __init__(self, icon: str, color: str, label: str,
                 detail: str, timestamp: str,
                 tag: str = "", tag_color: str = ""):
        self.icon       = icon
        self.color      = color
        self.label      = label
        self.detail     = detail
        self.timestamp  = timestamp
        self.tag        = tag
        self.tag_color  = tag_color


class Timeline(QScrollArea):
    """
    Scrollable activity timeline widget.

    Usage:
        tl = Timeline()
        tl.set_items([
            TimelineItem("◉", Colors.MEDIUM, "Risk Created",
                         "Unpatched server added", "2026-07-01 09:12",
                         "Risk", Colors.MEDIUM),
        ])
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._inner.setStyleSheet("border: none;")
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(1)
        self.setWidget(self._inner)

    def set_items(self, items: list[TimelineItem]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not items:
            empty = QLabel("No activity recorded.")
            empty.setFont(Fonts.label())
            empty.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(empty)
            self._layout.addStretch()
            return

        for i, item in enumerate(items):
            bg = Colors.BG_CARD2 if i % 2 == 0 else "transparent"
            row = QFrame()
            row.setStyleSheet(
                f"background-color: {bg}; border: none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(Spacing.MD, 6, Spacing.MD, 6)
            rl.setSpacing(Spacing.SM)

            dot = QLabel(item.icon)
            dot.setFont(QFont(Fonts.FAMILY, 10))
            dot.setStyleSheet(
                f"color: {item.color}; border: none;")
            dot.setFixedWidth(16)
            rl.addWidget(dot)

            ts = QLabel(item.timestamp[:16])
            ts.setFont(Fonts.label_sm())
            ts.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; border: none;")
            ts.setFixedWidth(112)
            rl.addWidget(ts)

            act = QLabel(item.label)
            act.setFont(Fonts.label_sm_bold())
            act.setStyleSheet(
                f"color: {item.color}; border: none;")
            act.setFixedWidth(138)
            rl.addWidget(act)

            detail = QLabel(item.detail[:70])
            detail.setFont(Fonts.label_sm())
            detail.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            rl.addWidget(detail, 1)

            if item.tag and item.tag_color:
                tf = QFrame()
                tf.setFixedHeight(20)
                tf.setStyleSheet(
                    f"background-color: {item.tag_color};"
                    f"border-radius: {Radius.SM}px; border: none;")
                tl = QHBoxLayout(tf)
                tl.setContentsMargins(6, 0, 6, 0)
                t_lbl = QLabel(item.tag)
                t_lbl.setFont(Fonts.badge())
                t_lbl.setStyleSheet("color: white; border: none;")
                tl.addWidget(t_lbl)
                rl.addWidget(tf)

            self._layout.addWidget(row)

        self._layout.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
#  FilterBar
# ══════════════════════════════════════════════════════════════════════════════

class FilterBarItem:
    """Descriptor for one dropdown filter in a FilterBar."""
    __slots__ = ("label", "items", "width")

    def __init__(self, label: str, items: list[str],
                 width: int = 140):
        self.label = label
        self.items = items
        self.width = width


class FilterBar(QFrame):
    """
    Standardised horizontal filter bar.

    Renders:
        [Label: DropDown]  [Label: DropDown] … [⌕ Search…] [Clear]

    Usage:
        bar = FilterBar([
            FilterBarItem("Status:", ["All","Open","Closed"]),
            FilterBarItem("NIST:",   ["All"] + NIST_FUNCTIONS),
        ])
        bar.changed.connect(lambda: reload_data())
        status = bar.value("Status:")
    """
    changed = Signal()

    def __init__(self, filters: list[FilterBarItem],
                 show_search: bool = True,
                 parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {Colors.BG_CARD};"
            f"border-bottom: 1px solid {Colors.BG_BORDER};")

        hl = QHBoxLayout(self)
        hl.setContentsMargins(
            Spacing.XL, Spacing.SM, Spacing.XL, Spacing.SM)
        hl.setSpacing(Spacing.SM)

        self._combos: dict[str, QComboBox] = {}

        for f in filters:
            lbl = QLabel(f.label)
            lbl.setFont(Fonts.label_sm())
            lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED};")
            hl.addWidget(lbl)

            cb = QComboBox()
            cb.addItems(f.items)
            cb.setFixedWidth(f.width)
            cb.setFixedHeight(28)
            cb.setStyleSheet(f"""
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
                    selection-background-color:
                        {Colors.ACCENT_BLUE};
                }}
            """)
            cb.currentIndexChanged.connect(
                lambda _: self.changed.emit())
            self._combos[f.label] = cb
            hl.addWidget(cb)
            hl.addSpacing(Spacing.SM)

        if show_search:
            self._search = QLineEdit()
            self._search.setPlaceholderText("⌕  Search…")
            self._search.setFixedHeight(28)
            self._search.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {Colors.BG_CARD2};
                    color: {Colors.TEXT_PRIMARY};
                    border: 1px solid {Colors.BG_BORDER};
                    border-radius: {Radius.SM}px;
                    padding: 0 10px; font-size: 10pt;
                }}
            """)
            self._search.textChanged.connect(
                lambda _: self.changed.emit())
            hl.addWidget(self._search, 1)
        else:
            self._search = None

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(28)
        clear_btn.setFixedWidth(55)
        clear_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        clear_btn.clicked.connect(self.clear)
        hl.addWidget(clear_btn)

    def value(self, label: str) -> str:
        cb = self._combos.get(label)
        return cb.currentText() if cb else "All"

    def search_text(self) -> str:
        return self._search.text().strip() if self._search else ""

    def clear(self) -> None:
        for cb in self._combos.values():
            cb.blockSignals(True)
            cb.setCurrentIndex(0)
            cb.blockSignals(False)
        if self._search:
            self._search.blockSignals(True)
            self._search.clear()
            self._search.blockSignals(False)
        self.changed.emit()


# ══════════════════════════════════════════════════════════════════════════════
#  SearchPanel
# ══════════════════════════════════════════════════════════════════════════════

class SearchPanel(QWidget):
    """
    Standalone search input + clear button.
    Emits search_changed(str) on every keystroke.
    """
    search_changed = Signal(str)

    def __init__(self, placeholder: str = "⌕  Search…",
                 parent=None):
        super().__init__(parent)
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(Spacing.SM)

        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setFixedHeight(32)
        self._input.setStyleSheet(f"""
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
        self._input.textChanged.connect(self.search_changed.emit)
        hl.addWidget(self._input, 1)

        clear = QPushButton("✕")
        clear.setFixedSize(32, 32)
        clear.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor))
        clear.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_BORDER};
                color: {Colors.TEXT_MUTED}; border: none;
                border-radius: {Radius.SM}px; font-size: 11pt;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_CARD2};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        clear.clicked.connect(self.clear)
        hl.addWidget(clear)

    def text(self) -> str:
        return self._input.text().strip()

    def clear(self) -> None:
        self._input.clear()


# ══════════════════════════════════════════════════════════════════════════════
#  EmptyState
# ══════════════════════════════════════════════════════════════════════════════

class EmptyStateAction:
    """Data class for an action card inside EmptyState."""
    __slots__ = ("icon", "label", "description", "command")

    def __init__(self, icon: str, label: str,
                 description: str, command: Callable = None):
        self.icon        = icon
        self.label       = label
        self.description = description
        self.command     = command


class EmptyState(QWidget):
    """
    Centred empty state display matching Image 7.

    +─────────────────────────────────────────────────────+
    │                                                      │
    │                   [Large icon]                       │
    │               Title text (bold)                      │
    │             Subtitle text (muted)                    │
    │                                                      │
    │   [Action card 1]  [Action card 2]  [Action card 3]  │
    │                                                      │
    │              Optional info line                      │
    │                                                      │
    +─────────────────────────────────────────────────────+
    """
    def __init__(self, icon: str = "◉",
                 title: str = "No items found",
                 subtitle: str = "Try adjusting your filters.",
                 actions: list[EmptyStateAction] = None,
                 info_line: str = "",
                 parent=None):
        super().__init__(parent)
        self.setStyleSheet("border: none;")

        vl = QVBoxLayout(self)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setSpacing(Spacing.MD)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont(Fonts.FAMILY, 44))
        icon_lbl.setStyleSheet(
            f"color: {Colors.BG_BORDER}; border: none;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(icon_lbl)

        t = QLabel(title)
        t.setFont(QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        t.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setFont(Fonts.label())
            s.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.addWidget(s)

        if actions:
            cards_row = QWidget()
            cards_row.setStyleSheet("border: none;")
            cr = QHBoxLayout(cards_row)
            cr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cr.setSpacing(Spacing.MD)

            for action in actions:
                cf = QFrame()
                cf.setFixedSize(200, 110)
                cf.setStyleSheet(
                    f"background-color: {Colors.BG_CARD2};"
                    f"border-radius: {Radius.LG}px; border: none;")
                cf.setCursor(
                    QCursor(Qt.CursorShape.PointingHandCursor))
                cl = QVBoxLayout(cf)
                cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cl.setSpacing(4)

                il = QLabel(action.icon)
                il.setFont(QFont(Fonts.FAMILY, 20))
                il.setStyleSheet(
                    f"color: {Colors.ACCENT_BLUE}; border: none;")
                il.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cl.addWidget(il)

                nl = QLabel(action.label)
                nl.setFont(
                    QFont(Fonts.FAMILY, 11, QFont.Weight.Bold))
                nl.setStyleSheet(
                    f"color: {Colors.TEXT_PRIMARY}; border: none;")
                nl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cl.addWidget(nl)

                dl = QLabel(action.description)
                dl.setFont(Fonts.label_sm())
                dl.setStyleSheet(
                    f"color: {Colors.TEXT_MUTED}; border: none;")
                dl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                dl.setWordWrap(True)
                cl.addWidget(dl)

                if action.command:
                    cmd = action.command
                    cf.mousePressEvent = (
                        lambda e, c=cmd: c())
                cr.addWidget(cf)
            vl.addWidget(cards_row)

        if info_line:
            info = QLabel(info_line)
            info.setFont(Fonts.label_sm())
            info.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; border: none;")
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.addWidget(info)


# ══════════════════════════════════════════════════════════════════════════════
#  LoadingOverlay
# ══════════════════════════════════════════════════════════════════════════════

class LoadingOverlay(QWidget):
    """
    Semi-transparent overlay shown while data loads.

    Usage:
        overlay = LoadingOverlay(parent_widget)
        overlay.show()
        # … after data loads:
        overlay.hide()
    """
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            False)
        self.setStyleSheet(
            "background-color: rgba(10, 14, 23, 0.72);")
        vl = QVBoxLayout(self)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._spinner = QLabel("◌")
        self._spinner.setFont(QFont(Fonts.FAMILY, 36))
        self._spinner.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE}; border: none; "
            f"background: transparent;")
        self._spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(self._spinner)

        self._text = QLabel("Loading…")
        self._text.setFont(Fonts.label())
        self._text.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none; "
            f"background: transparent;")
        self._text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(self._text)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._spin)
        self._chars = ["◌","◍","◎","●","○"]
        self._idx   = 0
        self.hide()

    def set_text(self, text: str) -> None:
        self._text.setText(text)

    def show(self) -> None:
        self.resize(self.parent().size())
        self.raise_()
        self._timer.start(200)
        super().show()

    def hide(self) -> None:
        self._timer.stop()
        super().hide()

    def _spin(self) -> None:
        self._spinner.setText(
            self._chars[self._idx % len(self._chars)])
        self._idx += 1

    def resizeEvent(self, event) -> None:
        if self.parent():
            self.resize(self.parent().size())
        super().resizeEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
#  Toast
# ══════════════════════════════════════════════════════════════════════════════

class Toast(QFrame):
    """
    Slide-in notification banner anchored to the bottom-right of a parent.
    Auto-dismisses after `duration` ms.

    Usage:
        Toast.show_in(parent_widget, "✅  Risk saved", Colors.SUCCESS_LT)
    """
    def __init__(self, message: str, color: str,
                 duration: int, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setMinimumWidth(280)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG_CARD};
                border-radius: {Radius.MD}px;
                border: 1px solid {color};
                border-left: 4px solid {color};
            }}
        """)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(Spacing.MD, 0, Spacing.MD, 0)
        hl.setSpacing(Spacing.SM)

        msg = QLabel(message)
        msg.setFont(Fonts.label_sm_bold())
        msg.setStyleSheet(f"color: {color}; border: none;")
        hl.addWidget(msg, 1)

        close = QPushButton("✕")
        close.setFixedSize(20, 20)
        close.setStyleSheet(f"""
            QPushButton {{
                color: {Colors.TEXT_DIM}; border: none;
                background: transparent; font-size: 10pt;
            }}
            QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}
        """)
        close.clicked.connect(self._dismiss)
        hl.addWidget(close)

        self._reposition()
        self.show()
        self.raise_()

        # Auto-dismiss
        QTimer.singleShot(duration, self._dismiss)

    def _reposition(self) -> None:
        if self.parent():
            pw = self.parent().width()
            ph = self.parent().height()
            self.adjustSize()
            x = pw - self.width() - Spacing.LG
            y = ph - self.height() - Spacing.LG
            self.move(x, y)

    def _dismiss(self) -> None:
        self.deleteLater()

    @staticmethod
    def show_in(parent: QWidget, message: str,
                color: str = Colors.SUCCESS_LT,
                duration: int = 3000) -> "Toast":
        t = Toast(message, color, duration, parent)
        t._reposition()
        return t


# ══════════════════════════════════════════════════════════════════════════════
#  ConfirmationDialog
# ══════════════════════════════════════════════════════════════════════════════

class ConfirmationDialog(QDialog):
    """
    Modal confirm/cancel dialog.

    Usage:
        dlg = ConfirmationDialog(
            "Delete Risk",
            "This will permanently remove the risk and all treatments.",
            confirm_label="Delete",
            confirm_color=Colors.CRITICAL,
            parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            do_delete()
    """
    def __init__(self, title: str, body: str,
                 confirm_label: str = "Confirm",
                 cancel_label:  str = "Cancel",
                 confirm_color: str = Colors.ACCENT_BLUE,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(420)
        self.setStyleSheet(
            f"background-color: {Colors.BG_CARD}; border: none;")

        vl = QVBoxLayout(self)
        vl.setContentsMargins(
            Spacing.XL, Spacing.XL, Spacing.XL, Spacing.LG)
        vl.setSpacing(Spacing.MD)

        t = QLabel(title)
        t.setFont(QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        t.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none;")
        vl.addWidget(t)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(
            f"background-color: {Colors.BG_BORDER};"
            f"max-height: 1px; border: none;")
        vl.addWidget(rule)

        b = QLabel(body)
        b.setFont(Fonts.label())
        b.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        b.setWordWrap(True)
        vl.addWidget(b)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel = _styled_btn(cancel_label, Colors.BG_BORDER,
                             Colors.TEXT_MUTED, 34)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        confirm = _styled_btn(confirm_label, confirm_color,
                              "white", 34)
        confirm.setFont(
            QFont(Fonts.FAMILY, 10, QFont.Weight.Bold))
        confirm.clicked.connect(self.accept)
        btn_row.addWidget(confirm)
        vl.addLayout(btn_row)
