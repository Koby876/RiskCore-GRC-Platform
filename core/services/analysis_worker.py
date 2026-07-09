"""
core/services/analysis_worker.py
──────────────────────────────────
Background worker that runs the full AI document analysis pipeline
on a QThread so the UI never blocks.

The worker emits fine-grained progress signals so the AI workspace
can show a live step-by-step progress view matching Image 9.

Progress steps:
  1. Extracting text from document
  2. Identifying risks and issues
  3. Mapping to frameworks
  4. Scoring risks (NIST SP 800-30)
  5. Generating recommendations
  6. Compiling results
"""

import json
import re
import urllib.request
import urllib.error
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.services.ai_service import (
    extract_pdf_text,
    build_analysis_prompt,
    build_executive_summary,
)
from core.database.db import (
    get_organisation_scope,
    insert_risk,
    audit,
    load_api_key,
)


class AnalysisWorker(QObject):
    """
    Runs the full AI analysis pipeline off the UI thread.

    Signals
    -------
    progress(str, float)  : step description + 0.0–1.0 progress value
    finished(dict)        : full result dict when complete
    error(str)            : error message if something fails
    """

    progress = Signal(str, float)
    finished = Signal(object)  # dict — use object for cross-thread safety
    error    = Signal(str)

    def __init__(
        self,
        pdf_path: str,
        api_key: str,
        company_name: str,
        org_scope: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.pdf_path    = pdf_path
        self.api_key     = api_key
        self.company_name = company_name
        self.org_scope   = org_scope

    def run(self) -> None:
        try:
            # Step 1 — Extract PDF text
            self.progress.emit("Extracting text from document", 0.1)
            text = extract_pdf_text(self.pdf_path)
            if text.startswith("ERROR"):
                raise RuntimeError(text)

            # Step 2 — Build prompt
            self.progress.emit("Identifying risks and issues", 0.2)
            prompt = build_analysis_prompt(
                text, self.company_name, org_scope=self.org_scope)

            # Step 3 — Call API
            self.progress.emit("Mapping to frameworks", 0.4)
            result = self._call_api(prompt)

            # Step 4 — Score risks
            self.progress.emit("Scoring risks (NIST SP 800-30)", 0.65)

            # Step 5 — Build executive summary (no extra API call)
            self.progress.emit("Generating recommendations", 0.8)
            risks = result.get("risks", [])
            result["_exec_summary"] = build_executive_summary(
                result, risks, org_scope=self.org_scope)

            # Step 6 — Done
            self.progress.emit("Compiling results", 1.0)
            audit("AI_ANALYSIS",
                  detail=(f"PDF: {Path(self.pdf_path).name} → "
                          f"{len(risks)} risks, posture: "
                          f"{result.get('overall_risk_posture','?')}"))

            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))

    def _call_api(self, prompt: str) -> dict:
        payload = json.dumps({
            "model":      "claude-sonnet-4-6",
            "max_tokens": 4000,
            "messages":   [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        text = "".join(
            b.get("text", "")
            for b in raw.get("content", [])
            if b.get("type") == "text"
        )
        text = re.sub(r'^```[a-z]*\n?', '', text.strip())
        text = re.sub(r'\n?```$',       '', text.strip())
        return json.loads(text)


class ApproveWorker(QObject):
    """
    Saves approved AI risks to the database on a background thread.
    Emits finished(count) when done, error(str) on failure.
    """
    finished = Signal(int)
    error    = Signal(str)

    def __init__(
        self,
        risks: list,
        pdf_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.risks    = risks
        self.pdf_name = pdf_name

    def run(self) -> None:
        try:
            count = 0
            for risk in self.risks:
                risk["ai_suggestion"] = (
                    f"AI-identified from: {self.pdf_name}")
                insert_risk(risk, source="AI Analysis")
                count += 1
            audit("AI_APPROVE",
                  detail=f"{count} risks approved from {self.pdf_name}")
            self.finished.emit(count)
        except Exception as e:
            self.error.emit(str(e))
