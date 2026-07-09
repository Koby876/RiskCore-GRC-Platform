"""
core/services/ai_service.py
────────────────────────────
Clean import point for all AI and intelligence services.

Imports from riskcore_ai.py (stable production AI backend) and re-exports
everything the UI needs. The UI must only import AI functions from here.
"""

import sys
import os

_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from riskcore_ai import (
    # PDF text extraction
    extract_pdf_text,

    # Prompt builder
    build_analysis_prompt,

    # Executive intelligence services
    build_executive_summary,
    format_evidence,
    format_confidence,

    # Framework Coverage Dashboard
    build_framework_coverage_report,
    FW_NAMES,

    # NIST SP 800-53 Recommendation Engine
    get_800_53_recommendations,
    get_800_53_recommendations_for_register,
    NIST_800_53_CONTROLS,

    # Data-driven analysis (no AI call)
    build_data_driven_analysis,

    # PDF generation
    generate_pdf_report,
)

__all__ = [
    "extract_pdf_text",
    "build_analysis_prompt",
    "build_executive_summary",
    "format_evidence",
    "format_confidence",
    "build_framework_coverage_report",
    "FW_NAMES",
    "get_800_53_recommendations",
    "get_800_53_recommendations_for_register",
    "NIST_800_53_CONTROLS",
    "build_data_driven_analysis",
    "generate_pdf_report",
]
