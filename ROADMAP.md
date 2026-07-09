# RiskCore GRC Platform — Roadmap

## v1.5 — Current Release

### Intelligence Layer ✅ Complete
- [x] AI Risk Analysis (Claude claude-sonnet-4-6)
- [x] Executive Summary Engine
- [x] Evidence & Confidence Engine
- [x] Framework Intelligence (NIST CSF 2.0, ISO 27001, MITRE ATT&CK, CIS v8, CIA Triad)
- [x] Framework Coverage Dashboard
- [x] NIST SP 800-53 Rev 5 Recommendation Engine (57 controls, 14 families)
- [x] Organisation Scope integration
- [x] PDF Report generation (ReportLab, professional executive layout)

### PySide6 Migration ✅ Complete
- [x] Phase 1 — Main Window, Design System, Navigation, Dashboard
- [x] Phase 2 — AI Workspace
- [x] Phase 3 — Risk Register (virtualised QTableView)
- [x] Phase 4 — Risk Detail dialog
- [x] Phase 5 — Treatments
- [x] Phase 6 — Risk Matrix + Activity Center
- [x] Phase 7 — Export & Report
- [x] Phase 8 — Settings
- [x] Phase 9 — Add / Edit Risk form
- [x] Phase 10 — Widget library, final wiring, project restructure

---

## v1.6 — Near Term

### Organisation Scope (full UI)
- [ ] Dedicated Organisation Scope page
- [ ] Business units editor
- [ ] Asset inventory management
- [ ] Framework selection UI

### Risk Register Enhancements
- [ ] Bulk actions (select multiple → change status / owner / priority)
- [ ] Column visibility toggle
- [ ] Export filtered view to CSV
- [ ] Risk comparison view (before/after treatment)

### Treatments
- [ ] Treatment roadmap Gantt view
- [ ] Budget tracker (cost estimate aggregation)
- [ ] Treatment effectiveness scoring
- [ ] Email reminder integration (placeholder)

### AI Analysis
- [ ] Analysis history browser (view past analyses)
- [ ] Side-by-side document comparison
- [ ] Re-analyse existing risks against new document
- [ ] Confidence calibration from user feedback

---

## v2.0 — Medium Term

### Executive PowerPoint Export
- [ ] python-pptx integration
- [ ] Executive slide deck from existing analysis
- [ ] Framework coverage charts embedded
- [ ] Risk heat map slide

### Multi-User Support
- [ ] User accounts with role-based access (CISO / Analyst / Auditor / Read-only)
- [ ] Activity attribution per user
- [ ] Approval workflow (risk flagged → reviewed → approved)

### Framework Crosswalk Integration
- [ ] MITRE ATT&CK ↔ NIST 800-53 official crosswalk (CTID dataset)
- [ ] NIST CSF 2.0 ↔ NIST 800-53 mapping (SP 800-53B)
- [ ] ISO 27001:2022 ↔ NIST 800-53 mapping
- [ ] CIS Controls v8 ↔ NIST 800-53 mapping

### Dashboard Charts
- [ ] QCharts integration (native Qt — replaces bar-strip approximations)
- [ ] Real donut chart for risk severity distribution
- [ ] Trend line for risk score over time
- [ ] Framework coverage radar chart

### Risk Register
- [ ] Drag-to-reorder priority
- [ ] Risk dependency graph (risk A depends on risk B)
- [ ] Version history per risk (audit trail with diff view)

---

## v2.5 — Long Term

### Compliance Modules
- [ ] PCI DSS mapping
- [ ] HIPAA mapping
- [ ] SOC 2 mapping
- [ ] GDPR mapping
- [ ] Manufacturing / OT-specific controls (IEC 62443)

### Integrations
- [ ] JIRA ticket creation from risk
- [ ] ServiceNow integration
- [ ] Microsoft 365 / Teams notifications
- [ ] Splunk / SIEM log pull for evidence

### AI Enhancements
- [ ] Continuous monitoring mode (re-analyse on schedule)
- [ ] Risk score prediction from control changes
- [ ] Peer benchmarking (anonymised industry posture)
- [ ] Natural language risk query ("what are our top cloud risks?")

### Reporting
- [ ] Board-level executive dashboard (read-only view)
- [ ] Scheduled automated PDF delivery
- [ ] Custom report templates
- [ ] Regulatory submission format export

---

## Known Limitations (v1.5)

| Item | Status |
|---|---|
| MITRE ↔ NIST 800-53 crosswalk | Deferred — requires CTID dataset acquisition |
| QCharts bar/donut charts | Using QFrame approximations — QCharts integration in v2.0 |
| Multi-user | Single-user local SQLite — multi-user in v2.0 |
| Logo upload | Placeholder exists in PDF + Settings — file picker in v1.6 |
| Risk form edit via register row | Wired — edit page rebuilds fresh per risk |
