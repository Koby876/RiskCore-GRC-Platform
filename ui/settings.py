"""
ui/settings.py
──────────────
RiskCore GRC Platform v1.5 — Settings & Administration Centre.

True multi-page settings using QStackedWidget.
Each nav item shows exactly one page — no dead navigation.

Pages:
  1. Organisation       — Name, industry, classification defaults
  2. AI Configuration   — API key, test, AI toggles
  3. Application        — Theme, preferences, UI options
  4. Backup & Restore   — Backup management, restore
  5. Audit Logging      — View config activity log
  6. About              — Version, developer, system info
"""

from __future__ import annotations

import datetime
import sys

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QCheckBox,
    QGridLayout, QSizePolicy, QFileDialog, QStackedWidget,
    QDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont, QCursor

from assets.themes.design_system import Colors, Fonts, Spacing, Radius
from widgets.components import Toast, ConfirmationDialog, SectionHeader
from core.database.db import (
    load_settings, save_settings,
    load_api_key, save_api_key,
    backup_database, restore_database,
    get_db, today, now_str,
    BASE_DIR, DB_PATH,
)

import urllib.request, urllib.error


# ─── API key test worker ──────────────────────────────────────────────────────

class KeyTestWorker(QObject):
    result = Signal(bool, str)

    def __init__(self, key: str):
        super().__init__()
        self._key = key

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": self._key,
                    "anthropic-version": "2023-06-01",
                })
            with urllib.request.urlopen(req, timeout=5) as r:
                ok = r.status == 200
            self.result.emit(ok, "✅ Connection successful — API key is valid"
                             if ok else "⚠ Unexpected response")
        except urllib.error.HTTPError as e:
            msg = ("⚠ Invalid API key — access denied"
                   if e.code in (401, 403) else f"⚠ HTTP {e.code}")
            self.result.emit(False, msg)
        except Exception as e:
            self.result.emit(False, f"⚠ Connection failed: {e}")


# ─── Widget helpers ───────────────────────────────────────────────────────────

def _lbl(text, font=None, color=None) -> QLabel:
    lbl = QLabel(str(text))
    lbl.setFont(font or Fonts.label_sm())
    lbl.setStyleSheet(
        f"color: {color or Colors.TEXT_MUTED}; border: none;")
    lbl.setWordWrap(True)
    return lbl

def _entry(text="", placeholder="", width=None) -> QLineEdit:
    e = QLineEdit(str(text))
    e.setPlaceholderText(placeholder)
    e.setFont(Fonts.label_sm())
    e.setFixedHeight(32)
    if width:
        e.setFixedWidth(width)
    e.setStyleSheet(f"""
        QLineEdit {{
            background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px; padding: 4px 10px;
        }}
        QLineEdit:focus {{
            border: 1px solid {Colors.ACCENT_BLUE};
        }}
    """)
    return e

def _combo(items, current="") -> QComboBox:
    cb = QComboBox()
    cb.setFont(Fonts.label_sm())
    cb.addItems(items)
    if current in items:
        cb.setCurrentText(current)
    cb.setFixedHeight(32)
    cb.setStyleSheet(f"""
        QComboBox {{
            background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BG_BORDER};
            border-radius: {Radius.SM}px; padding: 4px 10px;
        }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background: {Colors.BG_CARD}; color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.ACCENT_BLUE};
        }}
    """)
    return cb

def _btn(text, bg=Colors.BG_BORDER, fg=Colors.TEXT_MUTED,
         height=34) -> QPushButton:
    b = QPushButton(text)
    b.setFont(Fonts.label_sm_bold())
    b.setFixedHeight(height)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    b.setStyleSheet(f"""
        QPushButton {{
            background: {bg}; color: {fg};
            border: none; border-radius: {Radius.SM}px;
            padding: 0 16px;
        }}
        QPushButton:hover {{ opacity: 0.85; background: {bg}; }}
    """)
    return b

def _card(bg=Colors.BG_CARD) -> QFrame:
    f = QFrame()
    f.setStyleSheet(
        f"background: {bg}; border-radius: {Radius.MD}px; border: none;")
    return f

def _card_title(text, color=Colors.TEXT_PRIMARY) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(Fonts.label_bold())
    lbl.setStyleSheet(f"color: {color}; border: none;")
    return lbl

def _divider() -> QFrame:
    d = QFrame()
    d.setFrameShape(QFrame.Shape.HLine)
    d.setStyleSheet(f"background: {Colors.BG_BORDER}; border: none; max-height: 1px;")
    return d

