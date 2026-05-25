from __future__ import annotations

import base64
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

# ── Light colour palette ─────────────────────────────────────────────
PRIMARY       = "#1a56db"
CHART_COLORS  = ["#2563eb", "#f97316", "#06b6d4", "#8b5cf6", "#10b981",
                 "#f59e0b", "#ef4444", "#14b8a6"]

REPORT_CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 10pt;
  color: #111827;
  background: #ffffff;
}

/* ── Top brand bar ── */
.top-bar {
  background: #ffffff;
  border-top: 4pt solid #2563eb;
  padding: 16pt 44pt 12pt;
}
.brand-row {
  display: table; width: 100%;
}
.brand-left { display: table-cell; vertical-align: top; }
.brand-right { display: table-cell; vertical-align: top; text-align: right; }
.brand-name {
  font-size: 11pt; font-weight: bold; color: #2563eb; letter-spacing: 0.5pt;
}
.brand-sub { font-size: 8pt; color: #6b7280; margin-top: 1pt; }
.top-right-meta { font-size: 8pt; color: #6b7280; }
.confidential-badge {
  background: #fef3c7; color: #92400e;
  font-size: 7pt; font-weight: bold;
  padding: 2pt 8pt; border-radius: 10pt;
  display: inline-block; margin-top: 3pt;
}

/* ── Title block ── */
.title-block {
  padding: 14pt 44pt 14pt;
  border-bottom: 1pt solid #e5e7eb;
}
.report-title {
  font-size: 22pt; font-weight: bold; color: #111827;
  line-height: 1.2; margin-bottom: 5pt;
}
.report-meta { font-size: 8.5pt; color: #6b7280; margin-bottom: 10pt; }

/* ── KPI cards ── */
.kpi-row {
  display: table; width: 100%; border-collapse: collapse;
  border: 1pt solid #e5e7eb; border-radius: 4pt;
  margin-top: 8pt;
}
.kpi-cell {
  display: table-cell;
  padding: 10pt 14pt;
  border-right: 1pt solid #e5e7eb;
  vertical-align: top;
  width: 20%;
}
.kpi-cell:last-child { border-right: none; }
.kpi-value {
  font-size: 15pt; font-weight: bold; color: #111827; line-height: 1.2;
}
.kpi-label { font-size: 7.5pt; color: #6b7280; margin-top: 2pt; }

/* ── Stat badges ── */
.stat-row { margin-top: 8pt; }
.stat-badge {
  display: inline-block;
  background: #dbeafe; color: #1d4ed8;
  font-size: 7.5pt; font-weight: bold;
  padding: 2pt 9pt; border-radius: 10pt;
  margin-right: 5pt;
}

/* ── Body wrapper ── */
.body-wrap { padding: 20pt 44pt 30pt; }

/* ── Section headings ── */
.section-header {
  background: #1a56db;
  color: #f0f9ff;
  font-size: 10.5pt; font-weight: bold;
  padding: 6pt 12pt;
  border-radius: 3pt;
  margin-top: 20pt; margin-bottom: 10pt;
}

/* ── Summary box ── */
.summary-box {
  background: #f0f9ff;
  border-left: 3.5pt solid #2563eb;
  border-radius: 3pt;
  padding: 11pt 14pt;
  margin-bottom: 14pt;
  font-size: 9.5pt; color: #374151; line-height: 1.65;
}

/* ── Bullet lists ── */
.bullet-list { margin: 0 0 6pt 0; padding: 0; }
.bullet-item {
  font-size: 9.5pt; color: #374151;
  padding: 4pt 0 4pt 14pt; line-height: 1.55;
  border-bottom: 0.5pt solid #f3f4f6;
}
.bullet-item:last-child { border-bottom: none; }

/* ── Data tables ── */
.data-table {
  width: 100%; border-collapse: collapse;
  margin-top: 6pt; margin-bottom: 4pt; font-size: 8.5pt;
}
.data-table th {
  background: #1a56db; color: #ffffff;
  padding: 5pt 9pt; text-align: left; font-weight: bold;
}
.data-table td {
  padding: 4pt 9pt; color: #374151;
  border-bottom: 0.5pt solid #f3f4f6;
}
.data-table tr:nth-child(even) td { background: #f9fafb; }

/* ── Viz block ── */
.viz-block {
  background: #ffffff;
  border: 1pt solid #e5e7eb;
  border-radius: 4pt;
  padding: 12pt 14pt 8pt;
  margin: 0 0 14pt 0;
  page-break-inside: avoid;
}
.viz-title {
  font-size: 10pt; font-weight: bold; color: #111827;
  margin-bottom: 8pt; text-align: center;
}
.viz-caption {
  font-size: 7.5pt; color: #9ca3af;
  margin-top: 6pt; text-align: center;
}
.viz-chart { text-align: center; margin: 4pt 0; }

/* ── Conversation ── */
.message-block {
  margin-bottom: 8pt; padding: 7pt 11pt;
  border-radius: 3pt; font-size: 9pt; line-height: 1.55;
}
.message-user {
  background: #eff6ff; border-left: 3pt solid #2563eb; color: #1e40af;
}
.message-assistant {
  background: #f9fafb; border-left: 3pt solid #d1d5db; color: #374151;
}
.message-role {
  font-size: 7pt; font-weight: bold; text-transform: uppercase;
  letter-spacing: 0.5pt; color: #6b7280; margin-bottom: 3pt;
}

/* ── Divider / footer ── */
.divider { border: none; border-top: 0.5pt solid #e5e7eb; margin: 12pt 0; }
.footer {
  background: #f9fafb; color: #9ca3af;
  font-size: 7pt; padding: 7pt 44pt;
  border-top: 1pt solid #e5e7eb;
  display: table; width: 100%;
}
.footer-left  { display: table-cell; }
.footer-right { display: table-cell; text-align: right; }
"""


# ── Matplotlib chart helpers ─────────────────────────────────────────

def _chart_to_b64(fig) -> str:
    """Render a matplotlib figure to base64 PNG."""
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor="#ffffff", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _bar_chart_b64(rows: list[dict]) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        return ""

    if not rows:
        return ""
    keys = list(rows[0].keys())
    label_key, value_key = keys[0], (keys[1] if len(keys) > 1 else keys[0])
    labels = [str(r.get(label_key, ""))[:18] for r in rows[:10]]
    try:
        values = [float(r.get(value_key, 0) or 0) for r in rows[:10]]
    except (TypeError, ValueError):
        return ""

    n = len(labels)
    fig_h = max(2.6, 0.45 * n + 0.8)
    fig, ax = plt.subplots(figsize=(6.5, fig_h))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    colors = [CHART_COLORS[i % len(CHART_COLORS)] for i in range(n)]

    if n <= 6:
        # vertical
        bars = ax.bar(labels, values, color=colors, width=0.55, zorder=3)
        ax.set_xticks(range(n))
        ax.set_xticklabels(labels, fontsize=8, rotation=20 if n > 4 else 0, ha="right")
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                    _fmt_value(val), ha="center", va="bottom", fontsize=7.5, fontweight="bold", color="#111827")
    else:
        # horizontal
        bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.55, zorder=3)
        for bar, val in zip(bars, values[::-1]):
            ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                    _fmt_value(val), ha="left", va="center", fontsize=7.5, fontweight="bold", color="#111827")
        ax.set_xlabel("")

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
    ax.tick_params(axis="y", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")
    ax.yaxis.grid(True, color="#f3f4f6", zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(pad=0.4)
    return _chart_to_b64(fig)


def _line_chart_b64(rows: list[dict]) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        return ""

    if not rows:
        return ""
    keys = list(rows[0].keys())
    label_key, value_key = keys[0], (keys[1] if len(keys) > 1 else keys[0])
    labels = [str(r.get(label_key, "")) for r in rows[:12]]
    try:
        values = [float(r.get(value_key, 0) or 0) for r in rows[:12]]
    except (TypeError, ValueError):
        return ""

    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    xs = range(len(labels))
    ax.fill_between(xs, values, alpha=0.08, color="#2563eb")
    ax.plot(xs, values, color="#2563eb", linewidth=2.2, marker="o",
            markersize=5, markerfacecolor="#2563eb", markeredgecolor="#ffffff",
            markeredgewidth=1.5, zorder=3)

    # value labels
    for i, v in enumerate(values):
        ax.text(i, v + max(values) * 0.02, _fmt_value(v),
                ha="center", va="bottom", fontsize=7, fontweight="bold", color="#111827")

    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=8, rotation=30 if len(labels) > 6 else 0, ha="right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
    ax.tick_params(axis="y", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e5e7eb")
    ax.spines["bottom"].set_color("#e5e7eb")
    ax.yaxis.grid(True, color="#f3f4f6", zorder=0)
    ax.set_axisbelow(True)
    plt.tight_layout(pad=0.4)
    return _chart_to_b64(fig)


def _pie_chart_b64(rows: list[dict]) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return ""

    if not rows:
        return ""
    keys = list(rows[0].keys())
    label_key, value_key = keys[0], (keys[1] if len(keys) > 1 else keys[0])
    labels = [str(r.get(label_key, ""))[:20] for r in rows[:6]]
    try:
        values = [float(r.get(value_key, 0) or 0) for r in rows[:6]]
    except (TypeError, ValueError):
        return ""

    colors = [CHART_COLORS[i % len(CHART_COLORS)] for i in range(len(labels))]
    fig, ax = plt.subplots(figsize=(5.5, 2.8))
    fig.patch.set_facecolor("#ffffff")
    wedges, texts, autotexts = ax.pie(
        values, labels=None, colors=colors,
        autopct="%1.1f%%", startangle=90,
        wedgeprops={"linewidth": 1.5, "edgecolor": "#ffffff"},
        pctdistance=0.75,
    )
    for at in autotexts:
        at.set_fontsize(7.5)
        at.set_color("#ffffff")
        at.set_fontweight("bold")
    # Donut hole
    centre = plt.Circle((0, 0), 0.5, fc="#ffffff")
    ax.add_patch(centre)
    # Legend
    ax.legend(wedges, [f"{l}  {_fmt_value(v)}" for l, v in zip(labels, values)],
              loc="center left", bbox_to_anchor=(1, 0.5),
              fontsize=8, frameon=False)
    ax.set_aspect("equal")
    plt.tight_layout(pad=0.4)
    return _chart_to_b64(fig)


def _render_chart_b64(payload: dict) -> str:
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if not rows:
        return ""
    chart_type = str(payload.get("chart_type") or "BAR").upper()
    if chart_type == "LINE":
        return _line_chart_b64(rows)
    if chart_type in ("PIE", "DONUT"):
        return _pie_chart_b64(rows)
    return _bar_chart_b64(rows)


def _fmt_value(v: float) -> str:
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        s = f"{v / 1_000_000:.1f}M"
        return f"${s}" if v >= 0 else f"-${s[1:]}"
    if abs_v >= 1_000:
        s = f"{v / 1_000:.1f}K"
        return f"${s}" if v >= 0 else f"-${s[1:]}"
    if abs_v == int(abs_v):
        return str(int(v))
    return f"{v:.2f}"


# ── HTML builder ─────────────────────────────────────────────────────

def _build_html_report(*, session: dict, narrative: dict[str, Any]) -> str:
    messages = session.get("messages", [])
    user_msgs  = [m for m in messages if m.get("role") == "user"]
    asst_msgs  = [m for m in messages if m.get("role") == "assistant"]
    visual_payloads = _visual_payloads(messages)
    generated_at = datetime.now().strftime("%d %b %Y")
    title = _esc(str(narrative.get("title") or session.get("title") or "DataSage Analytics Report"))
    first_user_q = _esc(_trunc(str(user_msgs[0].get("content") or ""), 80)) if user_msgs else ""

    def bullet_section(heading: str, items: Any) -> str:
        if isinstance(items, str):
            items = [items]
        rows_html = "".join(
            f'<div class="bullet-item">&#8226;&ensp;{_esc(str(item))}</div>'
            for item in (items or ["No additional notes."])
        )
        return f'<div class="section-header">{heading}</div><div class="bullet-list">{rows_html}</div>'

    def data_table_html(rows: list[dict]) -> str:
        if not rows:
            return ""
        headers = list(rows[0].keys())[:6]
        ths = "".join(f"<th>{_esc(str(h).replace('_', ' ').title())}</th>" for h in headers)
        trs = ""
        for row in rows[:10]:
            tds = "".join(f"<td>{_esc(_trunc(str(row.get(h, '')), 40))}</td>" for h in headers)
            trs += f"<tr>{tds}</tr>"
        return f'<table class="data-table"><tr>{ths}</tr>{trs}</table>'

    # ── Stat badges ──
    stats_html = (
        f'<div class="stat-row">'
        f'<span class="stat-badge">&#128172; {len(user_msgs)} user messages</span>'
        f'<span class="stat-badge">&#129302; {len(asst_msgs)} AI responses</span>'
        f'<span class="stat-badge">&#128202; {len(visual_payloads)} visualizations</span>'
        f'</div>'
    )

    # ── Visualizations ──
    viz_html = ""
    if visual_payloads:
        viz_html += '<div class="section-header">Visualizations &amp; Data</div>'
        for idx, payload in enumerate(visual_payloads[:6], 1):
            rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
            vtitle_raw = str(payload.get("explanation") or payload.get("summary") or f"Visualization {idx}")
            vtitle = _esc(_trunc(vtitle_raw, 120))
            chart_type = str(payload.get("chart_type") or "BAR").upper()
            b64 = _render_chart_b64(payload)
            chart_img = (
                f'<img src="data:image/png;base64,{b64}" '
                f'style="width:100%;max-width:480pt;" />'
                if b64 else ""
            )
            viz_html += f"""
<div class="viz-block">
  <div class="viz-title">{vtitle}</div>
  <div class="viz-chart">{chart_img}</div>
  <div class="viz-caption">&#9632; {chart_type} chart &bull; {len(rows)} data rows</div>
  {data_table_html(rows)}
</div>"""

    # ── Conversation transcript ──
    convo_html = '<div class="section-header">Session Transcript</div>'
    convo_html += '<p style="font-size:8pt;color:#9ca3af;margin-bottom:10pt;">Full record of the analyst\'s queries and DataSage AI responses during this session.</p>'
    for msg in messages:
        role = str(msg.get("role") or "")
        content = _esc(_trunc(str(msg.get("content") or ""), 800))
        if role == "user":
            convo_html += f'<div class="message-block message-user"><div class="message-role">&#9632; You</div>{content}</div>'
        elif role == "assistant":
            convo_html += f'<div class="message-block message-assistant"><div class="message-role">&#9632; DataSage AI</div>{content}</div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>{REPORT_CSS}</style>
</head>
<body>

<!-- TOP BRAND BAR -->
<div class="top-bar">
  <div class="brand-row">
    <div class="brand-left">
      <div class="brand-name">DATASAGE AI</div>
      <div class="brand-sub">AI-Powered Analytics Platform</div>
    </div>
    <div class="brand-right">
      <div class="top-right-meta">Generated: {generated_at}</div>
      <div><span class="confidential-badge">CONFIDENTIAL</span></div>
    </div>
  </div>
</div>

<!-- TITLE BLOCK -->
<div class="title-block">
  <div class="report-title">{title}</div>
  <div class="report-meta">
    {first_user_q} &middot; Session Report &middot; {len(user_msgs)} queries &middot; {len(visual_payloads)} visualisations
  </div>
  {stats_html}
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
  <span class="footer-left">DataSage AI &bull; Confidential Analytics Report</span>
  <span class="footer-right">Page 1</span>
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
        user_messages     = [str(m.get("content") or "").strip() for m in messages if m.get("role") == "user"]
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
            raise RuntimeError("xhtml2pdf is not installed. Run: pip install xhtml2pdf") from exc

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