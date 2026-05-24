from __future__ import annotations

import io
import json
import re
from typing import Any

import httpx
from bson import ObjectId
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.mongo import get_database


MIN_REPORT_USER_MESSAGES = 4
logger = get_logger(__name__)


class ReportChart(Flowable):
    def __init__(self, title: str, rows: list[dict[str, Any]], chart_type: str | None) -> None:
        super().__init__()
        self.title = title
        self.rows = rows[:8]
        self.chart_type = chart_type or "bar"
        self.width = 6.7 * inch
        self.height = 2.6 * inch

    def draw(self) -> None:
        canvas: Canvas = self.canv
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(colors.HexColor("#1f2937"))
        canvas.drawString(0, self.height - 12, self.title[:90])

        labels, values = self._labels_and_values()
        if not labels or not values:
            self._draw_table_preview(canvas)
            return

        if self.chart_type in {"line", "radar"}:
            self._draw_line(canvas, labels, values)
        else:
            self._draw_bars(canvas, labels, values)

    def _labels_and_values(self) -> tuple[list[str], list[float]]:
        if not self.rows:
            return [], []
        first = self.rows[0]
        numeric_key = next((key for key, value in first.items() if isinstance(value, (int, float))), None)
        label_key = next((key for key, value in first.items() if key != numeric_key and not isinstance(value, (int, float))), None)
        if not numeric_key:
            return [], []
        labels = [str(row.get(label_key) if label_key else index + 1) for index, row in enumerate(self.rows)]
        values = [float(row.get(numeric_key) or 0) for row in self.rows]
        return labels, values

    def _draw_bars(self, canvas: Canvas, labels: list[str], values: list[float]) -> None:
        left = 28
        bottom = 34
        chart_width = self.width - 56
        chart_height = self.height - 72
        max_value = max(max(values), 1)
        bar_gap = 8
        bar_width = max(12, (chart_width - bar_gap * (len(values) - 1)) / max(len(values), 1))

        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.line(left, bottom, left + chart_width, bottom)
        canvas.setFillColor(colors.HexColor("#2563eb"))
        for index, value in enumerate(values):
            bar_height = (value / max_value) * chart_height
            x = left + index * (bar_width + bar_gap)
            canvas.rect(x, bottom, bar_width, bar_height, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#374151"))
            canvas.setFont("Helvetica", 7)
            canvas.drawCentredString(x + bar_width / 2, bottom - 12, labels[index][:12])
            canvas.drawCentredString(x + bar_width / 2, bottom + bar_height + 4, self._format_number(value))
            canvas.setFillColor(colors.HexColor("#2563eb"))

    def _draw_line(self, canvas: Canvas, labels: list[str], values: list[float]) -> None:
        left = 28
        bottom = 34
        chart_width = self.width - 56
        chart_height = self.height - 72
        max_value = max(max(values), 1)
        step = chart_width / max(len(values) - 1, 1)
        points = []
        for index, value in enumerate(values):
            x = left + index * step
            y = bottom + (value / max_value) * chart_height
            points.append((x, y))

        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.line(left, bottom, left + chart_width, bottom)
        canvas.setStrokeColor(colors.HexColor("#0f766e"))
        canvas.setLineWidth(1.8)
        for start, end in zip(points, points[1:]):
            canvas.line(start[0], start[1], end[0], end[1])
        canvas.setFillColor(colors.HexColor("#0f766e"))
        for index, (x, y) in enumerate(points):
            canvas.circle(x, y, 2.5, fill=1, stroke=0)
            canvas.setFillColor(colors.HexColor("#374151"))
            canvas.setFont("Helvetica", 7)
            canvas.drawCentredString(x, bottom - 12, labels[index][:12])
            canvas.setFillColor(colors.HexColor("#0f766e"))

    def _draw_table_preview(self, canvas: Canvas) -> None:
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#4b5563"))
        y = self.height - 34
        for row in self.rows[:5]:
            text = ", ".join(f"{key}: {value}" for key, value in list(row.items())[:3])
            canvas.drawString(24, y, text[:110])
            y -= 14

    def _format_number(self, value: float) -> str:
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if abs(value) >= 1_000:
            return f"{value / 1_000:.1f}K"
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}"


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
        user_message_count = sum(1 for message in messages if message.get("role") == "user")
        if user_message_count < MIN_REPORT_USER_MESSAGES:
            remaining = MIN_REPORT_USER_MESSAGES - user_message_count
            suffix = "" if remaining == 1 else "s"
            raise ValueError(f"Send {remaining} more message{suffix} before generating a report.")

        narrative = await self._generate_report_narrative(session)
        pdf = self._build_pdf(session=session, narrative=narrative)
        filename = self._safe_filename(str(session.get("title") or "datasage-report")) + ".pdf"
        return pdf, filename

    async def _generate_report_narrative(self, session: dict) -> dict[str, Any]:
        if not self.settings.openrouter_report_api_key:
            return self._fallback_narrative(session)
        try:
            narrative = await self._generate_openrouter_narrative(session)
        except Exception as exc:
            logger.warning("Falling back to local report narrative because OpenRouter report generation failed: %s", exc)
            return self._fallback_narrative(session)
        return self._normalize_narrative(narrative, session)

    async def _generate_openrouter_narrative(self, session: dict) -> dict[str, Any]:
        transcript = self._compact_transcript(session.get("messages", []))
        visuals = self._visual_summaries(session.get("messages", []))
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
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
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
        user_messages = [str(message.get("content") or "").strip() for message in messages if message.get("role") == "user"]
        assistant_messages = [
            str(message.get("content") or "").strip() for message in messages if message.get("role") == "assistant"
        ]
        visuals = self._visual_summaries(messages)
        title = str(session.get("title") or "DataSage Report")

        summary_bits = [
            f"This report summarizes a DataSage session with {len(user_messages)} user requests and {len(assistant_messages)} assistant responses.",
            "The conversation focused on the user's data-analysis workflow, generated answers, charts or dashboard requests, and follow-up issues raised during the session.",
        ]
        if visuals:
            summary_bits.append(f"The session produced {len(visuals)} visualization-ready result set{'s' if len(visuals) != 1 else ''}.")

        findings = []
        for question in user_messages[-6:]:
            findings.append(f"User explored: {self._truncate(question, 180)}")
        for answer in assistant_messages[-4:]:
            findings.append(f"Assistant outcome: {self._truncate(answer, 200)}")
        if visuals:
            for visual in visuals[:3]:
                findings.append(
                    f"Visualization captured: {self._truncate(str(visual.get('title') or 'Untitled visualization'), 160)}"
                )

        return self._normalize_narrative(
            {
                "title": title,
                "executive_summary": " ".join(summary_bits),
                "key_findings": findings[:10],
                "recommendations": [
                    "Review the generated findings against the source data before sharing externally.",
                    "Ask follow-up questions with exact metrics, tables, companies, or periods where deeper analysis is needed.",
                    "Regenerate the report after the session includes final validated charts and conclusions.",
                ],
                "limitations": [
                    "This report is based only on the saved chat transcript and visualization payloads.",
                    "If an analysis failed or was rate-limited, its final answer may be incomplete in the report.",
                ],
            },
            session,
        )

    def _normalize_narrative(self, narrative: dict[str, Any], session: dict) -> dict[str, Any]:
        title = str(narrative.get("title") or session.get("title") or "DataSage Report")
        executive_summary = str(narrative.get("executive_summary") or "").strip()
        if not executive_summary:
            executive_summary = "This report summarizes the main analysis requests, responses, and follow-up items from the chat session."

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
            "recommendations": listify(narrative.get("recommendations"), "Continue the analysis with a more specific follow-up question."),
            "limitations": listify(narrative.get("limitations"), "The report only uses information saved in this chat session."),
        }

    def _build_pdf(self, *, session: dict, narrative: dict[str, Any]) -> bytes:
        buffer = io.BytesIO()
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=42,
            leftMargin=42,
            topMargin=42,
            bottomMargin=42,
            title=str(narrative.get("title") or session.get("title") or "DataSage Report"),
        )
        story: list[Any] = []

        title = str(narrative.get("title") or session.get("title") or "DataSage Report")
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 10))
        story.append(Paragraph(str(narrative.get("executive_summary") or ""), styles["BodyText"]))
        story.append(Spacer(1, 16))

        self._add_bullet_section(story, styles, "Key Findings", narrative.get("key_findings"))
        self._add_bullet_section(story, styles, "Recommendations", narrative.get("recommendations"))
        self._add_bullet_section(story, styles, "Limitations", narrative.get("limitations"))

        visual_payloads = self._visual_payloads(session.get("messages", []))
        if visual_payloads:
            story.append(PageBreak())
            story.append(Paragraph("Visualizations", styles["Heading1"]))
            for payload in visual_payloads[:4]:
                rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
                title_text = str(payload.get("summary") or payload.get("explanation") or "Visualization")
                story.append(ReportChart(title_text, rows, payload.get("chart_type")))
                story.append(Spacer(1, 10))
                story.append(self._rows_table(rows[:6]))
                story.append(Spacer(1, 18))

        story.append(PageBreak())
        story.append(Paragraph("Conversation Excerpts", styles["Heading1"]))
        for message in session.get("messages", [])[-12:]:
            role = str(message.get("role") or "").title()
            content = self._truncate(str(message.get("content") or ""), 900)
            story.append(Paragraph(f"<b>{role}</b>: {self._escape(content)}", styles["BodyText"]))
            story.append(Spacer(1, 8))

        doc.build(story)
        return buffer.getvalue()

    def _add_bullet_section(self, story: list[Any], styles: dict, title: str, items: Any) -> None:
        story.append(Paragraph(title, styles["Heading1"]))
        if isinstance(items, str):
            items = [items]
        for item in items or ["No additional notes."]:
            story.append(Paragraph(f"- {self._escape(str(item))}", styles["BodyText"]))
        story.append(Spacer(1, 14))

    def _rows_table(self, rows: list[dict[str, Any]]) -> Table:
        if not rows:
            return Table([["No rows available"]])
        headers = list(rows[0].keys())[:5]
        data = [headers]
        for row in rows:
            data.append([self._truncate(str(row.get(header, "")), 40) for header in headers])
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    def _compact_transcript(self, messages: list[dict]) -> str:
        lines = []
        for message in messages[-24:]:
            role = str(message.get("role") or "message")
            content = self._truncate(str(message.get("content") or ""), 1000)
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)

    def _visual_payloads(self, messages: list[dict]) -> list[dict[str, Any]]:
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

    def _visual_summaries(self, messages: list[dict]) -> list[dict[str, Any]]:
        summaries = []
        for payload in self._visual_payloads(messages):
            rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
            summaries.append(
                {
                    "title": payload.get("summary") or payload.get("explanation"),
                    "chart_type": payload.get("chart_type"),
                    "row_count": len(rows),
                    "sample_rows": rows[:3],
                }
            )
        return summaries

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if "```" in cleaned:
            parts = [part.strip() for part in cleaned.split("```") if part.strip()]
            cleaned = next((part.removeprefix("json").strip() for part in parts if "{" in part), cleaned)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.S)
            payload = json.loads(match.group(0)) if match else {}
        return payload if isinstance(payload, dict) else {}

    def _safe_filename(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
        return cleaned[:80] or "datasage-report"

    def _truncate(self, text: str, max_chars: int) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 3].rstrip()}..."

    def _escape(self, value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
