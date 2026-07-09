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
def build_analysis_prompt(doc_text: str,
                          company_name: str = "the organisation",
                          org_scope: dict = None) -> str:
    """
    Build the AI analysis prompt. When org_scope is provided (a dict
    returned by get_organisation_scope()), the prompt is enriched with
    industry, business context, critical assets, and scope information
    so the AI can tailor findings and recommendations rather than
    producing generic results. org_scope may be None (backward compat
    with any call site that doesn't pass it).
    """
    scope_context = ""
    if org_scope:
        parts = []
        if org_scope.get("industry"):
            parts.append(f"Industry: {org_scope['industry']}")
        if org_scope.get("organisation_size"):
            parts.append(f"Organisation size: {org_scope['organisation_size']}")
        if org_scope.get("business_function"):
            parts.append(f"Primary business function: "
                         f"{org_scope['business_function']}")
        if org_scope.get("assessment_name"):
            parts.append(f"Assessment: {org_scope['assessment_name']}")
        if org_scope.get("assessment_type"):
            parts.append(f"Assessment type: {org_scope['assessment_type']}")
        if org_scope.get("assessment_objective"):
            parts.append(f"Objective: {org_scope['assessment_objective']}")
        assets = org_scope.get("assets_in_scope") or []
        if assets:
            parts.append(f"Systems in scope: {', '.join(assets)}")
        units = org_scope.get("business_units") or []
        if units:
            parts.append(f"Business units: {', '.join(units)}")
        locs = org_scope.get("locations") or []
        if locs:
            parts.append(f"Locations: {', '.join(locs)}")
        if org_scope.get("critical_assets"):
            parts.append(f"Critical assets: {org_scope['critical_assets']}")
        if parts:
            scope_context = (
                "\n\nORGANISATION CONTEXT (use this to tailor findings "
                "and recommendations — a manufacturer's risks differ "
                "from a financial services firm's):\n"
                + "\n".join(f"- {p}" for p in parts)
                + "\n\nEnsure findings are specific to this organisation's "
                  "industry, size, and scope. Do not produce generic findings "
                  "that could apply to any organisation."
            )

    return f"""You are a senior GRC analyst and cybersecurity expert performing a professional risk assessment for {company_name}.{scope_context}

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

For evidence fields: quote directly from the document where possible.
If no specific text supports a finding, set evidence_text to null.
Never fabricate quotations. Only include text that genuinely appears in the document.

Respond ONLY with a valid JSON object, no markdown, no explanation, exactly this structure:
{{
  "company_context": "brief summary of what this document is about",
  "document_type": "type of document e.g. Security Policy, Audit Report, Vendor Assessment",
  "overall_risk_posture": "Critical|High|Medium|Low",
  "analyst_summary": "2-3 sentence professional executive summary of findings",
  "executive_summary": {{
    "risk_posture_explanation": "1-2 sentences explaining what the overall posture means for this organisation",
    "strongest_areas": "1-2 sentences on what the document shows is working well, or 'No clear strengths identified in this assessment.' if none",
    "weakest_areas": "1-2 sentences on the most significant gaps or vulnerabilities identified",
    "notable_observations": "1-2 sentences on anything unusual, systemic, or strategically important",
    "top_business_risks": ["risk title 1", "risk title 2", "risk title 3"],
    "immediate_priorities": ["action 1", "action 2", "action 3"],
    "strategic_recommendations": ["recommendation 1", "recommendation 2"]
  }},
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
      "confidence_reasoning": "one sentence explaining why this confidence level was assigned",
      "existing_controls": "controls already in place if mentioned",
      "recommended_mitigation": "specific actionable remediation steps",
      "priority": "Immediate|Short-term|Medium-term|Long-term",
      "owner_suggestion": "role that should own this risk e.g. CISO, IT Manager",
      "framework_cross_ref": "how the frameworks cross-reference for this risk",
      "evidence": {{
        "source_section": "section or page reference from document, or null if not determinable",
        "evidence_text": "direct quote or close paraphrase of the document text that supports this finding, or null if no specific text found",
        "reasoning": "one sentence explaining why this text/finding constitutes a risk"
      }}
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

# ── Executive Intelligence Services ──────────────────────────────────────────
# These functions structure and validate data returned by the AI analysis
# into reusable objects consumed by the UI, PDF, and future exports.
# They contain no AI calls and produce no fabricated content — they only
# organise, validate, and surface what the AI actually returned.

def build_executive_summary(analysis: dict, risks: list,
                             org_scope: dict = None) -> dict:
    """
    Build a validated Executive Summary object from the AI analysis result.

    Returns a dict with the following keys (all safe to display directly):
        posture         — "Critical"|"High"|"Medium"|"Low"|"Unknown"
        posture_explanation — one-line plain-text explanation
        summary         — analyst_summary from AI (2-3 sentences)
        strongest_areas — what is working well
        weakest_areas   — main gaps
        notable_observations — strategic or unusual findings
        top_business_risks   — list of risk title strings
        immediate_priorities — list of action strings
        strategic_recommendations — list of recommendation strings
        risk_counts     — dict of score-band counts
        confidence_dist — distribution of High/Medium/Low confidence findings
        avg_score       — average inherent score (float)
        frameworks_mapped — count of risks with at least one Confirmed mapping
        evidence_count  — how many risks have evidence text

    If the AI did not return an executive_summary block (e.g. older-format
    result or pre-v1.5 response), falls back gracefully to what's available.
    """
    es = analysis.get("executive_summary") or {}
    posture = (analysis.get("overall_risk_posture") or "Unknown").strip()
    posture_map = {
        "Critical": "The organisation faces critical-level cyber risk "
                    "requiring immediate executive attention and intervention.",
        "High":     "The organisation faces high-level cyber risk. "
                    "Several significant vulnerabilities require prompt action.",
        "Medium":   "The organisation faces moderate cyber risk. "
                    "Key controls exist but material gaps remain.",
        "Low":      "The organisation's current cyber risk posture is low. "
                    "Continue monitoring and maintain existing controls.",
        "Unknown":  "Risk posture could not be determined from available data.",
    }
    posture_explanation = (
        es.get("risk_posture_explanation")
        or posture_map.get(posture, posture_map["Unknown"])
    )

    # Risk counts directly from the risk list — never from AI text
    def _sc(r):
        return int(r.get("inherent_score") or
                   r.get("risk_score") or
                   (r.get("likelihood", 1) * r.get("impact", 1)) or 0)

    risk_counts = {
        "critical": sum(1 for r in risks if _sc(r) >= 15),
        "high":     sum(1 for r in risks if 10 <= _sc(r) <= 14),
        "medium":   sum(1 for r in risks if 5 <= _sc(r) <= 9),
        "low":      sum(1 for r in risks if _sc(r) <= 4),
        "total":    len(risks),
    }

    conf_dist = {"High": 0, "Medium": 0, "Low": 0, "Unknown": 0}
    evidence_count = 0
    scores = []
    for r in risks:
        c = r.get("confidence") or "Unknown"
        conf_dist[c if c in conf_dist else "Unknown"] += 1
        scores.append(_sc(r))
        ev = r.get("evidence") or {}
        if ev.get("evidence_text"):
            evidence_count += 1

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    # Framework coverage count (how many risks have at least one confirmed fw)
    frameworks_mapped = 0
    for r in risks:
        nist = r.get("nist_function") or ""
        iso  = r.get("iso_domain") or ""
        if nist and nist not in ("", "Not Applicable"):
            frameworks_mapped += 1
            continue
        if iso and iso not in ("", "Not Applicable"):
            frameworks_mapped += 1

    def _safe_list(key, fallback=None):
        val = es.get(key)
        if isinstance(val, list):
            return [str(v) for v in val if v]
        return fallback or []

    def _safe_str(key, fallback="Not available."):
        val = es.get(key)
        return str(val).strip() if val and str(val).strip() else fallback

    return {
        "posture":                  posture,
        "posture_explanation":      posture_explanation,
        "summary":                  analysis.get("analyst_summary") or "",
        "strongest_areas":          _safe_str("strongest_areas",
                                               "Not assessed in this document."),
        "weakest_areas":            _safe_str("weakest_areas",
                                               "Not assessed in this document."),
        "notable_observations":     _safe_str("notable_observations",
                                               "No notable observations recorded."),
        "top_business_risks":       _safe_list("top_business_risks"),
        "immediate_priorities":     _safe_list("immediate_priorities"),
        "strategic_recommendations":_safe_list("strategic_recommendations"),
        "risk_counts":              risk_counts,
        "confidence_dist":          conf_dist,
        "avg_score":                avg_score,
        "frameworks_mapped":        frameworks_mapped,
        "evidence_count":           evidence_count,
        "org_scope":                org_scope,
    }

def format_evidence(risk: dict) -> dict:
    """
    Extract and validate the evidence block for a single risk finding.
    Returns a plain dict safe to display in the UI or PDF.

    Never fabricates content — if the AI did not return an evidence block
    or evidence_text is null/missing, returns a safe fallback rather than
    inventing supporting text.
    """
    ev = risk.get("evidence")
    if not ev or not isinstance(ev, dict):
        return {
            "source_section":  None,
            "evidence_text":   None,
            "reasoning":       risk.get("description") or "",
            "has_evidence":    False,
            "display_text":    "No supporting evidence could be extracted.",
        }
    ev_text = ev.get("evidence_text")
    reasoning = (ev.get("reasoning") or
                 risk.get("description") or "")
    has_ev = bool(ev_text and str(ev_text).strip()
                  and str(ev_text).strip().lower() != "null")
    return {
        "source_section": ev.get("source_section") or None,
        "evidence_text":  ev_text if has_ev else None,
        "reasoning":      reasoning,
        "has_evidence":   has_ev,
        "display_text":   (str(ev_text).strip() if has_ev
                           else "No supporting evidence could be extracted."),
    }

def format_confidence(risk: dict) -> dict:
    """
    Extract and validate confidence level and reasoning for a finding.
    Returns a dict with 'level' and 'reasoning' safe for display.
    Falls back to 'Unknown' rather than fabricating a confidence level.
    """
    raw = (risk.get("confidence") or "").strip()
    valid = {"High", "Medium", "Low"}
    level = raw if raw in valid else "Unknown"
    reasoning = (risk.get("confidence_reasoning") or "").strip()
    if not reasoning:
        fallbacks = {
            "High":    "Evidence clearly identified in the source document.",
            "Medium":  "Partially supported by document content.",
            "Low":     "Inferred from limited document evidence.",
            "Unknown": "Confidence level not determinable from available data.",
        }
        reasoning = fallbacks.get(level, fallbacks["Unknown"])
    return {"level": level, "reasoning": reasoning}

# ── Framework Coverage Dashboard ─────────────────────────────────────────────
# Builds a reusable, self-contained coverage data object from a list of
# risks (dicts or sqlite3.Row objects). All calculations are done here
# so the UI, PDF, and future PowerPoint export consume identical data
# without duplicating any logic.

FW_NAMES = [
    "NIST CSF 2.0",
    "ISO/IEC 27001:2022",
    "MITRE ATT&CK",
    "CIS Controls v8",
    "CIA Triad",
]

# Maps each framework to the risk-dict key that carries its primary value,
# and the sentinel values that mean "not really mapped."
_FW_KEY_MAP = {
    "NIST CSF 2.0":       "nist_function",
    "ISO/IEC 27001:2022": "iso_domain",
    "MITRE ATT&CK":       "mitre_tactic",
    "CIS Controls v8":    "cis_control",
    "CIA Triad":          "cia_component",
}
_UNMAPPED_SENTINELS = {"", "Not Applicable", "N/A", None}

def _is_mapped(risk, fw_key):
    val = risk.get(fw_key)
    return val not in _UNMAPPED_SENTINELS

def build_framework_coverage_report(risks: list,
                                     analysis: dict = None) -> dict:
    """
    Build the complete Framework Coverage data object for an assessment.

    Parameters
    ----------
    risks    : list of risk dicts (from risks_approved or get_risks())
    analysis : optional AI analysis dict (for posture and confidence data)

    Returns a single dict with keys:
        summary_cards    — 6 KPI values for the top card row
        per_framework    — per-framework confirmed/unmapped/pct/findings
        chart_data       — pre-computed chart datasets (reusable by any renderer)
        health_insights  — highest/lowest coverage, most used, gaps
        posture          — overall posture string
        total            — total risk count

    All values are computed directly from `risks`. No AI call is made.
    No values are fabricated.
    """
    n = len(risks)
    analysis = analysis or {}

    # ── Per-framework mapping status ──────────────────────────────────────
    fw_confirmed = {fw: 0 for fw in FW_NAMES}
    fw_unmapped  = {fw: 0 for fw in FW_NAMES}
    fw_findings  = {fw: [] for fw in FW_NAMES}   # risk titles

    for r in risks:
        title = r.get("title", "Untitled")
        for fw in FW_NAMES:
            key = _FW_KEY_MAP[fw]
            if _is_mapped(r, key):
                fw_confirmed[fw] += 1
                fw_findings[fw].append(title)
            else:
                fw_unmapped[fw] += 1

    per_framework = {}
    for fw in FW_NAMES:
        pct = round(fw_confirmed[fw] / n * 100, 1) if n else 0.0
        per_framework[fw] = {
            "confirmed":  fw_confirmed[fw],
            "unmapped":   fw_unmapped[fw],
            "total":      n,
            "coverage_pct": pct,
            "findings":   fw_findings[fw],
        }

    # ── Summary card values ───────────────────────────────────────────────
    total_confirmed = sum(fw_confirmed.values())
    total_unmapped  = sum(fw_unmapped.values())
    total_mappings  = len(FW_NAMES) * n   # maximum possible

    # Average confidence from AI results
    conf_vals = []
    for r in risks:
        c = (r.get("confidence") or "").strip()
        if c == "High":    conf_vals.append(3)
        elif c == "Medium":conf_vals.append(2)
        elif c == "Low":   conf_vals.append(1)
    if conf_vals:
        avg_conf_num = sum(conf_vals) / len(conf_vals)
        avg_conf = ("High" if avg_conf_num >= 2.5 else
                    "Medium" if avg_conf_num >= 1.5 else "Low")
    else:
        avg_conf = "Unknown"

    overall_pct = (round(total_confirmed / total_mappings * 100, 1)
                   if total_mappings else 0.0)

    posture = (analysis.get("overall_risk_posture")
               or _derive_posture(risks))

    summary_cards = {
        "total_findings":        n,
        "confirmed_mappings":    total_confirmed,
        "unmapped_findings":     total_unmapped,
        "avg_confidence":        avg_conf,
        "overall_coverage_pct":  overall_pct,
        "risk_posture":          posture,
    }

    # ── Chart data (reusable by UI, PDF, PowerPoint) ─────────────────────
    # Score distribution
    def _sc(r):
        return int(r.get("inherent_score") or
                   r.get("risk_score") or
                   (r.get("likelihood",1)*r.get("impact",1)) or 0)

    score_bands = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    for r in risks:
        s = _sc(r)
        if s >= 15:         score_bands["Critical"] += 1
        elif s >= 10:       score_bands["High"]     += 1
        elif s >= 5:        score_bands["Medium"]   += 1
        else:               score_bands["Low"]      += 1

    # NIST function distribution
    nist_dist = {}
    for r in risks:
        fn = r.get("nist_function") or "Unmapped"
        nist_dist[fn] = nist_dist.get(fn, 0) + 1

    # Confidence distribution
    conf_dist = {"High": 0, "Medium": 0, "Low": 0, "Unknown": 0}
    for r in risks:
        c = (r.get("confidence") or "Unknown").strip()
        if c not in conf_dist:
            c = "Unknown"
        conf_dist[c] += 1

    # Framework coverage bar chart data
    fw_coverage_bars = [
        {"framework": fw,
         "pct": per_framework[fw]["coverage_pct"],
         "confirmed": per_framework[fw]["confirmed"],
         "unmapped":  per_framework[fw]["unmapped"]}
        for fw in FW_NAMES
    ]

    # Mapping status pie
    mapping_status = {
        "Confirmed": total_confirmed,
        "Unmapped":  total_unmapped,
    }

    chart_data = {
        "risk_distribution":      score_bands,
        "framework_coverage_bars":fw_coverage_bars,
        "confidence_distribution":conf_dist,
        "nist_function_dist":     nist_dist,
        "mapping_status":         mapping_status,
    }

    # ── Health insights ───────────────────────────────────────────────────
    if n:
        highest_fw = max(FW_NAMES, key=lambda fw:
                         per_framework[fw]["coverage_pct"])
        lowest_fw  = min(FW_NAMES, key=lambda fw:
                         per_framework[fw]["coverage_pct"])
        most_used_fw = max(FW_NAMES, key=lambda fw:
                           per_framework[fw]["confirmed"])
        most_unmapped_fw = max(FW_NAMES, key=lambda fw:
                               per_framework[fw]["unmapped"])
        needs_review = [fw for fw in FW_NAMES
                        if per_framework[fw]["coverage_pct"] < 50.0]
    else:
        highest_fw  = "—"
        lowest_fw   = "—"
        most_used_fw = "—"
        most_unmapped_fw = "—"
        needs_review = []

    health_insights = {
        "highest_coverage_framework": highest_fw,
        "lowest_coverage_framework":  lowest_fw,
        "most_frequently_used":       most_used_fw,
        "most_frequently_unmapped":   most_unmapped_fw,
        "frameworks_needing_review":  needs_review,
    }

    return {
        "summary_cards":    summary_cards,
        "per_framework":    per_framework,
        "chart_data":       chart_data,
        "health_insights":  health_insights,
        "posture":          posture,
        "total":            n,
    }

def _derive_posture(risks: list) -> str:
    """Derive overall posture from risk scores when no AI analysis available."""
    def _sc(r):
        return int(r.get("inherent_score") or r.get("risk_score") or 0)
    if any(_sc(r) >= 15 for r in risks):  return "Critical"
    if any(_sc(r) >= 10 for r in risks):  return "High"
    if any(_sc(r) >= 5  for r in risks):  return "Medium"
    if risks:                              return "Low"
    return "Unknown"

# ── NIST SP 800-53 Rev 5 Recommendation Engine ───────────────────────────────
#
# ARCHITECTURE NOTES
# ──────────────────
# This engine provides advisory NIST SP 800-53 Rev 5 control recommendations
# based on risk attributes. The mapping data is curated from the NIST SP
# 800-53 Rev 5 control catalogue (csrc.nist.gov/publications/detail/sp/
# 800-53/rev-5/final) and is explicitly documented as curated rather than
# exhaustive. The engine is designed so the mapping tables can be replaced
# with a full authoritative dataset (e.g. the NIST SP 800-53 Rev 5 JSON
# from the NIST NVD) without changing the public interface.
#
# EXTENSIBILITY HOOKS
# ───────────────────
# The _RECOMMEND_BY_* dicts are indexed by values already present in
# risk records (NIST CSF function, MITRE tactic, risk category, CIS
# control prefix). Adding support for a new framework (COBIT, HIPAA, PCI)
# means adding an additional dict and a lookup step in
# get_800_53_recommendations() — no restructuring required.
#
# CONFIDENCE TIERS
# ────────────────
# Confirmed   — the mapping is directly cited in NIST SP 800-53 Rev 5
#               control statements, or in NIST's own CSF↔800-53 mapping
#               document (SP 800-53B / SP 800-53A).
# Recommended — the relationship is strongly implied by the control
#               description but is not explicitly tabulated in a NIST
#               crosswalk document.
# Unavailable — no defensible recommendation can be made for this
#               combination without a sourced crosswalk dataset.

# Control metadata — exactly as they appear in NIST SP 800-53 Rev 5.
# Only controls that can be clearly justified are included.
NIST_800_53_CONTROLS = {
    # Access Control family
    "AC-1":  ("Access Control Policy and Procedures",          "AC"),
    "AC-2":  ("Account Management",                            "AC"),
    "AC-3":  ("Access Enforcement",                            "AC"),
    "AC-5":  ("Separation of Duties",                          "AC"),
    "AC-6":  ("Least Privilege",                               "AC"),
    "AC-17": ("Remote Access",                                 "AC"),
    # Awareness and Training
    "AT-1":  ("Policy and Procedures",                         "AT"),
    "AT-2":  ("Literacy Training and Awareness",               "AT"),
    "AT-3":  ("Role-Based Training",                           "AT"),
    # Audit and Accountability
    "AU-2":  ("Event Logging",                                 "AU"),
    "AU-6":  ("Audit Record Review, Analysis, and Reporting",  "AU"),
    "AU-9":  ("Protection of Audit Information",               "AU"),
    "AU-12": ("Audit Record Generation",                       "AU"),
    # Configuration Management
    "CM-2":  ("Baseline Configuration",                        "CM"),
    "CM-6":  ("Configuration Settings",                        "CM"),
    "CM-7":  ("Least Functionality",                           "CM"),
    "CM-8":  ("System Component Inventory",                    "CM"),
    # Contingency Planning
    "CP-2":  ("Contingency Plan",                              "CP"),
    "CP-9":  ("System Backup",                                 "CP"),
    "CP-10": ("System Recovery and Reconstitution",            "CP"),
    # Identification and Authentication
    "IA-2":  ("Identification and Authentication (Org Users)", "IA"),
    "IA-4":  ("Identifier Management",                         "IA"),
    "IA-5":  ("Authenticator Management",                      "IA"),
    "IA-8":  ("Identification and Authentication (Non-Org)",   "IA"),
    # Incident Response
    "IR-1":  ("Incident Response Policy and Procedures",       "IR"),
    "IR-4":  ("Incident Handling",                             "IR"),
    "IR-5":  ("Incident Monitoring",                           "IR"),
    "IR-6":  ("Incident Reporting",                            "IR"),
    # Maintenance
    "MA-2":  ("Controlled Maintenance",                        "MA"),
    "MA-5":  ("Maintenance Personnel",                         "MA"),
    # Media Protection
    "MP-2":  ("Media Access",                                  "MP"),
    "MP-6":  ("Media Sanitization",                            "MP"),
    # Physical and Environmental Protection
    "PE-2":  ("Physical Access Authorizations",                "PE"),
    "PE-3":  ("Physical Access Control",                       "PE"),
    "PE-6":  ("Monitoring Physical Access",                    "PE"),
    # Planning
    "PL-2":  ("System Security and Privacy Plans",             "PL"),
    # Program Management
    "PM-9":  ("Risk Management Strategy",                      "PM"),
    "PM-28": ("Risk Framing",                                  "PM"),
    # Personnel Security
    "PS-3":  ("Personnel Screening",                           "PS"),
    "PS-6":  ("Access Agreements",                             "PS"),
    # Risk Assessment
    "RA-3":  ("Risk Assessment",                               "RA"),
    "RA-5":  ("Vulnerability Monitoring and Scanning",         "RA"),
    "RA-7":  ("Risk Response",                                 "RA"),
    # System and Services Acquisition
    "SA-8":  ("Security and Privacy Engineering Principles",   "SA"),
    "SA-9":  ("External System Services",                      "SA"),
    # System and Communications Protection
    "SC-5":  ("Denial-of-Service Protection",                  "SC"),
    "SC-7":  ("Boundary Protection",                           "SC"),
    "SC-8":  ("Transmission Confidentiality and Integrity",    "SC"),
    "SC-28": ("Protection of Information at Rest",             "SC"),
    # System and Information Integrity
    "SI-2":  ("Flaw Remediation",                              "SI"),
    "SI-3":  ("Malicious Code Protection",                     "SI"),
    "SI-4":  ("System Monitoring",                             "SI"),
    "SI-7":  ("Software, Firmware, and Information Integrity", "SI"),
    "SI-10": ("Information Input Validation",                  "SI"),
    # Supply Chain Risk Management
    "SR-3":  ("Supply Chain Controls and Processes",           "SR"),
    "SR-5":  ("Acquisition Strategies and Tools",              "SR"),
    # Governance
    "CA-2":  ("Control Assessments",                           "CA"),
    "CA-5":  ("Plan of Action and Milestones",                 "CA"),
    "CA-7":  ("Continuous Monitoring",                         "CA"),
}

# Primary mapping: NIST CSF 2.0 function → recommended 800-53 controls
# Source: NIST SP 800-53B (csrc.nist.gov) and NIST CSF 2.0 core mapping
_RECOMMEND_BY_NIST_FUNCTION = {
    "Govern": [
        ("PM-9",  "Confirmed",    "Risk Management Strategy directly supports governance."),
        ("PM-28", "Confirmed",    "Risk Framing establishes governance context."),
        ("PL-2",  "Confirmed",    "System security plans are a core Govern function output."),
        ("CA-2",  "Recommended",  "Regular control assessments validate governance posture."),
        ("CA-5",  "Recommended",  "Plans of action track governance remediation."),
        ("CA-7",  "Confirmed",    "Continuous monitoring is a Govern/Detect cross-functional control."),
    ],
    "Identify": [
        ("CM-8",  "Confirmed",    "System Component Inventory directly supports asset identification."),
        ("RA-3",  "Confirmed",    "Risk Assessment is the primary Identify control activity."),
        ("RA-5",  "Confirmed",    "Vulnerability scanning is an Identify function requirement."),
        ("RA-7",  "Confirmed",    "Risk Response follows from Identify risk assessments."),
        ("PM-9",  "Recommended",  "Risk Management Strategy provides Identify context."),
        ("SA-9",  "Recommended",  "External system services must be identified and catalogued."),
    ],
    "Protect": [
        ("AC-1",  "Confirmed",    "Access control policy is foundational to Protection."),
        ("AC-2",  "Confirmed",    "Account management directly protects identity and access."),
        ("AC-3",  "Confirmed",    "Access enforcement implements protection decisions."),
        ("AC-6",  "Confirmed",    "Least privilege reduces the impact of compromised accounts."),
        ("IA-2",  "Confirmed",    "Authentication protects against unauthorised access."),
        ("IA-5",  "Confirmed",    "Authenticator management (passwords/MFA) is core Protect."),
        ("AT-2",  "Confirmed",    "Security awareness training protects against social engineering."),
        ("CM-2",  "Confirmed",    "Baseline configuration is the foundation of Protect."),
        ("CM-6",  "Confirmed",    "Configuration settings harden systems against attack."),
        ("SC-7",  "Confirmed",    "Boundary protection controls what enters and leaves the network."),
        ("SC-28", "Recommended",  "Protecting data at rest reduces confidentiality impact."),
    ],
    "Detect": [
        ("AU-2",  "Confirmed",    "Event logging is the primary Detect data source."),
        ("AU-6",  "Confirmed",    "Audit review drives detection of anomalous activity."),
        ("AU-12", "Confirmed",    "Audit record generation ensures detection coverage."),
        ("SI-4",  "Confirmed",    "System monitoring is the core Detect mechanism."),
        ("CA-7",  "Confirmed",    "Continuous monitoring links Detect to Govern oversight."),
        ("RA-5",  "Recommended",  "Vulnerability scanning detects weaknesses before exploitation."),
    ],
    "Respond": [
        ("IR-1",  "Confirmed",    "Incident response policy defines the Respond function."),
        ("IR-4",  "Confirmed",    "Incident handling is the operational Respond activity."),
        ("IR-5",  "Confirmed",    "Incident monitoring tracks response effectiveness."),
        ("IR-6",  "Confirmed",    "Incident reporting communicates response status."),
        ("CA-5",  "Recommended",  "Plans of action drive systematic remediation after incidents."),
    ],
    "Recover": [
        ("CP-2",  "Confirmed",    "Contingency plan defines recovery objectives and procedures."),
        ("CP-9",  "Confirmed",    "System backup is the primary enabler of data recovery."),
        ("CP-10", "Confirmed",    "Recovery and reconstitution restores operations after incidents."),
        ("IR-4",  "Recommended",  "Incident handling includes lessons-learned feeding recovery."),
    ],
}

# Secondary mapping: MITRE ATT&CK tactic → additional 800-53 controls
# These supplement the NIST-function mapping for technically-framed risks.
_RECOMMEND_BY_MITRE_TACTIC = {
    "Initial Access": [
        ("SC-7",  "Confirmed",    "Boundary protection limits initial access vectors."),
        ("SI-3",  "Confirmed",    "Malicious code protection blocks common initial access payloads."),
        ("AC-17", "Recommended",  "Remote access controls restrict external initial access."),
    ],
    "Credential Access": [
        ("IA-2",  "Confirmed",    "Multi-factor authentication directly counters credential attacks."),
        ("IA-5",  "Confirmed",    "Authenticator management prevents credential compromise."),
        ("AC-2",  "Confirmed",    "Account management limits what credentials can be exploited."),
    ],
    "Privilege Escalation": [
        ("AC-5",  "Confirmed",    "Separation of duties prevents horizontal privilege escalation."),
        ("AC-6",  "Confirmed",    "Least privilege limits the impact of escalation."),
        ("AC-2",  "Confirmed",    "Account management controls what privileges accounts hold."),
    ],
    "Defense Evasion": [
        ("AU-9",  "Confirmed",    "Protecting audit logs prevents evasion via log tampering."),
        ("SI-7",  "Confirmed",    "Integrity checking detects tampering attempts."),
        ("CM-6",  "Recommended",  "Hardened configuration reduces evasion opportunities."),
    ],
    "Lateral Movement": [
        ("SC-7",  "Confirmed",    "Boundary protection limits lateral movement across segments."),
        ("AC-3",  "Confirmed",    "Access enforcement prevents unauthorised lateral traversal."),
        ("AC-6",  "Confirmed",    "Least privilege limits what a moving attacker can access."),
    ],
    "Exfiltration": [
        ("SC-7",  "Confirmed",    "Boundary protection monitors and blocks outbound exfiltration."),
        ("SC-8",  "Confirmed",    "Transmission confidentiality prevents data being read in transit."),
        ("SC-28", "Confirmed",    "Data at rest protection limits value of exfiltrated data."),
        ("AU-12", "Recommended",  "Comprehensive logging creates evidence of exfiltration paths."),
    ],
    "Execution": [
        ("SI-3",  "Confirmed",    "Malicious code protection blocks execution of attacker tools."),
        ("CM-7",  "Confirmed",    "Least functionality limits what can be executed on systems."),
        ("SI-10", "Recommended",  "Input validation prevents code injection execution paths."),
    ],
    "Persistence": [
        ("CM-2",  "Confirmed",    "Baseline configuration detects persistence via drift."),
        ("SI-7",  "Confirmed",    "Integrity verification detects persistent backdoors."),
        ("AC-2",  "Recommended",  "Account management reviews catch persisted attacker accounts."),
    ],
    "Command & Control": [
        ("SC-7",  "Confirmed",    "Boundary protection can detect and block C2 traffic."),
        ("SI-4",  "Confirmed",    "System monitoring identifies C2 behavioural patterns."),
        ("AU-6",  "Recommended",  "Audit review catches anomalous outbound communication."),
    ],
    "Impact": [
        ("CP-9",  "Confirmed",    "Backups are the primary recovery control after destructive impact."),
        ("CP-10", "Confirmed",    "Recovery procedures restore operations after Impact-category attacks."),
        ("SC-5",  "Confirmed",    "DoS protection limits the surface for availability Impact attacks."),
    ],
    "Reconnaissance": [
        ("SC-7",  "Recommended",  "Boundary protection limits what an external recon can discover."),
        ("AU-2",  "Recommended",  "Logging recon probes enables early detection."),
        ("CM-8",  "Recommended",  "Asset inventory prevents unknown external-facing systems."),
    ],
    "Collection": [
        ("AC-3",  "Confirmed",    "Access enforcement limits what data a collecting attacker reaches."),
        ("MP-2",  "Confirmed",    "Media access control limits physical data collection."),
        ("SC-28", "Confirmed",    "Data at rest protection limits value of collected data."),
    ],
    "Discovery": [
        ("CM-8",  "Confirmed",    "Asset inventory ensures discovery of unknown systems."),
        ("AC-6",  "Recommended",  "Least privilege limits what an attacker can discover post-access."),
    ],
    "Resource Development": [
        ("SA-9",  "Recommended",  "External system controls limit attacker staging using your services."),
        ("SR-3",  "Recommended",  "Supply chain controls limit resource development via third parties."),
    ],
}

# Tertiary mapping: risk category → baseline 800-53 controls
# Used as a fallback when neither NIST function nor MITRE tactic provides
# confident recommendations.
_RECOMMEND_BY_CATEGORY = {
    "Technical": [
        ("SI-2",  "Confirmed",    "Flaw remediation addresses technical vulnerabilities."),
        ("CM-6",  "Confirmed",    "Configuration settings are the primary technical control."),
        ("RA-5",  "Confirmed",    "Vulnerability scanning identifies technical weaknesses."),
    ],
    "Operational": [
        ("MA-2",  "Confirmed",    "Controlled maintenance prevents operational security failures."),
        ("AT-3",  "Confirmed",    "Role-based training addresses operational security gaps."),
        ("IR-4",  "Recommended",  "Incident handling supports operational resilience."),
    ],
    "Compliance": [
        ("CA-2",  "Confirmed",    "Control assessments are the primary compliance verification activity."),
        ("CA-7",  "Confirmed",    "Continuous monitoring maintains ongoing compliance."),
        ("PL-2",  "Confirmed",    "System security plans document compliance posture."),
    ],
    "Strategic": [
        ("PM-9",  "Confirmed",    "Risk Management Strategy is the primary strategic security control."),
        ("PM-28", "Confirmed",    "Risk Framing establishes strategic risk context."),
        ("PL-2",  "Recommended",  "Security planning documents strategic security objectives."),
    ],
    "Third Party": [
        ("SA-9",  "Confirmed",    "External system services control governs third-party risk."),
        ("SR-3",  "Confirmed",    "Supply chain controls address third-party security requirements."),
        ("SR-5",  "Confirmed",    "Acquisition strategies embed security into vendor selection."),
        ("PS-6",  "Recommended",  "Access agreements formalise third-party security obligations."),
    ],
    "Financial": [
        ("AC-5",  "Confirmed",    "Separation of duties prevents financial fraud via access."),
        ("AU-6",  "Confirmed",    "Audit review detects anomalous financial system activity."),
        ("SC-28", "Confirmed",    "Data at rest protection covers financial records."),
    ],
    "Physical": [
        ("PE-2",  "Confirmed",    "Physical access authorizations control who enters facilities."),
        ("PE-3",  "Confirmed",    "Physical access control enforces physical boundary protection."),
        ("PE-6",  "Confirmed",    "Monitoring physical access detects unauthorised entry."),
        ("MA-5",  "Recommended",  "Maintenance personnel controls limit physical system access."),
    ],
}

def get_800_53_recommendations(risk: dict,
                                max_recommendations: int = 5) -> list:
    """
    Return a list of NIST SP 800-53 Rev 5 control recommendations for a
    single risk, ordered by confidence tier (Confirmed first) and deduped.

    Parameters
    ----------
    risk               : a risk dict (from AI analysis or register)
    max_recommendations: cap on returned controls (default 5)

    Returns a list of dicts, each with:
        control_id   — e.g. "IA-2"
        control_name — e.g. "Identification and Authentication"
        family       — e.g. "IA"
        confidence   — "Confirmed" | "Recommended" | "Unavailable"
        rationale    — why this control applies to the specific risk

    If no defensible recommendations can be made, returns:
        [{"control_id": "—", "control_name": "—", "family": "—",
          "confidence": "Unavailable",
          "rationale": "No defensible recommendation…"}]

    The recommendation engine queries three indices in priority order:
    1. NIST CSF function (highest confidence, explicit NIST mapping)
    2. MITRE ATT&CK tactic (technique-level, also well-documented)
    3. Risk category (category-level fallback)
    Deduplication ensures the same control is not listed twice even if
    it appears in multiple indices.
    """
    seen_controls = set()
    candidates = []   # (confidence_rank, control_id, rationale)

    conf_rank = {"Confirmed": 0, "Recommended": 1}

    def _add(control_id, confidence, rationale):
        if control_id in seen_controls:
            return
        if control_id not in NIST_800_53_CONTROLS:
            return
        seen_controls.add(control_id)
        candidates.append((
            conf_rank.get(confidence, 2),
            control_id, confidence, rationale
        ))

    # Priority 1: NIST CSF function mapping
    nist_fn = (risk.get("nist_function") or "").strip()
    for ctrl_id, conf, rationale in _RECOMMEND_BY_NIST_FUNCTION.get(
            nist_fn, []):
        _add(ctrl_id, conf, rationale)

    # Priority 2: MITRE ATT&CK tactic mapping
    mitre = (risk.get("mitre_tactic") or "").strip()
    for ctrl_id, conf, rationale in _RECOMMEND_BY_MITRE_TACTIC.get(
            mitre, []):
        _add(ctrl_id, conf, rationale)

    # Priority 3: Risk category fallback
    category = (risk.get("category") or "Technical").strip()
    for ctrl_id, conf, rationale in _RECOMMEND_BY_CATEGORY.get(
            category, _RECOMMEND_BY_CATEGORY.get("Technical", [])):
        _add(ctrl_id, conf, rationale)

    if not candidates:
        return [{
            "control_id":   "—",
            "control_name": "—",
            "family":       "—",
            "confidence":   "Unavailable",
            "rationale":    ("No defensible NIST SP 800-53 recommendation "
                             "can be made for this risk combination without "
                             "a full authoritative crosswalk dataset."),
        }]

    # Sort: Confirmed before Recommended; within same tier keep
    # insertion order (priority 1 > 2 > 3)
    candidates.sort(key=lambda c: c[0])
    candidates = candidates[:max_recommendations]

    result = []
    for rank, ctrl_id, confidence, rationale in candidates:
        name, family = NIST_800_53_CONTROLS[ctrl_id]
        result.append({
            "control_id":   ctrl_id,
            "control_name": name,
            "family":       family,
            "confidence":   confidence,
            "rationale":    rationale,
        })
    return result

def get_800_53_recommendations_for_register(risks: list,
                                             max_per_risk: int = 3) -> dict:
    """
    Return 800-53 recommendations for every risk in a list, keyed by
    risk title. Deduplication is per-risk only (same control can appear
    across risks). Used by the PDF report and future dashboard.
    """
    return {
        r.get("title", f"Risk {i}"): get_800_53_recommendations(
            r, max_per_risk)
        for i, r in enumerate(risks)
    }

# ── PDF Report Generator ──────────────────────────────────────────────────────



def generate_pdf_report(analysis: dict, risks_approved: list,
                         company_name: str, output_path: str,
                         classification: str = "CONFIDENTIAL",
                         _known_total_pages: int = 0,
                         org_scope: dict = None,
                         _known_registry: dict = None) -> str:
    """
    RiskCore GRC Platform v1.5 — Enterprise Executive PDF Report.
    Board-ready. Consultant-quality. Fully data-driven.
    """
    import io, math, os as _os, re as _re, html as _html
    from collections import Counter

    def xe(v):
        """Escape user-supplied text for safe use in ReportLab Paragraph().
        Escapes & < > " ' to prevent XML/HTML injection into PDF markup."""
        if v is None:
            return "—"
        s = str(v).strip()
        return _html.escape(s) if s else "—"

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle as PS
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, KeepTogether,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
    from reportlab.graphics.shapes import (
        Drawing, Rect, String, Line, Circle,
        PolyLine, Polygon, Group,
    )
    from reportlab.graphics import renderPDF
    from reportlab.platypus.flowables import Flowable

    class _SectionAnchor(Flowable):
        """Zero-height marker that records current page into a shared dict."""
        def __init__(self, key, registry):
            super().__init__()
            self._key = key; self._reg = registry
            self.width = 0; self.height = 0
        def draw(self):
            self._reg[self._key] = self.canv.getPageNumber()
        def wrap(self, *a): return 0, 0

    W, H  = A4
    MG    = 1.9 * cm
    CW    = W - 2 * MG
    COL2  = (CW - 8) / 2

    # ── Colour Design System ─────────────────────────────────────────────────
    cn = colors.HexColor
    C = {
        "navy":     cn("#0B1F3A"),
        "navy2":    cn("#112B52"),
        "blue":     cn("#1B5FCF"),
        "blue_lt":  cn("#EBF2FF"),
        "blue_mid": cn("#4B82DC"),
        "crit":     cn("#C0392B"),
        "crit_lt":  cn("#FDF0EF"),
        "high":     cn("#D4560A"),
        "high_lt":  cn("#FEF3EC"),
        "med":      cn("#C78B00"),
        "med_lt":   cn("#FEF9EA"),
        "low":      cn("#1A8C4E"),
        "low_lt":   cn("#EBF7F1"),
        "purple":   cn("#5B4DB2"),
        "teal":     cn("#0E7C7B"),
        "body":     cn("#1A2533"),
        "sub":      cn("#3D5166"),
        "muted":    cn("#697A8D"),
        "border":   cn("#DDE3EC"),
        "bg":       cn("#F5F7FA"),
        "card":     cn("#FFFFFF"),
        "alt":      cn("#F8FAFD"),
        "white":    colors.white,
        "silver":   cn("#CBD5E1"),
    }

    def sev_color(s):
        s = int(s or 0)
        if s >= 15: return C["crit"]
        if s >= 10: return C["high"]
        if s >= 5:  return C["med"]
        return C["low"]

    def sev_bg(s):
        s = int(s or 0)
        if s >= 15: return C["crit_lt"]
        if s >= 10: return C["high_lt"]
        if s >= 5:  return C["med_lt"]
        return C["low_lt"]

    def sev_label(s):
        s = int(s or 0)
        if s >= 15: return "CRITICAL"
        if s >= 10: return "HIGH"
        if s >= 5:  return "MEDIUM"
        return "LOW"

    # ── Typography ───────────────────────────────────────────────────────────
    def st(name, **kw):
        kw.setdefault("fontName", "Helvetica")
        return PS(name, **kw)

    T = {
        "page_title": st("pt", fontSize=22, textColor=C["navy"],
                         fontName="Helvetica-Bold", leading=28, spaceAfter=2),
        "page_sub":   st("ps", fontSize=10, textColor=C["muted"],
                         leading=14, spaceAfter=14),
        "h2": st("h2", fontSize=13, textColor=C["navy"],
                 fontName="Helvetica-Bold", leading=17, spaceBefore=14, spaceAfter=5,
                 keepWithNext=1),
        "h3": st("h3", fontSize=10.5, textColor=C["blue"],
                 fontName="Helvetica-Bold", leading=14, spaceBefore=8, spaceAfter=4,
                 keepWithNext=1),
        "h4": st("h4", fontSize=9.5, textColor=C["body"],
                 fontName="Helvetica-Bold", leading=13, spaceAfter=3),
        "body": st("body", fontSize=9.5, textColor=C["body"],
                   leading=15, spaceAfter=5, alignment=TA_JUSTIFY),
        "body_l": st("body_l", fontSize=9.5, textColor=C["body"],
                     leading=15, spaceAfter=5),
        "sm":   st("sm", fontSize=8.5, textColor=C["sub"], leading=13, spaceAfter=3),
        "xs":   st("xs", fontSize=7.5, textColor=C["muted"], leading=11, spaceAfter=2),
        "cap":  st("cap", fontSize=7.5, textColor=C["muted"],
                   leading=10, alignment=TA_CENTER),
        "bul":  st("bul", fontSize=9.5, textColor=C["body"],
                   leading=14, leftIndent=14, spaceAfter=3),
        "th":   st("th", fontSize=8, textColor=C["white"],
                   fontName="Helvetica-Bold", leading=10),
        "td":   st("td", fontSize=8.5, textColor=C["body"], leading=11),
        "td_b": st("tdb", fontSize=8.5, textColor=C["body"],
                   fontName="Helvetica-Bold", leading=11),
        "td_m": st("tdm", fontSize=7.5, textColor=C["muted"], leading=10),
        "td_l": st("tdl", fontSize=8.5, textColor=C["blue"], leading=11),
        "td_c": st("tdc", fontSize=8.5, textColor=C["body"],
                   leading=11, alignment=TA_CENTER),
    }

    # ── Vector Chart Engine ───────────────────────────────────────────────────
    class Embed(Flowable):
        def __init__(self, d):
            super().__init__()
            self._d = d
            self.width  = d.width
            self.height = d.height
        def wrap(self, *a): return self.width, self.height
        def draw(self):     renderPDF.draw(self._d, self.canv, 0, 0)

    def horiz_bars(vals, labels, bar_colors, width=None, height=None, title=""):
        w = width or CW
        n_ = len(vals)
        if not n_: return Spacer(1, 1)
        bar_h = 16
        gap   = 8
        lbl_w = 110
        h = height or (n_ * (bar_h + gap) + gap + (20 if title else 0))
        d = Drawing(w, h)
        max_v = max(vals) or 1
        track_w = w - lbl_w - 35
        base_y  = h - (20 if title else 0) - gap
        if title:
            d.add(String(w/2, h-12, title, fontName="Helvetica-Bold",
                         fontSize=9, fillColor=C["navy"], textAnchor="middle"))
        for i, (v, lbl, col) in enumerate(zip(vals, labels, bar_colors)):
            y = base_y - i * (bar_h + gap)
            d.add(String(lbl_w-4, y+3, str(lbl)[:22], fontName="Helvetica",
                         fontSize=8, fillColor=C["sub"], textAnchor="end"))
            d.add(Rect(lbl_w, y, track_w, bar_h, fillColor=cn("#EDF0F5"),
                       strokeColor=None, rx=4, ry=4))
            bw = (v/max_v)*track_w if max_v else 0
            if bw > 0:
                d.add(Rect(lbl_w, y, bw, bar_h, fillColor=col,
                           strokeColor=None, rx=4, ry=4))
            d.add(String(lbl_w+track_w+4, y+3, str(v),
                         fontName="Helvetica-Bold", fontSize=8,
                         fillColor=col if v else C["muted"], textAnchor="start"))
        return Embed(d)

    def donut_chart(vals, labels, cols_list, width=110, title=""):
        total = sum(vals) or 1
        r_out, r_in = 42, 24
        cx, cy = 50, 52
        leg_x  = 108
        h = 115
        d = Drawing(width, h)
        if all(v == 0 for v in vals):
            d.add(Circle(cx, cy, r_out, fillColor=cn("#EDF0F5"), strokeColor=None))
            d.add(Circle(cx, cy, r_in,  fillColor=C["white"],    strokeColor=None))
        else:
            start = 90.0
            for v, col in zip(vals, cols_list):
                if not v: continue
                sweep = 360 * v / total
                pts = []
                steps = max(int(abs(sweep)/4)+2, 3)
                for j in range(steps+1):
                    a = math.radians(start - sweep*j/steps)
                    pts += [cx+r_out*math.cos(a), cy+r_out*math.sin(a)]
                for j in range(steps, -1, -1):
                    a = math.radians(start - sweep*j/steps)
                    pts += [cx+r_in*math.cos(a),  cy+r_in*math.sin(a)]
                if len(pts) >= 6:
                    d.add(Polygon(pts, fillColor=col,
                                  strokeColor=C["white"], strokeWidth=1.5))
                start -= sweep
        d.add(String(cx, cy+5,  str(total), fontName="Helvetica-Bold",
                     fontSize=16, fillColor=C["navy"], textAnchor="middle"))
        d.add(String(cx, cy-8,  "Total",    fontName="Helvetica",
                     fontSize=7, fillColor=C["muted"], textAnchor="middle"))
        ly = h - 12
        for lbl, col, v in zip(labels, cols_list, vals):
            pct = f"{int(v/total*100)}%"
            d.add(Rect(leg_x, ly, 9, 9, fillColor=col,
                       strokeColor=None, rx=2, ry=2))
            d.add(String(leg_x+13, ly+1, f"{lbl}",
                         fontName="Helvetica", fontSize=7.5,
                         fillColor=C["sub"], textAnchor="start"))
            d.add(String(leg_x+13, ly-9, f"{v}  {pct}",
                         fontName="Helvetica-Bold", fontSize=7,
                         fillColor=col, textAnchor="start"))
            ly -= 26
        if title:
            d.add(String(cx, 5, title, fontName="Helvetica", fontSize=7.5,
                         fillColor=C["muted"], textAnchor="middle"))
        return Embed(d)

    def prog_bar(pct, label="", color=None, width=None, height=24):
        w   = width or CW
        col = color or C["blue"]
        d   = Drawing(w, height)
        lw  = 105
        vw  = 34
        bw  = w - lw - vw - 4
        by  = (height-10)/2
        if label:
            d.add(String(lw-4, by+1, label, fontName="Helvetica", fontSize=8,
                         fillColor=C["sub"], textAnchor="end"))
        d.add(Rect(lw, by, bw, 10, fillColor=cn("#EDF0F5"),
                   strokeColor=None, rx=5, ry=5))
        if pct > 0:
            d.add(Rect(lw, by, bw*min(pct,100)/100, 10, fillColor=col,
                       strokeColor=None, rx=5, ry=5))
        d.add(String(lw+bw+5, by+1, f"{int(pct)}%",
                     fontName="Helvetica-Bold", fontSize=8,
                     fillColor=col if pct else C["muted"], textAnchor="start"))
        return Embed(d)

    def heat_map_drawing(cell_scores, width=None):
        w = width or CW
        label_w = 30
        cell_w  = (w - label_w) / 5
        cell_h  = 38
        h_total = 5*cell_h + 30 + 20
        d = Drawing(w, h_total)
        cell_fills = {
            (1,1):cn("#1A8C4E"),(1,2):cn("#2D9A5A"),(1,3):cn("#C78B00"),
            (1,4):cn("#D4560A"),(1,5):cn("#C0392B"),
            (2,1):cn("#2D9A5A"),(2,2):cn("#C78B00"),(2,3):cn("#D4560A"),
            (2,4):cn("#C0392B"),(2,5):cn("#A93226"),
            (3,1):cn("#C78B00"),(3,2):cn("#D4560A"),(3,3):cn("#C0392B"),
            (3,4):cn("#A93226"),(3,5):cn("#922B21"),
            (4,1):cn("#D4560A"),(4,2):cn("#C0392B"),(4,3):cn("#A93226"),
            (4,4):cn("#922B21"),(4,5):cn("#7B241C"),
            (5,1):cn("#C0392B"),(5,2):cn("#A93226"),(5,3):cn("#922B21"),
            (5,4):cn("#7B241C"),(5,5):cn("#641E16"),
        }
        # Impact labels
        imp_lbls = ["Negligible","Minor","Moderate","Major","Critical"]
        for imp in range(1,6):
            x = label_w + (imp-1)*cell_w + cell_w/2
            d.add(String(x, h_total-10, f"I{imp}", fontName="Helvetica-Bold",
                         fontSize=7, fillColor=C["muted"], textAnchor="middle"))
            d.add(String(x, h_total-20, imp_lbls[imp-1][:8],
                         fontName="Helvetica", fontSize=5.5,
                         fillColor=C["muted"], textAnchor="middle"))
        # Likelihood labels + cells
        lik_lbls = ["Rare","Unlikely","Possible","Likely","Almost\nCertain"]
        for lik in range(5,0,-1):
            row_y = (5-lik)*cell_h + 28
            d.add(String(label_w-4, row_y+cell_h/2-4,
                         f"L{lik}", fontName="Helvetica-Bold", fontSize=7,
                         fillColor=C["muted"], textAnchor="end"))
            for imp in range(1,6):
                x     = label_w + (imp-1)*cell_w
                score = lik*imp
                cnt   = cell_scores.get((lik,imp), 0)
                bg    = cell_fills.get((lik,imp), cn("#C78B00"))
                d.add(Rect(x+1.5, row_y+1.5, cell_w-3, cell_h-3,
                           fillColor=bg, strokeColor=C["white"],
                           strokeWidth=2, rx=4, ry=4))
                d.add(String(x+cell_w/2, row_y+cell_h/2+2, str(score),
                             fontName="Helvetica-Bold", fontSize=13,
                             fillColor=C["white"], textAnchor="middle"))
                if cnt:
                    d.add(String(x+cell_w/2, row_y+6, f"({cnt})",
                                 fontName="Helvetica", fontSize=7.5,
                                 fillColor=C["white"], textAnchor="middle"))
        return Embed(d)

    # ── Layout Helpers ────────────────────────────────────────────────────────
    def sp(pts=8):  return Spacer(1, pts)
    def pb():       return PageBreak()
    def div(color=None, thickness=0.7, space=8):
        return HRFlowable(width="100%", thickness=thickness,
                          color=color or C["border"],
                          spaceBefore=space, spaceAfter=space)

    def page_title(title, subtitle=""):
        """Every section starts on a fresh page — no orphaned headings."""
        elems = [
            PageBreak(),
            Paragraph(title, T["page_title"]),
            HRFlowable(width="100%", thickness=2.0,
                        color=C["blue"], spaceBefore=4, spaceAfter=6),
        ]
        if subtitle:
            elems.append(Paragraph(subtitle, T["page_sub"]))
            elems.append(Paragraph("", T["body"]))  # breathing space
        return elems

    def kpi_table(items):
        cells = []
        for v, lbl, col in items:
            cells.append([
                Paragraph(str(v),
                          PS(f"kn{v}", fontName="Helvetica-Bold",
                             fontSize=26, textColor=cn(col),
                             leading=32, alignment=TA_CENTER)),
                Paragraph(lbl,
                          PS(f"kl{lbl[:6]}", fontName="Helvetica",
                             fontSize=8, textColor=C["muted"],
                             leading=10, alignment=TA_CENTER)),
            ])
        cw = CW / len(cells)
        t  = Table([cells], colWidths=[cw]*len(cells))
        ts = [
            ("TOPPADDING",    (0,0),(-1,-1), 12),
            ("BOTTOMPADDING", (0,0),(-1,-1), 12),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
            ("INNERGRID",     (0,0),(-1,-1), 0.5, C["border"]),
            ("BACKGROUND",    (0,0),(-1,-1), C["card"]),
        ]
        for i, (_, _, col) in enumerate(items):
            ts.append(("LINEABOVE", (i,0),(i,0), 3, cn(col)))
        t.setStyle(TableStyle(ts))
        return t

    def info_card(rows, col_widths=None):
        cw = col_widths or [4*cm, CW-4*cm]
        data = [[Paragraph(str(k), T["td_m"]),
                 Paragraph(str(v or "—"), T["td"])]
                for k, v in rows]
        t = Table(data, colWidths=cw)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,-1), C["bg"]),
            ("FONTNAME",      (0,0),(0,-1), "Helvetica-Bold"),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("LINEBELOW",     (0,0),(-1,-2), 0.4, C["border"]),
            ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        ]))
        return t

    def two_col(left_items, right_items):
        t = Table([[left_items, right_items]], colWidths=[COL2, COL2])
        t.setStyle(TableStyle([
            ("VALIGN",       (0,0),(-1,-1), "TOP"),
            ("LEFTPADDING",  (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(0,-1),  4),
            ("LEFTPADDING",  (1,0),(1,-1),  4),
            ("RIGHTPADDING", (1,0),(1,-1),  0),
            ("TOPPADDING",   (0,0),(-1,-1), 0),
            ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ]))
        return t

    def insight_box(text):
        icon_w = 1.2*cm
        t = Table([[
            Paragraph("◆", PS("iic", fontName="Helvetica-Bold",
                               fontSize=14, textColor=C["blue"], leading=16)),
            Paragraph(text, PS("iib", fontName="Helvetica",
                               fontSize=9.5, textColor=C["navy2"],
                               leading=14)),
        ]], colWidths=[icon_w, CW-icon_w])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), C["blue_lt"]),
            ("TOPPADDING",    (0,0),(-1,-1), 10),
            ("BOTTOMPADDING", (0,0),(-1,-1), 10),
            ("LEFTPADDING",   (0,0),(0,-1),  8),
            ("RIGHTPADDING",  (0,0),(0,-1),  4),
            ("LEFTPADDING",   (1,0),(1,-1),  8),
            ("RIGHTPADDING",  (1,0),(1,-1),  12),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("BOX",           (0,0),(-1,-1), 0.7, cn("#BFD4F5")),
        ]))
        return t

    def reg_table(hdrs, widths, rows, hdr_bg=None):
        hdr_row = [Paragraph(h, T["th"]) for h in hdrs]
        t = Table([hdr_row]+rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), hdr_bg or C["navy"]),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
            ("LINEBELOW",     (0,0),(-1,-2), 0.3, C["border"]),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [C["card"], C["alt"]]),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        ]))
        return t

    def rec_row(text, priority="High"):
        col_ = {"Critical":C["crit"],"High":C["high"],
                 "Medium":C["med"],"Low":C["low"]}.get(priority, C["blue"])
        badge_ = Table([[Paragraph(f"<b>{priority}</b>",
                                   PS(f"rp{priority}", fontName="Helvetica-Bold",
                                      fontSize=7.5, textColor=C["white"],
                                      leading=9, alignment=TA_CENTER))]],
                       colWidths=[1.8*cm])
        badge_.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), col_),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ]))
        row_t = Table(
            [[Paragraph(f"▸  {xe(text)}",
                        PS(f"rt{abs(hash(text))%9999}", fontName="Helvetica",
                           fontSize=9.5, textColor=C["body"], leading=14)),
              badge_]],
            colWidths=[CW-2.2*cm, 2.2*cm])
        row_t.setStyle(TableStyle([
            ("LEFTPADDING",   (0,0),(0,-1), 14),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LINEBEFORE",    (0,0),(0,-1), 3, col_),
            ("BACKGROUND",    (0,0),(-1,-1), C["alt"]),
            ("LINEBELOW",     (0,0),(-1,-1), 0.3, C["border"]),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        return row_t

    def sev_badge(text, score):
        col_ = sev_color(score)
        p = Paragraph(f"<b>{text}</b>",
                      PS(f"sb{text[:4]}", fontName="Helvetica-Bold",
                         fontSize=7, textColor=C["white"],
                         leading=8, alignment=TA_CENTER))
        t = Table([[p]], colWidths=[2*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), col_),
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
            ("LEFTPADDING",   (0,0),(-1,-1), 4),
            ("RIGHTPADDING",  (0,0),(-1,-1), 4),
        ]))
        return t

    # ── Data Layer ────────────────────────────────────────────────────────────
    risks = [dict(r) if not isinstance(r, dict) else r
             for r in (risks_approved or [])]
    n     = len(risks)

    def sc(r): return int(r.get("inherent_score") or r.get("risk_score") or 0)

    crit_  = [r for r in risks if sc(r) >= 15]
    high_  = [r for r in risks if 10 <= sc(r) <= 14]
    med_   = [r for r in risks if 5  <= sc(r) <= 9]
    low_   = [r for r in risks if sc(r) <= 4]

    status_ctr = Counter(r.get("status","Open") for r in risks)
    nist_ctr   = Counter(r.get("nist_function","") for r in risks
                         if r.get("nist_function"))
    cia_ctr    = Counter(r.get("cia_component","") for r in risks
                         if r.get("cia_component"))
    mitre_ctr  = Counter(r.get("mitre_tactic","") for r in risks
                         if r.get("mitre_tactic") and
                            r.get("mitre_tactic") != "Not Applicable")

    def _cis_key(v):
        m = _re.match(r"(CIS-\d+)", str(v or ""))
        return m.group(1) if m else v

    cis_ctr    = Counter(_cis_key(r.get("cis_control","")) for r in risks
                         if r.get("cis_control") and
                            r.get("cis_control") not in ("Not Applicable",""))
    owner_ctr  = Counter(r.get("owner","") for r in risks if r.get("owner"))
    iso_ctr    = Counter(r.get("iso_domain","") for r in risks
                         if r.get("iso_domain"))
    cat_ctr    = Counter(r.get("category","") for r in risks
                         if r.get("category"))

    open_c    = status_ctr.get("Open",0)
    closed_c  = sum(v for k,v in status_ctr.items()
                    if k.lower() in ("closed","mitigated","accepted","verified"))
    ai_c      = sum(1 for r in risks
                    if str(r.get("source","")).lower() == "ai analysis")
    no_mit    = sum(1 for r in risks
                    if not (r.get("mitigation") or "").strip())
    overdue   = sum(1 for r in risks
                    if (r.get("review_date") or "") < today()
                    and r.get("review_date"))
    avg_sc    = round(sum(sc(r) for r in risks) / max(n, 1), 1)
    max_sc    = max((sc(r) for r in risks), default=0)
    all_scores = sorted([sc(r) for r in risks])
    med_sc    = all_scores[len(all_scores)//2] if all_scores else 0

    posture   = ("Critical" if crit_ else "High" if high_ else
                 "Medium" if med_ else "Low" if risks else "Unknown")
    p_col     = {"Critical":C["crit"],"High":C["high"],
                 "Medium":C["med"],"Low":C["low"],
                 "Unknown":C["muted"]}.get(posture, C["muted"])

    all_fns   = {"Govern","Identify","Protect","Detect","Respond","Recover"}
    miss_fns  = all_fns - set(nist_ctr.keys())

    cell_scores = {}
    for r in risks:
        lik = int(r.get("likelihood") or 0)
        imp = int(r.get("impact") or 0)
        if lik and imp:
            cell_scores[(lik,imp)] = cell_scores.get((lik,imp), 0) + 1

    # ── Page Chrome ───────────────────────────────────────────────────────────
    page_num    = [0]
    total_pages = [_known_total_pages]

    def on_page(canvas, doc):
        page_num[0] += 1
        canvas.saveState()
        canvas.setFillColor(C["navy"])
        canvas.rect(0, H-7*mm, W, 7*mm, fill=1, stroke=0)
        canvas.setFillColor(C["blue"])
        canvas.rect(0, H-7*mm, 4*mm, 7*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(C["white"])
        canvas.drawString(MG, H-4.5*mm, f"{classification}  ·  {company_name}")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(cn("#93C5FD"))
        canvas.drawRightString(W-MG, H-4.5*mm, "RiskCore GRC Platform  v1.5")
        canvas.setStrokeColor(C["border"])
        canvas.setLineWidth(0.7)
        canvas.line(MG, 16*mm, W-MG, 16*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(C["muted"])
        canvas.drawString(MG, 11*mm,
                          f"RiskCore GRC Platform v1.5  ·  Cyber Risk Assessment Report  ·  {today()}")
        pg = (f"Page {page_num[0]} of {total_pages[0]}"
              if total_pages[0] else f"Page {page_num[0]}")
        canvas.drawRightString(W-MG, 11*mm, pg)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(cn("#94A3B8"))
        canvas.drawString(MG, 7*mm,
                          f"{classification} — NOT FOR DISTRIBUTION  ·  "
                          f"Generated: {today()} {now()}")
        canvas.restoreState()

    # ── Cover Page ────────────────────────────────────────────────────────────
    def on_cover(canvas, doc):
        import os as _os2
        split = H * 0.52
        # Navy header with subtle geometric pattern
        canvas.setFillColor(C["navy"])
        canvas.rect(0, split, W, H-split, fill=1, stroke=0)
        canvas.setFillColor(C["navy2"])
        canvas.rect(0, split, W, (H-split)*0.35, fill=1, stroke=0)
        # Subtle geometric lines
        canvas.setStrokeColor(cn("#1B5FCF"))
        canvas.setLineWidth(0.4)
        for i in range(8):
            y1 = split + i * 28
            canvas.line(0, y1, W*0.4, y1+52)
        canvas.setStrokeColor(cn("#0F2D5C"))
        canvas.setLineWidth(0.8)
        for i in range(4):
            x = W * 0.7 + i * 40
            canvas.line(x, split, x, H)

        # White content zone
        canvas.setFillColor(C["white"])
        canvas.rect(0, 0, W, split, fill=1, stroke=0)
        # Subtle dot pattern
        canvas.setFillColor(cn("#F0F4FA"))
        for row in range(0, int(split), 18):
            for col in range(0, int(W), 18):
                canvas.circle(col, row, 0.8, fill=1, stroke=0)

        # Left accent bar
        canvas.setFillColor(C["blue"])
        canvas.rect(0, 0, 5*mm, H, fill=1, stroke=0)

        # Classification ribbon
        clf_c = {"CONFIDENTIAL":cn("#C0392B"),"RESTRICTED":cn("#C78B00"),
                 "INTERNAL":cn("#1B5FCF"),"PUBLIC":cn("#1A8C4E")}.get(
                 classification, cn("#C0392B"))
        canvas.setFillColor(clf_c)
        canvas.rect(0, H-7*mm, W, 7*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(C["white"])
        canvas.drawCentredString(W/2, H-4.5*mm,
            f"  {classification}  ·  {company_name}  ·  "
            f"CYBER RISK ASSESSMENT  ·  {classification}  ")

        # Logo
        _adir = _os2.path.dirname(_os2.path.abspath(__file__))
        for _lp in [
            _os2.path.join(_adir, "assets", "images", "riskcore_logo.png"),
            _os2.path.join(_adir, "..", "assets", "images", "riskcore_logo.png"),
        ]:
            if _os2.path.exists(_lp):
                try:
                    canvas.drawImage(_lp, 10*mm, H-7*mm-4.2*cm,
                                     width=3.8*cm, height=3.8*cm,
                                     preserveAspectRatio=True, mask="auto")
                    break
                except Exception:
                    pass

        # Brand wordmark
        bx = 10*mm + 3.8*cm + 7*mm
        by = H - 7*mm - 1.5*cm
        canvas.setFont("Helvetica-Bold", 28)
        canvas.setFillColor(C["white"])
        canvas.drawString(bx, by, "RiskCore")
        canvas.setFont("Helvetica", 11)
        canvas.setFillColor(cn("#93C5FD"))
        canvas.drawString(bx, by-16, "GRC Platform  v1.5")
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(cn("#4B7AB0"))
        canvas.drawString(bx, by-30, "Governance  |  Risk  |  Compliance")

        # Accent rule
        ry = H - 7*mm - 5.2*cm
        canvas.setStrokeColor(C["blue"])
        canvas.setLineWidth(1.5)
        canvas.line(10*mm, ry, W-10*mm, ry)

        # Report title
        a_t = (org_scope or {}).get("assessment_type","")
        t1  = ("Gap Assessment" if "Gap" in a_t else
               "Security Audit" if "Audit" in a_t else "Cyber Risk Assessment")
        ty  = H - 7*mm - 8*cm
        canvas.setFont("Helvetica-Bold", 38)
        canvas.setFillColor(C["white"])
        canvas.drawString(10*mm, ty, t1)
        canvas.setFont("Helvetica-Bold", 20)
        canvas.setFillColor(cn("#93C5FD"))
        canvas.drawString(10*mm, ty-2.0*cm, "Report")
        org_n = ((org_scope or {}).get("organisation_name") or company_name or "")
        canvas.setFont("Helvetica", 15)
        canvas.setFillColor(cn("#CBD8E8"))
        canvas.drawString(10*mm, ty-3.6*cm, str(org_n)[:54])

        parts = [v for k in ("industry","organisation_size")
                 if (v := (org_scope or {}).get(k))]
        if parts:
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(cn("#6B8CAE"))
            canvas.drawString(10*mm, ty-4.5*cm, "  ·  ".join(parts))

        # Blue transition strip
        canvas.setFillColor(C["blue"])
        canvas.rect(0, split-3, W, 3, fill=1, stroke=0)

        # White zone: KPI summary cards
        cards = [
            (str(n),          "Total Risks",   "#1B5FCF"),
            (str(len(crit_)), "Critical",      "#C0392B"),
            (str(len(high_)), "High",          "#D4560A"),
            (str(len(med_)),  "Medium",        "#C78B00"),
            (posture,         "Risk Posture",  {
                "Critical":"#C0392B","High":"#D4560A",
                "Medium":"#C78B00","Low":"#1A8C4E",
                "Unknown":"#697A8D"}.get(posture,"#1B5FCF")),
        ]
        total_cw = W - 20*mm
        cw_each  = total_cw / len(cards)
        card_h   = 2.0*cm
        card_y   = split - 0.8*cm

        for i, (val, lbl, col_hex) in enumerate(cards):
            cx2 = 10*mm + i * cw_each
            # Shadow
            canvas.setFillColor(cn("#E0E8F0"))
            canvas.roundRect(cx2+1, card_y-card_h-1, cw_each-4, card_h, 5, fill=1, stroke=0)
            # Card
            canvas.setFillColor(C["white"])
            canvas.roundRect(cx2, card_y-card_h, cw_each-4, card_h, 5, fill=1, stroke=0)
            # Top colour tab
            canvas.setFillColor(cn(col_hex))
            canvas.setLineWidth(3)
            canvas.line(cx2, card_y, cx2+cw_each-4, card_y)
            # Value
            canvas.setFont("Helvetica-Bold", 20)
            canvas.setFillColor(cn(col_hex))
            canvas.drawCentredString(cx2+(cw_each-4)/2, card_y-card_h/2-2, str(val)[:10])
            # Label
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(C["muted"])
            canvas.drawCentredString(cx2+(cw_each-4)/2, card_y-card_h+8, lbl)

        # Metadata strip
        meta_y = card_y - card_h - 0.6*cm
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C["muted"])
        canvas.drawString(10*mm, meta_y,
                          f"Report Date: {today()}   ·   Generated: {now()}   ·   "
                          f"Classification: {classification}")

        # NIST pills
        pill_y = meta_y - 0.8*cm
        nist_pills = [("GOVERN","#1B5E20"),("IDENTIFY","#1565C0"),
                      ("PROTECT","#2E7D32"),("DETECT","#E65100"),
                      ("RESPOND","#880E4F"),("RECOVER","#4A148C")]
        pw_each = (total_cw - 5*3*mm) / 6
        px = 10*mm
        for pn, phex in nist_pills:
            cnt_ = nist_ctr.get(pn.capitalize(), 0)
            canvas.setFillColor(cn(phex))
            canvas.roundRect(px, pill_y-13, pw_each, 13, 3, fill=1, stroke=0)
            canvas.setFont("Helvetica-Bold", 7)
            canvas.setFillColor(C["white"])
            canvas.drawCentredString(px+pw_each/2, pill_y-8, pn)
            px += pw_each + 3*mm

        # Footer
        canvas.setStrokeColor(C["border"])
        canvas.setLineWidth(0.7)
        canvas.line(10*mm, 1.8*cm, W-10*mm, 1.8*cm)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.setFillColor(C["navy"])
        canvas.drawString(10*mm, 1.2*cm, "RiskCore GRC Platform  v1.5")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C["muted"])
        canvas.drawString(10*mm, 0.7*cm, "Governance  |  Risk  |  Compliance")
        canvas.drawRightString(W-10*mm, 0.7*cm, f"Generated: {today()}")

    def cover_page(canvas, doc):
        if doc.page == 1:
            on_cover(canvas, doc)
        else:
            on_page(canvas, doc)

    # ════════════════════════════════════════════════════════════════════════
    # BUILD STORY
    # ════════════════════════════════════════════════════════════════════════
    story = []
    # On pass 2, pre-populate page_registry from pass 1 results
    # so TOC numbers are available when the story is built
    page_registry = dict(_known_registry) if _known_registry else {}

    def anc(key):
        """Insert a section anchor — records actual page number."""
        return _SectionAnchor(key, page_registry)

    def toc_pg(key):
        """Return actual page number from registry, or '—' if not yet known."""
        v = page_registry.get(key)
        return str(v) if v else "—"

    # ── COVER ────────────────────────────────────────────────────────────────
    # (PageBreak now in page_title())

    # ── TABLE OF CONTENTS ────────────────────────────────────────────────────
    story += page_title("Contents", f"RiskCore GRC Platform v1.5  ·  {company_name}")

    # ── Page number tracking for TOC ─────────────────────────────────────────
    # TOC page numbers come from _SectionAnchor flowables via page_registry.
    # On the first (dummy) pass, toc_pg() returns "—".
    # On the second pass it returns the actual page number recorded during
    # the first pass — giving accurate TOC page numbers regardless of
    # how long the report is.
    toc_sections = [
        # (num, title, is_sub, registry_key)
        ("1",  "Organisation Scope",         False, "s1"),
        ("2",  "Executive Summary",          False, "s2"),
        ("3",  "Risk Analytics",             False, "s3"),
        ("4",  "Risk Heat Map",              False, "s4"),
        ("5",  "Risk Register",              False, "s5"),
        ("6",  "Detailed Risk Profiles",     False, "s6"),
        ("7",  "Framework Intelligence",     False, "s7"),
        ("7a", "NIST CSF 2.0",              True,  "s7a"),
        ("7b", "ISO/IEC 27001:2022",        True,  "s7b"),
        ("7c", "MITRE ATT&CK",             True,  "s7c"),
        ("7d", "CIS Controls v8",           True,  "s7d"),
        ("7e", "CIA Triad",                 True,  "s7e"),
        ("7f", "Framework Recommendations", True,  "s7f"),
        ("8",  "AI Recommendations",        False, "s8"),
        ("9",  "Treatment Roadmap",         False, "s9"),
        ("10", "Executive Conclusion",      False, "s10"),
        ("11", "Methodology Appendix",      False, "s11"),
    ]

    toc_rows = []
    for num, title, is_sub, reg_key in toc_sections:
        indent = 12 if is_sub else 0
        actual_pg = toc_pg(reg_key)   # actual page from registry (or "—" on pass 1)
        num_p = Paragraph(
            f"<b>{num}</b>",
            PS(f"tn{num}", fontName="Helvetica-Bold",
               fontSize=10 if not is_sub else 9,
               textColor=C["blue"] if not is_sub else C["muted"],
               leading=20))
        title_p = Paragraph(
            title,
            PS(f"tt{num}", fontName="Helvetica",
               fontSize=10 if not is_sub else 9,
               textColor=C["body"] if not is_sub else C["sub"],
               leading=20, leftIndent=indent))
        pg_p = Paragraph(
            f"<b>{actual_pg}</b>",
            PS(f"tp{num}", fontName="Helvetica-Bold",
               fontSize=10 if not is_sub else 9,
               textColor=C["blue"] if not is_sub else C["muted"],
               leading=20, alignment=TA_RIGHT))
        toc_rows.append([num_p, title_p, pg_p])

    toc_t = Table(toc_rows, colWidths=[1.5*cm, CW-3.5*cm, 2.0*cm])
    toc_t.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (2,0),(2,-1),  8),
        ("LINEBELOW",     (0,0),(-1,-2), 0.4, C["border"]),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [C["card"], C["alt"]]),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        # Right border before page number
        ("LINEBEFORE",    (2,0),(2,-1),  0.4, C["border"]),
    ]))
    story.append(toc_t)
    story.append(sp(12))
    story.append(insight_box(
        f"Report covers {n} risk(s) across {len(set(r.get('nist_function','') for r in risks if r.get('nist_function')))} "
        f"NIST CSF 2.0 functions. Overall posture: {posture}. "
        f"Average risk score: {avg_sc}. Generated by RiskCore GRC Platform v1.5."))
    # (PageBreak now in page_title())

    # ── 1. ORGANISATION SCOPE ────────────────────────────────────────────────
    story.append(anc("s1"))
    story += page_title("1.  Organisation Scope",
                        "Assessment context, scope boundaries, and organisational profile")
    scope = org_scope
    if not scope:
        story.append(Paragraph(
            "No Organisation Scope configured. Set up scope in the AI Analysis "
            "workspace before generating reports.", T["body"]))
    else:
        def sv(k): return scope.get(k) or "—"
        def sl(k):
            v = scope.get(k)
            return v if isinstance(v, list) else []

        story.append(Paragraph("Organisation Profile", T["h2"]))
        story.append(info_card([
            ("Organisation Name",  sv("organisation_name")),
            ("Industry",           sv("industry")),
            ("Organisation Size",  sv("organisation_size")),
            ("Business Function",  sv("business_function")),
        ]))
        story.append(sp(10))
        story.append(Paragraph("Assessment Details", T["h2"]))
        story.append(info_card([
            ("Assessment Name",      sv("assessment_name")),
            ("Assessment Type",      sv("assessment_type")),
            ("Objective",            sv("assessment_objective")),
            ("Report Date",          today()),
            ("Classification",       classification),
            ("Prepared By",          "RiskCore GRC Platform v1.5"),
        ]))
        story.append(sp(10))

        assets_ = sl("assets_in_scope")
        units_  = sl("business_units")
        if assets_ or units_:
            story.append(Paragraph("Scope Boundaries", T["h2"]))
            def buls(items):
                return ([Paragraph(f"• {x}", T["bul"]) for x in items]
                        or [Paragraph("Not specified.", T["sm"])])
            lc = [Paragraph("Assets in Scope", T["h3"])] + buls(assets_)
            rc = [Paragraph("Business Units",  T["h3"])] + buls(units_)
            mr = max(len(lc), len(rc))
            lc += [sp(1)] * (mr - len(lc))
            rc += [sp(1)] * (mr - len(rc))
            story.append(two_col(lc, rc))

    story.append(sp(10))
    story.append(insight_box(
        "Accurate scope definition is critical for a credible risk assessment. "
        "Ensure all in-scope assets, systems, and business units are documented "
        "to enable comprehensive framework coverage analysis."))
    # (PageBreak now in page_title())

    # ── 2. EXECUTIVE SUMMARY ─────────────────────────────────────────────────
    story.append(anc("s2"))
    story += page_title("2.  Executive Summary",
                        "Overall risk posture and key findings for executive leadership")

    # ── KPI Cards ────────────────────────────────────────────────────────────
    story.append(kpi_table([
        (n,           "Total Risks",    "#1B5FCF"),
        (len(crit_),  "Critical",       "#C0392B"),
        (len(high_),  "High",           "#D4560A"),
        (len(med_),   "Medium",         "#C78B00"),
        (len(low_),   "Low",            "#1A8C4E"),
    ]))
    story.append(sp(6))
    story.append(kpi_table([
        (open_c,    "Open",          "#C0392B"),
        (closed_c,  "Closed/Mitig.", "#1A8C4E"),
        (ai_c,      "AI Sourced",    "#5B4DB2"),
        (overdue,   "Overdue",       "#D4560A"),
        (no_mit,    "No Mitigation", "#C78B00"),
    ]))
    story.append(sp(14))

    # ─────────────────────────────────────────────────────────────────────────
    # Generate all consultant-quality narrative from register data
    # Every paragraph is data-driven — no generic filler
    # ─────────────────────────────────────────────────────────────────────────

    # Determine dominant NIST function for narrative
    dominant_fn  = nist_ctr.most_common(1)[0][0] if nist_ctr else "Protect"
    dominant_cnt = nist_ctr.most_common(1)[0][1] if nist_ctr else 0

    # Identify dominant attack themes from titles and descriptions
    titles_lower = " ".join(
        (r.get("title","") + " " + r.get("description","")).lower()
        for r in risks)

    themes = []
    if any(w in titles_lower for w in ("mfa","authenticat","credential","password","brute")):
        themes.append("identity and access management weaknesses")
    if any(w in titles_lower for w in ("patch","update","vulnerability","cve","unpatched")):
        themes.append("vulnerability and patch management deficiencies")
    if any(w in titles_lower for w in ("phish","awareness","training","social engineer")):
        themes.append("security awareness and human factor risks")
    if any(w in titles_lower for w in ("backup","recovery","restore","rto","bcp","disaster")):
        themes.append("data recovery and business continuity gaps")
    if any(w in titles_lower for w in ("firewall","network","segmentation","perimeter")):
        themes.append("network security control weaknesses")
    if any(w in titles_lower for w in ("ransomware","malware","encrypt","virus")):
        themes.append("malware and ransomware exposure")
    if any(w in titles_lower for w in ("insider","privilege","access control","least privilege")):
        themes.append("privileged access and insider threat risks")
    if any(w in titles_lower for w in ("gdpr","regulation","compliance","pii","privacy")):
        themes.append("regulatory compliance and data protection gaps")
    if not themes:
        themes.append("general cybersecurity control deficiencies")

    themes_str = (themes[0] if len(themes) == 1
                  else ", ".join(themes[:-1]) + f", and {themes[-1]}")

    # Governance gap language
    gov_gap = ""
    if no_mit > 0:
        gov_gap = (f" The absence of documented mitigation plans for "
                   f"{no_mit} of the identified risk{'s' if no_mit>1 else ''} "
                   f"suggests that governance processes require strengthening.")
    elif miss_fns:
        gov_gap = (f" Coverage gaps exist across the "
                   f"{', '.join(sorted(miss_fns))} function"
                   f"{'s' if len(miss_fns)>1 else ''} of NIST CSF 2.0, "
                   f"indicating areas of the security programme that require "
                   f"further assessment and documentation.")

    # Immediate priorities for narrative
    imm_priorities = []
    if any(w in titles_lower for w in ("mfa","authenticat","credential","password")):
        imm_priorities.append("privileged access protection")
    if any(w in titles_lower for w in ("patch","update","vulnerability")):
        imm_priorities.append("production patch management")
    if any(w in titles_lower for w in ("backup","recovery","restore")):
        imm_priorities.append("backup resilience and recovery validation")
    if any(w in titles_lower for w in ("firewall","network")):
        imm_priorities.append("network perimeter controls")
    if any(w in titles_lower for w in ("ransomware","malware")):
        imm_priorities.append("endpoint protection and ransomware defences")
    if not imm_priorities:
        imm_priorities = ["risk treatment planning", "control documentation"]

    imm_str = (imm_priorities[0] if len(imm_priorities) == 1
               else ", ".join(imm_priorities[:-1]) + f", and {imm_priorities[-1]}")

    # ── Posture Statement ────────────────────────────────────────────────────
    posture_desc = {
        "Critical": (
            f"The organisation's overall cyber risk posture is assessed as <b>CRITICAL</b>. "
            f"{len(crit_)} critical risk(s) demand immediate board escalation and executive "
            f"resourcing within 72 hours. Risk exposure at this level represents a material "
            f"threat to business continuity, regulatory standing, and reputational integrity. "
            f"Treatment plans must be assigned, funded, and actively monitored."),
        "High": (
            f"The organisation's overall cyber risk posture is assessed as <b>HIGH</b>. "
            f"{len(high_)} high-severity risk(s) require executive attention and documented "
            f"treatment plans within 30 days. Continued exposure without active remediation "
            f"increases the probability of a material security incident."),
        "Medium": (
            f"The organisation's overall cyber risk posture is assessed as <b>MEDIUM</b>. "
            f"No critical or high risks are currently registered. Sustained governance discipline "
            f"and quarterly review cycles are recommended to maintain this posture."),
        "Low": (
            f"The organisation's overall cyber risk posture is assessed as <b>LOW</b>. "
            f"The current register reflects a well-controlled environment. Continue monitoring, "
            f"conduct regular assessments, and maintain staff awareness programmes."),
        "Unknown": "No risks registered. Initiate risk capture to generate posture analysis.",
    }.get(posture, "")

    posture_box = Table(
        [[Paragraph(posture_desc,
                    PS("pd", fontName="Helvetica", fontSize=10.5,
                       textColor=C["white"], leading=16))]],
        colWidths=[CW])
    posture_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), p_col),
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
        ("LEFTPADDING",   (0,0),(-1,-1), 18),
        ("RIGHTPADDING",  (0,0),(-1,-1), 18),
    ]))
    story.append(posture_box)
    story.append(sp(14))

    # ── Consultant paragraph helper ──────────────────────────────────────────
    def _consultant_para(text):
        t = Table([[Paragraph(text,
                               PS(f"cp{abs(hash(text))%9999}",
                                  fontName="Helvetica", fontSize=10,
                                  textColor=C["body"], leading=16))
                   ]], colWidths=[CW])
        t.setStyle(TableStyle([
            ("LEFTPADDING",   (0,0),(-1,-1), 16),
            ("TOPPADDING",    (0,0),(-1,-1), 10),
            ("BOTTOMPADDING", (0,0),(-1,-1), 10),
            ("RIGHTPADDING",  (0,0),(-1,-1), 16),
            ("LINEBEFORE",    (0,0),(-1,-1), 3, C["blue"]),
            ("BACKGROUND",    (0,0),(-1,-1), C["bg"]),
            ("BOX",           (0,0),(-1,-1), 0.5, C["border"]),
        ]))
        return t

    def _finding_card(label, label_color, body_text):
        """Three-column card: label | body — used for Observed/Implication/Rec."""
        lbl_p = Paragraph(f"<b>{label}</b>",
                          PS(f"fl{label[:4]}", fontName="Helvetica-Bold",
                             fontSize=8, textColor=label_color,
                             leading=11, alignment=TA_CENTER))
        lbl_t = Table([[lbl_p]], colWidths=[2.2*cm])
        lbl_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), label_color),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ]))
        body_p = Paragraph(body_text,
                           PS(f"fb{abs(hash(body_text))%9999}",
                              fontName="Helvetica", fontSize=9.5,
                              textColor=C["body"], leading=14))
        row_t = Table([[lbl_t, body_p]],
                      colWidths=[2.4*cm, CW - 2.4*cm])
        row_t.setStyle(TableStyle([
            ("LEFTPADDING",   (0,0),(0,-1), 0),
            ("RIGHTPADDING",  (0,0),(0,-1), 8),
            ("LEFTPADDING",   (1,0),(1,-1), 10),
            ("RIGHTPADDING",  (1,0),(1,-1), 0),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LINEBELOW",     (0,0),(-1,-1), 0.3, C["border"]),
            ("BACKGROUND",    (1,0),(1,-1), C["alt"]),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        return row_t

    # ─── Pre-compute evidence counts used across all narrative sections ────────
    protect_cnt  = nist_ctr.get("Protect",  0)
    govern_cnt   = nist_ctr.get("Govern",   0)
    detect_cnt   = nist_ctr.get("Detect",   0)
    respond_cnt  = nist_ctr.get("Respond",  0)
    recover_cnt  = nist_ctr.get("Recover",  0)
    identify_cnt = nist_ctr.get("Identify", 0)
    prot_pct     = int(protect_cnt  / max(n, 1) * 100)
    gov_pct      = int(govern_cnt   / max(n, 1) * 100)
    det_pct      = int(detect_cnt   / max(n, 1) * 100)
    iso_mapped_n = sum(1 for r in risks if r.get("iso_domain"))
    iso_pct      = int(iso_mapped_n / max(n, 1) * 100)
    mit_doc_n    = n - no_mit
    mit_pct_str  = f"{int(mit_doc_n/max(n,1)*100)}%"
    mapped_mit_c = sum(1 for r in risks if r.get("mitre_tactic") and
                       r.get("mitre_tactic") != "Not Applicable")
    mapped_cis_c = sum(1 for r in risks if r.get("cis_control") and
                       r.get("cis_control") not in ("Not Applicable",""))
    total_tbi    = sum(float(r.get("total_business_impact") or 0) for r in risks)
    total_ttc    = sum(float(r.get("total_treatment_cost")  or 0) for r in risks)

    # ── ANALYST ASSESSMENT ───────────────────────────────────────────────────
    story.append(Paragraph("Analyst Assessment", T["h2"]))

    analyst_ai = (analysis or {}).get("analyst_summary","") if analysis else ""
    opening    = analyst_ai if analyst_ai else (
        f"Based on the information available at the time of this assessment, "
        f"the organisation's cybersecurity posture is assessed as {posture}.")

    # Evidence-cited concentration statement
    conc_evidence = (
        f"Based on {protect_cnt} of {n} identified risk{'s' if n!=1 else ''} "
        f"({prot_pct}%) being mapped to the NIST CSF 2.0 Protect function, "
        f"the highest concentration of risk exists in identity management, "
        f"vulnerability management, and access control.") if protect_cnt else ""

    gov_evidence = ""
    if no_mit > 0:
        gov_evidence = (
            f" {no_mit} of {n} risks ({int(no_mit/max(n,1)*100)}%) have no "
            f"documented mitigation plan, indicating that governance and "
            f"treatment planning processes require strengthening.")

    detect_evidence = ""
    if detect_cnt == 0 and n > 0:
        detect_evidence = (
            f" No risks are currently mapped to the Detect function of NIST CSF 2.0, "
            f"suggesting a gap in detection and monitoring capabilities that "
            f"may increase breach dwell time.")
    elif detect_cnt > 0:
        detect_evidence = (
            f" {detect_cnt} risk{'s' if detect_cnt!=1 else ''} "
            f"({int(detect_cnt/max(n,1)*100)}%) are mapped to the Detect function, "
            f"indicating known gaps in monitoring and anomaly detection.")

    imm_evidence = (f" Immediate attention should be directed toward {imm_str} "
                    f"to reduce exposure to the most probable attack vectors.")

    analyst_text = " ".join(filter(None, [
        opening, conc_evidence, gov_evidence, detect_evidence, imm_evidence]))

    story.append(_consultant_para(xe(analyst_text)))
    story.append(sp(10))

    # ── OBSERVED FINDINGS | RISK IMPLICATIONS | RECOMMENDATIONS ─────────────
    story.append(Paragraph("Findings, Implications, and Recommendations", T["h2"]))
    story.append(Paragraph(
        "The following table separates observed findings (facts from the register) "
        "from their risk implications (what those facts mean for the business) "
        "and specific recommendations (what should be done).",
        T["sm"]))
    story.append(sp(6))

    # Table header
    fir_hdr = Table([[
        Paragraph("<b>Category</b>", T["th"]),
        Paragraph("<b>Detail</b>",   T["th"]),
    ]], colWidths=[2.4*cm, CW-2.4*cm])
    fir_hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), C["navy"]),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(fir_hdr)

    # Build findings dynamically from register data
    fir_rows = []

    # ── Observed Findings ────────────────────────────────────────────────────
    fir_rows.append(_finding_card(
        "OBSERVED", C["blue"],
        f"{n} risk{'s' if n!=1 else ''} assessed: "
        f"{len(crit_)} Critical, {len(high_)} High, "
        f"{len(med_)} Medium, {len(low_)} Low. "
        f"Average inherent score: {avg_sc}. Maximum inherent score: {max_sc}."))

    if protect_cnt > 0:
        fir_rows.append(_finding_card(
            "OBSERVED", C["blue"],
            f"{protect_cnt} of {n} risks ({int(protect_cnt/max(n,1)*100)}%) "
            f"concentrated in NIST CSF 2.0 Protect function — the largest single "
            f"function cluster in this assessment."))

    if miss_fns:
        fir_rows.append(_finding_card(
            "OBSERVED", C["blue"],
            f"NIST CSF 2.0 functions with no mapped risks: "
            f"{', '.join(sorted(miss_fns))}. "
            f"This represents {len(miss_fns)} of 6 functions "
            f"({int(len(miss_fns)/6*100)}%) with no assessed exposure."))

    if no_mit > 0:
        fir_rows.append(_finding_card(
            "OBSERVED", C["blue"],
            f"{no_mit} of {n} risks ({int(no_mit/max(n,1)*100)}%) "
            f"have no documented mitigation plan at the time of this assessment."))

    if overdue > 0:
        fir_rows.append(_finding_card(
            "OBSERVED", C["blue"],
            f"{overdue} risk{'s' if overdue!=1 else ''} "
            f"have passed their scheduled review date without update, "
            f"indicating a gap in register governance and review cadence."))

    if mitre_ctr:
        top_tactic = mitre_ctr.most_common(1)[0]
        fir_rows.append(_finding_card(
            "OBSERVED", C["blue"],
            f"MITRE ATT&CK tactic most represented: {top_tactic[0]} "
            f"({top_tactic[1]} risk{'s' if top_tactic[1]!=1 else ''}). "
            f"{mapped_mit_c} of {n} risks ({int(mapped_mit_c/max(n,1)*100)}%) "
            f"mapped to adversary tactics."))

    # ── Risk Implications ────────────────────────────────────────────────────
    fir_rows.append(_finding_card(
        "IMPLICATION", C["high"],
        f"An overall posture of <b>{posture}</b> indicates that the organisation "
        f"faces{'a material' if posture in ('Critical','High') else ' moderate'} "
        f"probability of a security incident if identified risks are not treated. "
        f"The risk register, as assessed, reflects an organisation that requires "
        f"{'immediate' if posture == 'Critical' else 'structured'} "
        f"remediation activity."))

    if crit_:
        fir_rows.append(_finding_card(
            "IMPLICATION", C["high"],
            f"{len(crit_)} Critical risk{'s' if len(crit_)>1 else ''} "
            f"(score ≥ 15) represent the highest tier of inherent exposure. "
            f"At this severity level, the probability of exploitation — combined "
            f"with the potential business impact — justifies immediate "
            f"board-level escalation and resourcing."))

    if no_mit > 0:
        fir_rows.append(_finding_card(
            "IMPLICATION", C["high"],
            f"The absence of mitigation documentation for {no_mit} risk"
            f"{'s' if no_mit>1 else ''} means that residual risk cannot be "
            f"assessed for those items. From a governance perspective, "
            f"undocumented risks cannot be effectively tracked, escalated, "
            f"or demonstrated to auditors or regulators."))

    if "Detect" in miss_fns:
        fir_rows.append(_finding_card(
            "IMPLICATION", C["high"],
            "The absence of risks mapped to the Detect function suggests "
            "that detection and monitoring capabilities have not been "
            "formally assessed. This increases the risk of extended breach "
            "dwell time — the global average is 258 days "
            "(IBM Cost of a Data Breach 2024)."))

    # ── Recommendations ──────────────────────────────────────────────────────
    if crit_:
        fir_rows.append(_finding_card(
            "RECOMMENDATION", C["low"],
            f"Assign named executive owners to all {len(crit_)} Critical risk"
            f"{'s' if len(crit_)>1 else ''} and initiate treatment plans within "
            f"72 hours. Report progress to board within 14 days."))

    if high_:
        fir_rows.append(_finding_card(
            "RECOMMENDATION", C["low"],
            f"Document and fund treatment plans for {len(high_)} High severity "
            f"risk{'s' if len(high_)>1 else ''} within 30 days. "
            f"Assign measurable milestones and a named risk owner for each."))

    if no_mit > 0:
        fir_rows.append(_finding_card(
            "RECOMMENDATION", C["low"],
            f"Complete mitigation documentation for all {no_mit} undocumented "
            f"risk{'s' if no_mit>1 else ''} before the next assessment cycle. "
            f"This is a prerequisite for ISO 27001:2022 compliance and "
            f"external audit readiness."))

    if miss_fns:
        fir_rows.append(_finding_card(
            "RECOMMENDATION", C["low"],
            f"Conduct targeted risk identification workshops for uncovered "
            f"NIST CSF 2.0 functions: "
            f"{', '.join(sorted(miss_fns))}. "
            f"Assign risk owners and document findings in the register within "
            f"60 days."))

    for row in fir_rows:
        story.append(row)
    story.append(sp(10))

    # ── OVERALL RISK NARRATIVE ───────────────────────────────────────────────
    story.append(Paragraph("Overall Risk Narrative", T["h2"]))

    # Build attack techniques from register data (computed here for narrative)
    attack_techniques = []
    if any(w in titles_lower for w in ("credential","mfa","password","authenticat")):
        attack_techniques.append("credential theft and authentication bypass")
    if any(w in titles_lower for w in ("phish","social engineer","awareness")):
        attack_techniques.append("phishing and social engineering")
    if any(w in titles_lower for w in ("privilege","insider","access control")):
        attack_techniques.append("privilege abuse and lateral movement")
    if any(w in titles_lower for w in ("patch","vulnerability","cve","exploit","unpatched")):
        attack_techniques.append("exploitation of unpatched vulnerabilities")
    if any(w in titles_lower for w in ("ransomware","malware","virus")):
        attack_techniques.append("malware deployment and ransomware")
    if not attack_techniques:
        attack_techniques = ["common cyber attack techniques"]

    att_str = (attack_techniques[0] if len(attack_techniques) == 1
               else ", ".join(attack_techniques[:-1]) + f", and {attack_techniques[-1]}")

    ctrl_gaps = []
    if "Govern" in miss_fns or "Identify" in miss_fns:
        ctrl_gaps.append("governance and risk identification")
    if "Detect" in miss_fns:
        ctrl_gaps.append("detection and monitoring")
    if "Respond" in miss_fns or "Recover" in miss_fns:
        ctrl_gaps.append("incident response and recovery")
    if no_mit > 0:
        ctrl_gaps.append("treatment planning and control documentation")
    gap_str = (", ".join(ctrl_gaps) if ctrl_gaps
               else "several critical control areas")

    narrative_text = (
        f"Based on the {n} risk{'s' if n!=1 else ''} assessed, the current risk "
        f"profile indicates that the organisation is vulnerable to {att_str}. "
        f"While existing controls provide a degree of protection "
        f"({mit_doc_n} of {n} risks have documented mitigations), "
        f"significant gaps remain across {gap_str}. "
        f"With an average inherent score of {avg_sc} and {len(crit_)} risk"
        f"{'s' if len(crit_)!=1 else ''} in the Critical tier, "
        f"the organisation is placed in the <b>{posture}</b> risk tier. "
        f"Continued operation without remediation increases the likelihood of "
        f"operational disruption, regulatory penalties, financial loss, and "
        f"reputational damage. "
        f"This assessment reflects a point-in-time view of the risk register; "
        f"the actual threat landscape may present additional exposure "
        f"not yet captured in the register."
    )
    story.append(_consultant_para(xe(narrative_text)))
    story.append(sp(10))

    # ── KEY FINDINGS ─────────────────────────────────────────────────────────
    story.append(Paragraph("Key Findings", T["h2"]))
    findings = []
    if crit_:
        findings.append(
            f"{len(crit_)} Critical risk{'s' if len(crit_)>1 else ''} "
            f"(score ≥ 15) — immediate board escalation required")
    if high_:
        findings.append(
            f"{len(high_)} High severity risk{'s' if len(high_)>1 else ''} "
            f"— treatment plans required within 30 days")
    if no_mit:
        findings.append(
            f"{no_mit} of {n} risks ({int(no_mit/max(n,1)*100)}%) "
            f"have no documented mitigation plan")
    if overdue:
        findings.append(
            f"{overdue} risk{'s' if overdue>1 else ''} "
            f"overdue for scheduled review")
    if miss_fns:
        findings.append(
            f"NIST CSF 2.0 gaps: {', '.join(sorted(miss_fns))} "
            f"— {len(miss_fns)} of 6 functions unassessed")
    if ai_c:
        findings.append(
            f"{ai_c} risk{'s' if ai_c>1 else ''} "
            f"surfaced through AI document analysis")
    if not findings:
        findings.append("No immediate action items — maintain current control posture")
    for f_ in findings:
        story.append(Paragraph(f"• {f_}", T["bul"]))
    story.append(sp(12))

    # ── BUSINESS IMPACT ANALYSIS ─────────────────────────────────────────────
    story.append(Paragraph("Business Impact Analysis", T["h2"]))
    story.append(Paragraph(
        "If the identified risks remain untreated, the organisation could experience "
        "the following impacts. Where industry benchmarks are referenced, they are "
        "cited for context only — actual costs will depend on the organisation's "
        "size, operations, sector, and existing controls.",
        T["sm"]))
    story.append(sp(6))

    impact_items = []

    # Financial exposure from register (if populated)
    if total_tbi > 0:
        impact_items.append(
            f"Estimated total financial exposure across all assessed risks: "
            f"<b>${total_tbi:,.0f}</b> (based on cost analysis entered in the "
            f"risk register). Estimated treatment investment: ${total_ttc:,.0f}.")

    if crit_ or high_:
        impact_items.append(
            "Extended operational downtime affecting revenue, productivity, "
            "and customer commitments.")

    if any(w in titles_lower for w in ("gdpr","regulation","compliance","pii","data protection")):
        impact_items.append(
            "Regulatory investigations, mandatory breach notifications, and "
            "potential fines under GDPR (up to 4% of global annual turnover), "
            "PCI-DSS, or other applicable legislation.")
    else:
        impact_items.append(
            "Regulatory investigations and potential fines from sector regulators "
            "or data protection authorities.")

    impact_items.append(
        "Loss of customer and stakeholder confidence, with long-term impact "
        "on client retention and market position.")

    impact_items.append(
        "Increased cyber insurance premiums or potential loss of coverage "
        "following a notifiable incident.")

    if any(w in titles_lower for w in ("ransomware","malware","backup","recovery")):
        impact_items.append(
            "Recovery and remediation costs significantly exceeding proactive "
            "treatment investment. For context, industry studies report average "
            "ransomware recovery costs of approximately $2.73M "
            "(Sophos State of Ransomware 2024). Actual costs for this "
            "organisation will depend on its size, operations, and controls.")
    else:
        impact_items.append(
            "Recovery and remediation costs significantly exceeding the "
            "investment required for proactive treatment.")

    impact_items.append(
        "Potential legal liabilities following a reportable breach, "
        "including class-action exposure and regulatory enforcement action.")

    if any(w in titles_lower for w in ("third","vendor","supplier","supply chain")):
        impact_items.append(
            "Supply chain disruption if vendor or third-party systems are "
            "compromised, with downstream impact on business operations.")

    impact_items.append(
        "Intellectual property theft or competitive intelligence exposure "
        "if adversaries achieve persistent access to internal systems.")

    for item in impact_items:
        story.append(Paragraph(f"• {item}", T["bul"]))
    story.append(sp(12))

    # ── BOARD RECOMMENDATIONS ─────────────────────────────────────────────────
    story.append(Paragraph("Board Recommendations", T["h2"]))

    board_recs = []
    rec_num = 1

    if crit_:
        board_recs.append(
            f"{rec_num}. Approve funding for the immediate remediation of "
            f"{len(crit_)} Critical risk{'s' if len(crit_)>1 else ''} — "
            f"treatment plans to be initiated within 72 hours and reported "
            f"to the board within 14 days.")
        rec_num += 1

    board_recs.append(
        f"{rec_num}. Assign named executive ownership for each risk treatment "
        f"plan, with defined accountability, authority, and escalation paths.")
    rec_num += 1

    board_recs.append(
        f"{rec_num}. Mandate monthly progress reporting to the board or audit "
        f"committee until all Critical and High risks are reduced to an "
        f"accepted residual level, as defined by the organisation's risk appetite.")
    rec_num += 1

    if any(w in titles_lower for w in ("patch","vulnerability","mfa","authenticat")):
        board_recs.append(
            f"{rec_num}. Commission an independent penetration test after "
            f"primary remediation is complete, to validate control effectiveness "
            f"and identify residual exposure not visible in the risk register.")
        rec_num += 1

    board_recs.append(
        f"{rec_num}. Review and formally approve the organisation's cyber risk "
        f"appetite and tolerance thresholds, providing a benchmark against "
        f"which future assessments can be calibrated.")
    rec_num += 1

    board_recs.append(
        f"{rec_num}. Confirm that cyber insurance coverage is adequate and "
        f"that policy limits reflect the estimated financial exposure "
        f"identified in this assessment.")
    rec_num += 1

    board_recs.append(
        f"{rec_num}. Schedule a follow-up risk assessment within 90 days to "
        f"verify treatment progress and formally re-evaluate the organisation's "
        f"risk posture.")

    board_box = Table(
        [[Paragraph(rec,
                    PS(f"br{i}", fontName="Helvetica", fontSize=9.5,
                       textColor=C["body"], leading=15))
         ] for i, rec in enumerate(board_recs)],
        colWidths=[CW])
    board_box.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), C["bg"]),
        ("LEFTPADDING",   (0,0),(-1,-1), 16),
        ("RIGHTPADDING",  (0,0),(-1,-1), 16),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LINEBELOW",     (0,0),(-1,-2), 0.4, C["border"]),
        ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        ("LINEBEFORE",    (0,0),(-1,-1), 3, C["navy"]),
    ]))
    story.append(board_box)
    story.append(sp(12))

    # ── ANALYST CONFIDENCE ────────────────────────────────────────────────────
    story.append(Paragraph("Analyst Confidence", T["h2"]))
    story.append(Paragraph(
        "Confidence reflects the completeness and quality of the available "
        "assessment data. It does not represent the probability of a cyber incident "
        "occurring — it indicates how well-evidenced the conclusions in this report "
        "are, based on the data present in the risk register at the time of generation.",
        T["sm"]))
    story.append(sp(8))

    # Score calculation — transparent, documented
    conf_score    = 0
    conf_factors  = []
    conf_deductions = []

    # 1. Risk volume
    if n >= 10:
        conf_score += 20
        conf_factors.append(
            f"Risk volume: {n} risks assessed — statistically reliable posture picture")
    elif n >= 5:
        conf_score += 15
        conf_factors.append(
            f"Risk volume: {n} risks assessed — adequate for posture assessment")
    elif n >= 1:
        conf_score += 8
        conf_deductions.append(
            f"Risk volume: only {n} risk{'s' if n!=1 else ''} assessed — "
            f"further risk identification is recommended")

    # 2. NIST CSF coverage
    covered_fn_count = len(all_fns - miss_fns)
    fn_pct2 = int(covered_fn_count / 6 * 100)
    if fn_pct2 >= 80:
        conf_score += 20
        conf_factors.append(
            f"NIST CSF 2.0: {fn_pct2}% of functions mapped "
            f"({covered_fn_count}/6) — strong framework coverage")
    elif fn_pct2 >= 50:
        conf_score += 12
        conf_factors.append(
            f"NIST CSF 2.0: {fn_pct2}% of functions mapped "
            f"({covered_fn_count}/6) — partial framework coverage")
    else:
        conf_score += 5
        conf_deductions.append(
            f"NIST CSF 2.0: only {fn_pct2}% of functions mapped "
            f"({covered_fn_count}/6) — framework coverage limits analysis depth")

    # 3. Multi-framework mapping
    fw_mapped2 = sum([
        1 if iso_mapped_n / max(n,1) >= 0.7 else 0,
        1 if mapped_mit_c / max(n,1) >= 0.5 else 0,
        1 if mapped_cis_c / max(n,1) >= 0.5 else 0,
    ])
    if fw_mapped2 >= 3:
        conf_score += 20
        conf_factors.append(
            f"Framework mapping: ISO 27001, MITRE ATT&CK, and CIS Controls all "
            f"mapped at sufficient coverage — cross-framework validation achieved")
    elif fw_mapped2 >= 2:
        conf_score += 13
        conf_factors.append(
            f"Framework mapping: {fw_mapped2}/3 additional frameworks mapped at "
            f"sufficient coverage — partial cross-framework validation")
    elif fw_mapped2 >= 1:
        conf_score += 6
        conf_deductions.append(
            f"Framework mapping: only {fw_mapped2}/3 additional frameworks "
            f"(ISO 27001, MITRE ATT&CK, CIS Controls) at sufficient coverage")
    else:
        conf_deductions.append(
            "Framework mapping: ISO 27001, MITRE ATT&CK, and CIS Controls not "
            "mapped at sufficient coverage — cross-framework validation limited")

    # 4. Mitigation documentation
    mit_pct2 = int(mit_doc_n / max(n,1) * 100)
    if mit_pct2 >= 80:
        conf_score += 20
        conf_factors.append(
            f"Mitigation documentation: {mit_pct2}% of risks documented "
            f"({mit_doc_n}/{n}) — supports residual risk assessment")
    elif mit_pct2 >= 50:
        conf_score += 12
        conf_factors.append(
            f"Mitigation documentation: {mit_pct2}% of risks documented "
            f"({mit_doc_n}/{n}) — partial coverage")
    else:
        conf_score += 5
        conf_deductions.append(
            f"Mitigation documentation: only {mit_pct2}% of risks documented "
            f"({mit_doc_n}/{n}) — residual risk cannot be fully assessed")

    # 5. Evidence source
    if ai_c > 0:
        conf_score += 10
        conf_factors.append(
            f"Evidence: {ai_c} risk{'s' if ai_c!=1 else ''} validated through "
            f"AI document analysis — evidence-backed indicators present")
    else:
        conf_score += 7
        conf_factors.append(
            "Evidence: all risks captured through manual analyst review — "
            "human judgement underpins the assessment")

    # 6. Register currency
    if overdue == 0:
        conf_score += 10
        conf_factors.append(
            "Register currency: all risks within scheduled review dates — "
            "register is current at time of assessment")
    else:
        conf_score -= 5
        conf_deductions.append(
            f"Register currency: {overdue} risk{'s' if overdue!=1 else ''} "
            f"overdue for review — register may not fully reflect current posture")

    conf_score = max(40, min(conf_score, 97))
    conf_label = ("High"   if conf_score >= 80 else
                  "Medium" if conf_score >= 60 else "Low")
    conf_color = (C["low"] if conf_score >= 80 else
                  C["med"] if conf_score >= 60 else C["crit"])

    # Confidence header card
    conf_hdr = Table([[
        Paragraph(
            f"Overall Confidence:  <b>{conf_label}  ({conf_score}%)</b>",
            PS("ch", fontName="Helvetica-Bold", fontSize=13,
               textColor=conf_color, leading=16)),
    ]], colWidths=[CW])
    conf_hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), C["bg"]),
        ("TOPPADDING",    (0,0),(-1,-1), 12),
        ("BOTTOMPADDING", (0,0),(-1,-1), 12),
        ("LEFTPADDING",   (0,0),(-1,-1), 16),
        ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        ("LINEBEFORE",    (0,0),(-1,-1), 4, conf_color),
    ]))
    story.append(conf_hdr)
    story.append(sp(8))

    story.append(Paragraph("Factors supporting confidence:", T["h4"]))
    for factor in conf_factors:
        story.append(Paragraph(f"✓  {factor}", T["bul"]))
    if conf_deductions:
        story.append(sp(4))
        story.append(Paragraph("Factors reducing confidence:", T["h4"]))
        for ded in conf_deductions:
            story.append(Paragraph(f"⚠  {ded}", T["bul"]))

    story.append(sp(8))
    story.append(insight_box(
        "Confidence will increase as framework mapping is completed, mitigation "
        "plans are documented, and the register is reviewed on a regular cadence. "
        "An independent penetration test or third-party audit would provide "
        "additional assurance beyond what automated register analysis can deliver."))
    story.append(sp(10))

    # ── EVIDENCE SUMMARY ─────────────────────────────────────────────────────
    story.append(Paragraph("Evidence Summary", T["h2"]))
    story.append(Paragraph(
        "This table provides immediate context for the analysis presented in this report.",
        T["sm"]))
    story.append(sp(6))

    fw_list = []
    if nist_ctr:   fw_list.append("NIST CSF 2.0")
    if iso_ctr:    fw_list.append("ISO/IEC 27001:2022")
    if mitre_ctr:  fw_list.append("MITRE ATT&CK")
    if cis_ctr:    fw_list.append("CIS Controls v8")
    if cia_ctr:    fw_list.append("CIA Triad")
    fw_str = ", ".join(fw_list) if fw_list else "Not yet mapped"

    org_name_ev = ((org_scope or {}).get("organisation_name") or company_name or "—")
    a_type_ev   = ((org_scope or {}).get("assessment_type") or "Manual Register Assessment")
    a_name_ev   = ((org_scope or {}).get("assessment_name") or "Cyber Risk Assessment")

    ev_rows = [
        ("Risks Assessed",            str(n)),
        ("Critical Risks",            str(len(crit_))),
        ("High Risks",                str(len(high_))),
        ("Medium Risks",              str(len(med_))),
        ("Low Risks",                 str(len(low_))),
        ("Frameworks Analysed",       fw_str),
        ("Treatments Documented",     f"{mit_doc_n}/{n}  ({int(mit_doc_n/max(n,1)*100)}%)"),
        ("AI-Sourced Risks",          str(ai_c)),
        ("Overdue Reviews",           str(overdue)),
        ("Average Inherent Score",    str(avg_sc)),
        ("Maximum Inherent Score",    str(max_sc)),
        ("Report Generated",          f"{today()} at {now()}"),
        ("Assessment Name",           a_name_ev),
        ("Assessment Type",           a_type_ev),
        ("Organisation",              org_name_ev),
        ("Classification",            classification),
        ("Report Version",            "RiskCore GRC Platform v1.5"),
    ]

    ev_data = [
        [Paragraph(k, T["td_m"]), Paragraph(str(v), T["td"])]
        for k, v in ev_rows]
    ev_t = Table(ev_data, colWidths=[5.5*cm, CW - 5.5*cm])
    ev_ts = [
        ("BACKGROUND",    (0,0),(0,-1), C["bg"]),
        ("FONTNAME",      (0,0),(0,-1), "Helvetica-Bold"),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("LINEBELOW",     (0,0),(-1,-2), 0.3, C["border"]),
        ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        ("ROWBACKGROUNDS",(1,0),(1,-1), [C["card"], C["alt"]]),
    ]
    # Highlight critical row
    for i, (k, _) in enumerate(ev_rows):
        if "Critical" in k:
            ev_ts.append(("TEXTCOLOR", (1,i),(1,i), C["crit"]))
            ev_ts.append(("FONTNAME",  (1,i),(1,i), "Helvetica-Bold"))
    ev_t.setStyle(TableStyle(ev_ts))
    story.append(ev_t)
    # (PageBreak now in page_title())

    # ── 3. RISK ANALYTICS ────────────────────────────────────────────────────
    story.append(anc("s3"))
    story += page_title("3.  Risk Analytics",
                        "Visual breakdown of risk distribution, ownership, and trends")

    # Donut + NIST bar
    sev_d  = [len(crit_), len(high_), len(med_), len(low_)]
    sev_l  = ["Critical","High","Medium","Low"]
    sev_c  = [C["crit"], C["high"], C["med"], C["low"]]
    donut_ = donut_chart(sev_d, sev_l, sev_c, width=int(COL2+18),
                          title="Severity Distribution")

    nist_ord  = ["Govern","Identify","Protect","Detect","Respond","Recover"]
    nist_cols = [cn("#1B5E20"),cn("#1565C0"),cn("#2E7D32"),
                 cn("#E65100"),cn("#880E4F"),cn("#4A148C")]
    nist_vals = [nist_ctr.get(f, 0) for f in nist_ord]
    nist_bar_ = horiz_bars(nist_vals, nist_ord, nist_cols,
                            width=int(COL2+18), height=130,
                            title="NIST CSF Function Distribution")

    story.append(two_col([donut_], [nist_bar_]))
    story.append(sp(10))

    # Status distribution
    story.append(Paragraph("Risk Status Distribution", T["h2"]))
    st_items = list(status_ctr.items())
    st_cols  = [C["crit"],C["low"],C["blue"],C["med"],C["muted"]][:len(st_items)]
    if st_items:
        story.append(horiz_bars([v for _,v in st_items],
                                [k for k,_ in st_items], st_cols,
                                height=max(60, len(st_items)*24+20)))
    story.append(sp(8))

    # CIA + Top owners side by side
    cia_items = list(cia_ctr.items())
    cia_c_    = [C["blue"],C["low"],C["med"],C["purple"]][:len(cia_items)]
    own_items = owner_ctr.most_common(6)
    own_c_    = [C["blue"]] * len(own_items)

    if cia_items or own_items:
        lc_ = ([Paragraph("CIA Triad Distribution", T["h3"]),
                horiz_bars([v for _,v in cia_items],
                           [k for k,_ in cia_items], cia_c_,
                           width=int(COL2), height=max(60,len(cia_items)*24+20))]
               if cia_items else [sp(1)])
        rc_ = ([Paragraph("Top Risk Owners", T["h3"]),
                horiz_bars([v for _,v in own_items],
                           [k[:16] for k,_ in own_items], own_c_,
                           width=int(COL2), height=max(60,len(own_items)*24+20))]
               if own_items else [sp(1)])
        story.append(two_col(lc_, rc_))
    story.append(sp(8))

    # Category distribution
    if cat_ctr:
        story.append(Paragraph("Risk Category Distribution", T["h2"]))
        cat_items = cat_ctr.most_common()
        story.append(horiz_bars([v for _,v in cat_items],
                                [k for k,_ in cat_items],
                                [C["blue_mid"]]*len(cat_items),
                                height=max(60, len(cat_items)*24+20)))
        story.append(sp(8))

    # MITRE distribution
    if mitre_ctr:
        story.append(Paragraph("MITRE ATT&CK Tactic Coverage", T["h2"]))
        mt_top = mitre_ctr.most_common(8)
        story.append(horiz_bars([v for _,v in mt_top],
                                [k[:30] for k,_ in mt_top],
                                [C["crit"]]*len(mt_top),
                                height=max(70, len(mt_top)*24+20)))

    story.append(sp(8))
    story.append(insight_box(
        f"Severity: {len(crit_)} Critical, {len(high_)} High, "
        f"{len(med_)} Medium, {len(low_)} Low. "
        f"Average score: {avg_sc}. Highest score: {max_sc}. "
        f"Median score: {med_sc}. "
        + (f"Most exposed NIST function: {nist_ctr.most_common(1)[0][0]} "
           f"({nist_ctr.most_common(1)[0][1]} risks). " if nist_ctr else "")
        + (f"Primary CIA impact: {cia_ctr.most_common(1)[0][0]}." if cia_ctr else "")))
    # (PageBreak now in page_title())

    # ── 4. RISK HEAT MAP ─────────────────────────────────────────────────────
    story.append(anc("s4"))
    story += page_title("4.  Risk Heat Map",
                        "5×5 NIST SP 800-30 Rev 1 Likelihood × Impact matrix")
    story.append(Paragraph(
        "The heat map visualises assessed risks across the NIST SP 800-30 Rev 1 "
        "5×5 scoring matrix. Cell colour reflects inherent risk severity. "
        "Numbers in brackets show how many risks sit at that coordinate. "
        "Darker red cells represent the highest priority areas for treatment. "
        "Multiple risks in a single cell indicate a systemic control gap.",
        T["body"]))
    story.append(sp(8))
    story.append(heat_map_drawing(cell_scores))
    story.append(sp(10))

    leg_data = [[
        Table([[Paragraph("<b>CRITICAL  ≥ 15</b>",
                          PS("lc",fontName="Helvetica-Bold",fontSize=7.5,
                             textColor=C["white"],leading=9,alignment=TA_CENTER))]],
               colWidths=[2.5*cm]),
        Table([[Paragraph("<b>HIGH  10–14</b>",
                          PS("lh",fontName="Helvetica-Bold",fontSize=7.5,
                             textColor=C["white"],leading=9,alignment=TA_CENTER))]],
               colWidths=[2.5*cm]),
        Table([[Paragraph("<b>MEDIUM  5–9</b>",
                          PS("lm",fontName="Helvetica-Bold",fontSize=7.5,
                             textColor=C["white"],leading=9,alignment=TA_CENTER))]],
               colWidths=[2.5*cm]),
        Table([[Paragraph("<b>LOW  1–4</b>",
                          PS("ll",fontName="Helvetica-Bold",fontSize=7.5,
                             textColor=C["white"],leading=9,alignment=TA_CENTER))]],
               colWidths=[2.5*cm]),
    ]]
    for badge, col_ in zip(leg_data[0],
                           [C["crit"],C["high"],C["med"],C["low"]]):
        badge.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),col_),
            ("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
    leg_t = Table(leg_data, colWidths=[2.5*cm]*4)
    leg_t.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),
                                ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(leg_t)
    story.append(sp(10))
    story.append(info_card([
        ("Likelihood",    "1=Rare  2=Unlikely  3=Possible  4=Likely  5=Almost Certain"),
        ("Impact",        "1=Negligible  2=Minor  3=Moderate  4=Major  5=Critical"),
        ("Score Formula", "Inherent Risk Score = Likelihood × Impact  (Range: 1–25)"),
        ("Critical Zone", f"Scores ≥ 15 — top-right cells — {len(crit_)} risk(s) require immediate treatment"),
    ]))
    # (PageBreak now in page_title())

    # ── 5. RISK REGISTER ─────────────────────────────────────────────────────
    story.append(anc("s5"))
    story += page_title("5.  Risk Register",
                        f"Complete register — {n} risk(s) sorted by descending score")
    if not risks:
        story.append(Paragraph("No risks currently registered.", T["body"]))
    else:
        hdrs   = ["#","Score","Title","NIST","CIA","Owner","Status"]
        widths = [0.6*cm,1.6*cm,7.2*cm,1.8*cm,2.0*cm,2.8*cm,1.4*cm]
        rows_  = []
        for idx, r in enumerate(sorted(risks, key=lambda x: sc(x), reverse=True), 1):
            s_ = sc(r)
            rows_.append([
                Paragraph(str(idx), T["td_m"]),
                Paragraph(f"<b>{s_}</b>  {sev_label(s_)}",
                          PS(f"rs{idx}", fontName="Helvetica-Bold",
                             fontSize=8.5, textColor=sev_color(s_),
                             leading=11, alignment=TA_CENTER)),
                Paragraph(xe(r.get("title","—"))[:70], T["td"]),
                Paragraph(xe(r.get("nist_function","—"))[:12], T["td_l"]),
                Paragraph(xe(r.get("cia_component","—"))[:15], T["td"]),
                Paragraph(xe(r.get("owner","—"))[:22], T["td"]),
                Paragraph(str(r.get("status","—")),
                          PS(f"rst{idx}", fontName="Helvetica-Bold",
                             fontSize=8, textColor=(C["low"] if str(r.get("status",""))
                             .lower() in ("mitigated","closed","verified")
                             else C["crit"]), leading=10)),
            ])

        reg_t = Table([
            [Paragraph(h, T["th"]) for h in hdrs]
        ] + rows_, colWidths=widths, repeatRows=1)
        reg_styles = [
            ("BACKGROUND",    (0,0),(-1,0), C["navy"]),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
            ("LINEBELOW",     (0,0),(-1,-2), 0.3, C["border"]),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [C["card"], C["alt"]]),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        ]
        # Score+sev column background
        for i, r in enumerate(sorted(risks, key=lambda x: sc(x), reverse=True), 1):
            reg_styles.append(("BACKGROUND", (1,i),(1,i), sev_bg(sc(r))))
        reg_t.setStyle(TableStyle(reg_styles))
        story.append(reg_t)

    story.append(sp(10))
    story.append(insight_box(
        f"Register sorted by descending inherent risk score. "
        + (f"Highest-scored risk: '{xe(str(risks[0].get('title','?')))}' "
           f"(score {sc(risks[0])}, {sev_label(sc(risks[0]))}). "
           if risks else "")
        + "Ensure every Open risk has an assigned owner and a target review date."))
    # (PageBreak now in page_title())

    # ── 6. DETAILED RISK PROFILES ────────────────────────────────────────────
    story.append(anc("s6"))
    story += page_title("6.  Detailed Risk Profiles",
                        "Individual risk assessment cards with full intelligence mapping")
    story.append(sp(6))

    lik_lbl = {1:"Rare",2:"Unlikely",3:"Possible",4:"Likely",5:"Almost Certain"}
    imp_lbl = {1:"Negligible",2:"Minor",3:"Moderate",4:"Major",5:"Critical"}

    for r in sorted(risks, key=lambda x: sc(x), reverse=True):
        s_    = sc(r)
        sl_   = sev_label(s_)
        sc_   = sev_color(s_)
        lik_  = int(r.get("likelihood") or 0)
        imp_  = int(r.get("impact") or 0)

        # Header band
        hdr_t = Table([[
            Paragraph(f"<b>Risk #{r.get('id','?')}</b>  ·  {sl_}  ·  Score {s_}",
                      PS(f"rph{r.get('id')}", fontName="Helvetica-Bold",
                         fontSize=10.5, textColor=C["white"], leading=14)),
            Paragraph(xe(r.get("title","Untitled"))[:80],
                      PS(f"rpt{r.get('id')}", fontName="Helvetica",
                         fontSize=10, textColor=cn("#E8EDF5"), leading=13)),
        ]], colWidths=[5*cm, CW-5*cm])
        hdr_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), sc_),
            ("TOPPADDING",    (0,0),(-1,-1), 9),
            ("BOTTOMPADDING", (0,0),(-1,-1), 9),
            ("LEFTPADDING",   (0,0),(-1,-1), 12),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))

        # Description row
        if r.get("description"):
            desc_t = Table([[
                Paragraph("Description", T["td_m"]),
                Paragraph(xe(r.get("description","") or "No description provided")[:400], T["td"]),
            ]], colWidths=[3.5*cm, CW-3.5*cm])
            desc_t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(0,-1), C["bg"]),
                ("FONTNAME",      (0,0),(0,-1), "Helvetica-Bold"),
                ("TOPPADDING",    (0,0),(-1,-1), 7),
                ("BOTTOMPADDING", (0,0),(-1,-1), 7),
                ("LEFTPADDING",   (0,0),(-1,-1), 10),
                ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
            ]))
        else:
            desc_t = sp(1)

        # Two-column detail
        dcol_w = (CW-8)/2
        left_rows = [
            ("Owner",          xe(r.get("owner") or "—")),
            ("Category",       xe(r.get("category") or "—")),
            ("Status",         xe(r.get("status") or "—")),
            ("Priority",       xe(r.get("priority") or "—")),
            ("Review Date",    xe(r.get("review_date") or "—")),
            ("Source",         xe(r.get("source") or "Manual")),
            ("Likelihood",     f"{lik_} — {lik_lbl.get(lik_,'')}" if lik_ else "—"),
            ("Impact",         f"{imp_} — {imp_lbl.get(imp_,'')}" if imp_ else "—"),
            ("Inherent Score", f"{s_} ({sl_})"),
            ("Residual Score", str(r.get("residual_score") or "—")),
        ]
        right_rows = [
            ("NIST CSF 2.0",
             xe(f"{r.get('nist_function','—')} › {r.get('nist_category','—')}")),
            ("NIST Subcategory", xe(r.get("nist_subcategory") or "—")),
            ("ISO 27001:2022",
             xe(f"{r.get('iso_domain','—')} {r.get('iso_control','') or ''}".strip())),
            ("MITRE ATT&CK",
             xe(f"{r.get('mitre_tactic','—')} {r.get('mitre_technique','') or ''}".strip())),
            ("CIS Control",    xe(r.get("cis_control") or "—")),
            ("CIA Component",  xe(r.get("cia_component") or "—")),
            ("Existing Controls",
             xe((r.get("existing_controls") or "None documented")[:200])),
            ("Mitigation Plan",
             xe((r.get("mitigation") or "Not yet documented")[:200])),
            ("AI Recommendation",
             xe((r.get("ai_suggestion") or "Not generated")[:200])),
            ("Notes",          xe((r.get("notes") or "—")[:120])),
        ]

        left_card  = info_card(left_rows,  [3.2*cm, dcol_w-3.2*cm])
        right_card = info_card(right_rows, [3.8*cm, dcol_w-3.8*cm])
        detail_t   = Table([[left_card, right_card]],
                           colWidths=[dcol_w, dcol_w])
        detail_t.setStyle(TableStyle([
            ("VALIGN",       (0,0),(-1,-1), "TOP"),
            ("LEFTPADDING",  (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(0,-1),  4),
            ("LEFTPADDING",  (1,0),(1,-1),  4),
            ("RIGHTPADDING", (1,0),(1,-1),  0),
            ("TOPPADDING",   (0,0),(-1,-1), 0),
            ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ]))

        # Cost analysis (if populated)
        ttc = float(r.get("total_treatment_cost") or 0)
        tbi = float(r.get("total_business_impact") or 0)
        rosi_v = float(r.get("rosi_pct") or 0)
        if ttc > 0 or tbi > 0:
            cost_summary = Table([[
                Paragraph(f"Treatment Cost: <b>${ttc:,.0f}</b>",
                          PS("csc", fontName="Helvetica", fontSize=9,
                             textColor=C["blue"], leading=12)),
                Paragraph(f"Business Impact: <b>${tbi:,.0f}</b>",
                          PS("csi", fontName="Helvetica", fontSize=9,
                             textColor=C["crit"], leading=12)),
                Paragraph(f"ROSI: <b>{rosi_v:+.0f}%</b>  ·  "
                          f"Savings: <b>${max(0,float(r.get('projected_savings',0))):,.0f}</b>",
                          PS("csr", fontName="Helvetica", fontSize=9,
                             textColor=C["low"] if rosi_v >= 0 else C["crit"],
                             leading=12)),
            ]], colWidths=[CW/3]*3)
            cost_summary.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), C["bg"]),
                ("TOPPADDING",    (0,0),(-1,-1), 6),
                ("BOTTOMPADDING", (0,0),(-1,-1), 6),
                ("LEFTPADDING",   (0,0),(-1,-1), 10),
                ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
                ("INNERGRID",     (0,0),(-1,-1), 0.3, C["border"]),
                ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ]))
        else:
            cost_summary = None

        story.append(KeepTogether([hdr_t, sp(2), desc_t, sp(4)]))
        story.append(detail_t)
        if cost_summary:
            story.append(cost_summary)
        story.append(sp(16))

    # (PageBreak now in page_title())

    # ════════════════════════════════════════════════════════════════════════
    # 7. FRAMEWORK INTELLIGENCE
    # ════════════════════════════════════════════════════════════════════════
    story.append(anc("s7"))
    story += page_title("7.  Framework Intelligence",
                        "Coverage analysis, gap identification, and executive action items")

    def _fw_rec(text, priority="High"):
        col_ = {"Critical":C["crit"],"High":C["high"],
                 "Medium":C["med"],"Low":C["low"]}.get(priority, C["blue"])
        badge_ = Table([[Paragraph(f"<b>{priority}</b>",
                                   PS(f"fwp{priority}", fontName="Helvetica-Bold",
                                      fontSize=7.5, textColor=C["white"],
                                      leading=9, alignment=TA_CENTER))]],
                       colWidths=[1.8*cm])
        badge_.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), col_),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ]))
        row_t = Table(
            [[Paragraph(f"▸  {text}",
                        PS(f"fwt{abs(hash(text))%9999}", fontName="Helvetica",
                           fontSize=9.5, textColor=C["body"], leading=14)),
              badge_]],
            colWidths=[CW-2.2*cm, 2.2*cm])
        row_t.setStyle(TableStyle([
            ("LEFTPADDING",   (0,0),(0,-1), 14),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LINEBEFORE",    (0,0),(0,-1), 3, col_),
            ("BACKGROUND",    (0,0),(-1,-1), C["alt"]),
            ("LINEBELOW",     (0,0),(-1,-1), 0.3, C["border"]),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        return row_t

    def _top_risks(fn_risks, max_show=3):
        top = sorted(fn_risks,
                     key=lambda r: int(r.get("risk_score") or 0),
                     reverse=True)[:max_show]
        if not top:
            return None
        parts = "  ·  ".join(
            f"{xe(str(r.get('title','?'))[:35])} ({r.get('risk_score',0)})"
            for r in top)
        return Paragraph(f"Top risks: {parts}", T["sm"])

    # ── 7a. NIST CSF 2.0 ─────────────────────────────────────────────────────
    story.append(anc("s7a"))
    story += page_title("7a.  NIST CSF 2.0",
                        "Cybersecurity Framework coverage and function analysis")
    covered_fns = sum(1 for fn in
                      ["Govern","Identify","Protect","Detect","Respond","Recover"]
                      if nist_ctr.get(fn, 0) > 0)
    story.append(Paragraph(
        f"{covered_fns} of 6 NIST CSF 2.0 functions covered across {n} risk(s). "
        "The NIST Cybersecurity Framework 2.0 is the gold-standard governance "
        "model for cybersecurity programmes. Coverage across all six functions "
        "demonstrates a holistic approach to security management. Gaps in any "
        "function represent strategic blind spots in the organisation's security posture.",
        T["body"]))
    story.append(sp(8))

    nist_fn_detail = [
        ("Govern",   "#1B5E20",
         "Sets the strategic direction for cybersecurity. Risks here indicate "
         "gaps in policy, governance structures, roles, or cyber risk management strategy. "
         "Without strong governance, all other functions lack direction and accountability.",
         "Formalise a cybersecurity policy approved by board. Assign named risk owners. "
         "Establish a GRC committee with executive-level representation."),
        ("Identify", "#1565C0",
         "Understanding assets, data, and risks. Gaps mean the organisation "
         "may not know what it owns or what is at risk — making it impossible "
         "to protect what you cannot see.",
         "Conduct an asset inventory and data classification exercise. "
         "Complete a full risk assessment across all business units."),
        ("Protect",  "#2E7D32",
         "Implementing safeguards to prevent or limit cyber events. "
         "The largest risk cluster here shows your greatest control deficiencies "
         "and represents the highest-value area for security investment.",
         "Prioritise MFA deployment, patch management, privileged access controls, "
         "and mandatory security awareness training."),
        ("Detect",   "#E65100",
         "Identifying cybersecurity events promptly. Gaps here mean threats go "
         "undetected, increasing dwell time and breach severity. Average dwell time "
         "for undetected breaches: 197 days (IBM Cost of a Data Breach 2024).",
         "Deploy SIEM and endpoint detection (EDR). Enable alerting on "
         "anomalous behaviour. Test detection capabilities quarterly."),
        ("Respond",  "#880E4F",
         "Taking effective action following a detected event. Gaps here mean the "
         "organisation cannot contain incidents effectively, amplifying damage "
         "and regulatory exposure.",
         "Develop and test an Incident Response Plan. Define escalation paths, "
         "containment procedures, and external communication protocols."),
        ("Recover",  "#4A148C",
         "Restoring capabilities after an incident. Gaps risk extended operational "
         "downtime and unrecoverable revenue loss. The average cost of a major "
         "outage exceeds $5,600 per minute (Gartner).",
         "Test backup restoration quarterly. Document and validate RTO/RPO targets. "
         "Conduct BCP tabletop exercises at least annually."),
    ]

    for fn_n, fn_hex, fn_desc, fn_action in nist_fn_detail:
        fn_risks_l = [r for r in risks if r.get("nist_function") == fn_n]
        cnt_n = len(fn_risks_l)
        pct_n = int(cnt_n / max(n, 1) * 100)
        story.append(prog_bar(pct_n,
                              f"{fn_n}  ({cnt_n} risk{'s' if cnt_n!=1 else ''}  ·  {pct_n}%)",
                              cn(fn_hex), width=CW))
        story.append(Paragraph(fn_desc, T["sm"]))
        tp_ = _top_risks(fn_risks_l)
        if tp_: story.append(tp_)
        pri_ = ("Critical" if cnt_n == 0 and fn_n in ("Protect","Detect")
                else "High" if cnt_n == 0 else "Medium")
        story.append(_fw_rec(fn_action, pri_))
        story.append(sp(6))

    if miss_fns:
        story.append(insight_box(
            f"NIST CSF functions with no mapped risks: {', '.join(sorted(miss_fns))}. "
            "These gaps may reflect genuine control coverage OR unassessed risk areas. "
            "Review each unmapped function and either confirm coverage by existing controls "
            "or create new risks to capture the exposure."))
    # (PageBreak now in page_title())

    # ── 7b. ISO 27001:2022 ────────────────────────────────────────────────────
    story.append(anc("s7b"))
    story += page_title("7b.  ISO/IEC 27001:2022",
                        "Information Security Management System domain coverage")
    mapped_iso = sum(1 for r in risks if r.get("iso_domain"))
    story.append(Paragraph(
        f"{mapped_iso} of {n} risks mapped to ISO 27001:2022 domains "
        f"({int(mapped_iso/max(n,1)*100)}% mapping coverage). "
        "ISO/IEC 27001:2022 is the internationally recognised standard for "
        "Information Security Management Systems (ISMS). Alignment across all "
        "four Annex A domains demonstrates a structured, auditable approach to "
        "information security and supports regulatory compliance.",
        T["body"]))
    story.append(sp(8))

    iso_detail = [
        ("A.5 Organisational Controls", "#15803D",
         "37 controls covering policies, roles, asset management, threat intelligence, "
         "and supplier relationships. Weaknesses here affect the entire security programme.",
         "Ensure a documented ISMS policy is board-approved, reviewed annually, "
         "and communicated to all staff. Assign information asset owners."),
        ("A.6 People Controls", "#15803D",
         "8 controls covering personnel security — screening, training, disciplinary "
         "processes, and offboarding. People remain the largest attack vector.",
         "Implement pre-employment background checks, mandatory security awareness "
         "training, and formal offboarding procedures that revoke all access immediately."),
        ("A.7 Physical Controls", "#15803D",
         "14 controls covering physical access, equipment security, secure areas, and "
         "clear desk/screen policies. Physical breaches can bypass all technical controls.",
         "Review physical access logs monthly, implement visitor management, "
         "enforce clean desk policy, and document secure equipment disposal procedures."),
        ("A.8 Technological Controls", "#15803D",
         "34 controls including access management, encryption, vulnerability management, "
         "logging, endpoint protection, and secure development. The most technical domain "
         "and typically the highest-risk area for organisations.",
         "Prioritise: MFA for all privileged accounts, automated patch management, "
         "privileged access management (PAM), and centralised SIEM logging."),
    ]

    for dom, dhex, ddesc, daction in iso_detail:
        dom_risks = [r for r in risks if r.get("iso_domain") == dom]
        cnt_i = len(dom_risks)
        pct_i = int(cnt_i / max(n, 1) * 100)
        story.append(prog_bar(pct_i, f"{dom}  ({cnt_i})", cn(dhex), width=CW))
        story.append(Paragraph(ddesc, T["sm"]))
        tp_ = _top_risks(dom_risks)
        if tp_: story.append(tp_)
        controls = sorted(set(r.get("iso_control","") for r in dom_risks
                               if r.get("iso_control")))
        if controls:
            story.append(Paragraph(
                f"Controls referenced: {', '.join(controls[:8])}",
                PS("isoc", fontName="Helvetica", fontSize=8,
                   textColor=C["low"], leading=11)))
        story.append(_fw_rec(daction, "High" if cnt_i == 0 else "Medium"))
        story.append(sp(6))

    # (PageBreak now in page_title())

    # ── 7c. MITRE ATT&CK ─────────────────────────────────────────────────────
    story.append(anc("s7c"))
    story += page_title("7c.  MITRE ATT&CK",
                        "Adversary tactic coverage, detection gaps, and defence recommendations")
    all_tactics_ord = [
        "Reconnaissance","Resource Development","Initial Access",
        "Execution","Persistence","Privilege Escalation",
        "Defense Evasion","Credential Access","Discovery",
        "Lateral Movement","Collection","Command & Control",
        "Exfiltration","Impact",
    ]
    covered_tactics = set(mitre_ctr.keys())
    miss_t = [t for t in all_tactics_ord if t not in covered_tactics]

    story.append(Paragraph(
        f"{len(covered_tactics)} of 14 MITRE ATT&CK adversarial tactics represented "
        f"across {sum(mitre_ctr.values())} mapped risk(s). "
        "MITRE ATT&CK maps your risks directly to real-world adversary techniques "
        "documented in active threat intelligence. This translates your risk register "
        "into the language that attackers use — enabling targeted detection, "
        "monitoring investment, and defence prioritisation.",
        T["body"]))
    story.append(sp(8))

    tactic_actions_map = {
        "Reconnaissance":       ("Review internet-facing attack surface. Patch public services. Monitor for scanning.", "High"),
        "Resource Development": ("Deploy threat intelligence feeds. Monitor for spoofed domains.", "Medium"),
        "Initial Access":       ("Enforce MFA on remote access. Patch VPNs. Implement email filtering.", "Critical"),
        "Execution":            ("Deploy application whitelisting and EDR. Disable Office macros.", "High"),
        "Persistence":          ("Audit scheduled tasks, startup items, and privileged accounts. Enable integrity monitoring.", "High"),
        "Privilege Escalation": ("Enforce least privilege. Separate admin accounts. Monitor escalation events.", "High"),
        "Defense Evasion":      ("Tune SIEM rules. Enable audit logging. Deploy file integrity monitoring.", "High"),
        "Credential Access":    ("Enforce MFA everywhere. Policy-mandated password manager. Alert on failed logins.", "Critical"),
        "Discovery":            ("Network segmentation. Alert on internal scanning. Deploy honeypots.", "Medium"),
        "Lateral Movement":     ("Micro-segmentation. Jump servers for admin access. Monitor SMB/RDP traffic.", "High"),
        "Collection":           ("DLP tools. Classify sensitive data. Alert on bulk file access.", "High"),
        "Command & Control":    ("DNS filtering. Proxy inspection. Block known C2 via threat intelligence.", "High"),
        "Exfiltration":         ("Monitor outbound transfers. Block unapproved cloud storage. DLP policy.", "Critical"),
        "Impact":               ("Offline immutable backups. Tested restoration. Ransomware-specific detection.", "Critical"),
    }

    if mitre_ctr:
        story.append(Paragraph("Tactics Present in Your Risk Register:", T["h3"]))
        for tactic, count in sorted(mitre_ctr.items(),
                                     key=lambda x: x[1], reverse=True):
            tactic_risks = [r for r in risks if r.get("mitre_tactic") == tactic]
            pct_t = int(count / max(n, 1) * 100)
            story.append(prog_bar(pct_t,
                                   f"{tactic}  ({count} risk{'s' if count!=1 else ''})",
                                   cn("#B91C1C"), width=CW))
            tp_ = _top_risks(tactic_risks)
            if tp_: story.append(tp_)
            action_txt, pri = tactic_actions_map.get(
                tactic, ("Review and implement controls for this tactic.", "Medium"))
            story.append(_fw_rec(action_txt, pri))
            story.append(sp(4))

    if miss_t:
        story.append(sp(6))
        story.append(Paragraph("Tactics Not Yet in Register:", T["h3"]))
        story.append(Paragraph(
            "These attack tactics have no mapped risks. Confirm whether your "
            "organisation has assessed exposure — absence of a mapped risk does "
            "not mean absence of exposure:",
            T["sm"]))
        story.append(sp(4))
        for t in miss_t:
            act, pri = tactic_actions_map.get(
                t, ("Assess exposure and create risks if applicable.", "Low"))
            story.append(_fw_rec(f"{t} — {act}", pri))
            story.append(sp(2))

    # (PageBreak now in page_title())

    # ── 7d. CIS Controls v8 ───────────────────────────────────────────────────
    story.append(anc("s7d"))
    story += page_title("7d.  CIS Controls v8",
                        "Control coverage by Implementation Group with gap analysis")
    story.append(Paragraph(
        f"{len(cis_ctr)} of 18 CIS Control families represented. "
        "CIS Controls v8 provides 18 prioritised safeguard families with "
        "Implementation Groups (IG1=Essential for all organisations, "
        "IG2=Advanced for those managing sensitive data, "
        "IG3=Expert for critical infrastructure). "
        "IG1 controls prevent the majority of common attacks and are achievable "
        "by organisations of all sizes and budgets.",
        T["body"]))
    story.append(sp(8))

    try:
        from core.database.lookups import CIS_CONTROL_DATA
        import re as _re3

        def _ck(v):
            m = _re3.match(r"(CIS-\d+)", str(v or ""))
            return m.group(1) if m else v

        cis_norm = Counter(_ck(r.get("cis_control","")) for r in risks
                           if r.get("cis_control") and
                              r.get("cis_control") not in ("Not Applicable",""))

        for ig in ("IG1", "IG2", "IG3"):
            ig_controls = {k: v for k, v in CIS_CONTROL_DATA.items()
                           if v.get("ig") == ig and k != "Not Applicable"}
            ig_covered  = [c for c in ig_controls if cis_norm.get(c, 0) > 0]
            ig_pct = int(len(ig_covered)/len(ig_controls)*100) if ig_controls else 0
            ig_desc = {
                "IG1": "Essential — basic cyber hygiene every organisation must implement immediately.",
                "IG2": "Advanced — for organisations managing sensitive data or regulated services.",
                "IG3": "Expert — for organisations managing critical infrastructure or high-value targets.",
            }.get(ig,"")

            story.append(Paragraph(
                f"Implementation Group {ig[-1]} ({ig})  —  "
                f"{len(ig_covered)}/{len(ig_controls)} controls  ({ig_pct}%)  —  {ig_desc}",
                T["h3"]))
            story.append(prog_bar(ig_pct, f"IG{ig[-1]} Coverage",
                                   cn("#C2410C"), width=CW))

            cis_rows_ig = []
            for key, info in ig_controls.items():
                cnt_c = cis_norm.get(key, 0)
                cis_rows_ig.append([
                    Paragraph("✓" if cnt_c else "○",
                              PS(f"cic{key}", fontName="Helvetica-Bold",
                                 fontSize=10,
                                 textColor=C["low"] if cnt_c else C["muted"],
                                 leading=12, alignment=TA_CENTER)),
                    Paragraph(f"<b>{key}</b>  ·  {info['title']}",
                              T["td_b"] if cnt_c else T["td_m"]),
                    Paragraph(info.get("desc","")[:90], T["xs"]),
                    Paragraph(str(cnt_c) if cnt_c else "—",
                              PS(f"civ{key}", fontName="Helvetica-Bold",
                                 fontSize=8.5,
                                 textColor=C["blue"] if cnt_c else C["muted"],
                                 leading=11, alignment=TA_CENTER)),
                ])

            if cis_rows_ig:
                t_cis = Table(cis_rows_ig,
                              colWidths=[0.7*cm, 5.5*cm, CW-7.2*cm, 1.0*cm])
                t_cis.setStyle(TableStyle([
                    ("TOPPADDING",    (0,0),(-1,-1), 6),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 6),
                    ("LEFTPADDING",   (0,0),(-1,-1), 6),
                    ("LINEBELOW",     (0,0),(-1,-2), 0.3, C["border"]),
                    ("ROWBACKGROUNDS",(0,0),(-1,-1), [C["card"], C["alt"]]),
                    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                    ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
                ]))
                story.append(t_cis)
            story.append(sp(10))

    except ImportError:
        story.append(Paragraph("CIS Controls reference data unavailable.", T["sm"]))

    # (PageBreak now in page_title())

    # ── 7e. CIA Triad ─────────────────────────────────────────────────────────
    story.append(anc("s7e"))
    story += page_title("7e.  CIA Triad",
                        "Risk distribution across Confidentiality, Integrity, and Availability")
    story.append(Paragraph(
        "The CIA Triad is the foundational model for information security risk. "
        "Understanding risk distribution across these three pillars enables "
        "targeted investment and clear board-level communication. Each pillar "
        "failure has distinct business consequences:",
        T["body"]))
    story.append(sp(8))

    cia_detail = [
        ("Confidentiality", "#1B5FCF",
         "Protecting information from unauthorised access. Failures cause regulatory "
         "fines (GDPR up to 4% of global turnover), reputational damage, loss of "
         "customer trust, and competitive disadvantage.",
         "Review data classification, enforce encryption at rest and in transit, "
         "implement DLP, and restrict access on a need-to-know basis."),
        ("Integrity",       "#1A8C4E",
         "Ensuring data accuracy and preventing unauthorised modification. Failures "
         "corrupt financial records, operational decisions, and erode trust in "
         "business-critical systems and reporting.",
         "Implement change management controls, file integrity monitoring (FIM), "
         "digital signatures for critical data, and database activity monitoring."),
        ("Availability",    "#C78B00",
         "Ensuring systems are accessible when needed. Failures cause direct revenue "
         "loss, SLA penalties, and customer churn. Average cost of unplanned "
         "downtime: $5,600/minute (Gartner 2024).",
         "Prioritise BCP/DR planning, test backup restoration quarterly, "
         "deploy redundant systems for critical services, implement DDoS mitigation."),
        ("All Three",       "#5B4DB2",
         "Risks affecting all CIA components — ransomware, major data breaches, "
         "and sophisticated insider threats fall here. Maximum exposure requiring "
         "the highest treatment priority and board-level escalation.",
         "Immediate escalation required. Ensure cyber insurance coverage is adequate "
         "and incident response plans specifically address these scenarios."),
    ]

    for comp, chex, cdesc, caction in cia_detail:
        comp_risks = [r for r in risks if r.get("cia_component") == comp]
        cnt_c = len(comp_risks)
        pct_c = int(cnt_c / max(n, 1) * 100)
        story.append(prog_bar(pct_c,
                               f"{comp}  ({cnt_c} risk{'s' if cnt_c!=1 else ''}  ·  {pct_c}%)",
                               cn(chex), width=CW))
        story.append(Paragraph(cdesc, T["sm"]))
        tp_ = _top_risks(comp_risks)
        if tp_: story.append(tp_)
        story.append(_fw_rec(caction,
                              "Critical" if comp == "All Three" and cnt_c > 0
                              else "High" if cnt_c > 0 else "Medium"))
        story.append(sp(6))

    unmapped_cia = sum(1 for r in risks if not r.get("cia_component")
                        or r.get("cia_component") == "Unmapped")
    if unmapped_cia:
        story.append(insight_box(
            f"{unmapped_cia} risk(s) not mapped to a CIA component. "
            "Assign Confidentiality, Integrity, or Availability to each risk "
            "to complete the impact analysis and enable accurate prioritisation."))
    # (PageBreak now in page_title())

    # ── 7f. Framework Recommendations ────────────────────────────────────────
    story.append(anc("s7f"))
    story += page_title("7f.  Framework Recommendations",
                        "Priority-ranked actions derived directly from your risk register")

    def _build_fw_recs(risks_list):
        recs = []
        titles = " ".join(
            (r.get("title","") + " " + r.get("description","")).lower()
            for r in risks_list)
        crit_c = sum(1 for r in risks_list if int(r.get("risk_score") or 0) >= 15)
        if crit_c:
            recs.append(("Critical",
                          f"{crit_c} critical risk(s) (score ≥ 15) require immediate "
                          f"treatment plans, named owners, and target dates this week."))
        if any(w in titles for w in ("mfa","multi-factor","authenticat","credential","password","brute")):
            recs.append(("Critical" if crit_c else "High",
                          "Credential and authentication risks detected. Implement "
                          "MFA for all privileged accounts immediately."))
        if any(w in titles for w in ("ransomware","malware","encrypt","virus","worm")):
            recs.append(("Critical",
                          "Malware/ransomware risks identified. Deploy EDR and maintain "
                          "offline immutable backups. Test restoration monthly."))
        if any(w in titles for w in ("patch","update","vulnerability","cve","unpatched")):
            recs.append(("High",
                          "Patch management risks present. Deploy centralised patch "
                          "management and establish a monthly patching cadence."))
        if any(w in titles for w in ("backup","recovery","restore","rto","rpo","disaster")):
            recs.append(("High",
                          "Data recovery risks identified. Test backup restoration "
                          "quarterly and document RTO/RPO targets."))
        if any(w in titles for w in ("insider","privilege","access control","least privilege")):
            recs.append(("High",
                          "Access control risks present. Implement least privilege and "
                          "conduct quarterly access reviews."))
        if any(w in titles for w in ("gdpr","data protection","pii","personal data","privacy")):
            recs.append(("High",
                          "Data protection risks identified. Review GDPR compliance "
                          "and conduct a data mapping exercise."))
        if any(w in titles for w in ("firewall","network","perimeter","segmentation")):
            recs.append(("Medium",
                          "Network security risks present. Review firewall rules "
                          "quarterly and implement network segmentation."))
        if any(w in titles for w in ("vendor","third.party","supplier","supply chain")):
            recs.append(("Medium",
                          "Vendor/supply chain risks present. Conduct annual vendor "
                          "security assessments and review contractual SLAs."))
        if any(w in titles for w in ("phish","email","social engineer","awareness","training")):
            recs.append(("Medium",
                          "Social engineering risks present. Implement security "
                          "awareness training and regular phishing simulations."))
        if miss_fns:
            recs.append(("Low",
                          f"NIST CSF coverage gaps: {', '.join(sorted(miss_fns))}. "
                          "Complete framework mapping to improve posture reporting."))
        if not recs:
            recs.append(("Medium",
                          "Review all High and Critical risks monthly to "
                          "ensure treatment plans remain on track."))
            recs.append(("Low",
                          "Schedule a quarterly GRC review to assess posture "
                          "changes and update the risk register."))
        return recs

    fw_recs = _build_fw_recs(risks)
    for priority in ("Critical","High","Medium","Low"):
        pr_recs = [(p,t) for p,t in fw_recs if p == priority]
        if not pr_recs:
            continue
        pc_ = {"Critical":C["crit"],"High":C["high"],
               "Medium":C["med"],"Low":C["low"]}.get(priority, C["blue"])
        story.append(Paragraph(
            f"<b>{priority} Priority  —  {len(pr_recs)} "
            f"recommendation{'s' if len(pr_recs)!=1 else ''}</b>",
            PS(f"fwph{priority}", fontName="Helvetica-Bold",
               fontSize=11, textColor=pc_, leading=16, spaceBefore=10)))
        for _, txt in pr_recs:
            story.append(_fw_rec(txt, priority))
            story.append(sp(3))
        story.append(sp(8))

    # (PageBreak now in page_title())

    # ── 8. AI RECOMMENDATIONS ─────────────────────────────────────────────────
    story.append(anc("s8"))
    story += page_title("8.  AI Recommendations",
                        "Strategic intelligence insights and predictive risk observations")
    story.append(sp(6))

    def ai_rec_group(title, items, color, icon="◆"):
        if not items:
            return
        story.append(Paragraph(f"{icon}  {title}", T["h2"]))
        for item in items:
            rb = Table([[Paragraph(f"▸  {xe(item)}",
                                    PS(f"air{abs(hash(item))%9999}",
                                       fontName="Helvetica", fontSize=9.5,
                                       textColor=C["body"], leading=14))]],
                       colWidths=[CW])
            rb.setStyle(TableStyle([
                ("LEFTPADDING",   (0,0),(-1,-1), 16),
                ("TOPPADDING",    (0,0),(-1,-1), 8),
                ("BOTTOMPADDING", (0,0),(-1,-1), 8),
                ("LINEBEFORE",    (0,0),(-1,-1), 3, color),
                ("BACKGROUND",    (0,0),(-1,-1), C["alt"]),
                ("LINEBELOW",     (0,0),(-1,-1), 0.3, C["border"]),
            ]))
            story.append(rb)
            story.append(sp(3))
        story.append(sp(10))

    imm_, s30_, s90_, str_ = [], [], [], []

    if crit_:
        import html as _h2
        titles_ = ", ".join(_h2.escape(str(r.get("title","?"))[:30]) for r in crit_[:3])
        imm_.append(f"Escalate {len(crit_)} critical risk(s) to board level — "
                    f"initiate treatment: {titles_}")
    if overdue:
        imm_.append(f"Assign review dates to {overdue} overdue risk(s) this week")
    if no_mit:
        imm_.append(f"Create treatment plans for {no_mit} risk(s) with no mitigation documented")
    if high_:
        s30_.append(f"Remediate {len(high_)} high-severity risk(s) — target 30 days")
    if cia_ctr.get("Confidentiality",0):
        s30_.append("Review data classification and access controls for Confidentiality risks")
    if cia_ctr.get("Availability",0):
        s30_.append("Verify BCP/DR plans address all Availability risks")
    if miss_fns:
        s90_.append(f"Address NIST CSF gaps: {', '.join(sorted(miss_fns))}")
    unmapped_iso_c = sum(1 for r in risks if not r.get("iso_domain"))
    if unmapped_iso_c:
        s90_.append(f"Complete ISO 27001:2022 mapping for {unmapped_iso_c} unmapped risk(s)")
    if med_:
        s90_.append(f"Schedule treatment planning for {len(med_)} medium-severity risk(s)")
    str_.append("Implement continuous monitoring to detect emerging risks proactively")
    str_.append("Establish quarterly GRC review cadence at board level")
    if ai_c:
        str_.append(f"Expand AI document analysis — {ai_c} risk(s) already surfaced from PDF scanning")
    str_.append("Develop a cyber risk quantification model to express exposure in financial terms")
    str_.append("Consider third-party penetration testing to validate control effectiveness")

    ai_rec_group("Immediate Actions (< 72 Hours)", imm_, C["crit"], "🔴")
    ai_rec_group("Short-Term Actions (30 Days)",   s30_,  C["high"],  "🟠")
    ai_rec_group("Medium-Term Actions (90 Days)",  s90_,  C["med"],   "🟡")
    ai_rec_group("Strategic Initiatives",          str_,  C["blue"],  "🔵")

    story.append(insight_box(
        "AI recommendations are generated directly from your risk register data. "
        "Immediate Actions carry the highest urgency — every day of delay on "
        "critical risks increases the probability of an incident. "
        "Review this section quarterly as the register evolves."))
    # (PageBreak now in page_title())

    # ── 9. TREATMENT ROADMAP ──────────────────────────────────────────────────
    story.append(anc("s9"))
    story += page_title("9.  Treatment Roadmap",
                        "Recommended treatment timeline by severity and priority")

    roadmap_cfg = [
        ("Immediate\n< 1 Week",  C["crit"], crit_,  "Board escalation required"),
        ("Short-Term\n30 Days",  C["high"], high_,  "Executive priority"),
        ("Medium-Term\n90 Days", C["med"],  med_,   "Management action"),
        ("Long-Term\n180+ Days", C["low"],  low_,   "Monitor and review"),
    ]
    rm_hdrs = [Paragraph(f"<b>{p}</b>",
                          PS(f"rmh{i}", fontName="Helvetica-Bold",
                             fontSize=8.5, textColor=C["white"],
                             leading=12, alignment=TA_CENTER))
               for i, (p,_,_,_) in enumerate(roadmap_cfg)]

    def rm_cell(risks_, color):
        if not risks_:
            return [Paragraph("—  None at this tier", T["sm"])]
        items = []
        for r_ in risks_[:5]:
            items.append(Paragraph(
                f"• {xe(str(r_.get('title','?')))[:35]}",
                PS(f"rmi{r_.get('id',0)}", fontName="Helvetica",
                   fontSize=8.5, textColor=C["body"], leading=12)))
            items.append(Paragraph(
                f"  Owner: {r_.get('owner','—')[:18]}  ·  "
                f"Score: {sc(r_)}",
                PS(f"rmio{r_.get('id',0)}", fontName="Helvetica",
                   fontSize=7.5, textColor=C["muted"], leading=11)))
        if len(risks_) > 5:
            items.append(Paragraph(f"  + {len(risks_)-5} more", T["xs"]))
        return items

    rm_cells = [rm_cell(r_, col) for _, col, r_, _ in roadmap_cfg]
    max_rm   = max(len(c) for c in rm_cells) if rm_cells else 1
    for c in rm_cells:
        c += [sp(1)] * (max_rm - len(c))

    rm_data = [rm_hdrs] + [list(row) for row in zip(*rm_cells)]
    rm_t    = Table(rm_data, colWidths=[CW/4]*4)
    rm_s    = [
        ("VALIGN",       (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",   (0,0),(-1,-1), 8),
        ("BOTTOMPADDING",(0,0),(-1,-1), 8),
        ("LEFTPADDING",  (0,0),(-1,-1), 8),
        ("RIGHTPADDING", (0,0),(-1,-1), 8),
        ("LINEBELOW",    (0,1),(-1,-1), 0.3, C["border"]),
        ("BOX",          (0,0),(-1,-1), 0.7, C["border"]),
        ("INNERGRID",    (0,0),(-1,0),  0, C["white"]),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C["card"], C["alt"]]),
    ]
    for ci, (_, col_, _, _) in enumerate(roadmap_cfg):
        rm_s.append(("BACKGROUND", (ci,0),(ci,0), col_))
    rm_t.setStyle(TableStyle(rm_s))
    story.append(rm_t)
    story.append(sp(12))

    # Treatment progress gauges
    story.append(Paragraph("Severity Distribution Gauges", T["h2"]))
    gauges_ = []
    for sev_name, sev_risks, sev_col in [
        ("Critical", crit_, C["crit"]), ("High", high_, C["high"]),
        ("Medium",   med_,  C["med"]),  ("Low",  low_,  C["low"]),
    ]:
        pct_ = int(len(sev_risks)/max(n,1)*100)
        h_   = 60
        w_   = int(CW/4) - 4
        d_   = Drawing(w_, h_)
        r_   = min(w_/2-6, 26)
        cx_  = w_/2
        # Background arc
        pts_bg = []
        for a_ in range(0, 181, 8):
            rad = math.radians(a_)
            pts_bg += [cx_-r_*math.cos(rad), 14+r_*math.sin(rad)]
        if len(pts_bg) >= 4:
            d_.add(PolyLine(pts_bg, strokeColor=cn("#EDF0F5"),
                            strokeWidth=7, strokeLineCap=1))
        fill_a = int(pct_*180/100)
        pts_fg = []
        for a_ in range(0, fill_a+1, max(fill_a//20, 1)):
            rad = math.radians(min(a_, 180))
            pts_fg += [cx_-r_*math.cos(rad), 14+r_*math.sin(rad)]
        if len(pts_fg) >= 4:
            d_.add(PolyLine(pts_fg, strokeColor=sev_col,
                            strokeWidth=7, strokeLineCap=1))
        d_.add(String(cx_, 18, f"{pct_}%",
                      fontName="Helvetica-Bold", fontSize=11,
                      fillColor=sev_col, textAnchor="middle"))
        d_.add(String(cx_, 4, sev_name,
                      fontName="Helvetica", fontSize=7,
                      fillColor=C["muted"], textAnchor="middle"))
        gauges_.append(Embed(d_))

    g_t = Table([gauges_], colWidths=[CW/4]*4)
    g_t.setStyle(TableStyle([
        ("ALIGN",        (0,0),(-1,-1), "CENTER"),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("BOX",          (0,0),(-1,-1), 0.7, C["border"]),
        ("BACKGROUND",   (0,0),(-1,-1), C["card"]),
        ("TOPPADDING",   (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
    ]))
    story.append(g_t)
    story.append(sp(8))
    story.append(insight_box(
        "Treatment velocity is critical. Each quarter without treatment on a "
        "critical or high risk increases incident probability. Assign named owners "
        "with escalation accountability for every Immediate and Short-Term item."))
    # (PageBreak now in page_title())

    # ── 10. EXECUTIVE CONCLUSION ──────────────────────────────────────────────
    story.append(anc("s10"))
    story += page_title("10.  Executive Conclusion",
                        "Board-level summary, priorities, and forward-looking recommendations")

    concl = (
        f"This Cyber Risk Assessment was conducted using the RiskCore GRC Platform "
        f"v1.5, employing NIST SP 800-30 Rev 1 risk scoring with cross-framework "
        f"mapping to NIST CSF 2.0, ISO/IEC 27001:2022, MITRE ATT&CK, CIS Controls v8, "
        f"and the CIA Triad. "
        f"The assessment identified <b>{n} risk{'s' if n!=1 else ''}</b> with an overall "
        f"posture of <b>{posture}</b> and an average inherent risk score of <b>{avg_sc}</b>.")
    story.append(Paragraph(concl, T["body"]))
    story.append(sp(10))

    story.append(Paragraph("Current Posture Assessment", T["h2"]))
    posture_stmt = {
        "Critical": (
            f"{len(crit_)} critical risk(s) represent a material threat requiring "
            f"immediate board-level resourcing. The organisation should assess whether "
            f"current cyber insurance, incident response capabilities, and business "
            f"continuity plans are adequate at this risk level."),
        "High": (
            f"The presence of {len(high_)} high-severity risk(s) indicates significant "
            f"residual exposure requiring executive ownership and 30-day treatment plans."),
        "Medium": (
            f"The organisation demonstrates a managed risk posture with no critical or "
            f"high risks currently registered. Continued governance discipline is required "
            f"to maintain this posture."),
        "Low": (
            f"The organisation demonstrates strong risk management discipline. "
            f"Sustaining this requires ongoing monitoring and regular assessments."),
        "Unknown": "No risks registered. Initiate risk capture to generate posture analysis.",
    }.get(posture, "")
    story.append(Paragraph(posture_stmt, T["body"]))
    story.append(sp(10))

    story.append(Paragraph("Board-Level Priorities", T["h2"]))
    priorities_ = []
    if crit_:
        priorities_.append(
            f"Board resolution: approve immediate treatment for {len(crit_)} critical risk(s)")
    if high_:
        priorities_.append(
            f"Executive mandate: 30-day treatment plans for {len(high_)} high-severity risk(s)")
    if no_mit:
        priorities_.append(
            f"Governance action: {no_mit} risk(s) require treatment plans this quarter")
    if miss_fns:
        priorities_.append(
            f"Framework gap: address NIST CSF coverage gaps — {', '.join(sorted(miss_fns))}")
    priorities_.append("Cadence: establish quarterly GRC board reporting cycle")
    priorities_.append(
        "Capability: invest in cyber risk quantification to express exposure in financial terms")
    for p_ in priorities_:
        story.append(Paragraph(f"• {p_}", T["bul"]))
    story.append(sp(12))

    # Sign-off
    signoff = Table([[Paragraph(
        "This report was generated by <b>RiskCore GRC Platform v1.5</b> "
        "using data available in the live Risk Register at the time of generation. "
        "All risk data, scores, framework mappings, and recommendations are derived "
        "directly from the register — no data has been modified or supplemented. "
        f"Generated: {today()} at {now()}. Classification: {classification}.",
        PS("so", fontName="Helvetica", fontSize=8.5, textColor=C["muted"],
           leading=13, alignment=TA_CENTER))]],
        colWidths=[CW])
    signoff.setStyle(TableStyle([
        ("BOX",           (0,0),(-1,-1), 0.7, C["border"]),
        ("BACKGROUND",    (0,0),(-1,-1), C["bg"]),
        ("TOPPADDING",    (0,0),(-1,-1), 14),
        ("BOTTOMPADDING", (0,0),(-1,-1), 14),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
        ("RIGHTPADDING",  (0,0),(-1,-1), 20),
    ]))
    story.append(signoff)
    # (PageBreak now in page_title())

    # ── 11. METHODOLOGY APPENDIX ──────────────────────────────────────────────
    story.append(anc("s11"))
    story += page_title("11.  Methodology Appendix",
                        "Scoring methodology, severity bands, frameworks, and glossary")

    story.append(Paragraph("Risk Scoring Methodology", T["h2"]))
    story.append(Paragraph(
        "Risk scoring follows the NIST SP 800-30 Rev 1 methodology. "
        "Inherent Risk Score = Likelihood (1–5) × Impact (1–5). "
        "Maximum score: 25. Residual risk reflects the score after treatment "
        "controls are applied. Both are captured per risk and used for "
        "heat-map positioning and treatment prioritisation.",
        T["body"]))
    story.append(sp(8))

    story.append(Paragraph("Severity Bands", T["h2"]))
    band_rows = [
        [Paragraph("<b>CRITICAL</b>",PS("bc",fontName="Helvetica-Bold",fontSize=8,textColor=C["white"],leading=10,alignment=TA_CENTER)),
         Paragraph("15–25",T["td_b"]),
         Paragraph("Immediate board escalation. Treatment within 72 hours.",T["td"]),
         Paragraph("Board",T["td"])],
        [Paragraph("<b>HIGH</b>",PS("bh",fontName="Helvetica-Bold",fontSize=8,textColor=C["white"],leading=10,alignment=TA_CENTER)),
         Paragraph("10–14",T["td_b"]),
         Paragraph("Executive priority. Treatment plan within 30 days.",T["td"]),
         Paragraph("Executive",T["td"])],
        [Paragraph("<b>MEDIUM</b>",PS("bm",fontName="Helvetica-Bold",fontSize=8,textColor=C["white"],leading=10,alignment=TA_CENTER)),
         Paragraph("5–9",T["td_b"]),
         Paragraph("Management action. Treatment plan within 90 days.",T["td"]),
         Paragraph("Manager",T["td"])],
        [Paragraph("<b>LOW</b>",PS("bl",fontName="Helvetica-Bold",fontSize=8,textColor=C["white"],leading=10,alignment=TA_CENTER)),
         Paragraph("1–4",T["td_b"]),
         Paragraph("Monitor quarterly. Document and review.",T["td"]),
         Paragraph("Owner",T["td"])],
    ]
    band_t = Table(band_rows, colWidths=[2*cm,1.8*cm,CW-5.8*cm,2*cm], repeatRows=0)
    band_styles = [
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("GRID",          (0,0),(-1,-1), 0.5, C["border"]),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [C["card"], C["alt"]]),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]
    for i, col_ in enumerate([C["crit"],C["high"],C["med"],C["low"]]):
        band_styles.append(("BACKGROUND", (0,i),(0,i), col_))
    band_t.setStyle(TableStyle(band_styles))
    story.append(band_t)
    story.append(sp(10))

    story.append(Paragraph("Frameworks Referenced", T["h2"]))
    fw_rows = [
        [Paragraph("<b>NIST CSF 2.0</b>",T["td_b"]),
         Paragraph("2.0 (2024)",T["td"]),
         Paragraph("NIST Cybersecurity Framework — Govern, Identify, Protect, Detect, Respond, Recover",T["td"])],
        [Paragraph("<b>NIST SP 800-30</b>",T["td_b"]),
         Paragraph("Rev 1",T["td"]),
         Paragraph("Guide for Conducting Risk Assessments — risk scoring methodology used throughout",T["td"])],
        [Paragraph("<b>ISO/IEC 27001</b>",T["td_b"]),
         Paragraph("2022",T["td"]),
         Paragraph("Information Security Management Systems — Annex A controls A.5–A.8",T["td"])],
        [Paragraph("<b>MITRE ATT&CK</b>",T["td_b"]),
         Paragraph("v14",T["td"]),
         Paragraph("Adversarial Tactics, Techniques and Common Knowledge — 14 tactical stages",T["td"])],
        [Paragraph("<b>CIS Controls</b>",T["td_b"]),
         Paragraph("v8",T["td"]),
         Paragraph("18 safeguard families with Implementation Groups IG1 (Essential) through IG3 (Expert)",T["td"])],
        [Paragraph("<b>CIA Triad</b>",T["td_b"]),
         Paragraph("—",T["td"]),
         Paragraph("Confidentiality, Integrity, Availability — foundational information security model",T["td"])],
    ]
    fw_t = Table(fw_rows, colWidths=[3.2*cm,2*cm,CW-5.2*cm], repeatRows=0)
    fw_t.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("GRID",          (0,0),(-1,-1), 0.5, C["border"]),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [C["card"], C["alt"]]),
    ]))
    story.append(fw_t)
    story.append(sp(10))
    story.append(div())
    story.append(sp(4))
    story.append(Paragraph(
        f"RiskCore GRC Platform v1.5  ·  Generated: {today()} {now()}  ·  "
        f"All findings derived from live register data at time of generation.",
        PS("fin", fontName="Helvetica", fontSize=7.5, textColor=C["muted"],
           leading=11, alignment=TA_CENTER)))

    # ════════════════════════════════════════════════════════════════════════
    # BUILD — two-pass for Page X of Y
    # ════════════════════════════════════════════════════════════════════════
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MG, rightMargin=MG,
        topMargin=2.4*cm, bottomMargin=2.0*cm,
        title=f"{company_name} — Cyber Risk Assessment Report",
        author="RiskCore GRC Platform v1.5",
        subject="Cyber Risk Assessment",
        creator="RiskCore GRC Platform v1.5")

    if _known_total_pages == 0:
        buf = io.BytesIO()
        dummy = SimpleDocTemplate(buf, pagesize=A4,
                                  leftMargin=MG, rightMargin=MG,
                                  topMargin=2.4*cm, bottomMargin=2.0*cm)
        dummy.build(story, onFirstPage=cover_page, onLaterPages=on_page)
        disc = page_num[0]
        # Pass the registry from pass 1 into pass 2 so TOC gets real page numbers
        return generate_pdf_report(
            analysis, risks_approved, company_name, output_path,
            classification, _known_total_pages=disc, org_scope=org_scope,
            _known_registry=dict(page_registry))

    total_pages[0] = _known_total_pages
    doc.build(story, onFirstPage=cover_page, onLaterPages=on_page)
    return output_path