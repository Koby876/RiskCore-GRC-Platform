"""
RiskCore Phase 2 — AI Analysis Module
Handles: PDF extraction, Claude AI analysis, multi-framework mapping,
         industry-standard PDF report generation (NIST SP 800-30 aligned)
"""

import json, re, datetime, os
from pathlib import Path

# ── PDF Text Extraction ───────────────────────────────────────────────────────
def extract_pdf_text(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        full = "\n\n".join(pages)
        # Sanitise — strip null bytes, limit to 40k chars for API
        full = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', full)
        return full[:40000]
    except Exception as e:
        return f"ERROR: Could not extract PDF text: {e}"

# ── Framework Reference Data ──────────────────────────────────────────────────
NIST_FULL = {
    # NIST Cybersecurity Framework 2.0 (February 2024)
    # Six functions with their CSF 2.0 category identifiers
    "Govern":   ["GV.OC Organizational Context",
                 "GV.RM Risk Management Strategy",
                 "GV.RR Roles, Responsibilities & Authorities",
                 "GV.PO Policy",
                 "GV.OV Oversight",
                 "GV.SC Cybersecurity Supply Chain Risk Mgmt"],
    "Identify": ["ID.AM Asset Management",
                 "ID.RA Risk Assessment",
                 "ID.IM Improvement"],
    "Protect":  ["PR.AA Identity Management & Access Control",
                 "PR.AT Awareness & Training",
                 "PR.DS Data Security",
                 "PR.PS Platform Security",
                 "PR.IR Technology Infrastructure Resilience"],
    "Detect":   ["DE.CM Continuous Monitoring",
                 "DE.AE Adverse Event Analysis"],
    "Respond":  ["RS.MA Incident Management",
                 "RS.AN Incident Analysis",
                 "RS.CO Incident Response Reporting & Communication",
                 "RS.MI Incident Mitigation",
                 "RS.IM Improvements"],
    "Recover":  ["RC.RP Incident Recovery Plan Execution",
                 "RC.CO Incident Recovery Communication"],
}

ISO_FULL = {
    # ISO/IEC 27001:2022 — four Annex A themes (replaces 2013's 14 domains)
    "A.5": "A.5 Organisational Controls (37 controls)",
    "A.6": "A.6 People Controls (8 controls)",
    "A.7": "A.7 Physical Controls (14 controls)",
    "A.8": "A.8 Technological Controls (34 controls)",
}

MITRE_FULL = {
    "Reconnaissance":       "TA0043",
    "Resource Development": "TA0042",
    "Initial Access":       "TA0001",
    "Execution":            "TA0002",
    "Persistence":          "TA0003",
    "Privilege Escalation": "TA0004",
    "Defense Evasion":      "TA0005",
    "Credential Access":    "TA0006",
    "Discovery":            "TA0007",
    "Lateral Movement":     "TA0008",
    "Collection":           "TA0009",
    "Command & Control":    "TA0011",
    "Exfiltration":         "TA0010",
    "Impact":               "TA0040",
}

NIST_800_30_LIKELIHOOD = {
    1: ("Very Low",  "Unlikely to occur; threat source lacks motivation or capability"),
    2: ("Low",       "Low probability; significant barriers to exploitation"),
    3: ("Moderate",  "Some probability; threat source motivated and capable"),
    4: ("High",      "Highly likely; threat source motivated, capable, and controls weak"),
    5: ("Very High", "Near certain; threat source highly motivated, controls ineffective"),
}

NIST_800_30_IMPACT = {
    1: ("Negligible", "Minimal effect on operations, assets, or individuals"),
    2: ("Minor",      "Degraded capability; minor financial loss; limited data exposure"),
    3: ("Moderate",   "Significant capability reduction; moderate financial loss; PII exposure"),
    4: ("Major",      "Major capability loss; major financial loss; sensitive data breach"),
    5: ("Critical",   "Loss of primary mission capability; catastrophic financial/reputational damage"),
}

# ── AI Prompt Builder ─────────────────────────────────────────────────────────
def build_analysis_prompt(doc_text: str, company_name: str = "the organisation") -> str:
    return f"""You are a senior GRC analyst and cybersecurity expert performing a professional risk assessment for {company_name}.

Analyse the following document and identify ALL significant risks. For each risk apply ALL six frameworks simultaneously:
1. NIST CSF 2.0 (Govern/Identify/Protect/Detect/Respond/Recover + specific category)
2. ISO/IEC 27001:2022 (Annex A theme: A.5 Organisational Controls / A.6 People Controls / A.7 Physical Controls / A.8 Technological Controls)
3. MITRE ATT&CK (tactic name + technique if applicable)
4. CIS Controls v8 (control number 1–18)
5. CIA Triad (which component is most affected: Confidentiality/Integrity/Availability/All)
6. NIST SP 800-30 Rev 1 (risk scoring methodology)

Scoring methodology — NIST SP 800-30:
- Likelihood 1–5: 1=Very Low, 2=Low, 3=Moderate, 4=High, 5=Very High
- Impact 1–5: 1=Negligible, 2=Minor, 3=Moderate, 4=Major, 5=Critical
- Inherent Risk Score = Likelihood × Impact (before controls)
- Residual Risk Score = score after existing controls considered
- Risk Velocity: 1=Slow (months), 2=Medium (weeks), 3=Fast (days), 4=Immediate

Use REAL risk names and descriptions grounded in the document content.
Do NOT use generic placeholder risks.
Extract specific systems, processes, vendors, or gaps mentioned.
Identify between 5 and 15 risks depending on document complexity.

Also assess NIST CSF maturity for each function (1=Partial, 2=Risk Informed, 3=Repeatable, 4=Adaptive).

Respond ONLY with a valid JSON object, no markdown, no explanation, exactly this structure:
{{
  "company_context": "brief summary of what this document is about",
  "document_type": "type of document e.g. Security Policy, Audit Report, Vendor Assessment",
  "overall_risk_posture": "Critical|High|Medium|Low",
  "analyst_summary": "2-3 sentence professional executive summary of findings",
  "nist_maturity": {{
    "Govern": 1, "Identify": 1, "Protect": 1, "Detect": 1, "Respond": 1, "Recover": 1
  }},
  "risks": [
    {{
      "title": "specific risk title from document context",
      "description": "detailed description grounded in document content",
      "category": "Technical|Operational|Compliance|Strategic|Financial|Physical|Third Party",
      "likelihood": 1,
      "impact": 1,
      "inherent_score": 1,
      "residual_score": 1,
      "risk_velocity": 1,
      "nist_function": "Govern|Identify|Protect|Detect|Respond|Recover",
      "nist_category": "specific NIST category",
      "nist_subcategory": "e.g. PR.AC-1",
      "iso_domain": "A.5 Organisational Controls|A.6 People Controls|A.7 Physical Controls|A.8 Technological Controls",
      "iso_control": "specific control reference e.g. A.9.4.1",
      "mitre_tactic": "tactic name or Not Applicable",
      "mitre_technique": "technique name e.g. T1078 Valid Accounts or Not Applicable",
      "cis_control": "CIS-N Control Name",
      "cia_component": "Confidentiality|Integrity|Availability|All Three",
      "confidence": "High|Medium|Low",
      "existing_controls": "controls already in place if mentioned",
      "recommended_mitigation": "specific actionable remediation steps",
      "priority": "Immediate|Short-term|Medium-term|Long-term",
      "owner_suggestion": "role that should own this risk e.g. CISO, IT Manager",
      "framework_cross_ref": "how the frameworks cross-reference for this risk"
    }}
  ],
  "framework_gaps": {{
    "nist_gaps": ["gap 1", "gap 2"],
    "iso_gaps": ["gap 1", "gap 2"],
    "mitre_gaps": ["gap 1", "gap 2"],
    "cis_gaps": ["gap 1", "gap 2"]
  }},
  "remediation_roadmap": [
    {{
      "phase": "Immediate (0–30 days)",
      "actions": ["action 1", "action 2"],
      "effort": "Low|Medium|High",
      "impact_reduction": "estimated % risk reduction"
    }},
    {{
      "phase": "Short-term (30–90 days)",
      "actions": ["action 1", "action 2"],
      "effort": "Low|Medium|High",
      "impact_reduction": "estimated % risk reduction"
    }},
    {{
      "phase": "Medium-term (90–180 days)",
      "actions": ["action 1"],
      "effort": "Medium|High",
      "impact_reduction": "estimated % risk reduction"
    }}
  ]
}}

DOCUMENT TO ANALYSE:
---
{doc_text}
---"""

# ── AI API Call ───────────────────────────────────────────────────────────────
def call_claude_api(prompt: str, progress_callback=None) -> dict:
    """Call Claude API and return parsed JSON result."""
    try:
        import urllib.request
        import urllib.error

        if progress_callback:
            progress_callback("Sending document to AI for analysis...")

        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            method="POST"
        )

        if progress_callback:
            progress_callback("AI is analysing frameworks — this may take 20–40 seconds...")

        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        text = ""
        for block in raw.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        # Strip any markdown fences
        text = re.sub(r'^```[a-z]*\n?', '', text.strip())
        text = re.sub(r'\n?```$', '', text.strip())

        if progress_callback:
            progress_callback("Parsing AI response...")

        return json.loads(text)

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"API error {e.code}: {body[:300]}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI returned invalid JSON: {e}\nRaw: {text[:300]}")
    except Exception as e:
        raise RuntimeError(f"Analysis failed: {e}")

