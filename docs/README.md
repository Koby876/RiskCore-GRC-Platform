# RiskCore GRC Platform v1.5

> **See Risk Clearly. Decide Confidently.**

A native Windows enterprise GRC desktop application.  
Single-user · Local SQLite · AI-powered · PySide6 (Qt 6)

---

## Quick Start

```bash
# 1. Install dependencies
cd RiskCore
pip install -r requirements.txt

# 2. Launch
python main.py
```

The database is created automatically at `RiskCore/data/riskcore.db` on first launch.

---

## What's Inside

### Risk Management
- **Risk Register** — full CRUD, virtualised table, live search and filters
- **Risk Matrix** — 5×5 NIST SP 800-30 heat map, click any cell to view risks
- **Risk Detail** — all 24 fields, framework mappings, NIST 800-53 recommendations, treatments
- **Add / Edit Risk** — 5-section form with live scoring card
- **Delete Risk** — confirmation dialog, cascade deletes treatments, refreshes all pages

### Treatment Management
- Full lifecycle: Draft → Approved → In Progress → Completed → Verified
- Linked to parent risk with residual score tracking
- Treatment counts shown in register and dashboard

### AI Analysis
- Upload any PDF (policy, audit report, vendor assessment)
- Claude identifies risks, maps to 5 frameworks, scores with NIST SP 800-30
- Evidence engine cites source text — never fabricates
- Approved risks appear immediately in Dashboard, Register, Matrix, Export

### Framework Intelligence
- Per-framework coverage analysis derived live from the risk register
- **NIST CSF 2.0** — per-function risk counts, covered/missing categories
- **ISO 27001:2022** — per-domain coverage, unmapped risks
- **MITRE ATT&CK** — tactic coverage, detection and mitigation guidance
- **CIS Controls v8** — per-IG grouped view, full control names and descriptions
- **CIA Triad** — per-component risk distribution, recommendations
- **Recommendations** — intelligent, context-aware recommendations generated from your register

### Export & Reporting
- **PDF Report** — professional executive report (ReportLab)
- **CSV Export** — all 23 fields, UTF-8, Excel compatible
- **Database Backup** — timestamped SQLite copy, one-click restore

### Audit Log (Activity Center)
- ISO/IEC 27001:2022 A.8 compliant
- 7 filter groups with live counts
- Every create / update / delete / AI / export / backup event recorded

### Settings
- Organisation profile, industry, classification default
- Anthropic API key (AES-256 encrypted, local only)
- Backup management with live status

---

## Frameworks Supported

| Framework | Coverage |
|---|---|
| NIST CSF 2.0 | All 6 functions, categories, subcategories |
| ISO/IEC 27001:2022 | All 4 Annex A domains |
| MITRE ATT&CK | All 14 tactics with IDs and technique guidance |
| CIS Controls v8 | All 18 controls with official titles, IG classification |
| CIA Triad | Confidentiality / Integrity / Availability / All Three |
| NIST SP 800-30 Rev 1 | Risk scoring (Likelihood × Impact, 1–25) |
| NIST SP 800-53 Rev 5 | 57 advisory controls across 14 families |

---

## Project Structure

```
RiskCore/
├── main.py                     Entry point
├── riskcore_phase2.py          Backend (DB, business logic, PDF)
├── riskcore_ai.py              AI engine (analysis, recommendations)
├── requirements.txt
│
├── ui/                         Page modules
│   ├── main_window.py
│   ├── dashboard.py
│   ├── ai_workspace.py
│   ├── risk_register.py
│   ├── risk_detail.py
│   ├── risk_form.py
│   ├── treatments.py
│   ├── matrix.py
│   ├── framework_intelligence.py
│   ├── reports.py
│   ├── audit_log.py
│   └── settings.py
│
├── widgets/                    Reusable Qt components
│   ├── cards.py
│   ├── tables.py
│   ├── navigation.py
│   └── components.py
│
├── core/
│   ├── database/db.py          Backend bridge (56 exports)
│   ├── database/lookups.py     CIS and MITRE reference data
│   ├── services/ai_service.py  AI bridge
│   └── services/analysis_worker.py
│
├── assets/themes/design_system.py   Colours, fonts, QSS
│
└── data/                       riskcore.db auto-created here
```

---

## AI Setup

1. Get your API key at [console.anthropic.com](https://console.anthropic.com) → API Keys
2. In RiskCore: **AI Analysis** → enter key → **Save Key**
3. Or: **Settings** → AI Configuration → **Test Connection** → **Save Changes**

Keys are encrypted with Fernet (AES-256) and stored locally only.

---

**Waugh Development Group · RiskCore GRC Platform v1.5**