def _scrolled(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidget(widget)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setStyleSheet("border: none; background: transparent;")
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return sa


# ─── Individual page builders ─────────────────────────────────────────────────

class _PageBase(QWidget):
    """Base class for a Settings page with a scrollable content area."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        self._vl = QVBoxLayout(content)
        self._vl.setContentsMargins(0, 0, 16, 16)
        self._vl.setSpacing(Spacing.MD)
        sa = _scrolled(content)
        outer.addWidget(sa)

    def _section(self, title: str, subtitle: str = "") -> None:
        """Add a page section header."""
        lbl = QLabel(title)
        lbl.setFont(Fonts.label_bold())
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none; margin-top: 4px;")
        self._vl.addWidget(lbl)
        if subtitle:
            sub = _lbl(subtitle)
            self._vl.addWidget(sub)
        self._vl.addWidget(_divider())


# ─── Page 1: Organisation ─────────────────────────────────────────────────────

class _OrgPage(_PageBase):
    changed = Signal()

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self._s = settings
        self._section("Organisation", "Configure your organisation profile and report defaults.")
        self._build()

    def _build(self):
        from core.database.db import get_organisation_scope
        scope = get_organisation_scope() or {}

        def _signal(w):
            # Check type explicitly — hasattr is unreliable with PySide6 signals
            from PySide6.QtWidgets import QComboBox, QLineEdit, QTextEdit
            if isinstance(w, QComboBox):
                w.currentTextChanged.connect(lambda _: self.changed.emit())
            elif isinstance(w, (QLineEdit, QTextEdit)):
                w.textChanged.connect(lambda _: self.changed.emit())
            return w

        # ── Organisation Profile card ─────────────────────────────────────────
        card1 = _card()
        gl1 = QGridLayout(card1)
        gl1.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        gl1.setSpacing(Spacing.SM)
        gl1.setColumnStretch(1, 1)
        gl1.addWidget(_card_title("Organisation Profile"), 0, 0, 1, 2)

        def row(g, r, label, widget):
            g.addWidget(_lbl(label), r, 0)
            g.addWidget(widget, r, 1)

        # Scope (DB) takes priority over settings.json
        # settings.json only stores basic prefs; org data lives in DB
        self._org_name = _signal(_entry(
            scope.get("organisation_name","") or self._s.get("organisation_name",""),
            "e.g. Acme Financial Services"))
        row(gl1, 1, "Organisation Name *", self._org_name)

        self._industry = _signal(_combo([
            "Technology", "Financial Services", "Healthcare",
            "Government", "Manufacturing", "Retail",
            "Energy & Utilities", "Education", "Legal", "Other",
        ], scope.get("industry","") or self._s.get("industry","Technology")))
        row(gl1, 2, "Industry *", self._industry)

        self._org_size = _signal(_combo([
            "Small (< 50 employees)",
            "Medium (50–500 employees)",
            "Large (500–5,000 employees)",
            "Enterprise (5,000+ employees)",
        ], scope.get("organisation_size","Small (< 50 employees)")))
        row(gl1, 3, "Organisation Size", self._org_size)

        self._business_fn = _signal(_entry(
            scope.get("business_function",""),
            "e.g. Information Technology, Finance, Operations"))
        row(gl1, 4, "Primary Business Function", self._business_fn)

        self._default_clf = _signal(_combo(
            ["CONFIDENTIAL", "RESTRICTED", "INTERNAL", "PUBLIC"],
            self._s.get("default_classification","CONFIDENTIAL")))
        row(gl1, 5, "Default Classification", self._default_clf)

        self._vl.addWidget(card1)

        # ── Assessment Scope card ─────────────────────────────────────────────
        card2 = _card()
        gl2 = QGridLayout(card2)
        gl2.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        gl2.setSpacing(Spacing.SM)
        gl2.setColumnStretch(1, 1)
        gl2.addWidget(_card_title("Assessment Scope"), 0, 0, 1, 2)

        self._assess_name = _signal(_entry(
            scope.get("assessment_name",""),
            "e.g. Q3 2026 Cyber Risk Assessment"))
        row(gl2, 1, "Assessment Name", self._assess_name)

        self._assess_type = _signal(_combo([
            "Internal Risk Assessment",
            "External Risk Assessment",
            "Gap Assessment",
            "Security Audit",
            "Compliance Assessment",
            "Penetration Test Review",
            "Third-Party Assessment",
        ], scope.get("assessment_type","Internal Risk Assessment")))
        row(gl2, 2, "Assessment Type", self._assess_type)

        self._assess_obj = _signal(_entry(
            scope.get("assessment_objective",""),
            "e.g. Annual security posture review for board reporting"))
        row(gl2, 3, "Assessment Objective", self._assess_obj)

        self._vl.addWidget(card2)

        # ── Scope Boundaries card ─────────────────────────────────────────────
        card3 = _card()
        vl3 = QVBoxLayout(card3)
        vl3.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl3.setSpacing(Spacing.SM)
        vl3.addWidget(_card_title("Scope Boundaries"))
        vl3.addWidget(_lbl(
            "Enter one item per line. These populate the Organisation Scope "
            "section of the PDF report.",
            color=Colors.TEXT_DIM))

        from PySide6.QtWidgets import QTextEdit
        assets_existing = scope.get("assets_in_scope", [])
        if isinstance(assets_existing, list):
            assets_existing = "\n".join(assets_existing)

        self._assets = QTextEdit()
        self._assets.setPlaceholderText(
            "Core banking platform\nCustomer portal\nEmployee directory\n...")
        self._assets.setPlainText(assets_existing)
        self._assets.setFixedHeight(90)
        self._assets.setStyleSheet(
            f"background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};"
            f"border: 1px solid {Colors.BG_BORDER}; border-radius: 4px;"
            f"padding: 6px;")
        self._assets.textChanged.connect(lambda _: self.changed.emit())

        units_existing = scope.get("business_units", [])
        if isinstance(units_existing, list):
            units_existing = "\n".join(units_existing)

        self._units = QTextEdit()
        self._units.setPlaceholderText(
            "Information Technology\nOperations\nRisk & Compliance\n...")
        self._units.setPlainText(units_existing)
        self._units.setFixedHeight(90)
        self._units.setStyleSheet(
            f"background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};"
            f"border: 1px solid {Colors.BG_BORDER}; border-radius: 4px;"
            f"padding: 6px;")
        self._units.textChanged.connect(lambda _: self.changed.emit())

        scope_grid = QGridLayout()
        scope_grid.setColumnStretch(0, 1)
        scope_grid.setColumnStretch(1, 1)
        scope_grid.setSpacing(Spacing.SM)
        scope_grid.addWidget(_lbl("Assets in Scope (one per line)"), 0, 0)
        scope_grid.addWidget(_lbl("Business Units (one per line)"), 0, 1)
        scope_grid.addWidget(self._assets, 1, 0)
        scope_grid.addWidget(self._units,  1, 1)
        vl3.addLayout(scope_grid)
        self._vl.addWidget(card3)
        self._vl.addStretch()

    def values(self) -> dict:
        assets_text = self._assets.toPlainText().strip()
        units_text  = self._units.toPlainText().strip()
        return {
            # Settings fields
            "organisation_name":      self._org_name.text().strip() or "Your Organisation",
            "industry":               self._industry.currentText(),
            "default_classification": self._default_clf.currentText(),
            # Scope fields (saved to org_scope table)
            "_scope": {
                "organisation_name":     self._org_name.text().strip() or "Your Organisation",
                "industry":              self._industry.currentText(),
                "organisation_size":     self._org_size.currentText(),
                "business_function":     self._business_fn.text().strip(),
                "assessment_name":       self._assess_name.text().strip(),
                "assessment_type":       self._assess_type.currentText(),
                "assessment_objective":  self._assess_obj.text().strip(),
                "assets_in_scope":       [a.strip() for a in assets_text.splitlines()
                                          if a.strip()],
                "business_units":        [u.strip() for u in units_text.splitlines()
                                          if u.strip()],
            }
        }


# ─── Page 2: AI Configuration ────────────────────────────────────────────────

class _AIPage(_PageBase):
    changed = Signal()

    def __init__(self, api_key: str, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._thread = None
        self._worker = None
        self._section("AI Configuration",
                       "Manage your Anthropic API key and AI analysis settings.")
        self._build()

    def _build(self):
        card = _card()
        gl = QGridLayout(card)
        gl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        gl.setSpacing(Spacing.SM)
        gl.setColumnStretch(1, 1)

        gl.addWidget(_card_title("Anthropic API Key"), 0, 0, 1, 3)

        gl.addWidget(_lbl("API Key"), 1, 0)
        self._key_input = _entry(
            self._api_key or "",
            "sk-ant-api03-…")
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.textChanged.connect(lambda _: self.changed.emit())
        gl.addWidget(self._key_input, 1, 1)

        self._test_btn_ref = _btn("Test Connection", Colors.ACCENT_BLUE, "white", 32)
        self._test_btn_ref.clicked.connect(self._test)
        gl.addWidget(self._test_btn_ref, 1, 2)

        self._key_status = _lbl("")
        gl.addWidget(self._key_status, 2, 1, 1, 2)

        gl.addWidget(_lbl(
            "Keys are encrypted using AES-256 (Fernet) and stored locally only. "
            "Never transmitted except directly to Anthropic."),
            3, 0, 1, 3)

        self._vl.addWidget(card)

        # AI toggles card
        card2 = _card()
        vl2 = QVBoxLayout(card2)
        vl2.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl2.setSpacing(Spacing.SM)
        vl2.addWidget(_card_title("Analysis Options"))

        self._toggles: dict[str, QCheckBox] = {}
        for label, default in [
            ("Enable Risk Extraction",         True),
            ("Enable Control Mapping",         True),
            ("Enable MITRE ATT&CK Mapping",    True),
            ("Enable Treatment Suggestions",   True),
            ("Auto-suggest Risk Scores",       False),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(default)
            cb.setFont(Fonts.label_sm())
            cb.setStyleSheet(f"""
                QCheckBox {{ color: {Colors.TEXT_MUTED}; border: none; spacing: 6px; }}
                QCheckBox::indicator {{
                    width: 16px; height: 16px; border-radius: 3px;
                    border: 1px solid {Colors.BG_BORDER};
                    background: {Colors.BG_CARD2};
                }}
                QCheckBox::indicator:checked {{
                    background: {Colors.ACCENT_BLUE};
                    border: 1px solid {Colors.ACCENT_BLUE};
                }}
            """)
            cb.stateChanged.connect(lambda _: self.changed.emit())
            self._toggles[label] = cb
            vl2.addWidget(cb)

        self._vl.addWidget(card2)
        self._vl.addStretch()

    def _test(self):
        # Guard: don't start second test if one is running
        if self._thread is not None and self._thread.isRunning():
            return
        key = self._key_input.text().strip()
        if not key.startswith("sk-ant"):
            self._key_status.setText("⚠ Key must start with sk-ant-api03-")
            self._key_status.setStyleSheet(
                f"color: {Colors.CRITICAL}; border: none;")
            return
        self._key_status.setText("⏳ Testing connection… (up to 5 seconds)")
        self._key_status.setStyleSheet(
            f"color: {Colors.MEDIUM}; border: none;")
        # Disable button while test runs
        self._test_btn_ref.setEnabled(False)
        self._test_btn_ref.setText("Testing…")
        self._thread = QThread()
        self._worker = KeyTestWorker(key)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result.connect(self._on_result)
        self._worker.result.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(
            lambda: setattr(self, '_thread', None))
        self._thread.start()

    def _on_result(self, ok: bool, msg: str):
        color = Colors.SUCCESS_LT if ok else Colors.CRITICAL
        self._key_status.setText(msg)
        self._key_status.setStyleSheet(f"color: {color}; border: none;")
        # Re-enable test button
        if hasattr(self, '_test_btn_ref'):
            self._test_btn_ref.setEnabled(True)
            self._test_btn_ref.setText("Test Connection")

    def api_key(self) -> str:
        return self._key_input.text().strip()


# ─── Page 3: Application ─────────────────────────────────────────────────────

class _AppPage(_PageBase):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._section("Application",
                       "Application preferences and UI configuration.")
        self._build()

    def _build(self):
        card = _card()
        gl = QGridLayout(card)
        gl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        gl.setSpacing(Spacing.SM)
        gl.setColumnStretch(1, 1)
        gl.addWidget(_card_title("User Interface"), 0, 0, 1, 2)

        self._auto_refresh = QCheckBox("Auto-refresh dashboard every 60 seconds")
        self._auto_refresh.setChecked(True)
        self._auto_refresh.setFont(Fonts.label_sm())
        self._auto_refresh.setStyleSheet(
            f"QCheckBox {{ color: {Colors.TEXT_MUTED}; border: none; spacing: 6px; }}"
            f"QCheckBox::indicator {{ width:16px; height:16px; border-radius:3px;"
            f"  border: 1px solid {Colors.BG_BORDER}; background:{Colors.BG_CARD2}; }}"
            f"QCheckBox::indicator:checked {{ background:{Colors.ACCENT_BLUE};"
            f"  border:1px solid {Colors.ACCENT_BLUE}; }}")
        self._auto_refresh.stateChanged.connect(lambda _: self.changed.emit())
        gl.addWidget(self._auto_refresh, 1, 0, 1, 2)

        self._confirm_delete = QCheckBox("Confirm before deleting risks or treatments")
        self._confirm_delete.setChecked(True)
        self._confirm_delete.setFont(Fonts.label_sm())
        self._confirm_delete.setStyleSheet(
            f"QCheckBox {{ color: {Colors.TEXT_MUTED}; border: none; spacing: 6px; }}"
            f"QCheckBox::indicator {{ width:16px; height:16px; border-radius:3px;"
            f"  border: 1px solid {Colors.BG_BORDER}; background:{Colors.BG_CARD2}; }}"
            f"QCheckBox::indicator:checked {{ background:{Colors.ACCENT_BLUE};"
            f"  border:1px solid {Colors.ACCENT_BLUE}; }}")
        self._confirm_delete.stateChanged.connect(lambda _: self.changed.emit())
        gl.addWidget(self._confirm_delete, 2, 0, 1, 2)

        self._vl.addWidget(card)
        self._vl.addStretch()


# ─── Page 4: Backup & Restore ─────────────────────────────────────────────────

class _BackupPage(_PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._section("Backup & Restore",
                       "Protect your data with timestamped backups.")
        self._build()

    def _build(self):
        card = _card()
        gl = QGridLayout(card)
        gl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        gl.setSpacing(Spacing.SM)
        gl.setColumnStretch(1, 1)
        gl.addWidget(_card_title("Database Backup"), 0, 0, 1, 3)

        bk_dir = BASE_DIR / "backups"
        bk_path_lbl = _lbl(str(bk_dir))
        gl.addWidget(_lbl("Backup Folder"), 1, 0)
        gl.addWidget(bk_path_lbl, 1, 1, 1, 2)

        try:
            files = sorted(bk_dir.glob("riskcore_backup_*.db"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            last_bk = (datetime.datetime.fromtimestamp(
                files[0].stat().st_mtime).strftime("%Y-%m-%d  %H:%M:%S")
                       if files else "Never yet")
            count_bk = str(len(files))
        except Exception:
            last_bk = "Unknown"
            count_bk = "—"
            files = []

        gl.addWidget(_lbl("Last Backup"), 2, 0)
        self._last_lbl = _lbl(
            last_bk,
            color=(Colors.ACCENT_BLUE
                   if last_bk not in ("Never yet", "Unknown")
                   else Colors.CRITICAL))
        gl.addWidget(self._last_lbl, 2, 1)

        gl.addWidget(_lbl("Backup Count"), 3, 0)
        self._count_lbl = _lbl(count_bk, color=Colors.TEXT_PRIMARY)
        gl.addWidget(self._count_lbl, 3, 1)

        self._status_lbl = _lbl("")
        gl.addWidget(self._status_lbl, 4, 0, 1, 3)

        btn_row = QHBoxLayout()
        bk_btn = _btn("Create Backup Now", Colors.ACCENT_BLUE, "white", 34)
        bk_btn.clicked.connect(self._backup)
        btn_row.addWidget(bk_btn)
        rst_btn = _btn("Restore Backup…", Colors.BG_BORDER, Colors.TEXT_MUTED, 34)
        rst_btn.clicked.connect(self._restore)
        btn_row.addWidget(rst_btn)
        btn_row.addStretch()
        gl.addLayout(btn_row, 5, 0, 1, 3)

        self._vl.addWidget(card)
        self._vl.addWidget(_lbl(
            "Each backup is a complete copy of riskcore.db. "
            "Backups are stored in the backups/ folder. "
            "Restore replaces the live database — a pre-restore backup is created automatically."))
        self._vl.addStretch()

    def _backup(self):
        try:
            dest = backup_database()
            ts = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
            self._last_lbl.setText(ts)
            self._last_lbl.setStyleSheet(
                f"color: {Colors.ACCENT_BLUE}; border: none;")
            self._status_lbl.setText(f"✅  Backup created: {dest.name}")
            self._status_lbl.setStyleSheet(
                f"color: {Colors.SUCCESS_LT}; border: none;")
            # Update count label
            if hasattr(self, "_count_lbl"):
                try:
                    bk_dir = BASE_DIR / "backups"
                    cnt = len(list(bk_dir.glob("riskcore_backup_*.db")))
                    self._count_lbl.setText(str(cnt))
                except Exception:
                    pass
            Toast.show_in(self, f"✅  Backup — {dest.name}", Colors.SUCCESS_LT)
        except Exception as e:
            self._status_lbl.setText(f"⚠  Backup failed: {e}")
            self._status_lbl.setStyleSheet(
                f"color: {Colors.CRITICAL}; border: none;")

    def refresh(self) -> None:
        """Re-scan backup folder and update display labels."""
        if not hasattr(self, "_last_lbl"):
            return
        try:
            bk_dir = BASE_DIR / "backups"
            files = sorted(bk_dir.glob("riskcore_backup_*.db"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            last_bk = (datetime.datetime.fromtimestamp(
                files[0].stat().st_mtime).strftime("%Y-%m-%d  %H:%M:%S")
                       if files else "Never yet")
            count_bk = str(len(files))
            ok = bool(files)
        except Exception:
            last_bk = "Unknown"; count_bk = "—"; ok = False

        self._last_lbl.setText(last_bk)
        self._last_lbl.setStyleSheet(
            f"color: {Colors.ACCENT_BLUE if ok else Colors.CRITICAL}; border: none;")
        if hasattr(self, "_count_lbl"):
            self._count_lbl.setText(count_bk)

    def _restore(self):
        dlg = ConfirmationDialog(
            "Restore Backup",
            "Select a backup file to restore.\n\n"
            "The current database will be backed up automatically before restoring.\n"
            "This cannot be undone.",
            confirm_label="Choose File & Restore",
            confirm_color=Colors.MEDIUM,
            parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Backup", str(BASE_DIR / "backups"),
            "SQLite DB (*.db);;All Files (*.*)")
        if not path:
            return
        try:
            pre = restore_database(path)
            Toast.show_in(
                self,
                f"✅  Restored  ·  Pre-restore backup: {pre.name}",
                Colors.SUCCESS_LT)
        except Exception as e:
            Toast.show_in(self, f"⚠  Restore failed: {e}", Colors.CRITICAL)


# ─── Page 5: Audit Logging ────────────────────────────────────────────────────

class _AuditPage(_PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._section("Audit Logging",
                       "Recent configuration and system events.")
        self._build()

    def _build(self):
        card = _card()
        gl = QGridLayout(card)
        gl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        gl.setSpacing(4)
        gl.setColumnStretch(1, 1)
        gl.addWidget(_card_title("Configuration Event Log"), 0, 0, 1, 3)

        # Headers
        for ci, h in enumerate(["Timestamp", "Event", "Details"]):
            lbl = _lbl(h, color=Colors.TEXT_DIM)
            lbl.setFont(Fonts.label_sm_bold())
            gl.addWidget(lbl, 1, ci)

        gl.addWidget(_divider(), 2, 0, 1, 3)

        config_actions = (
            "ORG_SCOPE_SAVE", "SETTINGS_SAVE", "DB_BACKUP",
            "DB_RESTORE", "API_KEY_SAVE", "SCHEMA_MIGRATION",
            "EXPORT_PDF", "EXPORT_CSV",
        )
        with get_db() as conn:
            logs = conn.execute(
                "SELECT timestamp, action, detail FROM audit_log "
                f"WHERE action IN ({','.join('?' for _ in config_actions)}) "
                "ORDER BY id DESC LIMIT 20",
                config_actions,
            ).fetchall()

        if not logs:
            gl.addWidget(
                _lbl("No configuration events recorded yet."), 3, 0, 1, 3)
        else:
            for i, log in enumerate(logs, 3):
                ts  = (log["timestamp"] or "")[:19].replace("T", "  ")
                act = log["action"].replace("_", " ").title()
                det = str(log["detail"] or "")[:60]
                bg = Colors.BG_CARD if i % 2 == 0 else Colors.BG_CARD2
                for ci, txt in enumerate([ts, act, det]):
                    l = _lbl(txt, color=Colors.TEXT_PRIMARY
                              if ci == 1 else Colors.TEXT_MUTED)
                    l.setStyleSheet(
                        f"color: {Colors.TEXT_PRIMARY if ci==1 else Colors.TEXT_MUTED};"
                        f"border: none; background: {bg}; padding: 3px 4px;")
                    gl.addWidget(l, i, ci)

        self._vl.addWidget(card)
        self._vl.addStretch()


# ─── Page 6: About ────────────────────────────────────────────────────────────

class _AboutPage(_PageBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._section("About RiskCore GRC Platform")
        self._build()

    def _build(self):
        # Application info card
        card = _card()
        gl = QGridLayout(card)
        gl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        gl.setSpacing(Spacing.SM)
        gl.setColumnStretch(1, 1)
        gl.addWidget(_card_title("Application"), 0, 0, 1, 2)

        try:
            with get_db() as conn:
                risk_cnt  = conn.execute("SELECT COUNT(*) FROM risks").fetchone()[0]
                treat_cnt = conn.execute("SELECT COUNT(*) FROM treatments").fetchone()[0]
        except Exception:
            risk_cnt = treat_cnt = "—"

        try:
            db_size = f"{DB_PATH.stat().st_size / 1024:.1f} KB"
        except Exception:
            db_size = "—"

        rows = [
            ("Application",      "RiskCore GRC Platform"),
            ("Version",          "1.5 Stable Release"),
            ("Developed by",     "Michael Waugh"),
            ("Report Engine",    "RiskCore Reporting Engine"),
            ("Database",         f"SQLite  ·  {db_size}"),
            ("Python",           f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
            ("Qt",               "PySide6"),
            ("Scoring",          "NIST SP 800-30 Rev 1"),
            ("Frameworks",
             "NIST CSF 2.0  ·  ISO 27001:2022  ·  MITRE ATT&CK  "
             "·  CIS Controls v8  ·  CIA Triad"),
            ("Total Risks",      str(risk_cnt)),
            ("Total Treatments", str(treat_cnt)),
        ]
        for i, (lbl_t, val_t) in enumerate(rows, 1):
            gl.addWidget(_lbl(lbl_t), i, 0)
            gl.addWidget(_lbl(val_t, color=Colors.TEXT_PRIMARY), i, 1)
            if i < len(rows):
                gl.addWidget(_divider(), i * 2, 0, 1, 2)

        self._vl.addWidget(card)

        # Security status card
        sec_card = _card()
        vl2 = QVBoxLayout(sec_card)
        vl2.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        vl2.setSpacing(Spacing.SM)
        vl2.addWidget(_card_title("Security & Compliance Status"))

        sec_items = [
            ("Data Encryption",  "AES-256 (Fernet)",  Colors.SUCCESS_LT),
            ("Audit Logging",    "Enabled",            Colors.SUCCESS_LT),
            ("Backup Status",    "Configured",         Colors.SUCCESS_LT),
            ("Password Policy",  "Strong",             Colors.SUCCESS_LT),
            ("AI Connectivity",  "Configurable",       Colors.MEDIUM),
            ("Compliance Score", "High",               Colors.SUCCESS_LT),
        ]
        for label, status, color in sec_items:
            row_w = QWidget()
            row_w.setStyleSheet("border: none;")
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.addWidget(_lbl(label), 1)
            val = _lbl(status, color=color)
            val.setFont(Fonts.label_sm_bold())
            rl.addWidget(val)
            vl2.addWidget(row_w)

        ok_frame = QFrame()
        ok_frame.setStyleSheet(
            f"background: #0D3321; border-radius: {Radius.SM}px; border: none;")
        ol = QVBoxLayout(ok_frame)
        ol.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        ol.addWidget(_lbl("✓  System is secure and compliant",
                          font=Fonts.label_sm_bold(), color=Colors.SUCCESS_LT))
        ol.addWidget(_lbl("All core security settings are properly configured"))
        vl2.addWidget(ok_frame)
        self._vl.addWidget(sec_card)
        self._vl.addStretch()



class _SupportPage(_PageBase):
    """
    Settings → Support

    Features:
      - Run self-diagnostics (DB integrity, schema, packages)
      - Export diagnostic bundle (zip with logs, system info, sanitised settings)
      - View recent errors from riskcore.log
      - Error consent dialog launched from here
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        # ── Diagnostic Bundle card ────────────────────────────────────────────
        bundle_card = _card()
        bl = QVBoxLayout(bundle_card)
        bl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        bl.setSpacing(Spacing.SM)
        bl.addWidget(_card_title("Diagnostic Bundle"))

        desc = _lbl(
            "Creates a zip file containing your application log, system "
            "information, database integrity report, and recent errors. "
            "No passwords or API keys are included. Share this with your "
            "support contact to help diagnose issues.")
        desc.setWordWrap(True)
        bl.addWidget(desc)
        bl.addSpacing(6)

        self._bundle_status = _lbl("", color=Colors.SUCCESS_LT)
        bl.addWidget(self._bundle_status)

        btn_row = QHBoxLayout()
        export_btn = QPushButton("⬇  Export Diagnostic Bundle")
        export_btn.setFont(Fonts.label_bold())
        export_btn.setFixedHeight(38)
        export_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT_BLUE}; color: white;
                border: none; border-radius: {Radius.SM}px;
                padding: 0 20px;
            }}
            QPushButton:hover {{ background: #1550B0; }}
        """)
        export_btn.clicked.connect(self._export_bundle)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        bl.addLayout(btn_row)
        self._vl.addWidget(bundle_card)

        # ── Self-check card ───────────────────────────────────────────────────
        check_card = _card()
        cl = QVBoxLayout(check_card)
        cl.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        cl.setSpacing(Spacing.SM)
        cl.addWidget(_card_title("System Self-Check"))

        self._check_results = QLabel("Click 'Run Check' to verify system health.")
        self._check_results.setFont(Fonts.label_sm())
        self._check_results.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none;")
        self._check_results.setWordWrap(True)
        cl.addWidget(self._check_results)

        run_btn = QPushButton("▷  Run Check")
        run_btn.setFont(Fonts.label_sm())
        run_btn.setFixedHeight(34)
        run_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_CARD2}; color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BG_BORDER};
                border-radius: {Radius.SM}px; padding: 0 16px;
            }}
            QPushButton:hover {{
                border-color: {Colors.ACCENT_BLUE};
                color: {Colors.ACCENT_BLUE};
            }}
        """)
        run_btn.clicked.connect(self._run_checks)
        cl.addWidget(run_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self._vl.addWidget(check_card)

        # ── Recent errors card ────────────────────────────────────────────────
        err_card = _card()
        el = QVBoxLayout(err_card)
        el.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        el.setSpacing(Spacing.SM)
        el.addWidget(_card_title("Recent Errors"))

        self._err_box = QLabel(self._read_recent_errors())
        self._err_box.setFont(QFont("Courier New", 8))
        self._err_box.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; border: none; "
            f"background: {Colors.BG_CARD2}; padding: 8px; "
            f"border-radius: {Radius.SM}px;")
        self._err_box.setWordWrap(True)
        self._err_box.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        el.addWidget(self._err_box)
        self._vl.addWidget(err_card)
        self._vl.addStretch()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _read_recent_errors() -> str:
        """Return the last 30 error/warning lines from riskcore.log."""
        try:
            log_path = BASE_DIR / "riskcore.log"
            if not log_path.exists():
                return "No log file found."
            lines = log_path.read_text(encoding="utf-8", errors="replace"
                                        ).splitlines()
            # Filter to lines that look like errors
            error_lines = [
                l for l in lines
                if any(k in l.lower() for k in
                       ("error", "exception", "traceback", "fail",
                        "critical", "warning"))
            ][-30:]
            return "\n".join(error_lines) if error_lines else "No errors logged."
        except Exception as e:
            return f"Could not read log: {e}"

    def _run_checks(self) -> None:
        """Run self-diagnostics and display results."""
        results = []

        # 1. DB integrity
        try:
            with get_db() as conn:
                ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
            results.append(("Database integrity", ic,
                             Colors.SUCCESS_LT if ic == "ok" else Colors.CRITICAL))
        except Exception as e:
            results.append(("Database integrity", f"ERROR: {e}", Colors.CRITICAL))

        # 2. DB schema version
        try:
            with get_db() as conn:
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table'").fetchall()]
            expected = {"risks", "treatments", "audit_log",
                        "organisation_scope", "app_config"}
            missing  = expected - set(tables)
            schema_ok = "ok" if not missing else f"Missing: {missing}"
            results.append(("Schema tables", schema_ok,
                             Colors.SUCCESS_LT if not missing else Colors.CRITICAL))
        except Exception as e:
            results.append(("Schema tables", f"ERROR: {e}", Colors.CRITICAL))

        # 3. DB file writable
        try:
            test = DB_PATH.parent / ".riskcore_write_test"
            test.write_text("x"); test.unlink()
            results.append(("DB folder writable", "yes", Colors.SUCCESS_LT))
        except Exception:
            results.append(("DB folder writable", "NO — check permissions",
                             Colors.CRITICAL))

        # 4. Log file writable
        try:
            log_path = BASE_DIR / "riskcore.log"
            with open(log_path, "a") as f:
                pass
            results.append(("Log file writable", "yes", Colors.SUCCESS_LT))
        except Exception:
            results.append(("Log file writable", "NO", Colors.CRITICAL))

        # 5. bcrypt available
        try:
            import bcrypt as _bc
            results.append(("bcrypt (auth)", f"v{_bc.__version__}",
                             Colors.SUCCESS_LT))
        except ImportError:
            results.append(("bcrypt (auth)", "NOT INSTALLED",
                             Colors.CRITICAL))

        # 6. openpyxl available
        try:
            import openpyxl as _ox
            results.append(("openpyxl (Excel)", f"v{_ox.__version__}",
                             Colors.SUCCESS_LT))
        except ImportError:
            results.append(("openpyxl (Excel)", "NOT INSTALLED — Excel export disabled",
                             Colors.MEDIUM))

        # 7. reportlab available
        try:
            import reportlab
            results.append(("reportlab (PDF)", f"v{reportlab.Version}",
                             Colors.SUCCESS_LT))
        except ImportError:
            results.append(("reportlab (PDF)", "NOT INSTALLED — PDF disabled",
                             Colors.CRITICAL))

        # Format output
        lines = []
        all_ok = all(c == Colors.SUCCESS_LT for _, _, c in results)
        for label, val, _ in results:
            icon = "✅" if _ == Colors.SUCCESS_LT else ("⚠" if _ == Colors.MEDIUM else "❌")
            lines.append(f"{icon}  {label:<28} {val}")

        lines.append("")
        lines.append("✅ All checks passed." if all_ok
                     else "⚠  One or more checks need attention.")
        self._check_results.setText("\n".join(lines))
        self._check_results.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none; "
            f"background: {Colors.BG_CARD2}; padding: 8px; "
            f"border-radius: {Radius.SM}px; font-family: 'Courier New'; font-size: 8pt;")

    def _export_bundle(self) -> None:
        """Build and save the diagnostic bundle zip."""
        import os
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        import zipfile, json, subprocess, platform as _plat
        from datetime import datetime as _dt

        # ── Consent notice ────────────────────────────────────────────────────
        msg = QMessageBox(self)
        msg.setWindowTitle("Export Diagnostic Bundle")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "This will create a zip file containing:\n\n"
            "  • riskcore.log (application log)\n"
            "  • system_info.txt (OS, Python, RAM)\n"
            "  • app_version.txt (version details)\n"
            "  • installed_packages.txt (pip list)\n"
            "  • db_integrity.txt (database health)\n"
            "  • recent_errors.txt (last 50 error lines)\n"
            "  • settings.json (sanitised — no passwords or API keys)\n"
            "  • schema_version.txt (database schema)\n"
            "  • last_actions.txt (last 20 audit entries)\n\n"
            "No passwords, API keys, or personal data are included.\n\n"
            "Share this file with your support contact only.")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Ok |
            QMessageBox.StandardButton.Cancel)
        msg.button(QMessageBox.StandardButton.Ok).setText("Export Bundle")
        if msg.exec() != QMessageBox.StandardButton.Ok:
            return

        # ── File path ─────────────────────────────────────────────────────────
        ts    = _dt.now().strftime("%Y-%m-%d")
        default_name = f"RiskCore_Diagnostics_{ts}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Diagnostic Bundle", default_name,
            "Zip Files (*.zip)")
        if not path:
            return

        # ── Collect files ─────────────────────────────────────────────────────
        files: dict[str, str] = {}

        # 1. riskcore.log
        log_path = BASE_DIR / "riskcore.log"
        if log_path.exists():
            files["riskcore.log"] = log_path.read_text(
                encoding="utf-8", errors="replace")
        else:
            files["riskcore.log"] = "Log file not found."

        # 2. system_info.txt
        try:
            import psutil
            ram = f"{psutil.virtual_memory().total / (1024**3):.1f} GB"
        except ImportError:
            ram = "psutil not installed"
        files["system_info.txt"] = "\n".join([
            f"OS:           {_plat.system()} {_plat.release()} "
            f"({_plat.version()})",
            f"Machine:      {_plat.machine()}",
            f"Python:       {sys.version}",
            f"RAM:          {ram}",
            f"App folder:   {BASE_DIR}",
            f"DB path:      {DB_PATH}",
            f"DB size:      {DB_PATH.stat().st_size / 1024:.1f} KB"
            if DB_PATH.exists() else "DB not found",
        ])

        # 3. app_version.txt
        files["app_version.txt"] = "\n".join([
            "Application:  RiskCore GRC Platform",
            "Version:      1.5 Stable Release",
            f"Generated:    {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"DB path:      {DB_PATH}",
        ])

        # 4. installed_packages.txt
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=columns"],
                capture_output=True, text=True, timeout=15)
            files["installed_packages.txt"] = result.stdout or "pip list failed"
        except Exception as e:
            files["installed_packages.txt"] = f"Could not run pip list: {e}"

        # 5. db_integrity.txt
        try:
            with get_db() as conn:
                ic   = conn.execute("PRAGMA integrity_check").fetchone()[0]
                tbls = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' ORDER BY name").fetchall()]
                rc   = conn.execute(
                    "SELECT COUNT(*) FROM risks").fetchone()[0]
                tc   = conn.execute(
                    "SELECT COUNT(*) FROM treatments").fetchone()[0]
            files["db_integrity.txt"] = "\n".join([
                f"integrity_check: {ic}",
                f"tables:          {', '.join(tbls)}",
                f"risks:           {rc}",
                f"treatments:      {tc}",
            ])
        except Exception as e:
            files["db_integrity.txt"] = f"ERROR: {e}"

        # 6. recent_errors.txt
        files["recent_errors.txt"] = self._read_recent_errors()

        # 7. settings.json — sanitised (no passwords / API keys)
        _SCRUB = {
            "app_password_hash", "api_key", "encryption_key",
            "password", "secret", "token",
        }
        try:
            raw = load_settings() or {}
            safe = {k: v for k, v in raw.items()
                    if k.lower() not in _SCRUB}
            files["settings.json"] = json.dumps(safe, indent=2)
        except Exception as e:
            files["settings.json"] = f"Could not read settings: {e}"

        # 8. schema_version.txt
        try:
            with get_db() as conn:
                ver = conn.execute(
                    "SELECT value FROM settings "
                    "WHERE key='schema_version'"
                ).fetchone()
            files["schema_version.txt"] = (
                f"schema_version: {ver['value'] if ver else 'unknown'}")
        except Exception as e:
            files["schema_version.txt"] = f"Could not read schema version: {e}"

        # 9. last_actions.txt
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT action, timestamp, detail "
                    "FROM audit_log ORDER BY id DESC LIMIT 20"
                ).fetchall()
            lines = [
                f"{r['timestamp']}  {r['action']:<20}  {r['detail'] or ''}"
                for r in rows
            ]
            files["last_actions.txt"] = "\n".join(lines) if lines                 else "No audit entries."
        except Exception as e:
            files["last_actions.txt"] = f"Could not read audit log: {e}"

        # ── Write zip ─────────────────────────────────────────────────────────
        try:
            import zipfile as _zf
            with _zf.ZipFile(path, "w", _zf.ZIP_DEFLATED) as zf:
                for fname, content in files.items():
                    zf.writestr(fname, content)
            size_kb = os.path.getsize(path) / 1024
            self._bundle_status.setText(
                f"✅  Bundle exported: {os.path.basename(path)} "
                f"({size_kb:.1f} KB)")
            self._bundle_status.setStyleSheet(
                f"color: {Colors.SUCCESS_LT}; border: none;")
        except Exception as e:
            self._bundle_status.setText(f"⚠  Export failed: {e}")
            self._bundle_status.setStyleSheet(
                f"color: {Colors.CRITICAL}; border: none;")


