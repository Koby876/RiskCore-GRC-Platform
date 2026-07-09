<div align="center">

# RiskCore GRC Platform

**See Risk Clearly. Decide Confidently.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
[![PySide6](https://img.shields.io/badge/UI-PySide6%20Qt%206-green.svg)](https://pypi.org/project/PySide6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.5-red.svg)](docs/RELEASE_NOTES.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey.svg)]()

A native Windows enterprise GRC desktop application.  
Single-user · Local SQLite · AI-powered analysis · Consultant-quality PDF and Excel reports

---

**[⬇ Download RiskCore v1.5 for Windows](https://github.com/YOUR_USERNAME/RiskCore/releases/latest)**  
*No Python required — single executable, double-click to run*

</div>

---

## What is RiskCore?

RiskCore is a full-featured Governance, Risk and Compliance (GRC) platform for cybersecurity risk management. It maps risks across five industry frameworks simultaneously, generates board-ready PDF reports, and produces professional Excel workbooks — all running locally with no cloud dependency or subscription.

**Built for:** GRC analysts, information security professionals, and small-to-medium organisations conducting internal risk assessments.

---

## Features

### Risk Management
- **Risk Register** — master-detail layout, live search, multi-filter by status, NIST function, severity, and owner
- **Risk Matrix** — interactive 5×5 NIST SP 800-30 heat map, click any cell to view risks
- **Risk Detail** — 24 fields including all framework mappings, AI recommendations, linked treatments
- **Treatment Plans** — strategy, owner, target date, cost estimate, residual scoring, approval workflow
- **Risk Scoring** — Likelihood × Impact with automatic Critical/High/Medium/Low classification

### Framework Intelligence
| Framework | Coverage |
|---|---|
| NIST CSF 2.0 | All 6 functions — Govern, Identify, Protect, Detect, Respond, Recover |
| ISO/IEC 27001:2022 | All domains with control-level mapping (A.5–A.8) |
| MITRE ATT&CK | Tactic and technique mapping with detection guidance |
| CIS Controls v8 | Control-level mapping |
| CIA Triad | Confidentiality / Integrity / Availability |

### Reporting
- **PDF Report** — 11-section, 40+ page consultant-quality report with accurate two-pass TOC
- **Excel Workbook** — 5 sheets: Executive Summary, Risk Register, Treatments, Charts & Analytics, Risk Analysis pivot
- **CSV Export** — raw data for further analysis
- **Database Backup** — one-click timestamped SQLite backups with restore

### AI Integration (Optional)
- Anthropic Claude API integration for document analysis and automated risk generation
- AI-assisted risk scoring and framework recommendations
- Evidence-based confidence scoring
- Graceful degradation when no API key is configured — full app works without it

### Security
- bcrypt password authentication (cost factor 12) with 5-attempt lockout
- AES-256 Fernet encryption for API key storage
- Parameterised SQL — no injection risk
- Full audit log of all changes
- Diagnostic bundle export for support (passwords and keys automatically scrubbed)

---

## Quick Start

### Option 1 — Download (Recommended)

**[Download RiskCore v1.5 for Windows →](https://github.com/YOUR_USERNAME/RiskCore/releases/latest)**

Extract the zip, double-click `RiskCore.exe`. No Python, no installation required.

### Option 2 — Run from Source

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/RiskCore.git
cd RiskCore

# Install dependencies
pip install -r requirements.txt

# Launch
python main.py
```

First launch prompts you to set an access password and creates the database automatically.

### Option 3 — Build the Executable Yourself

```bash
# One command — builds and packages the release
build_release.bat
```

Output: `RiskCore_v1.5_Windows.zip` ready to distribute.

---

## Requirements

### Running the exe
- Windows 10 or Windows 11 (64-bit)
- Nothing else

### Running from source
- Python 3.11+
- Dependencies in `requirements.txt`

| Package | Version | Purpose |
|---|---|---|
| PySide6 | ≥6.5.0 | Qt 6 desktop UI |
| reportlab | ≥4.0.0 | PDF generation |
| openpyxl | ≥3.1.0 | Excel export |
| bcrypt | ≥4.0.0 | Password hashing |
| cryptography | ≥41.0.0 | API key encryption |
| pypdf | ≥3.0.0 | PDF reading for AI analysis |
| pillow | ≥10.0.0 | Image handling (reportlab dependency) |

---

## Project Structure

```
RiskCore/
├── main.py                        # Entry point — auth, crash reporter
├── riskcore_phase2.py             # Backend — DB, CRUD, settings, encryption
├── riskcore_ai.py                 # AI engine + PDF generator
├── RiskCore.spec                  # PyInstaller build configuration
├── requirements.txt               # Python dependencies
├── build_release.bat              # One-command build + package script
│
├── assets/
│   ├── images/                    # Logo and icons
│   └── themes/
│       └── design_system.py       # Design tokens — colours, fonts, spacing
│
├── core/
│   ├── database/
│   │   ├── db.py                  # Single DB access point
│   │   └── lookups.py             # Framework reference data
│   └── services/
│       └── analysis_worker.py     # Background AI worker
│
├── ui/                            # Page modules
│   ├── main_window.py             # Shell, navigation, page switching
│   ├── login.py                   # Authentication dialogs
│   ├── dashboard.py               # KPI cards, NIST distribution, top risks
│   ├── risk_register.py           # Master-detail risk table
│   ├── risk_form.py               # Add / edit risk
│   ├── risk_detail.py             # Full risk detail dialog
│   ├── treatments.py              # Treatment plans
│   ├── matrix.py                  # 5×5 risk heat map
│   ├── framework_intelligence.py  # Per-framework coverage analysis
│   ├── ai_workspace.py            # AI document analysis
│   ├── reports.py                 # PDF / Excel / CSV / Backup export
│   ├── audit_log.py               # Change history
│   └── settings.py                # Organisation, AI, app, backup settings
│
├── widgets/                       # Reusable UI components
│   ├── navigation.py              # Sidebar navigation
│   ├── cards.py                   # KPI and content cards
│   └── tables.py                  # Virtualised table models
│
├── docs/                          # Extended documentation
│   ├── ARCHITECTURE.md
│   ├── RELEASE_NOTES.md
│   └── ROADMAP.md
│
└── screenshots/                   # UI screenshots
```

---

## Data Privacy

All data is stored locally in `riskcore.db` (SQLite). Nothing is sent externally except optional Anthropic API calls when using AI Analysis — which requires you to explicitly configure an API key.

No telemetry. No analytics. No cloud sync. No account required.

### User Data Files

These files are created at runtime and are excluded from version control by `.gitignore`:

| File | Contents |
|---|---|
| `riskcore.db` | All risks, treatments, org settings, password hash |
| `riskcore.key` | Fernet encryption key for API key storage |
| `riskcore_apikey.txt` | AES-256 encrypted Anthropic API key |
| `riskcore.log` | Application log (Shiboken warnings suppressed here) |
| `backups/` | Timestamped database backup copies |

---

## Documentation

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, data model, module responsibilities |
| [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md) | Version history and changelog |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Planned features for v2.0 |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting and security design |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

---

## Roadmap — v2.0

- Evidence management — attach files and screenshots to risks and controls
- Live audit view with real-time coverage metrics
- Policy library with Drafted → Reviewed → Approved → Published workflow
- Multi-user support with PostgreSQL backend
- Role-based access control (Analyst / Auditor / Admin)
- Trend dashboards — risk score over time, treatment completion rate
- OS keychain for API key storage (replaces file-based encryption)
- Client portal — read-only view for external auditors

See [docs/ROADMAP.md](docs/ROADMAP.md) for full details.

---

## Licence

MIT Licence — see [LICENSE](LICENSE) for details.

---

## Author

**Michael Waugh** — Product Owner, GRC Analyst  
Engineered with Claude AI

> *"Every GRC platform is built for the compliance team. RiskCore is built for the analyst."*
