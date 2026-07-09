"""
ui/login.py — RiskCore GRC Platform v1.5
─────────────────────────────────────────
Login dialog shown on every app start.

Security design:
  - Password hashed with bcrypt (cost factor 12) and stored in settings DB.
  - First-run: user sets a new password (no default — forces conscious setup).
  - Brute-force mitigation: 5 failed attempts → 30-second lockout, then reset.
  - "Forgot password": shows DB file path so admin can reset via settings.
  - No network calls — fully offline.

Architecture:
  LoginDialog.exec() returns QDialog.Accepted only on correct password.
  main.py refuses to open MainWindow if it returns anything else.
"""

from __future__ import annotations

import time
import bcrypt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QWidget,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from core.database.db import get_db, DB_PATH


_MAX_ATTEMPTS  = 5
_LOCKOUT_SECS  = 30
_BCRYPT_ROUNDS = 12

_PASS_TABLE = "app_config"   # single-row key-value table for app-level config


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(_BCRYPT_ROUNDS)).decode()


def _check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def get_stored_hash() -> str | None:
    """
    Return the stored bcrypt hash from app_config, or None if not set.
    Creates the table if it doesn't exist. Uses a single connection for
    both operations to avoid WAL visibility issues between connections.
    """
    try:
        import sqlite3 as _sq
        conn = _sq.connect(str(DB_PATH), timeout=10)
        conn.row_factory = _sq.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_config "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.commit()
        row = conn.execute(
            "SELECT value FROM app_config WHERE key='password_hash'"
        ).fetchone()
        result = row["value"] if row else None
        conn.close()
        return result
    except Exception as e:
        print(f"[login] get_stored_hash error: {e}")
        return None


