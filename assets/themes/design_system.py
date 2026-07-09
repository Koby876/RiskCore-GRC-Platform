"""
assets/themes/design_system.py
───────────────────────────────
RiskCore Enterprise Design System

Single source of truth for all visual tokens.
Every UI component imports from here.
No page or widget invents its own colours, fonts, or spacing.

Colours are taken directly from the existing riskcore_phase2.py palette
so the visual identity is preserved in the Qt migration.
"""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


# ── Colour Tokens ─────────────────────────────────────────────────────────────

class Colors:
    # Backgrounds
    BG_DEEP     = "#0A0E17"   # main window background
    BG_SIDEBAR  = "#0F1318"   # sidebar
    BG_CARD     = "#141A24"   # card background
    BG_CARD2    = "#1A2232"   # alternate / hover card
    BG_BORDER   = "#1E2D3D"   # borders, dividers, header rows

    # Accent
    ACCENT_RED  = "#E53935"   # primary red (RiskCore brand)
    ACCENT_BLUE = "#1565C0"   # secondary blue
    ACCENT_TEAL = "#00897B"   # treatment / verify
    ACCENT_CYAN = "#0097A7"   # completed actions

    # Text
    TEXT_PRIMARY  = "#ECF0F5"  # main text
    TEXT_MUTED    = "#6B7A8D"  # secondary / label text
    TEXT_DIM      = "#3E4A5A"  # disabled / hint text
    TEXT_WHITE    = "#FFFFFF"

    # Semantic — risk severity
    CRITICAL = "#C62828"
    HIGH     = "#E65100"
    MEDIUM   = "#F9A825"
    LOW      = "#43A047"

    # Background tints for severity (for KPI card highlights)
    BG_CRITICAL = "#1E0808"
    BG_HIGH     = "#1E0E00"
    BG_MEDIUM   = "#1E1A00"
    BG_LOW      = "#0A1A0A"

    # Semantic — status
    SUCCESS  = "#2E7D32"
    SUCCESS_LT = "#43A047"
    WARNING  = "#F9A825"
    ERROR    = "#C62828"
    INFO     = "#1565C0"

    # Purple family
    PURPLE    = "#6A1B9A"
    PURPLE_LT = "#8E24AA"

    # NIST CSF 2.0 function colours (official guidance-inspired)
    NIST_GOVERN  = "#1B5E20"
    NIST_IDENTIFY= "#1565C0"
    NIST_PROTECT = "#2E7D32"
    NIST_DETECT  = "#E65100"
    NIST_RESPOND = "#880E4F"
    NIST_RECOVER = "#4A148C"

    # Framework pill colours
    FW_NIST   = "#1565C0"
    FW_ISO    = "#2E7D32"
    FW_MITRE  = "#B71C1C"
    FW_CIS    = "#E65100"
    FW_CIA    = "#6A1B9A"

    # Treatment strategy colours
    TREAT_MITIGATE = "#1565C0"
    TREAT_ACCEPT   = "#E65100"
    TREAT_TRANSFER = "#00695C"
    TREAT_AVOID    = "#6A1B9A"

    @staticmethod
    def nist_color(function: str) -> str:
        return {
            "Govern":   Colors.NIST_GOVERN,
            "Identify": Colors.NIST_IDENTIFY,
            "Protect":  Colors.NIST_PROTECT,
            "Detect":   Colors.NIST_DETECT,
            "Respond":  Colors.NIST_RESPOND,
            "Recover":  Colors.NIST_RECOVER,
        }.get(function, Colors.ACCENT_BLUE)

    @staticmethod
    def severity_color(score: int) -> str:
        if score >= 15: return Colors.CRITICAL
        if score >= 10: return Colors.HIGH
        if score >= 5:  return Colors.MEDIUM
        return Colors.LOW

    @staticmethod
    def severity_bg(score: int) -> str:
        if score >= 15: return Colors.BG_CRITICAL
        if score >= 10: return Colors.BG_HIGH
        if score >= 5:  return Colors.BG_MEDIUM
        return Colors.BG_LOW

    @staticmethod
    def severity_label(score: int) -> str:
        if score >= 15: return "CRITICAL"
        if score >= 10: return "HIGH"
        if score >= 5:  return "MEDIUM"
        return "LOW"

    @staticmethod
    def treat_color(strategy: str) -> str:
        return {
            "Mitigate": Colors.TREAT_MITIGATE,
            "Accept":   Colors.TREAT_ACCEPT,
            "Transfer": Colors.TREAT_TRANSFER,
            "Avoid":    Colors.TREAT_AVOID,
        }.get(strategy, Colors.ACCENT_BLUE)

    @staticmethod
    def treat_status_color(status: str) -> str:
        return {
            "Draft":       Colors.TEXT_MUTED,
            "Approved":    Colors.ACCENT_BLUE,
            "In Progress": Colors.MEDIUM,
            "Completed":   Colors.ACCENT_CYAN,
            "Verified":    Colors.SUCCESS_LT,
            "Ineffective": Colors.CRITICAL,
        }.get(status, Colors.TEXT_MUTED)

    @staticmethod
    def fw_color(framework: str) -> str:
        return {
            "NIST CSF 2.0":       Colors.FW_NIST,
            "ISO/IEC 27001:2022": Colors.FW_ISO,
            "MITRE ATT&CK":       Colors.FW_MITRE,
            "CIS Controls v8":    Colors.FW_CIS,
            "CIA Triad":          Colors.FW_CIA,
        }.get(framework, Colors.ACCENT_BLUE)


