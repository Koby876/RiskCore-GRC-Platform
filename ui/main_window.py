"""
ui/main_window.py — RiskCore GRC Platform v1.5
Application shell.

CONSTRUCTION ORDER (must not be changed):
    1. _build_status_bar()    → creates _sb_db / _sb_stats / _sb_time
    2. _build_page("dashboard")
    3. _navigate("dashboard") → calls _refresh_status_bar() — safe because 1 ran
    4. QTimer for 60-second refresh
"""

from __future__ import annotations
import sys

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout,
    QStackedWidget, QStatusBar, QLabel,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from assets.themes.design_system import Colors, Fonts
from widgets.navigation import Sidebar
from widgets.components import Toast
from core.database.db import init_db, get_stats, now_str, DB_PATH


class PlaceholderPage(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QVBoxLayout
        lbl = QLabel(f"◎  {name}\n\nThis page will be available in a future update.")
        lbl.setFont(QFont(Fonts.FAMILY, 13))
        lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(lbl)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("RiskCore GRC Platform v1.5")
        self.resize(1280, 820)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(f"background-color: {Colors.BG_DEEP}; border: none;")

        # Cross-page state
        self._pending_ai_risks: list = []
        self._last_analysis:    dict = {}
        self._exec_summary:     dict = {}

        # Status bar label sentinels — None until _build_status_bar() runs.
        # _refresh_status_bar() checks these before use.
        self._sb_db:    QLabel | None = None
        self._sb_stats: QLabel | None = None
        self._sb_time:  QLabel | None = None

        init_db()

        # Shell layout
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.page_requested.connect(self._navigate)
        root.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {Colors.BG_DEEP};")
        root.addWidget(self._stack, 1)

        self._pages: dict[str, QWidget] = {}

        # ── ORDERED STARTUP — do not reorder ─────────────────────
        self._build_status_bar()          # Step 1 — must be first

        self._build_page("dashboard")     # Step 2

        self._navigate("dashboard")       # Step 3 — safe, status bar exists

        # Step 4 — periodic refresh timer
        self._sb_timer = QTimer(self)
        self._sb_timer.timeout.connect(self._refresh_status_bar)
        self._sb_timer.start(60_000)


    # ── Page construction ─────────────────────────────────────────

    def _build_page(self, key: str) -> QWidget:
        if key in self._pages:
            return self._pages[key]


        if key == "dashboard":
            from ui.dashboard import DashboardPage
            page = DashboardPage()
            page.navigate.connect(self._navigate)

        elif key == "ai":
            from ui.ai_workspace import AIWorkspacePage
            page = AIWorkspacePage()
            page.navigate.connect(self._navigate)
            page.analysis_complete.connect(self.set_pending_ai_risks)

        elif key == "register":
            from ui.risk_register import RiskRegisterPage
            page = RiskRegisterPage()
            page.navigate.connect(self._navigate)
            page.add_risk_requested.connect(lambda: self._navigate("add"))
            page.edit_risk_requested.connect(self._navigate_with_edit)
            page.data_changed.connect(self.refresh_all)
            # Wire "Add Treatment" from Risk Detail → Treatments page
            page.add_treatment_requested.connect(
                self.navigate_to_treatment)

        elif key == "treatments":
            from ui.treatments import TreatmentsPage
            page = TreatmentsPage()
            page.navigate.connect(self._navigate)
            page.treatment_saved.connect(self.refresh_all)

        elif key == "matrix":
            from ui.matrix import RiskMatrixPage
            page = RiskMatrixPage()
            page.navigate.connect(self._navigate)

        elif key == "export":
            from ui.reports import ReportsPage
            page = ReportsPage()
            page.navigate.connect(self._navigate)

        elif key == "audit":
            from ui.audit_log import AuditLogPage
            page = AuditLogPage()
            page.navigate.connect(self._navigate)

        elif key == "settings":
            from ui.settings import SettingsPage
            page = SettingsPage()
            page.navigate.connect(self._navigate)
            page.settings_saved.connect(self._on_settings_saved)

        elif key == "add":
            from ui.risk_form import RiskFormPage
            page = RiskFormPage(edit_id=None)
            page.saved.connect(self._after_risk_save)
            page.cancelled.connect(lambda: self._navigate("register"))

        elif key == "framework":
            from ui.framework_intelligence import FrameworkIntelligencePage
            page = FrameworkIntelligencePage()
            page.navigate.connect(self._navigate)

        else:
            page = PlaceholderPage(key)

        self._stack.addWidget(page)
        self._pages[key] = page
        return page

    # ── Navigation ────────────────────────────────────────────────

    def _navigate(self, page_key: str) -> None:
        page = self._build_page(page_key)
        self._stack.setCurrentWidget(page)
        self._sidebar.set_active_page(page_key)
        self._refresh_status_bar()

        if page_key == "dashboard":
            from ui.dashboard import DashboardPage as DP
            if isinstance(page, DP):
                page.set_exec_summary(self._exec_summary or None)
                page.refresh()

        elif page_key == "register":
            from ui.risk_register import RiskRegisterPage as RP
            if isinstance(page, RP):
                page.refresh()

        elif page_key == "treatments":
            from ui.treatments import TreatmentsPage as TP
            if isinstance(page, TP):
                page.refresh()

        elif page_key == "matrix":
            from ui.matrix import RiskMatrixPage as MP
            if isinstance(page, MP):
                page._load()

        elif page_key == "audit":
            from ui.audit_log import AuditLogPage as AP
            if isinstance(page, AP):
                page.refresh()

        elif page_key == "ai":
            from ui.ai_workspace import AIWorkspacePage as AI
            if (isinstance(page, AI)
                    and self._pending_ai_risks
                    and not page._pending_risks):
                page._pending_risks = self._pending_ai_risks
                page._last_analysis = self._last_analysis
                page._clear_body()
                page._build_results_body()
                page._update_summary_panel()
                page._update_kpi_strip()

        elif page_key == "export":
            from ui.reports import ReportsPage as RP2
            if isinstance(page, RP2):
                if self._last_analysis:
                    page.set_analysis(self._last_analysis)
                page.refresh()

        elif page_key == "framework":
            from ui.framework_intelligence import FrameworkIntelligencePage as FP
            if isinstance(page, FP):
                page.refresh()

    def _navigate_with_edit(self, rid: int) -> None:
        from ui.risk_form import RiskFormPage
        key = f"edit_{rid}"
        if key not in self._pages:
            page = RiskFormPage(edit_id=rid)
            page.saved.connect(self._after_risk_save)
            page.cancelled.connect(lambda: self._navigate("register"))
            self._stack.addWidget(page)
            self._pages[key] = page
        self._stack.setCurrentWidget(self._pages[key])
        self._sidebar.set_active_page("add")

    def _after_risk_save(self, rid: int) -> None:
        for k in [k for k in self._pages if k.startswith("edit_")]:
            w = self._pages.pop(k)
            self._stack.removeWidget(w)
            w.deleteLater()
        if "add" in self._pages:
            w = self._pages.pop("add")
            self._stack.removeWidget(w)
            w.deleteLater()
        self._navigate("register")
        self.refresh_all()
        Toast.show_in(self, f"✅  Risk #{rid} saved", Colors.SUCCESS_LT)

    def navigate_to_treatment(self, risk_id: int) -> None:
        page = self._build_page("treatments")
        self._stack.setCurrentWidget(page)
        self._sidebar.set_active_page("treatments")
        from ui.treatments import TreatmentsPage as TP
        if isinstance(page, TP):
            page.open_for_risk(risk_id)

    def _on_settings_saved(self) -> None:
        """
        Called when user clicks Save Changes in any Settings tab.
        Propagates changes to every page that uses org data:
          - Status bar (org name, db path)
          - Dashboard (org name in header, KPIs)
          - Export/Reports (company name field, classification)
          - AI Analysis (org context for prompts)
          - Framework Intelligence (org scope)
        Single source of truth: DB → every page reads fresh on next refresh.
        """
        self._refresh_status_bar()
        # Reload settings into memory
        from core.database.db import load_settings
        try:
            self._exec_summary = None  # reset cached analysis
        except Exception:
            pass
        # Refresh every built page so org name propagates everywhere
        _refresh_map = {
            "dashboard": "refresh", "register": "refresh",
            "export":    "refresh", "framework": "refresh",
            "matrix":    "_load",   "audit":     "refresh",
        }
        # Also refresh backup page if it's been built
        try:
            settings_widget = self._pages.get("settings")
            if settings_widget and hasattr(settings_widget, "_page_backup"):
                settings_widget._page_backup.refresh()
        except Exception:
            pass
        for key, method in _refresh_map.items():
            page = self._pages.get(key)
            if page and hasattr(page, method):
                try:
                    getattr(page, method)()
                except Exception:
                    pass

    def refresh_all(self) -> None:
        """Refresh every built page after any data change."""
        self._refresh_status_bar()
        for key, refresher in {
            "dashboard":  lambda p: p.refresh(),
            "register":   lambda p: p.refresh(),
            "treatments": lambda p: p.refresh(),
            "matrix":     lambda p: p._load(),
            "audit":      lambda p: p.refresh(),
            "export":     lambda p: p.refresh(),
            "framework":  lambda p: p.refresh(),
        }.items():
            if key in self._pages:
                try:
                    refresher(self._pages[key])
                except Exception:
                    pass  # page not yet built or refresh not applicable

    def closeEvent(self, event) -> None:
        """
        Flush WAL to the main database file before closing.
        Without this, writes sitting in the WAL file won't appear
        when the application is reopened (they're still valid SQLite
        data but require a checkpoint to move into the main DB file).
        """
        try:
            from core.database.db import get_db
            with get_db() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as _e:
            print(f"[close checkpoint] {_e}")
        # Stop the periodic timer cleanly
        if hasattr(self, '_sb_timer'):
            self._sb_timer.stop()
        super().closeEvent(event)

    # ── Status bar ────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)

        self._sb_db    = QLabel()
        self._sb_stats = QLabel()
        self._sb_time  = QLabel()

        for lbl in (self._sb_db, self._sb_stats, self._sb_time):
            lbl.setFont(QFont(Fonts.FAMILY, 9))
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")

        sb.addWidget(self._sb_db)
        sb.addWidget(self._sb_stats)
        sb.addPermanentWidget(self._sb_time)
        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        # Guard: safe to call before status bar is constructed
        if self._sb_db is None:
            return

        db_ok = DB_PATH.exists()
        self._sb_db.setText(
            f"  {'●' if db_ok else '✕'} "
            f"{'DB: Connected' if db_ok else 'DB ERROR'}")
        self._sb_db.setStyleSheet(
            f"color: {Colors.SUCCESS_LT if db_ok else Colors.CRITICAL};")

        if db_ok:
            try:
                stats = get_stats()
                self._sb_stats.setText(
                    f"   │   risks · {stats['total']}"
                    f"  ·  critical · {stats['critical']}"
                    f"  ·  treatments · {stats['treat_total']}")
            except Exception:
                self._sb_stats.setText("   │   loading...")
        else:
            self._sb_stats.setText("   │   database unavailable")

        self._sb_time.setText(f"v1.5  ·  {now_str()}   ")

    # ── AI state ──────────────────────────────────────────────────

    def set_pending_ai_risks(self, risks: list, analysis: dict) -> None:
        self._pending_ai_risks = risks
        self._last_analysis    = analysis
        self._sidebar.set_ai_pending(len(risks))

        if risks:
            try:
                from core.services.ai_service import build_executive_summary
                from core.database.db import get_organisation_scope
                self._exec_summary = build_executive_summary(
                    analysis, risks, org_scope=get_organisation_scope())
            except Exception:
                self._exec_summary = {}

        if "export" in self._pages:
            from ui.reports import ReportsPage as RP2
            p = self._pages["export"]
            if isinstance(p, RP2):
                p.set_analysis(analysis)
