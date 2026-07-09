# RiskCore GRC Platform — Release Notes

---

## v1.5.0 — 2026-07-02  (Current Release)

### Summary
Complete PySide6 (Qt 6) migration of RiskCore with full intelligence layer,
Framework Intelligence module, CIS/MITRE reference data, and production-grade
threading, signal marshalling, and refresh architecture.

---

### New Features

#### Framework Intelligence (new page)
- Live analysis of all 5 frameworks derived from the risk register
- NIST CSF 2.0: per-function risk bars, covered/missing categories
- ISO 27001:2022: per-domain coverage, unmapped risks list
- MITRE ATT&CK: tactic coverage with detection and mitigation guidance
- CIS Controls v8: per-IG grouped view with full official names
- CIA Triad: per-component distribution with recommendations
- Recommendations tab: intelligent, priority-ranked recommendations
  generated from risk titles and descriptions

#### CIS Controls v8 — complete reference data
- All 18 controls with official titles, descriptions, Implementation Group
- Displayed as "CIS-5 · Account Management" throughout the application
- New `core/database/lookups.py` module

#### MITRE ATT&CK — complete reference data
- All 14 tactics with IDs (TA0001–TA0043), descriptions
- Common techniques, detection guidance, mitigation recommendations
- Displayed as "TA0006 · Credential Access" throughout

#### AI-created risks
- AI-approved risks now appear immediately in Dashboard, Register,
  Matrix, Export, and Audit Log without special handling

#### Global refresh architecture
- `MainWindow.refresh_all()` refreshes all built pages after any data change
- Risk create/update/delete → all pages refresh
- Treatment save/delete → all pages refresh
- No restart required for any operation

#### Export fix
- PDF and CSV export now query the database fresh on every export
- Export page shows correct risk count at all times
- `refresh()` method added to ReportsPage

---

### Bug Fixes

| Bug | Fix |
|---|---|
| Export showed "No risks" despite 7 in register | `_risks_cache` was populated once at construction; now queries fresh every export |
| Dashboard stuck on "Loading..." | `Signal(dict)` cannot be marshalled through Qt C++ cross-thread; changed to `Signal(object)` |
| `QThread: Destroyed while thread still running` | Thread parented to widget broke `moveToThread`; removed parent, store as `self._thread` |
| `AttributeError: _sb_db` on startup | `_build_status_bar()` called after `_navigate()`; reordered construction |
| `AttributeError: '_thread'` on refresh | Missing `self._thread = None` sentinel in `__init__`; added to all pages |
| `RuntimeError: Internal C++ object deleted` | `thread.deleteLater()` deleted C++ while Python wrapper held it; replaced with `setattr(self, '_thread', None)` |
| Backup status showed "Never" after backup | Label reference not stored; stored as `self._last_bk_lbl`, updated immediately |
| Risk Register columns too narrow | All column widths increased; Title column stretches |
| Single-character risks accepted | Validation now requires minimum 3-character title, 2-character owner |

---

### Architecture Changes

- `Signal(dict)` → `Signal(object)` across all 7 worker/page signals
- `QThread(self)` → `QThread()` across all 5 threaded pages
- Thread cleanup: `finished → worker.deleteLater + setattr(_thread, None)`
- Re-entrant guard: `if self._thread is not None and self._thread.isRunning(): return`
- Worker stored as `self._worker` to prevent GC before thread completes

---

## v1.0.0 — 2026-06-01

Initial release: CustomTkinter desktop application with SQLite backend,
5-framework risk mapping, NIST SP 800-30 scoring, AI analysis, PDF reports,
treatment management, audit log, encrypted API key storage, backup/restore.