# ── Typography ────────────────────────────────────────────────────────────────

class Fonts:
    FAMILY = "Segoe UI"   # Windows native — falls back gracefully on macOS/Linux

    @staticmethod
    def heading_1() -> QFont:
        f = QFont(Fonts.FAMILY, 20)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def heading_2() -> QFont:
        f = QFont(Fonts.FAMILY, 14)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def heading_3() -> QFont:
        f = QFont(Fonts.FAMILY, 12)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    @staticmethod
    def label() -> QFont:
        return QFont(Fonts.FAMILY, 10)

    @staticmethod
    def label_bold() -> QFont:
        f = QFont(Fonts.FAMILY, 10)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def label_sm() -> QFont:
        return QFont(Fonts.FAMILY, 9)

    @staticmethod
    def label_sm_bold() -> QFont:
        f = QFont(Fonts.FAMILY, 9)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def kpi_value() -> QFont:
        f = QFont(Fonts.FAMILY, 28)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def kpi_value_sm() -> QFont:
        f = QFont(Fonts.FAMILY, 22)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def badge() -> QFont:
        f = QFont(Fonts.FAMILY, 8)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def mono() -> QFont:
        return QFont("Consolas", 10)


# ── Spacing & Radius ─────────────────────────────────────────────────────────

class Spacing:
    XS   = 4
    SM   = 8
    MD   = 12
    LG   = 16
    XL   = 24
    XXL  = 32

class Radius:
    SM  = 4
    MD  = 8
    LG  = 10
    XL  = 12
    PILL= 20


# ── Global QSS Stylesheet ────────────────────────────────────────────────────

