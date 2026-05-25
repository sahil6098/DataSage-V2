from __future__ import annotations

import io
import json
import re
from datetime import datetime
from typing import Any

import httpx
from bson import ObjectId

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.mongo import get_database


MIN_REPORT_USER_MESSAGES = 4
logger = get_logger(__name__)

# ── Colour palette ──────────────────────────────────────────────────
PRIMARY     = "#1e40af"   # deep blue
PRIMARY_MID = "#3b82f6"   # medium blue
ACCENT      = "#0ea5e9"   # sky blue
BG_DARK     = "#0f172a"   # header / footer
BG_LIGHT    = "#f0f9ff"   # section tint
BORDER      = "#bfdbfe"
TEXT_DARK   = "#1e293b"
TEXT_MID    = "#475569"
TEXT_LIGHT  = "#f8fafc"
BADGE_GREEN = "#dcfce7"
BADGE_GREEN_TEXT = "#166534"
BADGE_BLUE  = "#dbeafe"
BADGE_BLUE_TEXT = "#1d4ed8"

REPORT_CSS = """
@page {
  size: A4;
  margin: 0;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 10pt;
  color: #1e293b;
  background: #ffffff;
}

/* ── Cover / header band ── */
.cover {
  background: #0f172a;
  color: #f8fafc;
  padding: 40pt 48pt 32pt;
  border-bottom: 4pt solid #3b82f6;
}
.cover-brand {
  font-size: 10pt;
  color: #93c5fd;
  letter-spacing: 2pt;
  text-transform: uppercase;
  margin-bottom: 20pt;
}
.cover-title {
  font-size: 22pt;
  font-weight: bold;
  color: #f0f9ff;
  margin-bottom: 8pt;
  line-height: 1.25;
}
.cover-subtitle {
  font-size: 10pt;
  color: #93c5fd;
  margin-bottom: 20pt;
}
.cover-meta {
  font-size: 8pt;
  color: #64748b;
  border-top: 0.5pt solid #1e3a5f;
  padding-top: 12pt;
  margin-top: 20pt;
}

/* ── Body wrapper ── */
.body-wrap {
  padding: 28pt 48pt 32pt;
}

/* ── Section headings ── */
.section-header {
  background: #1e40af;
  color: #f0f9ff;
  font-size: 11pt;
  font-weight: bold;
  padding: 7pt 14pt;
  border-radius: 4pt;
  margin-top: 22pt;
  margin-bottom: 10pt;
}

/* ── Executive summary box ── */
.summary-box {
  background: #f0f9ff;
  border-left: 4pt solid #3b82f6;
  border-radius: 4pt;
  padding: 14pt 16pt;
  margin-bottom: 18pt;
  font-size: 10pt;
  color: #1e293b;
  line-height: 1.6;
}

/* ── Bullet lists ── */
.bullet-list { margin: 0 0 8pt 0; padding: 0; }
.bullet-item {
  font-size: 9.5pt;
  color: #334155;
  padding: 4pt 0 4pt 18pt;
  line-height: 1.55;
  border-bottom: 0.5pt solid #e2e8f0;
}
.bullet-item:last-child { border-bottom: none; }

/* ── Stat badges ── */
.stat-row {
  margin-bottom: 14pt;
}
.stat-badge {
  display: inline-block;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 8pt;
  font-weight: bold;
  padding: 3pt 10pt;
  border-radius: 10pt;
  margin-right: 6pt;
  margin-bottom: 4pt;
}

/* ── Data tables ── */
.data-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 6pt;
  margin-bottom: 14pt;
  font-size: 8.5pt;
}
.data-table th {
  background: #1e40af;
  color: #f0f9ff;
  padding: 6pt 8pt;
  text-align: left;
  font-weight: bold;
}
.data-table td {
  padding: 5pt 8pt;
  color: #334155;
  border-bottom: 0.5pt solid #e2e8f0;
}
.data-table tr:nth-child(even) td {
  background: #f8fafc;
}

/* ── Chart placeholder ── */
.chart-placeholder {
  background: #f8fafc;
  border: 1pt solid #bfdbfe;
  border-radius: 4pt;
  padding: 10pt 14pt;
  margin: 8pt 0 12pt;
  font-size: 8.5pt;
  color: #475569;
}
.chart-title {
  font-size: 9.5pt;
  font-weight: bold;
  color: #1e40af;
  margin-bottom: 6pt;
}

/* ── Conversation excerpts ── */
.message-block {
  margin-bottom: 10pt;
  padding: 8pt 12pt;
  border-radius: 4pt;
  font-size: 9pt;
  line-height: 1.55;
}
.message-user {
  background: #f0f9ff;
  border-left: 3pt solid #3b82f6;
  color: #1e293b;
}
.message-assistant {
  background: #f8fafc;
  border-left: 3pt solid #0ea5e9;
  color: #334155;
}
.message-role {
  font-size: 7.5pt;
  font-weight: bold;
  text-transform: uppercase;
  letter-spacing: 0.5pt;
  color: #64748b;
  margin-bottom: 3pt;
}

/* ── Page divider ── */
.divider {
  border: none;
  border-top: 0.5pt solid #bfdbfe;
  margin: 16pt 0;
}

/* ── Footer ── */
.footer {
  background: #0f172a;
  color: #64748b;
  font-size: 7pt;
  padding: 8pt 48pt;
  border-top: 2pt solid #1e40af;
}
"""