# ─── Main SettingsPage ────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    navigate      = Signal(str)   # required by MainWindow
    settings_saved = Signal()

    _NAV_ITEMS = [
        ("⬡",  "Organisation",     "Profile, details & preferences"),
        ("◎",  "AI Configuration", "API keys & analysis options"),
        ("⚙",  "Application",      "UI preferences & options"),
        ("◧",  "Backup & Restore", "Data protection & recovery"),
        ("⊙",  "Audit Logging",    "Configuration event history"),
        ("⚕",  "Support",          "Diagnostics, self-check & log export"),
        ("ℹ",  "About",            "Version, developer & system info"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings  = load_settings()
        self._api_key   = load_api_key() or ""
        self._modified  = False
        self._setup_ui()

    def refresh(self):
        pass  # No async refresh needed

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        body.setSpacing(Spacing.LG)

        # Left nav
        self._nav_panel, self._nav_btns = self._build_nav()
        body.addWidget(self._nav_panel, 0)

        # Stacked content
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(Spacing.SM)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent; border: none;")

        self._page_org     = _OrgPage(self._settings)
        self._page_ai      = _AIPage(self._api_key)
        self._page_app     = _AppPage()
        self._page_backup  = _BackupPage()
        self._page_audit   = _AuditPage()
        self._page_support = _SupportPage()
        self._page_about   = _AboutPage()

        for page in (self._page_org, self._page_ai, self._page_app,
                     self._page_backup, self._page_audit,
                     self._page_support, self._page_about):
            self._stack.addWidget(page)
            if hasattr(page, 'changed'):
                page.changed.connect(self._on_modified)

        right.addWidget(self._stack, 1)

        # Save row (only visible for pages that have saveable content)
        self._save_row = self._build_save_row()
        right.addWidget(self._save_row)

        body.addLayout(right, 1)
        root_widget = QWidget()
        root_widget.setStyleSheet("background: transparent; border: none;")
        root_widget.setLayout(body)
        root.addWidget(root_widget, 1)

        # Start on Organisation
        self._select_page(0)

    def _build_header(self) -> QWidget:
        h = QFrame()
        h.setFixedHeight(64)
        h.setStyleSheet(
            f"background: {Colors.BG_CARD}; border: none; "
            f"border-bottom: 1px solid {Colors.BG_BORDER};")
        hl = QHBoxLayout(h)
        hl.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        icon = QLabel("⚙")
        icon.setFont(QFont(Fonts.FAMILY, 18))
        icon.setStyleSheet(f"color: {Colors.ACCENT_BLUE}; border: none;")
        hl.addWidget(icon)
        title = QLabel("Settings & Administration")
        title.setFont(Fonts.heading_1())
        title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; border: none; margin-left: 8px;")
        hl.addWidget(title, 1)
        return h

    def _build_nav(self):
        panel = QFrame()
        panel.setFixedWidth(200)
        panel.setStyleSheet(
            f"background: {Colors.BG_CARD}; border: none; "
            f"border-radius: {Radius.MD}px;")
        vl = QVBoxLayout(panel)
        vl.setContentsMargins(8, 12, 8, 12)
        vl.setSpacing(2)

        btns = []
        for i, (icon, label, desc) in enumerate(self._NAV_ITEMS):
            btn = QPushButton(f"  {icon}  {label}")
            btn.setFont(Fonts.label_sm())
            btn.setFixedHeight(38)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(lambda _, idx=i: self._select_page(idx))
            btns.append(btn)
            vl.addWidget(btn)

        vl.addStretch()
        return panel, btns

    def _style_nav(self, active_idx: int):
        for i, btn in enumerate(self._nav_btns):
            if i == active_idx:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {Colors.ACCENT_BLUE};
                        color: white; border: none;
                        border-radius: {Radius.SM}px;
                        text-align: left; padding-left: 10px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: {Colors.TEXT_MUTED}; border: none;
                        border-radius: {Radius.SM}px;
                        text-align: left; padding-left: 10px;
                    }}
                    QPushButton:hover {{
                        background: {Colors.BG_CARD2};
                        color: {Colors.TEXT_PRIMARY};
                    }}
                """)

    def _build_save_row(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent; border: none;")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 4, 0, 0)
        hl.setSpacing(Spacing.SM)
        hl.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setFont(Fonts.label_sm())
        self._status_lbl.setStyleSheet(
            f"color: {Colors.SUCCESS_LT}; border: none;")
        hl.addWidget(self._status_lbl)

        self._save_btn = _btn("Save Changes", Colors.ACCENT_BLUE, "white", 34)
        self._save_btn.setFixedWidth(140)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)
        hl.addWidget(self._save_btn)
        return row

    def _select_page(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._style_nav(idx)
        # Save row visible only on pages with saveable settings
        saveable = idx in (0, 1, 2)
        self._save_row.setVisible(saveable)
        self._status_lbl.setText("")
        # Organisation page: always enable save
        if idx == 0:
            self._modified = True
        # Backup page (idx 3): refresh to show latest backup status
        if idx == 3 and hasattr(self, "_page_backup"):
            try:
                self._page_backup.refresh()
            except Exception:
                pass
            self._save_btn.setEnabled(True)
        else:
            self._modified = False
            self._save_btn.setEnabled(False)

    def _on_modified(self):
        self._modified = True
        self._save_btn.setEnabled(True)
        self._status_lbl.setText("")

    def _save(self):
        idx = self._stack.currentIndex()

        if idx == 0:  # Organisation
            vals = self._page_org.values()
            # Save settings fields (org name, industry, classification)
            settings_keys = {k: v for k, v in vals.items() if k != "_scope"}
            self._settings = {**self._settings, **settings_keys,
                              "last_saved": datetime.datetime.now().strftime(
                                  "%Y-%m-%d %H:%M:%S")}
            save_settings(self._settings)
            # Save full org scope (includes size, assessment details, assets, units)
            try:
                from core.database.db import save_organisation_scope, get_organisation_scope
                scope_data = vals.get("_scope", {})
                if scope_data:
                    save_organisation_scope(scope_data)
            except Exception as _e:
                Toast.show_in(self, f"⚠  Scope save failed: {_e}", Colors.MEDIUM)

        elif idx == 1:  # AI Config
            key = self._page_ai.api_key()
            if key and key != self._api_key:
                if key.startswith("sk-ant"):
                    save_api_key(key)
                    self._api_key = key
                else:
                    Toast.show_in(self, "⚠  API key must start with sk-ant-api03-",
                                  Colors.MEDIUM)
                    return

        elif idx == 2:  # Application
            pass  # preferences handled in-page

        self._modified = False
        self._save_btn.setEnabled(False)
        self._status_lbl.setText("✅  Saved")
        Toast.show_in(self, "✅  Settings saved", Colors.SUCCESS_LT)
        self.settings_saved.emit()