GLOBAL_QSS = f"""
/* ── Root application ──────────────────────────────────────────────── */
QApplication, QMainWindow, QWidget {{
    background-color: {Colors.BG_DEEP};
    color: {Colors.TEXT_PRIMARY};
    font-family: "Segoe UI";
    font-size: 10pt;
    border: none;
    outline: none;
}}

/* ── Scroll areas ──────────────────────────────────────────────────── */
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: {Colors.BG_CARD};
    width: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {Colors.BG_BORDER};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {Colors.TEXT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {Colors.BG_CARD};
    height: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {Colors.BG_BORDER};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {Colors.TEXT_DIM};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Frames / Cards ────────────────────────────────────────────────── */
QFrame[class="card"] {{
    background-color: {Colors.BG_CARD};
    border-radius: {Radius.LG}px;
    border: 1px solid {Colors.BG_BORDER};
}}
QFrame[class="card2"] {{
    background-color: {Colors.BG_CARD2};
    border-radius: {Radius.MD}px;
    border: 1px solid {Colors.BG_BORDER};
}}
QFrame[class="sidebar"] {{
    background-color: {Colors.BG_SIDEBAR};
    border-right: 1px solid {Colors.BG_BORDER};
}}

/* ── Buttons ───────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {Colors.BG_BORDER};
    color: {Colors.TEXT_MUTED};
    border: none;
    border-radius: {Radius.SM}px;
    padding: 6px 14px;
    font-size: 10pt;
}}
QPushButton:hover {{
    background-color: {Colors.BG_CARD2};
    color: {Colors.TEXT_PRIMARY};
}}
QPushButton:pressed {{
    background-color: {Colors.BG_CARD};
}}
QPushButton[class="primary"] {{
    background-color: {Colors.ACCENT_BLUE};
    color: white;
    font-weight: bold;
}}
QPushButton[class="primary"]:hover {{
    background-color: #1976D2;
}}
QPushButton[class="danger"] {{
    background-color: {Colors.CRITICAL};
    color: white;
}}
QPushButton[class="danger"]:hover {{
    background-color: #E53935;
}}
QPushButton[class="success"] {{
    background-color: {Colors.SUCCESS};
    color: white;
}}
QPushButton[class="ghost"] {{
    background-color: transparent;
    color: {Colors.TEXT_MUTED};
    border: 1px solid {Colors.BG_BORDER};
}}
QPushButton[class="ghost"]:hover {{
    background-color: {Colors.BG_CARD};
    color: {Colors.TEXT_PRIMARY};
}}
QPushButton[class="nav"] {{
    background-color: transparent;
    color: {Colors.TEXT_MUTED};
    border: none;
    border-radius: {Radius.SM}px;
    padding: 8px 12px;
    text-align: left;
}}
QPushButton[class="nav"]:hover {{
    background-color: {Colors.BG_BORDER};
    color: {Colors.TEXT_PRIMARY};
}}
QPushButton[class="nav-active"] {{
    background-color: {Colors.ACCENT_RED};
    color: white;
    border: none;
    border-radius: {Radius.SM}px;
    padding: 8px 12px;
    text-align: left;
    font-weight: bold;
}}

/* ── Labels ────────────────────────────────────────────────────────── */
QLabel {{
    background-color: transparent;
    color: {Colors.TEXT_PRIMARY};
}}
QLabel[class="muted"] {{
    color: {Colors.TEXT_MUTED};
}}
QLabel[class="dim"] {{
    color: {Colors.TEXT_DIM};
}}
QLabel[class="section-title"] {{
    color: {Colors.TEXT_PRIMARY};
    font-size: 11pt;
    font-weight: bold;
}}
QLabel[class="card-title"] {{
    color: {Colors.TEXT_MUTED};
    font-size: 9pt;
}}
QLabel[class="kpi-value"] {{
    color: {Colors.TEXT_PRIMARY};
    font-size: 28pt;
    font-weight: bold;
}}
QLabel[class="badge-critical"] {{
    background-color: {Colors.CRITICAL};
    color: white;
    border-radius: {Radius.SM}px;
    padding: 2px 6px;
    font-size: 8pt;
    font-weight: bold;
}}
QLabel[class="badge-high"] {{
    background-color: {Colors.HIGH};
    color: white;
    border-radius: {Radius.SM}px;
    padding: 2px 6px;
    font-size: 8pt;
    font-weight: bold;
}}
QLabel[class="badge-medium"] {{
    background-color: {Colors.MEDIUM};
    color: black;
    border-radius: {Radius.SM}px;
    padding: 2px 6px;
    font-size: 8pt;
    font-weight: bold;
}}
QLabel[class="badge-low"] {{
    background-color: {Colors.LOW};
    color: white;
    border-radius: {Radius.SM}px;
    padding: 2px 6px;
    font-size: 8pt;
    font-weight: bold;
}}

/* ── Line inputs ───────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {Colors.BG_CARD2};
    color: {Colors.TEXT_PRIMARY};
    border: 1px solid {Colors.BG_BORDER};
    border-radius: {Radius.SM}px;
    padding: 6px 10px;
    font-size: 10pt;
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {Colors.ACCENT_BLUE};
}}
QLineEdit::placeholder {{
    color: {Colors.TEXT_DIM};
}}

/* ── ComboBox (dropdown) ───────────────────────────────────────────── */
QComboBox {{
    background-color: {Colors.BG_CARD2};
    color: {Colors.TEXT_PRIMARY};
    border: 1px solid {Colors.BG_BORDER};
    border-radius: {Radius.SM}px;
    padding: 5px 10px;
    font-size: 10pt;
    min-width: 120px;
}}
QComboBox:hover {{
    border: 1px solid {Colors.ACCENT_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {Colors.TEXT_MUTED};
}}
QComboBox QAbstractItemView {{
    background-color: {Colors.BG_CARD};
    color: {Colors.TEXT_PRIMARY};
    border: 1px solid {Colors.BG_BORDER};
    selection-background-color: {Colors.ACCENT_BLUE};
    outline: none;
}}

/* ── Tables ────────────────────────────────────────────────────────── */
QTableView, QTreeView, QListView {{
    background-color: {Colors.BG_CARD};
    alternate-background-color: {Colors.BG_CARD2};
    color: {Colors.TEXT_PRIMARY};
    gridline-color: {Colors.BG_BORDER};
    border: none;
    border-radius: {Radius.LG}px;
    selection-background-color: {Colors.ACCENT_BLUE};
    selection-color: white;
    outline: none;
}}
QHeaderView::section {{
    background-color: {Colors.BG_BORDER};
    color: {Colors.TEXT_MUTED};
    padding: 6px 8px;
    border: none;
    font-size: 9pt;
    font-weight: bold;
}}
QHeaderView::section:hover {{
    background-color: {Colors.BG_CARD2};
}}
QTableView::item {{
    padding: 4px 8px;
    border: none;
}}
QTableView::item:selected {{
    background-color: {Colors.ACCENT_BLUE};
    color: white;
}}
QTableView::item:hover {{
    background-color: {Colors.BG_CARD2};
}}

/* ── Progress bars ─────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {Colors.BG_BORDER};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    border: none;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background-color: {Colors.ACCENT_BLUE};
}}

/* ── Sliders ───────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {Colors.BG_BORDER};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {Colors.ACCENT_BLUE};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {Colors.ACCENT_BLUE};
    border-radius: 3px;
}}

/* ── Splitter ──────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {Colors.BG_BORDER};
    width: 1px;
}}

/* ── Tab bar ───────────────────────────────────────────────────────── */
QTabBar::tab {{
    background-color: transparent;
    color: {Colors.TEXT_MUTED};
    padding: 8px 20px;
    border: none;
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
QTabWidget::pane {{
    border: none;
    background-color: {Colors.BG_CARD};
}}

/* ── Tooltip ───────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {Colors.BG_CARD2};
    color: {Colors.TEXT_PRIMARY};
    border: 1px solid {Colors.BG_BORDER};
    padding: 4px 8px;
    border-radius: {Radius.SM}px;
    font-size: 9pt;
}}

/* ── Status bar ────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: #060A10;
    color: {Colors.TEXT_DIM};
    font-size: 9pt;
    border-top: 1px solid {Colors.BG_BORDER};
}}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the RiskCore Enterprise theme to the QApplication."""
    app.setStyleSheet(GLOBAL_QSS)
    # Set the application palette for any widgets that
    # don't pick up QSS (e.g. native dialogs)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,
                     QColor(Colors.BG_DEEP))
    palette.setColor(QPalette.ColorRole.WindowText,
                     QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base,
                     QColor(Colors.BG_CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase,
                     QColor(Colors.BG_CARD2))
    palette.setColor(QPalette.ColorRole.Text,
                     QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button,
                     QColor(Colors.BG_BORDER))
    palette.setColor(QPalette.ColorRole.ButtonText,
                     QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight,
                     QColor(Colors.ACCENT_BLUE))
    palette.setColor(QPalette.ColorRole.HighlightedText,
                     QColor(Colors.TEXT_WHITE))
    palette.setColor(QPalette.ColorRole.Link,
                     QColor(Colors.ACCENT_BLUE))
    app.setPalette(palette)


def asset_path(relative: str) -> str:
    """
    Resolve an asset path that works both in development and
    when frozen by PyInstaller (--onedir or --onefile).

    Usage:
        from assets.themes.design_system import asset_path
        logo = asset_path("assets/images/riskcore_logo.png")
    """
    import os, sys
    base = (getattr(sys, "_MEIPASS", None)
            or os.path.normpath(
                os.path.join(os.path.dirname(
                    os.path.abspath(__file__)), "..", "..")))
    return os.path.join(base, relative)