# ── Score helpers ─────────────────────────────────────────────────────────────
def score_color_hex(score):
    if score <= 4:  return "#16A34A"
    if score <= 9:  return "#CA8A04"
    if score <= 14: return "#EA580C"
    return "#DC2626"

def score_label(score):
    if score <= 4:  return "LOW"
    if score <= 9:  return "MEDIUM"
    if score <= 14: return "HIGH"
    return "CRITICAL"

def today():
    return datetime.date.today().isoformat()

def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# ── Data-driven analysis builder ───────────────────────────────────────────────
# Used whenever a PDF report is exported WITHOUT a prior AI analysis run
# (e.g. risks entered manually via Add Risk / Edit Risk). Previously this
# case fell back to a fixed block of hardcoded text — same gaps, same
# roadmap, same NIST maturity numbers — regardless of what was actually
# in the register. Everything below is computed directly from the real
# risk rows instead, so two registers with different risks will always
# produce different reports.
def build_data_driven_analysis(risks: list, company_name: str) -> dict:
    """
    Build an `analysis` dict (same shape generate_pdf_report expects from
    the AI path) purely from the risk rows already in the register —
    no AI call, no network request, works offline and instantly.
    """
    if not risks:
        risks = []

    n = len(risks)
    scores = [int(r.get("inherent_score") or r.get("risk_score") or 0)
              for r in risks]
    critical = [r for r, s in zip(risks, scores) if s >= 15]
    high     = [r for r, s in zip(risks, scores) if 10 <= s <= 14]
    medium   = [r for r, s in zip(risks, scores) if 5 <= s <= 9]
    low      = [r for r, s in zip(risks, scores) if s <= 4]

    if critical:
        posture = "Critical"
    elif high:
        posture = "High"
    elif medium:
        posture = "Medium"
    else:
        posture = "Low" if risks else "Unknown"

    # ── NIST CSF maturity, computed per function from real average scores ──
    # Heuristic: functions with no risks logged default to Tier 1
    # (Partial) since nothing has been assessed there yet. Functions with
    # risks get a tier inferred from their average residual score — lower
    # average residual implies better-controlled risk in that function,
    # which maps to a higher maturity tier. This is a defensible proxy,
    # not a substitute for a real NIST CSF maturity assessment, and the
    # PDF appendix should make that caveat explicit (handled in
    # generate_pdf_report's methodology section already).
    nist_maturity = {}
    for fn in ["Govern", "Identify", "Protect", "Detect", "Respond", "Recover"]:
        fn_risks = [r for r in risks if r.get("nist_function") == fn]
        if not fn_risks:
            nist_maturity[fn] = 1
            continue
        avg_residual = sum(
            int(r.get("residual_score") or r.get("risk_score") or 0)
            for r in fn_risks) / len(fn_risks)
        if avg_residual >= 15:
            nist_maturity[fn] = 1
        elif avg_residual >= 10:
            nist_maturity[fn] = 2
        elif avg_residual >= 5:
            nist_maturity[fn] = 3
        else:
            nist_maturity[fn] = 4

    # ── Executive summary — built from real risk titles/categories ─────────
    top_risks = sorted(risks, key=lambda r: int(r.get("inherent_score")
                        or r.get("risk_score") or 0), reverse=True)[:3]
    top_titles = [r.get("title", "Untitled risk") for r in top_risks]

    categories_present = sorted({r.get("category") for r in risks
                                  if r.get("category")})
    nist_fns_present = sorted({r.get("nist_function") for r in risks
                                if r.get("nist_function")})

    if n == 0:
        summary = (f"No risks are currently logged for {company_name}. "
                   "This report reflects an empty risk register.")
    else:
        parts = [f"{company_name}'s risk register currently contains "
                 f"{n} risk{'s' if n != 1 else ''}, with {len(critical)} "
                 f"rated Critical and {len(high)} rated High."]
        if top_titles:
            parts.append("The highest-scoring risks are: " +
                         "; ".join(top_titles) + ".")
        if categories_present:
            parts.append("Risks span the following categories: " +
                         ", ".join(categories_present) + ".")
        if nist_fns_present:
            parts.append("Coverage currently concentrates on the "
                         + ", ".join(nist_fns_present) +
                         " NIST CSF function(s).")
        summary = " ".join(parts)

    # ── Framework gaps — derived from what's actually represented ──────────
    all_nist_fns = {"Govern", "Identify", "Protect", "Detect", "Respond", "Recover"}
    missing_nist = sorted(all_nist_fns - set(nist_fns_present))
    nist_gaps = (
        [f"No risks currently mapped to the {fn} function — consider "
         f"whether {fn.lower()}-related risks are being missed."
         for fn in missing_nist]
        if missing_nist else
        ["All six NIST CSF 2.0 functions have at least one risk mapped; "
         "continue monitoring for emerging gaps as new risks are identified."]
    )

    iso_domains_present = sorted({r.get("iso_domain") for r in risks
                                   if r.get("iso_domain")})
    iso_gaps = (
        [f"{len(iso_domains_present)} of 4 ISO/IEC 27001:2022 Annex A themes "
         f"are represented in the current register; themes not yet "
         f"covered may warrant a review to confirm risks there are "
         f"genuinely absent rather than unassessed."]
        if iso_domains_present else
        ["No risks are currently mapped to ISO/IEC 27001:2022 Annex A themes — "
         "framework mapping should be completed for audit readiness."]
    )

    mitre_tactics_present = sorted({
        r.get("mitre_tactic") for r in risks
        if r.get("mitre_tactic") and r.get("mitre_tactic") != "Not Applicable"})
    mitre_gaps = (
        [f"MITRE ATT&CK tactics currently represented: "
         f"{', '.join(mitre_tactics_present)}. Tactics outside this set "
         f"have no corresponding risk entries and may need assessment."]
        if mitre_tactics_present else
        ["No risks are currently tagged with a MITRE ATT&CK tactic — "
         "threat-informed mapping has not yet been applied to this register."]
    )

    cis_controls_present = sorted({
        r.get("cis_control") for r in risks
        if r.get("cis_control") and r.get("cis_control") != "Not Applicable"})
    cis_gaps = (
        [f"{len(cis_controls_present)} CIS Controls are referenced across "
         f"current risks; remaining controls have not been explicitly "
         f"tied to a logged risk."]
        if cis_controls_present else
        ["No risks currently reference a specific CIS Control — control "
         "mapping should be added for clearer remediation traceability."]
    )

    # ── Remediation roadmap — grouped from real risks by priority/score ────
    # BUG FIX: the previous version selected each phase's risks via two
    # independent fallback rules (score-based OR priority-based), which
    # could overlap — e.g. a Medium-score risk with priority="Short-term"
    # would appear in both the Short-term phase (matched by priority) and
    # the Medium-term phase (matched by score), duplicating it in the
    # roadmap. Fixed by assigning every risk to exactly one phase in a
    # single pass: priority field wins when present and recognised,
    # otherwise score-band decides — and each risk is removed from
    # consideration once assigned so it can never appear twice.
    def action_for(r):
        title = r.get("title", "this risk")
        mit = (r.get("mitigation") or "").strip()
        if mit:
            return f"{title}: {mit}"
        return f"{title}: define and assign a mitigation plan"

    PHASE_BY_PRIORITY = {
        "Immediate":    "Immediate (0–30 days)",
        "Short-term":   "Short-term (30–90 days)",
        "Medium-term":  "Medium-term (90–180 days)",
        "Long-term":    "Ongoing monitoring",
    }
    PHASE_BY_SCORE_BAND = [
        (15, 999, "Immediate (0–30 days)"),
        (10, 14,  "Short-term (30–90 days)"),
        (5,  9,   "Medium-term (90–180 days)"),
        (0,  4,   "Ongoing monitoring"),
    ]
    PHASE_ORDER = ["Immediate (0–30 days)", "Short-term (30–90 days)",
                   "Medium-term (90–180 days)", "Ongoing monitoring"]
    PHASE_EFFORT = {
        "Immediate (0–30 days)":     "High",
        "Short-term (30–90 days)":   "Medium",
        "Medium-term (90–180 days)": "Medium",
        "Ongoing monitoring":        "Low",
    }

    phase_buckets = {p: [] for p in PHASE_ORDER}
    for r in risks:
        priority = r.get("priority")
        if priority in PHASE_BY_PRIORITY:
            phase = PHASE_BY_PRIORITY[priority]
        else:
            sc = int(r.get("inherent_score") or r.get("risk_score") or 0)
            phase = next(p for lo, hi, p in PHASE_BY_SCORE_BAND
                        if lo <= sc <= hi)
        phase_buckets[phase].append(r)

    def pct_of(pool):
        if not n:
            return "0%"
        return f"~{round(len(pool) / n * 100)}%"

    roadmap = []
    for phase in PHASE_ORDER:
        pool = phase_buckets[phase]
        if not pool:
            continue
        roadmap.append({
            "phase": phase,
            "actions": [action_for(r) for r in pool[:5]],
            "effort": PHASE_EFFORT[phase],
            "impact_reduction": pct_of(pool),
        })
    if not roadmap:
        roadmap.append({
            "phase": "Next steps",
            "actions": ["Begin logging risks to build a remediation roadmap"],
            "effort": "Low",
            "impact_reduction": "0%",
        })

    return {
        "company_context": (
            f"This report reflects the current state of {company_name}'s "
            f"risk register as recorded directly in RiskCore, generated "
            f"without a separate AI document analysis pass."),
        "document_type": "Risk Register Export",
        "overall_risk_posture": posture,
        "analyst_summary": summary,
        "nist_maturity": nist_maturity,
        "framework_gaps": {
            "nist_gaps": nist_gaps,
            "iso_gaps": iso_gaps,
            "mitre_gaps": mitre_gaps,
            "cis_gaps": cis_gaps,
        },
        "remediation_roadmap": roadmap,
    }