def set_stored_hash(pw: str) -> None:
    """
    Hash pw and persist to app_config in a single connection.
    Explicit commit + checkpoint ensures the write survives app restart.
    """
    try:
        import sqlite3 as _sq
        hashed = _hash_password(pw)
        conn = _sq.connect(str(DB_PATH), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_config "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "INSERT INTO app_config(key, value) VALUES('password_hash', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (hashed,))
        conn.commit()
        # Force WAL checkpoint so hash is in the main DB file, not just WAL
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        print("[login] Password hash saved and checkpointed.")
    except Exception as e:
        print(f"[login] set_stored_hash error: {e}")
        raise


class _FieldStyle:
    INPUT = f"""
        QLineEdit {{
            background: #1C2A3A;
            color: #E8EDF4;
            border: 1px solid #2D3F52;
            border-radius: 6px;
            padding: 10px 14px;
            font-size: 11pt;
        }}
        QLineEdit:focus {{
            border-color: #1B5FCF;
        }}
    """
    BTN_PRIMARY = f"""
        QPushButton {{
            background: #1B5FCF;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 11px 0;
            font-size: 11pt;
            font-weight: bold;
        }}
        QPushButton:hover  {{ background: #1550B0; }}
        QPushButton:pressed {{ background: #0F3D8C; }}
        QPushButton:disabled {{
            background: #2D3F52;
            color: #697A8D;
        }}
    """
    BTN_GHOST = f"""
        QPushButton {{
            background: transparent;
            color: #697A8D;
            border: none;
            font-size: 9pt;
        }}
        QPushButton:hover {{ color: #93C5FD; }}
    """


class SetPasswordDialog(QDialog):
    """First-run: create the application password."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RiskCore — Set Access Password")
        self.setFixedSize(400, 380)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(f"background: {Colors.BG_DEEP}; color: {Colors.TEXT_PRIMARY};")

        vl = QVBoxLayout(self)
        vl.setContentsMargins(32, 28, 32, 28)
        vl.setSpacing(0)

        # Brand
        logo = QLabel("⬡")
        logo.setFont(QFont(Fonts.FAMILY, 32))
        logo.setStyleSheet(f"color: {Colors.ACCENT_RED};")
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(logo)
        vl.addSpacing(8)

        title = QLabel("RiskCore GRC Platform")
        title.setFont(QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)
        vl.addSpacing(4)

        sub = QLabel("First launch — set your access password")
        sub.setFont(QFont(Fonts.FAMILY, 9))
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        vl.addWidget(sub)
        vl.addSpacing(24)

        for attr, placeholder in [
            ("_pw1", "New password (min. 8 characters)"),
            ("_pw2", "Confirm password"),
        ]:
            f = QLineEdit()
            f.setPlaceholderText(placeholder)
            f.setEchoMode(QLineEdit.EchoMode.Password)
            f.setFixedHeight(44)
            f.setStyleSheet(_FieldStyle.INPUT)
            setattr(self, attr, f)
            vl.addWidget(f)
            vl.addSpacing(10)

        self._error = QLabel("")
        self._error.setFont(QFont(Fonts.FAMILY, 8))
        self._error.setStyleSheet(f"color: {Colors.CRITICAL};")
        self._error.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(self._error)
        vl.addSpacing(10)

        btn = QPushButton("Set Password & Continue")
        btn.setFixedHeight(46)
        btn.setStyleSheet(_FieldStyle.BTN_PRIMARY)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._submit)
        vl.addWidget(btn)

        self._pw1.returnPressed.connect(self._submit)
        self._pw2.returnPressed.connect(self._submit)

    def _submit(self) -> None:
        p1 = self._pw1.text()
        p2 = self._pw2.text()
        if len(p1) < 8:
            self._error.setText("Password must be at least 8 characters.")
            return
        if p1 != p2:
            self._error.setText("Passwords do not match.")
            self._pw2.clear()
            self._pw2.setFocus()
            return
        set_stored_hash(p1)
        self.accept()


class LoginDialog(QDialog):
    """
    Shown on every launch. Returns Accepted only on correct password.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._attempts    = 0
        self._locked_until: float = 0.0
        self._lock_timer  = QTimer(self)
        self._lock_timer.timeout.connect(self._tick_lockout)

        self.setWindowTitle("RiskCore — Sign In")
        self.setFixedSize(400, 420)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(
            f"background: {Colors.BG_DEEP}; color: {Colors.TEXT_PRIMARY};")

        vl = QVBoxLayout(self)
        vl.setContentsMargins(32, 28, 32, 28)
        vl.setSpacing(0)

        # Brand
        logo = QLabel("⬡")
        logo.setFont(QFont(Fonts.FAMILY, 32))
        logo.setStyleSheet(f"color: {Colors.ACCENT_RED};")
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        vl.addWidget(logo)
        vl.addSpacing(8)

        title = QLabel("RiskCore GRC Platform")
        title.setFont(QFont(Fonts.FAMILY, 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        vl.addWidget(title)
        vl.addSpacing(4)

        ver = QLabel("v1.5 — Secure Access")
        ver.setFont(QFont(Fonts.FAMILY, 9))
        ver.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ver.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        vl.addWidget(ver)
        vl.addSpacing(28)

        # Divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {Colors.BG_BORDER};")
        vl.addWidget(div)
        vl.addSpacing(24)

        pw_lbl = QLabel("Password")
        pw_lbl.setFont(QFont(Fonts.FAMILY, 9, QFont.Weight.Bold))
        pw_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        vl.addWidget(pw_lbl)
        vl.addSpacing(6)

        self._pw_input = QLineEdit()
        self._pw_input.setPlaceholderText("Enter password…")
        self._pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_input.setFixedHeight(46)
        self._pw_input.setStyleSheet(_FieldStyle.INPUT)
        self._pw_input.returnPressed.connect(self._submit)
        vl.addWidget(self._pw_input)
        vl.addSpacing(12)

        self._error_lbl = QLabel("")
        self._error_lbl.setFont(QFont(Fonts.FAMILY, 8))
        self._error_lbl.setStyleSheet(f"color: {Colors.CRITICAL};")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._error_lbl.setWordWrap(True)
        vl.addWidget(self._error_lbl)
        vl.addSpacing(10)

        self._sign_in_btn = QPushButton("Sign In")
        self._sign_in_btn.setFixedHeight(46)
        self._sign_in_btn.setStyleSheet(_FieldStyle.BTN_PRIMARY)
        self._sign_in_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sign_in_btn.clicked.connect(self._submit)
        vl.addWidget(self._sign_in_btn)
        vl.addSpacing(16)

        forgot_btn = QPushButton("Forgot password?")
        forgot_btn.setStyleSheet(_FieldStyle.BTN_GHOST)
        forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        forgot_btn.clicked.connect(self._show_forgot)
        vl.addWidget(forgot_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._pw_input.setFocus()

    def _submit(self) -> None:
        if self._locked_until and time.time() < self._locked_until:
            return

        pw = self._pw_input.text()
        if not pw:
            self._error_lbl.setText("Please enter your password.")
            return

        stored = get_stored_hash()
        if stored and _check_password(pw, stored):
            self._lock_timer.stop()
            self.accept()
            return

        # Wrong password
        self._pw_input.clear()
        self._attempts += 1
        remaining = _MAX_ATTEMPTS - self._attempts

        if self._attempts >= _MAX_ATTEMPTS:
            self._attempts      = 0
            self._locked_until  = time.time() + _LOCKOUT_SECS
            self._sign_in_btn.setEnabled(False)
            self._error_lbl.setText(
                f"Too many failed attempts. Locked for "
                f"{_LOCKOUT_SECS} seconds.")
            self._lock_timer.start(1000)
        else:
            self._error_lbl.setText(
                f"Incorrect password. {remaining} attempt(s) remaining.")
            self._pw_input.setFocus()

    def _tick_lockout(self) -> None:
        remaining = int(self._locked_until - time.time())
        if remaining <= 0:
            self._lock_timer.stop()
            self._locked_until = 0.0
            self._sign_in_btn.setEnabled(True)
            self._error_lbl.setText("")
            self._pw_input.setFocus()
        else:
            self._error_lbl.setText(
                f"Locked. Try again in {remaining}s.")

    def _show_forgot(self) -> None:
        self._error_lbl.setText(
            f"To reset: delete the file below and relaunch.\n"
            f"You will be prompted to set a new password.\n"
            f"DB: {DB_PATH}")