def _build_html_report(*, session: dict, narrative: dict[str, Any]) -> str:
    messages = session.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]
    asst_msgs = [m for m in messages if m.get("role") == "assistant"]
    visual_payloads = _visual_payloads(messages)
    generated_at = datetime.now().strftime("%B %d, %Y  %H:%M")
    title = _esc(str(narrative.get("title") or session.get("title") or "DataSage Analytics Report"))

    def bullet_section(heading: str, items: Any) -> str:
        if isinstance(items, str):
            items = [items]
        rows = "".join(
            f'<div class="bullet-item">&#8226;&nbsp; {_esc(str(item))}</div>'
            for item in (items or ["No additional notes."])
        )
        return f'<div class="section-header">{heading}</div><div class="bullet-list">{rows}</div>'

    def data_table_html(rows: list[dict]) -> str:
        if not rows:
            return ""
        headers = list(rows[0].keys())[:6]
        ths = "".join(f"<th>{_esc(h)}</th>" for h in headers)
        trs = ""
        for row in rows[:8]:
            tds = "".join(f"<td>{_esc(_trunc(str(row.get(h, '')), 40))}</td>" for h in headers)
            trs += f"<tr>{tds}</tr>"
        return f'<table class="data-table"><tr>{ths}</tr>{trs}</table>'

    # Stats badges
    stats_html = (
        f'<div class="stat-row">'
        f'<span class="stat-badge">&#128172; {len(user_msgs)} user messages</span>'
        f'<span class="stat-badge">&#129302; {len(asst_msgs)} AI responses</span>'
        f'<span class="stat-badge">&#128202; {len(visual_payloads)} visualizations</span>'
        f'</div>'
    )

    # Visualizations
    viz_html = ""
    if visual_payloads:
        viz_html += '<div class="section-header">Visualizations &amp; Data</div>'
        for idx, payload in enumerate(visual_payloads[:5], 1):
            rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
            vtitle = _esc(_trunc(str(payload.get("summary") or payload.get("explanation") or f"Visualization {idx}"), 120))
            chart_type = str(payload.get("chart_type") or "table").upper()
            viz_html += f"""
<div class="chart-placeholder">
  <div class="chart-title">&#128202; {vtitle} <span style="font-size:7.5pt;color:#94a3b8;">[{chart_type}]</span></div>
  {data_table_html(rows)}
</div>"""

    # Conversation excerpts (last 14 messages)
    convo_html = '<div class="section-header">Conversation Excerpts</div>'
    for msg in messages[-14:]:
        role = str(msg.get("role") or "")
        content = _esc(_trunc(str(msg.get("content") or ""), 800))
        if role == "user":
            convo_html += f'<div class="message-block message-user"><div class="message-role">&#128100; You</div>{content}</div>'
        elif role == "assistant":
            convo_html += f'<div class="message-block message-assistant"><div class="message-role">&#129302; DataSage AI</div>{content}</div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>{REPORT_CSS}</style>
</head>
<body>