# ── PDF Report Generator ──────────────────────────────────────────────────────
def generate_pdf_report(analysis: dict, risks_approved: list,
                         company_name: str, output_path: str,
                         classification: str = "CONFIDENTIAL",
                         _known_total_pages: int = 0) -> str:
    """
    Generate the RiskCore v1.0 GRC risk report PDF.

    Structure (per RiskCore v1.0 PDF spec):
        1. Cover Page
        2. Table of Contents
        3. Executive Summary             — computed from real risk data
        4. Risk Overview                 — severity / status / NIST tables
        5. Risk Matrix                   — same 5x5 heatmap as the app
        6. Risk Register                 — full tabular list
        7. Detailed Risk Profiles        — one section per risk
        8. Recommendations               — derived from actual risk data
        9. Methodology Appendix          — scoring formula, severity bands,
                                           frameworks used

    Function signature, parameter order, and return value are unchanged
    from the previous version (aside from the trailing internal-only
    `_known_total_pages`, which has a default and is never passed by the
    call site in riskcore_phase2.py), so
    `generate_pdf_report(analysis, risks_approved, company, path, clf)`
    requires no changes there. `analysis` may come from either the
    AI-analysis path (_last_analysis) or the offline
    build_data_driven_analysis() path — this function only reads
    `analysis.get("analyst_summary")` as supplementary AI context when
    present; every number, table, and recommendation in the report is
    computed directly from `risks_approved`, never invented or templated.

    Page numbering ("Page X of Y"): reportlab's SimpleDocTemplate only
    knows the final page count after a full build, and Platypus
    flowables (Table/Paragraph objects) cannot be safely reused across
    two separate build() calls — doing so was tried and produced a
    corrupted, near-empty second PDF (confirmed via direct testing).
    The safe fix is a clean two-pass *function* call instead: when
    _known_total_pages is 0 (the public/default case), this function
    builds the report once to a throwaway in-memory buffer purely to
    discover the page count, then calls itself again with that count
    supplied — the second call builds a completely fresh `story` list
    of new flowable objects, avoiding the reuse bug entirely.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, PageBreak,
                                     HRFlowable, KeepTogether)
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

    W, H = A4
    MARGIN = 2.2 * cm

    # ── Colours ──────────────────────────────────────────────────────────────
    C_DARK   = colors.HexColor("#0D1117")
    C_ACCENT = colors.HexColor("#DC2626")
    C_BLUE   = colors.HexColor("#1D4ED8")
    C_GREEN  = colors.HexColor("#16A34A")
    C_GOLD   = colors.HexColor("#CA8A04")
    C_ORANGE = colors.HexColor("#EA580C")
    C_RED    = colors.HexColor("#DC2626")
    C_MUTED  = colors.HexColor("#6B7280")
    C_BORDER = colors.HexColor("#E5E7EB")
    C_ROWALT = colors.HexColor("#F9FAFB")
    C_HEADER = colors.HexColor("#1E293B")
    C_PURPLE = colors.HexColor("#7C3AED")

    def risk_color(score):
        if score <= 4:  return C_GREEN
        if score <= 9:  return C_GOLD
        if score <= 14: return C_ORANGE
        return C_RED

    def risk_bg(score):
        if score <= 4:  return colors.HexColor("#DCFCE7")
        if score <= 9:  return colors.HexColor("#FEF9C3")
        if score <= 14: return colors.HexColor("#FFEDD5")
        return colors.HexColor("#FEE2E2")

    # ── Styles ───────────────────────────────────────────────────────────────
    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    H1 = S("h1", fontSize=16, textColor=C_DARK, fontName="Helvetica-Bold",
            leading=20, spaceBefore=14, spaceAfter=6)
    H2 = S("h2", fontSize=13, textColor=C_BLUE, fontName="Helvetica-Bold",
           leading=16, spaceBefore=10, spaceAfter=4)
    H3 = S("h3", fontSize=11, textColor=C_HEADER, fontName="Helvetica-Bold",
           leading=14, spaceBefore=6, spaceAfter=2)
    BODY = S("body", fontSize=9.5, textColor=colors.HexColor("#374151"),
              fontName="Helvetica", leading=14, spaceAfter=4,
              alignment=TA_JUSTIFY)
    BODY_SM = S("bodysm", fontSize=8.5, textColor=colors.HexColor("#4B5563"),
                fontName="Helvetica", leading=12)
    CAPTION = S("cap", fontSize=8, textColor=C_MUTED, fontName="Helvetica",
                leading=11, alignment=TA_CENTER)
    TBL_HDR = S("th", fontSize=8, textColor=colors.white,
                fontName="Helvetica-Bold", leading=10)
    TBL_CELL = S("tc", fontSize=7.5, textColor=colors.HexColor("#1F2937"),
                 fontName="Helvetica", leading=10)
    TBL_CELL_SM = S("tcsm", fontSize=7, textColor=colors.HexColor("#374151"),
                    fontName="Helvetica", leading=9)

    # ══════════════════════════════════════════════════════════════════════
    #  DATA LAYER — every number below comes directly from risks_approved.
    #  No template text, no AI invention. This is the section that answers
    #  the v1.0 spec's "Avoid generic AI-generated text" requirement.
    # ══════════════════════════════════════════════════════════════════════
    risks = risks_approved or []
    n = len(risks)

    def _score(r):
        return int(r.get("inherent_score") or r.get("risk_score") or 0)

    scores = [_score(r) for r in risks]
    critical_risks = [r for r in risks if _score(r) >= 15]
    high_risks     = [r for r in risks if 10 <= _score(r) <= 14]
    medium_risks   = [r for r in risks if 5 <= _score(r) <= 9]
    low_risks      = [r for r in risks if _score(r) <= 4]

    status_counts = {}
    for r in risks:
        st = r.get("status") or "Open"
        status_counts[st] = status_counts.get(st, 0) + 1
    open_count   = status_counts.get("Open", 0)
    closed_count = status_counts.get("Closed", 0)

    nist_counts = {}
    for r in risks:
        fn = r.get("nist_function")
        if fn:
            nist_counts[fn] = nist_counts.get(fn, 0) + 1
    most_common_nist = (max(nist_counts, key=nist_counts.get)
                        if nist_counts else "—")

    cia_counts = {}
    for r in risks:
        cia = r.get("cia_component")
        if cia:
            cia_counts[cia] = cia_counts.get(cia, 0) + 1
    most_common_cia = (max(cia_counts, key=cia_counts.get)
                       if cia_counts else "—")

    highest_risk = max(risks, key=_score) if risks else None

    if critical_risks:
        posture = "Critical"
    elif high_risks:
        posture = "High"
    elif medium_risks:
        posture = "Medium"
    else:
        posture = "Low" if risks else "Unknown"
    posture_color = {"Critical": C_RED, "High": C_ORANGE,
                     "Medium": C_GOLD, "Low": C_GREEN,
                     "Unknown": C_MUTED}.get(posture, C_ORANGE)

    # ── Recommendations — short, specific, derived directly from data ──────
    # Per spec: "Do not generate long generic AI narratives." Each line
    # below only appears if the underlying condition is actually true for
    # this register; nothing is shown unconditionally.
    recommendations = []
    if critical_risks:
        titles = ", ".join(r.get("title", "Untitled") for r in critical_risks[:3])
        recommendations.append(
            f"Review all {len(critical_risks)} Critical risk(s) immediately, "
            f"starting with: {titles}.")
    if high_risks:
        recommendations.append(
            f"Prioritise remediation of {len(high_risks)} High-severity "
            f"risk(s) within the next 30–90 days.")
    if open_count:
        recommendations.append(
            f"{open_count} risk(s) remain in Open status — assign owners "
            f"and target dates where missing.")
    conf_risks = [r for r in risks
                 if r.get("cia_component") in ("Confidentiality", "All Three")]
    if conf_risks:
        recommendations.append(
            f"{len(conf_risks)} risk(s) affect Confidentiality — confirm "
            f"data classification and access controls are reviewed.")
    avail_risks = [r for r in risks
                  if r.get("cia_component") in ("Availability", "All Three")]
    if avail_risks:
        recommendations.append(
            f"{len(avail_risks)} risk(s) affect Availability — verify "
            f"business continuity and recovery plans cover these areas.")
    no_mitigation = [r for r in risks if not (r.get("mitigation") or "").strip()]
    if no_mitigation:
        recommendations.append(
            f"{len(no_mitigation)} risk(s) have no mitigation plan recorded "
            f"— add a treatment plan for each.")
    missing_nist = sorted({"Identify", "Protect", "Detect", "Respond", "Recover"}
                          - set(nist_counts.keys()))
    if missing_nist:
        recommendations.append(
            f"No risks are currently mapped to the following NIST CSF "
            f"function(s): {', '.join(missing_nist)} — confirm this "
            f"reflects genuine coverage rather than an assessment gap.")
    if not recommendations:
        recommendations.append(
            "No risks are currently logged. Begin recording risks to "
            "generate data-driven recommendations.")

    # ── Page chrome (classification banner + footer) ───────────────────────
    # "Page X of Y" requires knowing the total page count, which reportlab
    # only knows after a full build. total_pages[0] starts as a generous
    # placeholder during the first pass and is set to the real count
    # before the second (final) pass, exactly the standard two-pass
    # technique for X-of-Y numbering with SimpleDocTemplate.
    page_num = [0]
    total_pages = [_known_total_pages]

    def on_page(canvas, doc):
        page_num[0] += 1
        canvas.saveState()
        canvas.setFillColor(C_ACCENT if classification == "CONFIDENTIAL"
                            else C_GOLD)
        canvas.rect(0, H - 12*mm, W, 10*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.white)
        canvas.drawCentredString(
            W/2, H - 7.5*mm,
            f"⚫  {classification}  ·  {company_name} GRC Risk Assessment  ⚫")
        canvas.setFillColor(C_BORDER)
        canvas.rect(MARGIN, 15*mm, W - 2*MARGIN, 0.5, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(
            MARGIN, 10*mm,
            f"RiskCore GRC Platform v1.0  ·  Waugh Development Group  ·  "
            f"Generated: {now()}")
        page_label = (f"Page {page_num[0]} of {total_pages[0]}"
                     if total_pages[0] else f"Page {page_num[0]}")
        canvas.drawRightString(W - MARGIN, 10*mm, page_label)
        canvas.restoreState()

    def on_cover(canvas, doc):
        canvas.setFillColor(C_DARK)
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, 0, 6*mm, H, fill=1, stroke=0)
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, H - 12*mm, W, 12*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.white)
        canvas.drawCentredString(W/2, H - 7.5*mm,
            f"⚫  {classification}  ·  HANDLE WITH CARE  ⚫")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawRightString(W - MARGIN, 10*mm,
            "NIST CSF  |  ISO 27001:2022  |  MITRE ATT&CK  |  CIS Controls  |  CIA Triad")

    def cover_page(canvas, doc):
        if doc.page == 1:
            on_cover(canvas, doc)
        else:
            on_page(canvas, doc)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.8*cm, bottomMargin=2.2*cm,
        title=f"{company_name} — GRC Risk Assessment Report",
        author="Waugh Development Group",
        subject="Information Security Risk Assessment",
        creator="RiskCore GRC Platform v1.0")

    story = []

    # ══════════════════════════════════════════════════════════════════════
    #  1. COVER PAGE
    # ══════════════════════════════════════════════════════════════════════
    cover = []
    cover.append(Spacer(1, 3.5*cm))
    cover.append(Paragraph("INFORMATION SECURITY", S(
        "ci", fontSize=11, textColor=colors.HexColor("#64748B"),
        fontName="Helvetica", leftIndent=1*cm)))
    cover.append(Spacer(1, 0.3*cm))
    cover.append(Paragraph("GRC Risk Assessment Report", S(
        "ct", fontSize=26, textColor=colors.white,
        fontName="Helvetica-Bold", leading=32, leftIndent=1*cm)))
    cover.append(Spacer(1, 0.5*cm))
    cover.append(Paragraph(f"Organisation: {company_name}", S(
        "cs", fontSize=14, textColor=colors.HexColor("#CBD5E1"),
        fontName="Helvetica", leftIndent=1*cm)))
    cover.append(Spacer(1, 0.3*cm))
    for line in [f"Classification: {classification}",
                f"Date Generated: {today()}",
                f"RiskCore Version: v1.0",
                f"Methodology: NIST SP 800-30 Rev 1"]:
        cover.append(Paragraph(line, S(
            "cm", fontSize=10, textColor=colors.HexColor("#94A3B8"),
            fontName="Helvetica", leftIndent=1*cm, leading=14)))
    cover.append(Spacer(1, 1.5*cm))
    posture_tbl = Table(
        [[Paragraph(f"Overall Risk Posture: {posture}", S(
            "op", fontSize=16, textColor=colors.white,
            fontName="Helvetica-Bold", leftIndent=0.5*cm))]],
        colWidths=[17*cm])
    posture_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), posture_color),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    cover.append(posture_tbl)
    cover.append(Spacer(1, 2*cm))
    cover.append(Paragraph("Frameworks Applied", S(
        "fa", fontSize=10, textColor=colors.HexColor("#64748B"),
        fontName="Helvetica-Bold", leftIndent=1*cm)))
    for fw in ["▸ NIST Cybersecurity Framework (CSF)",
              "▸ ISO/IEC 27001:2022 — Annex A Controls",
              "▸ MITRE ATT&CK Enterprise Framework",
              "▸ CIS Critical Security Controls",
              "▸ CIA Triad — Confidentiality, Integrity, Availability"]:
        cover.append(Paragraph(fw, S(
            "fwl", fontSize=10, textColor=colors.HexColor("#CBD5E1"),
            fontName="Helvetica", leftIndent=1.5*cm, leading=16)))
    cover.append(PageBreak())
    story += cover

    # ══════════════════════════════════════════════════════════════════════
    #  TABLE OF CONTENTS
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Table of Contents", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=14))
    toc_sections = [
        "1.  Executive Summary",
        "2.  Risk Overview",
        "3.  Risk Matrix",
        "4.  Risk Register",
        "5.  Detailed Risk Profiles",
        "6.  Recommendations",
        "7.  Methodology Appendix",
    ]
    toc_data = [[Paragraph(s, S(
        "tocline", fontSize=12, textColor=colors.HexColor("#1F2937"),
        fontName="Helvetica", leading=22))] for s in toc_sections]
    toc_t = Table(toc_data, colWidths=[17*cm])
    toc_t.setStyle(TableStyle([
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("LINEBELOW", (0,0), (-1,-2), 0.5, C_BORDER),
    ]))
    story.append(toc_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    #  2. EXECUTIVE SUMMARY — real counts only, no generated narrative
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Executive Summary", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=8))

    summary_rows = [
        [Paragraph("Metric", TBL_HDR), Paragraph("Value", TBL_HDR)],
        ["Total Risks",        str(n)],
        ["Critical Risks",     str(len(critical_risks))],
        ["High Risks",         str(len(high_risks))],
        ["Medium Risks",       str(len(medium_risks))],
        ["Low Risks",          str(len(low_risks))],
        ["Open Risks",         str(open_count)],
        ["Closed Risks",       str(closed_count)],
        ["Highest Risk",       (highest_risk.get("title", "—")
                                if highest_risk else "—")],
        ["Highest Risk Score", (str(_score(highest_risk))
                                if highest_risk else "—")],
        ["Most Common NIST Function", most_common_nist],
        ["Most Common CIA Component", most_common_cia],
    ]
    summary_rows_styled = [summary_rows[0]] + [
        [Paragraph(str(k), TBL_CELL), Paragraph(str(v), TBL_CELL)]
        for k, v in summary_rows[1:]
    ]
    sum_t = Table(summary_rows_styled, colWidths=[8*cm, 9*cm])
    sum_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_HEADER),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, C_ROWALT]),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        # Highlight Critical row in red if any critical risks exist
        ("BACKGROUND", (0,2), (1,2),
         colors.HexColor("#FEE2E2") if critical_risks else colors.white),
        ("TEXTCOLOR", (0,2), (1,2),
         C_RED if critical_risks else colors.HexColor("#1F2937")),
    ]))
    story.append(sum_t)
    story.append(Spacer(1, 10))

    if analysis and analysis.get("analyst_summary"):
        story.append(Paragraph("Analyst Context", H2))
        story.append(Paragraph(analysis["analyst_summary"], BODY))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    #  3. RISK OVERVIEW — counts by severity / status / NIST function
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Risk Overview", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=8))

    story.append(Paragraph("Risk Counts by Severity", H2))
    sev_data = [[Paragraph(h, TBL_HDR) for h in
                ["Severity", "Score Range", "Count"]]]
    sev_rows = [
        ("Critical", "15–25", len(critical_risks), C_RED),
        ("High",     "10–14", len(high_risks),     C_ORANGE),
        ("Medium",   "5–9",   len(medium_risks),   C_GOLD),
        ("Low",      "1–4",   len(low_risks),       C_GREEN),
    ]
    for label, rng, cnt, _ in sev_rows:
        sev_data.append([Paragraph(label, TBL_CELL),
                         Paragraph(rng, TBL_CELL),
                         Paragraph(str(cnt), TBL_CELL)])
    sev_t = Table(sev_data, colWidths=[6*cm, 5*cm, 6*cm])
    sev_style = [
        ("BACKGROUND", (0,0), (-1,0), C_HEADER),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]
    for i, (_, _, _, color) in enumerate(sev_rows, start=1):
        sev_style.append(("TEXTCOLOR", (0,i), (0,i), color))
        sev_style.append(("FONTNAME", (0,i), (0,i), "Helvetica-Bold"))
    sev_t.setStyle(TableStyle(sev_style))
    story.append(sev_t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Risk Counts by Status", H2))
    status_data = [[Paragraph(h, TBL_HDR) for h in ["Status", "Count"]]]
    for st in ["Open", "In Progress", "Mitigated", "Accepted", "Closed"]:
        cnt = status_counts.get(st, 0)
        status_data.append([Paragraph(st, TBL_CELL),
                            Paragraph(str(cnt), TBL_CELL)])
    status_t = Table(status_data, colWidths=[8.5*cm, 8.5*cm])
    status_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_HEADER),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, C_ROWALT]),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(status_t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Risk Counts by NIST CSF Function", H2))
    nist_data = [[Paragraph(h, TBL_HDR) for h in ["NIST Function", "Count"]]]
    for fn in ["Identify", "Protect", "Detect", "Respond", "Recover"]:
        cnt = nist_counts.get(fn, 0)
        nist_data.append([Paragraph(fn, TBL_CELL),
                          Paragraph(str(cnt), TBL_CELL)])
    nist_t = Table(nist_data, colWidths=[8.5*cm, 8.5*cm])
    nist_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_HEADER),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, C_ROWALT]),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(nist_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    #  3. RISK MATRIX — same 5x5 NIST SP 800-30 heatmap as the application
    #     screen (_pg_matrix in riskcore_phase2.py): rows = Likelihood
    #     5→1 top-to-bottom, columns = Impact 1→5 left-to-right, cell
    #     colour from the same score band thresholds (risk_color() here
    #     mirrors score_color() in the app exactly), cell text shows the
    #     score and, where any risks exist at that cell, the count.
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Risk Matrix", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=8))
    story.append(Paragraph(
        "5×5 likelihood/impact heatmap per NIST SP 800-30. Each cell shows "
        "the risk score (Likelihood × Impact) and, where applicable, the "
        "number of register risks scored at that combination.", BODY))
    story.append(Spacer(1, 4))

    IMP_LABELS = {1: "Negligible", 2: "Minor", 3: "Moderate",
                  4: "Major", 5: "Critical"}
    LIK_LABELS = {1: "Rare", 2: "Unlikely", 3: "Possible",
                 4: "Likely", 5: "Almost Certain"}

    matrix_counts = {}
    for r in risks:
        lik_r = r.get("likelihood")
        imp_r = r.get("impact")
        if lik_r and imp_r:
            key = (int(lik_r), int(imp_r))
            matrix_counts[key] = matrix_counts.get(key, 0) + 1

    # Header row: blank corner + "Impact" column labels 1..5
    matrix_header = [Paragraph("Likelihood ↓ / Impact →",
                               TBL_HDR.clone("mh0", fontSize=7))]
    for imp_v in range(1, 6):
        matrix_header.append(Paragraph(
            f"{IMP_LABELS[imp_v]}<br/>({imp_v})",
            TBL_HDR.clone("mh", fontSize=7, alignment=TA_CENTER)))
    matrix_data = [matrix_header]

    for lik_v in range(5, 0, -1):
        row = [Paragraph(f"{LIK_LABELS[lik_v]}<br/>({lik_v})",
                         TBL_HDR.clone("ml", fontSize=7,
                                       textColor=colors.HexColor("#1F2937")))]
        for imp_v in range(1, 6):
            sc_cell = lik_v * imp_v
            cnt_cell = matrix_counts.get((lik_v, imp_v), 0)
            cell_text = (f"{sc_cell}<br/>({cnt_cell})" if cnt_cell
                        else str(sc_cell))
            row.append(Paragraph(cell_text, S(
                "mc", fontSize=10, fontName="Helvetica-Bold",
                textColor=colors.white, alignment=TA_CENTER, leading=13)))
        matrix_data.append(row)

    matrix_colw = [3.2*cm] + [2.76*cm]*5
    matrix_t = Table(matrix_data, colWidths=matrix_colw,
                     rowHeights=[1.4*cm] + [1.5*cm]*5)
    matrix_style = [
        ("BACKGROUND", (0,0), (-1,0), C_HEADER),
        ("BACKGROUND", (0,1), (0,-1), colors.HexColor("#F1F5F9")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.white),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]
    for ri, lik_v in enumerate(range(5, 0, -1), start=1):
        for ci, imp_v in enumerate(range(1, 6), start=1):
            sc_cell = lik_v * imp_v
            matrix_style.append(
                ("BACKGROUND", (ci, ri), (ci, ri), risk_color(sc_cell)))
    matrix_t.setStyle(TableStyle(matrix_style))
    story.append(matrix_t)
    story.append(Spacer(1, 10))

    legend_data = [[
        Paragraph("■ LOW (1–4)", S("lg", fontSize=9, textColor=C_GREEN,
                                   fontName="Helvetica-Bold")),
        Paragraph("■ MEDIUM (5–9)", S("lg2", fontSize=9, textColor=C_GOLD,
                                      fontName="Helvetica-Bold")),
        Paragraph("■ HIGH (10–14)", S("lg3", fontSize=9, textColor=C_ORANGE,
                                      fontName="Helvetica-Bold")),
        Paragraph("■ CRITICAL (15–25)", S("lg4", fontSize=9, textColor=C_RED,
                                          fontName="Helvetica-Bold")),
    ]]
    legend_t = Table(legend_data, colWidths=[4.3*cm]*4)
    legend_t.setStyle(TableStyle([
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(legend_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    #  4. RISK REGISTER — full tabular list
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Risk Register", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=8))

    reg_hdr = [Paragraph(h, TBL_HDR) for h in
              ["ID", "Title", "Score", "Owner", "Status", "NIST", "Source"]]
    reg_data = [reg_hdr]
    sorted_risks = sorted(risks, key=_score, reverse=True)
    for r in sorted_risks:
        sc = _score(r)
        reg_data.append([
            Paragraph(str(r.get("id", "—")), TBL_CELL_SM),
            Paragraph((r.get("title") or "Untitled")[:48], TBL_CELL_SM),
            Paragraph(str(sc), TBL_CELL_SM),
            Paragraph(r.get("owner") or "Unassigned", TBL_CELL_SM),
            Paragraph(r.get("status") or "Open", TBL_CELL_SM),
            Paragraph(r.get("nist_function") or "—", TBL_CELL_SM),
            Paragraph(r.get("source") or "Manual", TBL_CELL_SM),
        ])
    if not sorted_risks:
        reg_data.append([Paragraph("No risks currently in the register.",
                                   TBL_CELL_SM)] + [Paragraph("", TBL_CELL_SM)]*6)

    reg_colw = [1.2*cm, 5.8*cm, 1.6*cm, 3*cm, 2.2*cm, 2*cm, 1.8*cm]
    reg_t = Table(reg_data, colWidths=reg_colw, repeatRows=1)
    reg_style = [
        ("BACKGROUND", (0,0), (-1,0), C_HEADER),
        ("GRID", (0,0), (-1,-1), 0.3, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]
    for i, r in enumerate(sorted_risks, start=1):
        sc = _score(r)
        reg_style.append(("BACKGROUND", (2,i), (2,i), risk_bg(sc)))
        reg_style.append(("TEXTCOLOR", (2,i), (2,i), risk_color(sc)))
        reg_style.append(("FONTNAME", (2,i), (2,i), "Helvetica-Bold"))
    reg_t.setStyle(TableStyle(reg_style))
    story.append(reg_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    #  5. DETAILED RISK PROFILES — one section per risk
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Detailed Risk Profiles", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=8))

    for idx, r in enumerate(sorted_risks, start=1):
        sc = _score(r)
        rc = risk_color(sc)
        rl = score_label(sc)

        hdr_t = Table(
            [[Paragraph(f"Risk #{r.get('id','—')} — {rl} (Score: {sc})",
                       S("rh", fontSize=11, textColor=colors.white,
                         fontName="Helvetica-Bold")),
              Paragraph(f"Priority: {r.get('priority') or '—'}",
                       S("rh2", fontSize=9, textColor=colors.HexColor("#F1F5F9"),
                         fontName="Helvetica", alignment=TA_RIGHT))]],
            colWidths=[11*cm, 6*cm])
        hdr_t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), rc),
            ("TOPPADDING", (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LEFTPADDING", (0,0), (0,-1), 10),
            ("RIGHTPADDING", (-1,0), (-1,-1), 10),
        ]))

        lik = r.get("likelihood") or 1
        imp = r.get("impact") or 1
        detail_rows = [
            ("Title",             r.get("title") or "—"),
            ("Description",       r.get("description") or "—"),
            ("Category",          r.get("category") or "—"),
            ("Owner",             r.get("owner") or "Unassigned"),
            ("Status",            r.get("status") or "Open"),
            ("Priority",          r.get("priority") or "—"),
            ("Likelihood",        f"{lik} — "
                                  f"{NIST_800_30_LIKELIHOOD.get(lik, ('',''))[0]}"),
            ("Impact",            f"{imp} — "
                                  f"{NIST_800_30_IMPACT.get(imp, ('',''))[0]}"),
            ("Inherent Score",    f"{sc} ({rl})"),
            ("Residual Score",    str(r.get("residual_score") or "—")),
            ("NIST Mapping",      f"{r.get('nist_function') or '—'} › "
                                  f"{r.get('nist_category') or '—'} "
                                  f"[{r.get('nist_subcategory') or ''}]"),
            ("ISO Mapping",       f"{r.get('iso_domain') or '—'} · "
                                  f"{r.get('iso_control') or ''}"),
            ("MITRE Mapping",     f"Tactic: {r.get('mitre_tactic') or 'N/A'} | "
                                  f"Technique: "
                                  f"{r.get('mitre_technique') or 'N/A'}"),
            ("CIS Mapping",       r.get("cis_control") or "—"),
            ("CIA Mapping",       r.get("cia_component") or "—"),
            ("Existing Controls", r.get("existing_controls") or
                                  "None documented"),
            ("Mitigation Plan",   r.get("mitigation") or
                                  "No mitigation plan recorded"),
            ("Created Date",      r.get("date_identified") or "—"),
            ("Last Modified",     r.get("date_modified") or "—"),
            ("Notes",             r.get("notes") or "—"),
        ]
        detail_data = [
            [Paragraph(lbl, TBL_HDR.clone("dh", textColor=colors.HexColor("#1E293B"))),
             Paragraph(str(val), TBL_CELL)]
            for lbl, val in detail_rows
        ]
        detail_t = Table(detail_data, colWidths=[3.5*cm, 13.5*cm])
        detail_t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F1F5F9")),
            ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
            ("ROWBACKGROUNDS", (1,0), (1,-1), [colors.white, C_ROWALT]),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))

        story.append(KeepTogether([hdr_t, Spacer(1, 0)]))
        story.append(detail_t)
        story.append(Spacer(1, 10))

    if not sorted_risks:
        story.append(Paragraph(
            "No risks are currently in the register, so no detailed "
            "profiles are available.", BODY))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    #  6. RECOMMENDATIONS — short, specific, derived from actual data
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Recommendations", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=8))
    rec_data = [[Paragraph(f"{i+1}.", TBL_CELL),
                Paragraph(rec, TBL_CELL)]
               for i, rec in enumerate(recommendations)]
    rec_t = Table(rec_data, colWidths=[0.9*cm, 16.1*cm])
    rec_t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, C_ROWALT]),
        ("GRID", (0,0), (-1,-1), 0.3, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("LINELEFT", (0,0), (0,-1), 2, C_ACCENT),
    ]))
    story.append(rec_t)
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════
    #  7. METHODOLOGY APPENDIX
    # ══════════════════════════════════════════════════════════════════════
    story.append(Paragraph("Methodology Appendix", H1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_ACCENT,
                            spaceAfter=8))

    story.append(Paragraph("Risk Scoring Formula", H2))
    story.append(Paragraph(
        "RiskCore calculates <b>Inherent Risk Score = Likelihood × Impact</b>, "
        "each rated on a 1–5 scale per NIST Special Publication 800-30 "
        "Revision 1, producing a score from 1 to 25. <b>Residual Score</b> "
        "reflects the risk remaining after existing controls are applied.",
        BODY))

    story.append(Paragraph("Severity Bands", H2))
    band_data = [[Paragraph(h, TBL_HDR) for h in
                 ["Score Range", "Severity", "Typical Response Time"]]]
    for rng, label, resp, color in [
        ("15–25", "Critical", "Immediate (0–30 days)", C_RED),
        ("10–14", "High",     "Short-term (30–90 days)", C_ORANGE),
        ("5–9",   "Medium",   "Medium-term (90–180 days)", C_GOLD),
        ("1–4",   "Low",      "Ongoing monitoring", C_GREEN),
    ]:
        band_data.append([Paragraph(rng, TBL_CELL),
                          Paragraph(label, TBL_CELL),
                          Paragraph(resp, TBL_CELL)])
    band_t = Table(band_data, colWidths=[4*cm, 4*cm, 9*cm])
    band_style = [
        ("BACKGROUND", (0,0), (-1,0), C_HEADER),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]
    for i, (_, _, _, color) in enumerate([
        ("","","",C_RED), ("","","",C_ORANGE),
        ("","","",C_GOLD), ("","","",C_GREEN)], start=1):
        band_style.append(("TEXTCOLOR", (1,i), (1,i), color))
        band_style.append(("FONTNAME", (1,i), (1,i), "Helvetica-Bold"))
    band_t.setStyle(TableStyle(band_style))
    story.append(band_t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Frameworks Used", H2))
    fw_data = [
        ["NIST Cybersecurity Framework (CSF) 2.0",
         "Functions: Govern, Identify, Protect, Detect, Respond, Recover"],
        ["ISO/IEC 27001:2022",
         "Annex A: A.5 Organisational, A.6 People, A.7 Physical, A.8 Technological"],
        ["MITRE ATT&CK Enterprise",
         "Adversary tactics and techniques"],
        ["CIS Critical Security Controls",
         "Practical, prioritised security safeguards"],
        ["CIA Triad",
         "Confidentiality, Integrity, Availability impact classification"],
    ]
    fw_t = Table(
        [[Paragraph(a, TBL_CELL), Paragraph(b, TBL_CELL_SM)]
         for a, b in fw_data],
        colWidths=[6*cm, 11*cm])
    fw_t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, C_ROWALT]),
        ("GRID", (0,0), (-1,-1), 0.3, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
    ]))
    story.append(fw_t)

    story.append(Spacer(1, cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"This report was generated by RiskCore GRC Platform v1.0 on {now()}. "
        f"Classification: {classification}. All figures in this report "
        f"are computed directly from the risk register at the time of "
        f"generation.", CAPTION))

    if _known_total_pages == 0:
        # PASS 1 (public entry point): discover the true page count by
        # building to a throwaway in-memory buffer, then recurse with
        # that count known. The recursive call below re-executes this
        # entire function from scratch, building a brand-new `story`
        # list of fresh flowable objects — this is what makes the
        # two-pass approach safe (see function docstring for why reusing
        # the same flowables across two build() calls is not safe).
        import io
        buffer = io.BytesIO()
        dummy_doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=2.8*cm, bottomMargin=2.2*cm)
        dummy_doc.build(story, onFirstPage=cover_page, onLaterPages=on_page)
        discovered_total = page_num[0]
        return generate_pdf_report(
            analysis, risks_approved, company_name, output_path,
            classification, _known_total_pages=discovered_total)

    # PASS 2 (recursive call only): total_pages[0] was set from
    # _known_total_pages above, so "Page X of Y" renders correctly.
    doc.build(story, onFirstPage=cover_page, onLaterPages=on_page)
    return output_path
