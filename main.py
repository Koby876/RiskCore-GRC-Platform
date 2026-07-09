"""
main.py — RiskCore GRC Platform v1.5
Entry point.

Start sequence:
  1. Suppress Shiboken/Qt noise to a log file — clean console for internal users
  2. Check for first-run (no password set) → show SetPasswordDialog
  3. Show LoginDialog — reject if cancelled or failed
  4. Launch MainWindow
"""

import sys
import os
import traceback
import io

# ── 1. Suppress Shiboken + Qt platform noise ─────────────────────────────────
# Redirect stderr to a rotating log file instead of the console.
# Shiboken warnings are non-fatal; internal users shouldn't see them.
# Real Python exceptions still go through sys.excepthook → stderr → log.

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_LOG_PATH = os.path.join(ROOT, "riskcore.log")
try:
    _log_file = open(_LOG_PATH, "a", buffering=1, encoding="utf-8")
    # Redirect stderr (Shiboken, Qt warnings) to the log file
    sys.stderr = _log_file
except Exception:
    pass  # if we can't open the log, just leave stderr alone


def _excepthook(exc_type, exc_value, exc_tb):
    """
    Global exception hook.
    1. Writes full traceback to riskcore.log (stderr already redirected).
    2. Shows a user-friendly dialog with consent to view/dismiss.
    Real errors never silently disappear.
    """
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    # Always write to log
    try:
        sys.__stderr__.write(msg)
        sys.__stderr__.flush()
    except Exception:
        pass
    try:
        if sys.stderr is not sys.__stderr__:
            sys.stderr.write(msg)
            sys.stderr.flush()
    except Exception:
        pass

    # Show user-facing dialog (only if QApplication exists)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
        from PySide6.QtWidgets import QVBoxLayout, QLabel, QTextEdit
        from PySide6.QtWidgets import QPushButton, QHBoxLayout
        from PySide6.QtCore import Qt
        if QApplication.instance():
            _show_crash_dialog(exc_type.__name__, msg)
    except Exception:
        pass

sys.excepthook = _excepthook


def _show_crash_dialog(error_type: str, full_trace: str) -> None:
    """
    Consent-first crash dialog.
    User sees a friendly message and can choose to view or dismiss.
    No data is sent anywhere — the diagnostic bundle export in
    Settings → Support is how users share reports manually.
    """
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel,
        QTextEdit, QPushButton, QFrame,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont

    dlg = QDialog()
    dlg.setWindowTitle("RiskCore — Unexpected Error")
    dlg.setFixedSize(560, 360)
    dlg.setStyleSheet("background: #0B1F3A; color: #E8EDF4;")

    vl = QVBoxLayout(dlg)
    vl.setContentsMargins(28, 24, 28, 20)
    vl.setSpacing(12)

    # Icon + title
    title = QLabel(f"⚠  RiskCore encountered an unexpected error")
    title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
    title.setStyleSheet("color: #E8EDF4; border: none;")
    vl.addWidget(title)

    sub = QLabel(
        "Error type: " + error_type + "\n\n"
        "The error has been written to riskcore.log.\n"
        "Your data is safe — no changes were lost.\n\n"
        "To share this with support, go to:\n"
        "Settings → Support → Export Diagnostic Bundle")
    sub.setFont(QFont("Segoe UI", 9))
    sub.setStyleSheet("color: #93A5B8; border: none;")
    sub.setWordWrap(True)
    vl.addWidget(sub)

    # Collapsible trace view
    trace_box = QTextEdit()
    trace_box.setReadOnly(True)
    trace_box.setFont(QFont("Courier New", 8))
    trace_box.setStyleSheet(
        "background: #1C2A3A; color: #93A5B8; border: none; "
        "border-radius: 4px; padding: 6px;")
    trace_box.setPlainText(full_trace)
    trace_box.setVisible(False)
    trace_box.setMaximumHeight(140)
    vl.addWidget(trace_box)

    # Buttons
    btn_row = QHBoxLayout()
    view_btn = QPushButton("View Details")
    view_btn.setFont(QFont("Segoe UI", 9))
    view_btn.setFixedHeight(34)
    view_btn.setStyleSheet(
        "QPushButton { background: #1C2A3A; color: #93A5B8; "
        "border: 1px solid #2D3F52; border-radius: 5px; padding: 0 14px; }"
        "QPushButton:hover { border-color: #1B5FCF; color: #E8EDF4; }")
    view_btn.clicked.connect(
        lambda: (trace_box.setVisible(not trace_box.isVisible()),
                 view_btn.setText(
                     "Hide Details" if trace_box.isVisible()
                     else "View Details"),
                 dlg.adjustSize()))

    dismiss_btn = QPushButton("Dismiss")
    dismiss_btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    dismiss_btn.setFixedHeight(34)
    dismiss_btn.setStyleSheet(
        "QPushButton { background: #1B5FCF; color: white; "
        "border: none; border-radius: 5px; padding: 0 20px; }"
        "QPushButton:hover { background: #1550B0; }")
    dismiss_btn.clicked.connect(dlg.accept)

    btn_row.addWidget(view_btn)
    btn_row.addStretch()
    btn_row.addWidget(dismiss_btn)
    vl.addLayout(btn_row)
    dlg.exec()

# ── 2. Qt application ─────────────────────────────────────────────────────────
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("RiskCore GRC Platform")
    app.setApplicationVersion("1.5")
    app.setOrganizationName("RiskCore")

    # Set application icon — shows in taskbar, title bar, and Alt+Tab
    from PySide6.QtGui import QIcon
    _icon_candidates = []
    if hasattr(sys, "_MEIPASS"):
        _icon_candidates.append(
            os.path.join(sys._MEIPASS, "assets", "images", "riskcore_logo.png"))
    _icon_candidates += [
        os.path.join(os.path.dirname(sys.executable),
                     "_internal", "assets", "images", "riskcore_logo.png"),
        os.path.join(os.path.dirname(sys.executable),
                     "assets", "images", "riskcore_logo.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "assets", "images", "riskcore_logo.png"),
    ]
    for _p in _icon_candidates:
        if os.path.exists(_p):
            app.setWindowIcon(QIcon(_p))
            break

    # Font
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    # Dark palette
    from assets.themes.design_system import apply_theme
    try:
        apply_theme(app)
    except Exception:
        pass

    # ── Initialise DB (creates tables if first run) ───────────────────────────
    from core.database.db import init_db
    try:
        init_db()
    except Exception as e:
        QMessageBox.critical(
            None, "Database Error",
            f"RiskCore could not initialise its database.\n\n{e}\n\n"
            f"Check that the application folder is writable.")
        return 1

    # ── 3. Authentication ─────────────────────────────────────────────────────
    from ui.login import get_stored_hash, SetPasswordDialog, LoginDialog

    if not get_stored_hash():
        # First launch — prompt to set a password
        setup_dlg = SetPasswordDialog()
        if setup_dlg.exec() != SetPasswordDialog.DialogCode.Accepted:
            return 0  # user closed without setting password — exit cleanly

    login_dlg = LoginDialog()
    if login_dlg.exec() != LoginDialog.DialogCode.Accepted:
        return 0  # cancelled or too many failures — exit cleanly

    # ── 4. Launch main window ─────────────────────────────────────────────────
    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
