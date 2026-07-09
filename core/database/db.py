"""
core/database/db.py
───────────────────
Single import point for all backend database functions.

This module imports from riskcore_phase2.py (the stable production backend)
and re-exports every function the UI needs. The UI layer must ONLY import
from here — never directly from riskcore_phase2.py.

This indirection means if a function is ever refactored or renamed in the
backend, only this file changes; no UI module needs updating.

The backend is not modified. It is consumed exactly as it exists.
"""

import sys
import os

# Locate riskcore_phase2.py — expected to be one directory above RiskCoreQt/
# Backend files (riskcore_phase2.py, riskcore_ai.py) live in the
# project root (same directory as main.py).
# When main.py runs it inserts ROOT into sys.path, so both files
# are already importable.  The guard below handles the case where
# core/database/db.py is imported before main.py has run
# (e.g. during testing).
_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Import and re-export all stable backend functions ────────────────────────
from riskcore_phase2 import (
    # Initialisation
    init_db,

    # Direct DB connection (used by pages that run custom queries)
    get_db,

    # Helpers
    today,
    now_str,
    days_until,
    sanitise,
    validate_date,
    score_color,
    score_label,
    score_bg,

    # Path constants
    BASE_DIR,
    DB_PATH,

    # Settings
    load_settings,
    save_settings,

    # API key
    load_api_key,
    save_api_key,

    # Risk CRUD
    get_risks,
    get_risk,
    insert_risk,
    update_risk,
    delete_risk,

    # Stats
    get_stats,
    get_owners,

    # Framework Intelligence
    get_framework_mapping,
    get_framework_coverage_summary,
    FRAMEWORK_CROSSWALK,

    # Organisation Scope
    get_organisation_scope,
    save_organisation_scope,
    ASSET_TYPES,
    ORG_SIZES,
    ASSESSMENT_TYPES,
    SCOPE_FRAMEWORKS,

    # Treatment CRUD
    insert_treatment,
    update_treatment,
    delete_treatment,
    get_treatments,
    get_treatment,
    get_pipeline_treatments,

    # Audit
    audit,

    # Backup
    backup_database,
    restore_database,

    # Constants
    CATEGORIES,
    RISK_STATUS,
    NIST_FUNCTIONS,
    NIST_CATEGORIES,
    NIST_COLORS,
    ISO_DOMAINS,
    CIA_COMPONENTS,
    MITRE_TACTICS,
    CIS_CONTROLS,
    LIKELIHOOD_LBL,
    IMPACT_LBL,
    TREATMENT_STRATEGIES,
    TREATMENT_STATUS,
    TREAT_COLORS,
    TREAT_STATUS_COLORS,
)

__all__ = [
    "init_db", "get_db",
    "today", "now_str", "days_until", "sanitise",
    "validate_date", "score_color", "score_label", "score_bg",
    "BASE_DIR", "DB_PATH",
    "load_settings", "save_settings",
    "load_api_key", "save_api_key",
    "get_risks", "get_risk", "insert_risk", "update_risk", "delete_risk",
    "get_stats", "get_owners",
    "get_framework_mapping", "get_framework_coverage_summary",
    "FRAMEWORK_CROSSWALK",
    "get_organisation_scope", "save_organisation_scope",
    "ASSET_TYPES", "ORG_SIZES", "ASSESSMENT_TYPES", "SCOPE_FRAMEWORKS",
    "insert_treatment", "update_treatment", "delete_treatment",
    "get_treatments", "get_treatment", "get_pipeline_treatments",
    "audit", "backup_database", "restore_database",
    "CATEGORIES", "RISK_STATUS", "NIST_FUNCTIONS", "NIST_CATEGORIES",
    "NIST_COLORS", "ISO_DOMAINS", "CIA_COMPONENTS", "MITRE_TACTICS",
    "CIS_CONTROLS", "LIKELIHOOD_LBL", "IMPACT_LBL",
    "TREATMENT_STRATEGIES", "TREATMENT_STATUS",
    "TREAT_COLORS", "TREAT_STATUS_COLORS",
]
