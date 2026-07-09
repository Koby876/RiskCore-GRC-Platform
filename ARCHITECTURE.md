# RiskCore GRC Platform v1.5 — Architecture

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                         │
│                                                               │
│   ui/           ← one file per page                         │
│   widgets/      ← reusable Qt components                    │
│                                                               │
│   Rules:                                                      │
│   • Never imports riskcore_phase2 or riskcore_ai directly   │
│   • Never writes SQL                                          │
│   • All DB queries on QThread workers                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ imports from
┌──────────────────────────▼──────────────────────────────────┐
│                     Service Layer                             │
│                                                               │
│   core/database/db.py          ← 56 re-exported DB names   │
│   core/database/lookups.py     ← CIS/MITRE reference data  │
│   core/services/ai_service.py  ← AI/intelligence bridge    │
│   core/services/analysis_worker.py  ← QThread workers      │
└──────────────────────────┬──────────────────────────────────┘
                           │ imports from
┌──────────────────────────▼──────────────────────────────────┐
│                     Backend Layer                             │
│                                                               │
│   riskcore_phase2.py   ← SQLite, business logic, PDF       │
│   riskcore_ai.py       ← Anthropic API, framework intel    │
│                                                               │
│   Stable. Never modified during Qt migration.               │
└─────────────────────────────────────────────────────────────┘
```

## Thread Safety Rules

Every page that loads data follows this exact pattern:

```python
def refresh(self) -> None:
    # 1. Re-entrant guard
    if self._thread is not None and self._thread.isRunning():
        return

    # 2. Create thread and worker with NO parent
    self._thread = QThread()          # no parent — required for moveToThread
    self._worker = MyWorker()         # no parent
    self._worker.moveToThread(self._thread)

    # 3. Connect signals
    self._thread.started.connect(self._worker.run)
    self._worker.finished.connect(self._on_loaded)
    self._worker.finished.connect(self._thread.quit)
    self._worker.error.connect(self._thread.quit)

    # 4. Cleanup — set self._thread to None (do NOT call deleteLater on thread)
    self._thread.finished.connect(self._worker.deleteLater)
    self._thread.finished.connect(
        lambda: setattr(self, '_thread', None))

    # 5. Start
    self._thread.start()
```

## Signal Type Rule

All signals that carry Python containers (dict, list) across thread boundaries
MUST use `Signal(object)` — NOT `Signal(dict)` or `Signal(list)`.

```python
# ❌ Wrong — Qt cannot C++-convert Python dicts cross-thread
finished = Signal(dict)

# ✅ Correct — passes Python object reference directly
finished = Signal(object)
```

## Page Construction Order (MainWindow.__init__)

```
1. self._build_status_bar()      # creates _sb_db, _sb_stats, _sb_time
2. self._build_page("dashboard") # constructs widget — no thread
3. self._navigate("dashboard")   # calls _refresh_status_bar() — safe
4. QTimer started (60s refresh)
```

This order must not change. `_refresh_status_bar()` requires the labels
to exist. `_navigate()` calls `_refresh_status_bar()` internally.

## Global Refresh

`MainWindow.refresh_all()` is called after every data-changing operation:

- Risk created / updated / deleted
- Treatment created / updated / deleted
- Settings saved
- Backup completed

It iterates every built page and calls its `refresh()` method, ensuring
Dashboard, Register, Matrix, Audit Log, Export, and Framework Intelligence
are all current without requiring a restart.

## File Map

| File | Responsibility |
|---|---|
| `main.py` | Entry point, QApplication, exception hook |
| `core/database/db.py` | Re-exports 56 backend functions |
| `core/database/lookups.py` | CIS v8 and MITRE ATT&CK static reference data |
| `core/services/ai_service.py` | Re-exports AI/intelligence functions |
| `core/services/analysis_worker.py` | QThread workers for AI pipeline |
| `assets/themes/design_system.py` | All colours, fonts, spacing, QSS |
| `widgets/cards.py` | KpiCard, FwCoverageRow, badges |
| `widgets/tables.py` | RiskTableModel, TreatmentTableModel, delegates |
| `widgets/navigation.py` | Sidebar, NavButton |
| `widgets/components.py` | Toast, EmptyState, FilterBar, Timeline, etc. |
| `ui/main_window.py` | App shell, QStackedWidget, routing, refresh_all |
| `ui/dashboard.py` | Executive Dashboard |
| `ui/ai_workspace.py` | AI Analysis workflow |
| `ui/risk_register.py` | Risk Register (virtualised QTableView) |
| `ui/risk_detail.py` | Risk Detail dialog (3 tabs) |
| `ui/risk_form.py` | Add / Edit Risk form |
| `ui/treatments.py` | Treatments page + dialog |
| `ui/matrix.py` | 5×5 Risk Matrix |
| `ui/framework_intelligence.py` | Framework Intelligence (6 tabs) |
| `ui/reports.py` | Export & Report |
| `ui/audit_log.py` | Activity Center |
| `ui/settings.py` | Settings |
