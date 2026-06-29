# RiskCore GRC Platform v1.0

## Overview

RiskCore is a desktop Governance, Risk, and Compliance (GRC) application designed to help organizations identify, assess, track, and report cybersecurity risks using industry-recognized frameworks.

The platform combines manual risk management with AI-assisted document analysis and provides reporting aligned to:

* NIST Cybersecurity Framework (CSF)
* ISO/IEC 27001:2022
* MITRE ATT&CK
* CIS Controls v8
* CIA Triad

---

## Key Features

### Risk Management

* Create and manage cybersecurity risks
* Edit and update existing risks
* Delete risks with audit logging
* Risk ownership and status tracking
* Residual risk scoring

### Risk Assessment

* NIST SP 800-30 based scoring model
* Likelihood × Impact methodology
* Automatic severity classification:

  * Low
  * Medium
  * High
  * Critical

### Framework Mapping

* NIST CSF Functions
* ISO 27001:2022 controls
* MITRE ATT&CK tactics and techniques
* CIS Controls v8
* CIA Triad impact classification

### Dashboard & Analytics

* Risk summary dashboard
* Severity metrics
* Open risk tracking
* Framework distribution statistics

### Risk Matrix

* Interactive 5×5 likelihood/impact heatmap
* Visual risk distribution
* Cell-based risk review

### Audit Logging

* Immutable audit trail
* Create, update, delete, export, and system events recorded

### Reporting

* Professional PDF report generation
* Executive Summary
* Risk Overview
* Risk Matrix
* Detailed Risk Profiles
* Recommendations
* Methodology Appendix

### AI Risk Analysis

* Claude API integration
* PDF document analysis
* AI-generated risk identification
* Risk approval workflow before adding to the register

---

## Technology Stack

* Python
* CustomTkinter
* SQLite
* ReportLab
* Anthropic Claude API
* PyInstaller

---

## Security Features

* Local SQLite database
* Encrypted API key storage
* Audit logging
* Local-first architecture
* No cloud dependency for risk management functions

---

## Intended Use

RiskCore is intended for:

* Cybersecurity Analysts
* GRC Analysts
* Risk Managers
* Compliance Teams
* Security Consultants
* Students and cybersecurity portfolios

---

## Author

Michael Waugh

RiskCore GRC Platform v1.0

Built as a cybersecurity governance, risk, and compliance project demonstrating practical implementation of risk management concepts, framework mapping, reporting, and auditability.