<!-- COVER -->
<div class="cover">
  <div class="cover-brand">DataSage AI &bull; Analytics Report</div>
  <div class="cover-title">{title}</div>
  <div class="cover-subtitle">AI-Powered Data Analysis Summary</div>
  {stats_html}
  <div class="cover-meta">Generated on {generated_at} &bull; Confidential &bull; DataSage</div>
</div>

<div class="body-wrap">

<!-- EXECUTIVE SUMMARY -->
<div class="section-header">Executive Summary</div>
<div class="summary-box">{_esc(str(narrative.get("executive_summary") or ""))}</div>

{bullet_section("Key Findings", narrative.get("key_findings"))}
<hr class="divider"/>
{bullet_section("Recommendations", narrative.get("recommendations"))}
<hr class="divider"/>
{bullet_section("Limitations &amp; Notes", narrative.get("limitations"))}

{viz_html}

<hr class="divider"/>
{convo_html}

</div>

<!-- FOOTER -->
<div class="footer">
  DataSage AI &bull; Confidential Analytics Report &bull; {generated_at}
</div>

</body>
</html>"""
    return html


def _visual_payloads(messages: list[dict]) -> list[dict[str, Any]]:
    payloads = []
    for message in messages:
        raw = message.get("viz_data")
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _visual_summaries(messages: list[dict]) -> list[dict[str, Any]]:
    summaries = []
    for payload in _visual_payloads(messages):
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        summaries.append({
            "title": payload.get("summary") or payload.get("explanation"),
            "chart_type": payload.get("chart_type"),
            "row_count": len(rows),
            "sample_rows": rows[:3],
        })
    return summaries


def _esc(value: str) -> str:
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _trunc(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars - 3].rstrip()}..."


class ReportService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.db = get_database()

    async def generate_chat_report(self, *, user_id: str, session_id: str) -> tuple[bytes, str]:
        session = await self.db.sessions.find_one({"_id": ObjectId(session_id), "user_id": user_id})
        if not session:
            raise ValueError("Session not found.")
        messages = session.get("messages", [])
        if not messages:
            raise ValueError("This chat has no messages to report yet.")
        user_message_count = sum(1 for m in messages if m.get("role") == "user")
        if user_message_count < MIN_REPORT_USER_MESSAGES:
            remaining = MIN_REPORT_USER_MESSAGES - user_message_count
            suffix = "" if remaining == 1 else "s"
            raise ValueError(f"Send {remaining} more message{suffix} before generating a report.")

        narrative = await self._generate_report_narrative(session)
        pdf_bytes = self._build_pdf(session=session, narrative=narrative)
        filename = self._safe_filename(str(session.get("title") or "datasage-report")) + ".pdf"
        return pdf_bytes, filename

    async def _generate_report_narrative(self, session: dict) -> dict[str, Any]:
        if not self.settings.openrouter_report_api_key:
            return self._fallback_narrative(session)
        try:
            narrative = await self._generate_openrouter_narrative(session)
        except Exception as exc:
            logger.warning("Falling back to local report narrative: %s", exc)
            return self._fallback_narrative(session)
        return self._normalize_narrative(narrative, session)

    async def _generate_openrouter_narrative(self, session: dict) -> dict[str, Any]:
        messages = session.get("messages", [])
        transcript = self._compact_transcript(messages)
        visuals = _visual_summaries(messages)
        system_prompt = (
            "You generate concise analytics report content as JSON only. Do not copy the transcript as Q/A. "
            "Return keys: title, executive_summary, key_findings, recommendations, limitations. "
            "key_findings and recommendations must be arrays of short strings. "
            "The executive_summary must be a real paragraph explaining what happened in the session, "
            "what was analyzed, what outcomes were produced, and what issues remain. "
            "Base the report only on the supplied chat transcript and visualization summaries."
        )
        user_prompt = (
            f"Session title: {session.get('title') or 'DataSage report'}\n\n"
            f"Transcript:\n{transcript}\n\n"
            f"Visualization summaries:\n{json.dumps(visuals, ensure_ascii=False)}"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.openrouter_report_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://127.0.0.1:3000",
                    "X-Title": "DataSage Report Generator",
                },
                json={
                    "model": self.settings.openrouter_report_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 900,
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._extract_json(content)

    def _fallback_narrative(self, session: dict) -> dict[str, Any]:
        messages = session.get("messages", [])
        user_messages = [str(m.get("content") or "").strip() for m in messages if m.get("role") == "user"]
        assistant_messages = [str(m.get("content") or "").strip() for m in messages if m.get("role") == "assistant"]
        visuals = _visual_summaries(messages)
        title = str(session.get("title") or "DataSage Analytics Report")

        summary_bits = [
            f"This report summarizes a DataSage session titled '{title}' comprising "
            f"{len(user_messages)} user requests and {len(assistant_messages)} AI-generated responses.",
            "The conversation focused on the connected data source, producing analytical answers, "
            "chart queries, and data-driven insights.",
        ]
        if visuals:
            suffix = "s" if len(visuals) != 1 else ""
            summary_bits.append(
                f"The session generated {len(visuals)} visualization-ready result set{suffix} suitable for dashboards."
            )

        findings = []
        for q in user_messages[-6:]:
            findings.append(f"User explored: {_trunc(q, 180)}")
        for a in assistant_messages[-3:]:
            findings.append(f"AI outcome: {_trunc(a, 200)}")
        for v in visuals[:2]:
            findings.append(f"Visualization: {_trunc(str(v.get('title') or 'Untitled'), 140)}")

        return self._normalize_narrative(
            {
                "title": title,
                "executive_summary": " ".join(summary_bits),
                "key_findings": findings[:10],
                "recommendations": [
                    "Validate AI-generated findings against raw source data before sharing externally.",
                    "Use exact column names, metrics, and time ranges in follow-up questions for precise results.",
                    "Regenerate this report after resolving any low-confidence or failed queries noted above.",
                ],
                "limitations": [
                    "This report is derived solely from the saved chat transcript and visualization payloads.",
                    "Rate-limited or failed queries may have incomplete answers reflected in the findings.",
                    "AI interpretations are probabilistic; always verify critical numbers in the source system.",
                ],
            },
            session,
        )

    def _normalize_narrative(self, narrative: dict[str, Any], session: dict) -> dict[str, Any]:
        title = str(narrative.get("title") or session.get("title") or "DataSage Analytics Report")
        executive_summary = str(narrative.get("executive_summary") or "").strip()
        if not executive_summary:
            executive_summary = (
                "This report summarizes the main analysis requests, responses, and follow-up items "
                "from the DataSage chat session."
            )

        def listify(value: Any, fallback: str) -> list[str]:
            if isinstance(value, list):
                items = [str(item).strip() for item in value if str(item).strip()]
            elif isinstance(value, str) and value.strip():
                items = [value.strip()]
            else:
                items = []
            return items or [fallback]

        return {
            "title": title,
            "executive_summary": executive_summary,
            "key_findings": listify(narrative.get("key_findings"), "No key findings were captured."),
            "recommendations": listify(narrative.get("recommendations"), "Continue the analysis with a more specific question."),
            "limitations": listify(narrative.get("limitations"), "The report only uses information saved in this chat session."),
        }

    def _build_pdf(self, *, session: dict, narrative: dict[str, Any]) -> bytes:
        try:
            from xhtml2pdf import pisa  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "xhtml2pdf is not installed. Run: pip install xhtml2pdf"
            ) from exc

        html = _build_html_report(session=session, narrative=narrative)
        buffer = io.BytesIO()
        result = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
        if result.err:
            logger.warning("xhtml2pdf reported %d error(s) during PDF generation.", result.err)
        buffer.seek(0)
        return buffer.read()

    def _compact_transcript(self, messages: list[dict]) -> str:
        lines = []
        for message in messages[-24:]:
            role = str(message.get("role") or "message")
            content = _trunc(str(message.get("content") or ""), 1000)
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if "```" in cleaned:
            parts = [p.strip() for p in cleaned.split("```") if p.strip()]
            cleaned = next((p.removeprefix("json").strip() for p in parts if "{" in p), cleaned)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.S)
            payload = json.loads(match.group(0)) if match else {}
        return payload if isinstance(payload, dict) else {}

    def _safe_filename(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
        return cleaned[:80] or "datasage-report"