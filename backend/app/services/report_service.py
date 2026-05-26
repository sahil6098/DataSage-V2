"""
report_service.py — DataSage professional PDF report generator.
Uses ReportLab directly (no HTML/CSS parsing) for fast, pixel-perfect output.

Fix log (v9):
  1. _normalize_unicode() added — strips em/en dashes, curly quotes, ellipsis,
     non-breaking spaces and other chars unsupported by Helvetica that were
     rendering as black squares (■). Applied in _esc(), _CalloutBox.draw(),
     and _TitleBlock.draw().
  2. vtitle boilerplate stripping fixed — _strip_boilerplate_prefix() now
     applied to the chart title (vtitle) before it is truncated and rendered,
     so "To create a graph of…" no longer appears as chart headings.
  3. Numeric month labels humanised — _humanize_label() converts "1"→"January"
     etc. Applied in all chart functions so axes show month names, not numbers.
  4. _line_img now accepts a list of vkeys and plots all series with distinct
     colours and a legend; previously only vkeys[0] was plotted, hiding the
     second Opex series.
  5. _render_chart passes full vkeys list to _line_img (not vkeys[0]).
  6. LLM-supplied important_qa_pairs filtered for quality (boilerplate /
     "could not" / too-short answers removed) even when the LLM path is used.
  --- (from v8) ---
  7. _combo_bar_line_img — diff/variance series rendered as line on 2nd axis.
  8. _split_series_by_scale threshold tightened to 8%.
  9. _data_table max_rows=12; _detect_value_keys samples rows[:12].
  10. Blank page 2 eliminated — conditional PageBreak.
  11. Index-based message pairing replaces zip misalignment.
  12. _variance_label() sign-correct terminology.
  --- (from v7) ---
  13. Title word-wrap, subtitle metadata-only, chronological sort, boilerplate
      filter, callout word-wrap, KPI date-only.
  --- (from v6) ---
  14. Secondary twin axis, negative bar labels, legend below, data-density
      scoring, MAX_CHART_H cap.
"""
from __future__ import annotations

import hashlib
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

logger = get_logger(__name__)

MIN_REPORT_USER_MESSAGES = 4

# ── ReportLab imports ─────────────────────────────────────────────────
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.platypus.frames import Frame
from reportlab.platypus.flowables import Flowable

# ── Brand palette ─────────────────────────────────────────────────────
C_PRIMARY      = HexColor("#1a56db")
C_PRIMARY_DARK = HexColor("#1e3a8a")
C_BG_LIGHT     = HexColor("#eff6ff")
C_BG_ALT       = HexColor("#f9fafb")
C_BORDER       = HexColor("#e5e7eb")
C_TEXT         = HexColor("#111827")
C_MUTED        = HexColor("#6b7280")

CHART_HEX = [
    "#2563eb", "#f97316", "#06b6d4", "#8b5cf6",
    "#10b981", "#f59e0b", "#ef4444", "#14b8a6",
]

# ── Page geometry ─────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN_H   = 18 * mm
MARGIN_TOP = 26 * mm
MARGIN_BOT = 14 * mm
CONTENT_W  = PAGE_W - 2 * MARGIN_H


# ══════════════════════════════════════════════════════════════════════
#  FIX v9 — Unicode normalisation
#  Helvetica (the only font embedded by default in ReportLab PDFs) does
#  not contain glyphs for curly quotes, em/en dashes, ellipsis, etc.
#  ReportLab silently substitutes a filled rectangle (■) for every missing
#  glyph.  We replace every such character with a plain ASCII equivalent
#  before ANY text reaches the canvas or a Paragraph flowable.
# ══════════════════════════════════════════════════════════════════════

def _normalize_unicode(text: str) -> str:
    """
    Replace Unicode characters that Helvetica cannot render with safe
    ASCII equivalents.  Must be called before _esc() and before any
    canvas.drawString() call.
    """
    return (
        text
        .replace("\u2014", "-")    # em dash —
        .replace("\u2013", "-")    # en dash –
        .replace("\u2012", "-")    # figure dash
        .replace("\u2015", "-")    # horizontal bar
        .replace("\u2010", "-")    # hyphen
        .replace("\u2011", "-")    # non-breaking hyphen
        .replace("\u2018", "'")    # left single quotation mark '
        .replace("\u2019", "'")    # right single quotation mark '
        .replace("\u201a", "'")    # single low-9 quotation mark ‚
        .replace("\u201b", "'")    # single high-reversed-9 mark ‛
        .replace("\u201c", '"')    # left double quotation mark "
        .replace("\u201d", '"')    # right double quotation mark "
        .replace("\u201e", '"')    # double low-9 quotation mark „
        .replace("\u2022", "*")    # bullet •
        .replace("\u00b7", "-")    # middle dot ·
        .replace("\u2026", "...")  # horizontal ellipsis …
        .replace("\u00a0", " ")    # non-breaking space
        .replace("\u00ad", "-")    # soft hyphen
        .replace("\u2039", "<")    # single left-pointing angle quotation ‹
        .replace("\u203a", ">")    # single right-pointing angle quotation ›
        .replace("\u00ab", '"')    # left-pointing double angle quotation «
        .replace("\u00bb", '"')    # right-pointing double angle quotation »
        .replace("\u2032", "'")    # prime ′
        .replace("\u2033", '"')    # double prime ″
    )


# ══════════════════════════════════════════════════════════════════════
#  Title cleaning
# ══════════════════════════════════════════════════════════════════════

_QUERY_VERBS = re.compile(
    r"^(give me|show me|what is|what are|list|get|find|tell me|fetch|"
    r"display|provide|calculate|can you|could you|please)\b",
    re.I,
)


def _clean_title(raw: str) -> str:
    s = _normalize_unicode(raw.strip())
    if not s:
        return "DataSage Analytics Report"

    if len(s) <= 60 and not _QUERY_VERBS.match(s) and "?" not in s:
        return s[:70]

    cleaned = _QUERY_VERBS.sub("", s).strip(" ,.")

    stop = {"and", "or", "of", "in", "for", "the", "a", "an", "to", "with", "by", "on", "at"}
    words = cleaned.split()
    title_words = []
    for i, w in enumerate(words):
        if i == 0 or w.lower() not in stop:
            title_words.append(w.capitalize())
        else:
            title_words.append(w.lower())

    result = " ".join(title_words)
    if len(result) > 70:
        result = result[:67].rstrip() + "..."

    return result or "DataSage Analytics Report"


# ══════════════════════════════════════════════════════════════════════
#  Boilerplate detection
# ══════════════════════════════════════════════════════════════════════

_BOILERPLATE_PREFIXES = (
    "to create a", "to make a", "to build a", "to generate a",
    "i can create", "i can make", "i can build", "i can generate",
    "i could not", "here is a", "here's a",
    "the graph will show", "the chart will show",
    "we can use the provided",
)


def _is_boilerplate(text: str) -> bool:
    lo = text.lower().strip()
    return any(lo.startswith(p) for p in _BOILERPLATE_PREFIXES)


def _strip_boilerplate_prefix(text: str) -> str:
    if not _is_boilerplate(text):
        return text
    sentences = re.split(r"\.\s+", text.strip())
    for sent in sentences:
        if not _is_boilerplate(sent) and len(sent.strip()) > 30:
            return sent.strip()
    return text


# ══════════════════════════════════════════════════════════════════════
#  Variance label helper
# ══════════════════════════════════════════════════════════════════════

def _variance_label(diff: float) -> str:
    if diff > 0:
        return "over budget (cost overrun)"
    elif diff < 0:
        return "under budget"
    return "on budget"


# ══════════════════════════════════════════════════════════════════════
#  Custom Flowables
# ══════════════════════════════════════════════════════════════════════

class _TitleBlock(Flowable):
    BASE_H = 36 * mm

    def __init__(self, title: str, subtitle: str, stats: list[tuple[str, str]]) -> None:
        super().__init__()
        # Normalise unicode NOW so the canvas never sees bad glyphs
        self.title    = _normalize_unicode(title)
        self.subtitle = _normalize_unicode(subtitle)[:130]
        self.stats    = stats
        self.width    = CONTENT_W

        _usable       = CONTENT_W - 20 * mm
        _approx_chars = max(1, int(_usable / 8.5))
        _lines        = max(1, -(-len(self.title) // _approx_chars))
        _extra        = max(0, _lines - 1) * 7 * mm
        self.height   = self.BASE_H + _extra

    def wrap(self, availW, availH):
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        H = self.height

        c.setFillColor(HexColor("#eff6ff"))
        c.roundRect(0, 0, self.width, H, 5, fill=1, stroke=0)

        c.setFillColor(C_PRIMARY)
        c.rect(0, H - 3, self.width, 3, fill=1, stroke=0)

        c.setFillColor(C_PRIMARY)
        c.rect(0, 10 * mm, 3.5, H - 13 * mm, fill=1, stroke=0)

        font, fsize = "Helvetica-Bold", 15
        line_h      = fsize * 1.35
        usable_w    = self.width - 20 * mm
        c.setFont(font, fsize)

        # self.title already normalised in __init__
        words, lines, cur = self.title.split(), [], ""
        for word in words:
            test = (cur + " " + word).strip()
            if c.stringWidth(test, font, fsize) <= usable_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)

        title_top_y = H - 11 * mm
        c.setFillColor(C_TEXT)
        for i, ln in enumerate(lines):
            c.drawString(10 * mm, title_top_y - i * line_h, ln)

        subtitle_y = title_top_y - len(lines) * line_h - 2 * mm
        c.setFillColor(C_MUTED)
        c.setFont("Helvetica", 7.5)
        # self.subtitle already normalised
        c.drawString(10 * mm, subtitle_y, self.subtitle)

        x = 10 * mm
        y = 4.5 * mm
        for value, label in self.stats[:5]:
            text = f"{value}  {label}"
            c.setFont("Helvetica-Bold", 7)
            tw = c.stringWidth(text, "Helvetica-Bold", 7)
            cw = tw + 14
            c.setFillColor(C_PRIMARY)
            c.roundRect(x, y, cw, 9, 4, fill=1, stroke=0)
            c.setFillColor(white)
            c.drawString(x + 7, y + 2.2, text)
            x += cw + 5


class _SectionHeader(Flowable):
    H = 9 * mm

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text   = _normalize_unicode(text)
        self.width  = CONTENT_W
        self.height = self.H

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(C_PRIMARY)
        c.roundRect(0, 1 * mm, self.width, 7.5 * mm, 3, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(7, 4.2 * mm, self.text.upper())


class _CalloutBox(Flowable):
    """Left-bordered callout box — word-wrap via canvas.stringWidth."""

    def __init__(self, text: str) -> None:
        super().__init__()
        # Normalise unicode before any processing
        self._text = _normalize_unicode(text)
        self.width = CONTENT_W
        chars_per_line = max(1, int((self.width - 22) / 4.8))
        total_lines = 0
        for raw_line in self._text.split("\n"):
            words = raw_line.split()
            if not words:
                total_lines += 1
                continue
            line, count = [], 0
            for word in words:
                if len(" ".join(line + [word])) <= chars_per_line:
                    line.append(word)
                else:
                    count += 1
                    line = [word]
            count += 1
            total_lines += count
        self.height = max(18 * mm, total_lines * 5.2 * mm + 10 * mm)

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(HexColor("#f0f9ff"))
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        c.setFillColor(C_PRIMARY)
        c.rect(0, 0, 3.5, self.height, fill=1, stroke=0)

        font, fsize, line_h = "Helvetica", 9, 5.2 * mm
        usable = self.width - 22
        c.setFont(font, fsize)

        # self._text already normalised in __init__
        words, cur, rendered = self._text.split(), "", []
        for word in words:
            test = (cur + " " + word).strip()
            if c.stringWidth(test, font, fsize) <= usable:
                cur = test
            else:
                rendered.append(cur)
                cur = word
        if cur:
            rendered.append(cur)

        c.setFillColor(C_TEXT)
        y = self.height - 7 * mm
        for ln in rendered:
            if y < 3 * mm:
                break
            c.drawString(10, y, ln)
            y -= line_h


# ══════════════════════════════════════════════════════════════════════
#  Paragraph styles
# ══════════════════════════════════════════════════════════════════════

def _st() -> dict[str, ParagraphStyle]:
    return {
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=9, leading=13,
            textColor=C_TEXT, leftIndent=10, spaceAfter=2),
        "caption": ParagraphStyle(
            "caption", fontName="Helvetica-Oblique", fontSize=7.5,
            textColor=C_MUTED, alignment=TA_CENTER),
        "sub": ParagraphStyle(
            "sub", fontName="Helvetica-Oblique", fontSize=8,
            textColor=C_MUTED, spaceAfter=5),
        "th": ParagraphStyle(
            "th", fontName="Helvetica-Bold", fontSize=7.5, textColor=white),
        "td": ParagraphStyle(
            "td", fontName="Helvetica", fontSize=7.5, leading=10, textColor=C_TEXT),
        "role": ParagraphStyle(
            "role", fontName="Helvetica-Bold", fontSize=6.5,
            textColor=C_MUTED, spaceAfter=1),
        "viz_explain": ParagraphStyle(
            "viz_explain", fontName="Helvetica", fontSize=8.5, leading=13,
            textColor=C_TEXT, spaceAfter=4, spaceBefore=3,
            leftIndent=4, rightIndent=4),
        "transcript_q": ParagraphStyle(
            "transcript_q", fontName="Helvetica-Bold", fontSize=8.5,
            leading=12, textColor=HexColor("#1e40af"),
            leftIndent=8, spaceAfter=2),
        "transcript_a": ParagraphStyle(
            "transcript_a", fontName="Helvetica", fontSize=8.5,
            leading=12, textColor=HexColor("#374151"),
            leftIndent=8, spaceAfter=8),
    }


# ══════════════════════════════════════════════════════════════════════
#  Shared text helpers
# ══════════════════════════════════════════════════════════════════════

def _esc(value: str) -> str:
    """Normalise unicode then XML-escape for ReportLab Paragraph markup."""
    value = _normalize_unicode(value)
    return (value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _trunc(text: str, max_chars: int) -> str:
    n = " ".join(text.split())
    return n if len(n) <= max_chars else f"{n[:max_chars - 3].rstrip()}..."


# ══════════════════════════════════════════════════════════════════════
#  Chart helpers
# ══════════════════════════════════════════════════════════════════════

def _fmt_value(v: float) -> str:
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        s = f"{abs_v / 1_000_000:.1f}M"
        return f"${s}" if v >= 0 else f"-${s}"
    if abs_v >= 1_000:
        s = f"{abs_v / 1_000:.1f}K"
        return f"${s}" if v >= 0 else f"-${s}"
    if abs_v == int(abs_v):
        return str(int(v))
    return f"{v:.2f}"


def _fmt_cell(value: str) -> str:
    s = value.strip()
    try:
        f = float(s)
        if abs(f) >= 1_000:
            return _fmt_value(f)
        if f != int(f):
            return f"{f:.2f}"
        return str(int(f))
    except ValueError:
        return s


def _is_numeric_str(s: str) -> bool:
    try:
        float(str(s).replace(",", "").replace("$", "").replace("-", "", 1))
        return True
    except ValueError:
        return False


# ── FIX v9: numeric month → name conversion ───────────────────────────

_MONTH_NUM_TO_NAME = {
    "1": "January",  "2": "February",  "3": "March",
    "4": "April",    "5": "May",       "6": "June",
    "7": "July",     "8": "August",    "9": "September",
    "10": "October", "11": "November", "12": "December",
}


def _humanize_label(label: str) -> str:
    """Convert numeric month labels ('1'..'12') to full month names."""
    return _MONTH_NUM_TO_NAME.get(label.strip(), label)


# ── Month / date chronological sorting ────────────────────────────────

_MONTH_ORDER = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_sort_key(label: str):
    lo = _humanize_label(label.strip()).lower()
    if lo in _MONTH_ORDER:
        return (0, _MONTH_ORDER[lo], 0)
    m = re.match(r"(\d{4})-(\d{2})", lo)
    if m:
        return (int(m.group(1)), int(m.group(2)), 0)
    mq = re.match(r"q(\d)\s*(\d{4})|(\d{4})\s*q(\d)", lo)
    if mq:
        yr  = int(mq.group(2) or mq.group(3))
        qtr = int(mq.group(1) or mq.group(4))
        return (yr, qtr * 3, 0)
    # Pure numeric month (1-12)
    try:
        n = int(label.strip())
        if 1 <= n <= 12:
            return (0, n, 0)
    except ValueError:
        pass
    return (9999, 0, label)


def _sort_rows_by_label(rows: list[dict], lk: str) -> list[dict]:
    if len(rows) < 2:
        return rows
    sample = [str(r.get(lk, "")).strip().lower() for r in rows[:3]]
    temporal = any(
        _humanize_label(lb).lower() in _MONTH_ORDER
        or re.match(r"\d{4}-\d{2}", lb)
        or (lb.isdigit() and 1 <= int(lb) <= 12)
        for lb in sample
    )
    return sorted(rows, key=lambda r: _month_sort_key(str(r.get(lk, "")))) if temporal else rows


def _detect_label_key(rows: list[dict]) -> str:
    if not rows:
        return ""
    for k in list(rows[0].keys()):
        if not _is_numeric_str(str(rows[0].get(k, ""))):
            return k
    return list(rows[0].keys())[0]


def _detect_value_keys(rows: list[dict], label_key: str) -> list[str]:
    if not rows:
        return []
    keys   = list(rows[0].keys())
    sample = rows[:12]
    result = []
    for k in keys:
        if k == label_key:
            continue
        nc = sum(1 for r in sample if _is_numeric_str(str(r.get(k, ""))))
        if nc >= max(1, len(sample) // 2):
            result.append(k)
    return result or ([keys[1]] if len(keys) > 1 else [])


def _is_diff_key(key: str) -> bool:
    lo = key.lower()
    return any(w in lo for w in ("diff", "variance", "delta", "change", "gap", "deviation"))


def _chart_to_rl_image(fig, max_w: float) -> Image:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="#ffffff", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    img         = Image(buf)
    MAX_CHART_H = 460.0
    scale_w     = min(1.0, max_w / img.imageWidth)
    scale_h     = min(1.0, MAX_CHART_H / img.imageHeight)
    scale       = min(scale_w, scale_h)
    img.drawWidth  = img.imageWidth  * scale
    img.drawHeight = img.imageHeight * scale
    return img


def _render_chart(payload: dict, max_w: float = CONTENT_W - 8) -> Image | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
    except ImportError:
        return None

    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if not rows:
        return None

    ctype = str(payload.get("chart_type") or "bar").lower()
    lk    = _detect_label_key(rows)
    vkeys = _detect_value_keys(rows, lk)
    if not vkeys:
        return None

    rows = _sort_rows_by_label(rows, lk)

    try:
        # FIX v9: pass full vkeys list to _line_img so all series are plotted
        if ctype == "line":
            return _line_img(rows, lk, vkeys, max_w)
        if ctype in ("pie", "donut"):
            return _donut_img(rows, lk, vkeys[0], max_w)

        # Auto-detect diff/variance columns → combo bar+line chart
        if len(vkeys) > 1:
            diff_keys    = [k for k in vkeys if _is_diff_key(k)]
            primary_keys = [k for k in vkeys if k not in diff_keys]
            if diff_keys and primary_keys:
                horizontal = ctype == "horizontal_bar" or len(rows) > 8
                return _combo_bar_line_img(rows, lk, primary_keys, diff_keys[0], max_w, horizontal)

        horizontal = ctype == "horizontal_bar" or len(rows) > 6
        if len(vkeys) > 1:
            return _grouped_bar_img(rows, lk, vkeys, max_w, horizontal)
        return _bar_img(rows, lk, vkeys[0], max_w, horizontal)
    except Exception:
        logger.exception("Chart render failed")
        return None


# ── FIX v9: multi-series line chart ──────────────────────────────────

def _line_img(rows, lk, vkeys: list[str], max_w: float):
    """
    Plot one or more series as lines.  Each series gets its own colour
    and a legend entry.  Previously only vkeys[0] was ever rendered.
    """
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    # Accept a plain string for backward-compat
    if isinstance(vkeys, str):
        vkeys = [vkeys]

    # Humanise numeric month labels
    labels = [_humanize_label(str(r.get(lk, ""))) for r in rows[:16]]
    xs     = range(len(labels))
    global_max = 1.0

    fig, ax = plt.subplots(figsize=(6.5, 3.2))

    plotted = 0
    for i, vk in enumerate(vkeys[:6]):
        try:
            values = [float(str(r.get(vk, 0) or 0).replace(",", "")) for r in rows[:16]]
        except (TypeError, ValueError):
            continue
        local_max = max(abs(v) for v in values) if values else 1
        global_max = max(global_max, local_max)
        color = CHART_HEX[i % len(CHART_HEX)]
        ax.fill_between(xs, values, alpha=0.07, color=color)
        ax.plot(xs, values, color=color, linewidth=2.0, marker="o",
                markersize=4.5, markerfacecolor=color,
                markeredgecolor="#ffffff", markeredgewidth=1.2,
                label=vk.replace("_", " ").title(), zorder=3 + i)
        for xi, v in enumerate(values):
            ax.text(xi, v + global_max * 0.025, _fmt_value(v),
                    ha="center", va="bottom", fontsize=5.5,
                    fontweight="bold", color=color, clip_on=True)
        plotted += 1

    if plotted == 0:
        return None

    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=7, rotation=30 if len(labels) > 6 else 0, ha="right")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
    if plotted > 1:
        ax.legend(fontsize=7, loc="upper right", framealpha=0.85)
    _style_ax(fig, ax)
    plt.tight_layout(pad=0.4)
    return _chart_to_rl_image(fig, max_w)


# ── Combo bar + line chart for budget/actual + diff data ──────────────

def _combo_bar_line_img(rows, lk, bar_keys, line_key, max_w, horizontal=False):
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np

    labels = [_humanize_label(str(r.get(lk, ""))[:22]) for r in rows[:12]]
    n      = len(labels)
    xs     = np.arange(n)

    bar_data = []
    for bk in bar_keys:
        try:
            vals = [float(str(r.get(bk, 0) or 0).replace(",", "")) for r in rows[:12]]
        except (TypeError, ValueError):
            vals = [0.0] * n
        bar_data.append(vals)

    try:
        line_vals = [float(str(r.get(line_key, 0) or 0).replace(",", "")) for r in rows[:12]]
    except (TypeError, ValueError):
        line_vals = [0.0] * n

    nb      = len(bar_keys)
    bar_w   = min(0.35, 0.7 / nb)
    offsets = np.linspace(-(nb - 1) * bar_w / 2, (nb - 1) * bar_w / 2, nb)

    all_bar_vals = [v for series in bar_data for v in series]
    max_bar      = max(abs(v) for v in all_bar_vals) if all_bar_vals else 1
    max_line     = max(abs(v) for v in line_vals) if line_vals else 1

    fig, ax1 = plt.subplots(figsize=(7.0, min(4.5, max(3.0, 0.45 * n + 1.5))))
    ax2      = ax1.twinx()

    for i, (bk, bvals, offset) in enumerate(zip(bar_keys, bar_data, offsets)):
        color = CHART_HEX[i % len(CHART_HEX)]
        bars  = ax1.bar(xs + offset, bvals, width=bar_w, color=color, zorder=3,
                        label=bk.replace("_", " ").title(), alpha=0.85)
        for bar, val in zip(bars, bvals):
            if abs(val) > max_bar * 0.02:
                ax1.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max_bar * 0.008,
                    _fmt_value(val),
                    ha="center", va="bottom", fontsize=5.5, fontweight="bold",
                    color="#111827", clip_on=True,
                )

    line_color = CHART_HEX[nb % len(CHART_HEX)]
    ax2.plot(xs, line_vals, color=line_color, linewidth=2.0, marker="o",
             markersize=5, markerfacecolor=line_color,
             markeredgecolor="#ffffff", markeredgewidth=1.2,
             label=line_key.replace("_", " ").title(), zorder=4)
    for xi, val in zip(xs, line_vals):
        ax2.text(xi, val + max_line * 0.06, _fmt_value(val),
                 ha="center", va="bottom", fontsize=5.5,
                 fontweight="bold", color=line_color, clip_on=True)

    ax1.set_xticks(xs)
    ax1.set_xticklabels(labels, fontsize=7.5, rotation=30 if n > 6 else 0, ha="right")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
    ax1.set_ylabel("Amount", fontsize=7.5, color="#111827")
    ax1.tick_params(axis="y", labelsize=7)

    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
    ax2.set_ylabel(line_key.replace("_", " ").title(), fontsize=7.5, color=line_color)
    ax2.tick_params(axis="y", labelsize=7, colors=line_color)
    ax2.spines["right"].set_color(line_color)
    ax2.spines["right"].set_linewidth(1.2)

    if min(line_vals) < 0 < max(line_vals):
        ax2.axhline(0, color=line_color, linewidth=0.7, linestyle="--", alpha=0.5, zorder=1)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper center",
               bbox_to_anchor=(0.5, -0.18), ncol=min(4, nb + 1),
               framealpha=0.9, borderpad=0.5)

    _style_ax(fig, ax1)
    ax2.set_facecolor("#ffffff")
    ax2.spines["top"].set_visible(False)

    plt.tight_layout(pad=0.6)
    fig.subplots_adjust(bottom=0.22)
    return _chart_to_rl_image(fig, max_w)


def _bar_img(rows, lk, vk, max_w, horizontal=False):
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    labels = [_humanize_label(str(r.get(lk, ""))[:22]) for r in rows[:12]]
    try:
        values = [float(str(r.get(vk, 0) or 0).replace(",", "")) for r in rows[:12]]
    except (TypeError, ValueError):
        return None
    n       = len(labels)
    palette = [CHART_HEX[i % len(CHART_HEX)] for i in range(n)]
    max_v   = max(abs(v) for v in values) if values else 1

    if horizontal:
        fig, ax = plt.subplots(figsize=(6.2, min(5.0, max(2.8, 0.38 * n + 0.8))))
        bars = ax.barh(labels[::-1], values[::-1], color=palette[::-1], height=0.6, zorder=3)
        for bar, val in zip(bars, values[::-1]):
            x_pos = bar.get_width() + max_v * 0.01 if val >= 0 else bar.get_width() - max_v * 0.01
            ha    = "left" if val >= 0 else "right"
            ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                    _fmt_value(val), ha=ha, va="center", fontsize=7, fontweight="bold")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels[::-1], fontsize=7.5)
        ax.set_xlim(0, max_v * 1.18)
    else:
        fig, ax = plt.subplots(figsize=(6.2, max(2.6, 0.5 * n + 0.6)))
        bars = ax.bar(labels, values, color=palette, width=0.6, zorder=3)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max_v * 0.01,
                _fmt_value(val), ha="center", va="bottom", fontsize=7, fontweight="bold",
            )
        ax.set_xticks(range(n))
        ax.set_xticklabels(labels, fontsize=7.5, rotation=20 if n > 4 else 0, ha="right")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))

    _style_ax(fig, ax)
    plt.tight_layout(pad=0.4)
    return _chart_to_rl_image(fig, max_w)


def _split_series_by_scale(vkeys, series_data):
    if len(vkeys) <= 1:
        return vkeys, series_data, [], []
    maxes      = [max(abs(v) for v in s) if s else 0 for s in series_data]
    global_max = max(maxes) if maxes else 1
    pk, pd_, sk, sd = [], [], [], []
    for k, d, m in zip(vkeys, series_data, maxes):
        if global_max > 0 and m / global_max < 0.08:
            sk.append(k); sd.append(d)
        else:
            pk.append(k); pd_.append(d)
    if not pk:
        return vkeys, series_data, [], []
    return pk, pd_, sk, sd


def _grouped_bar_img(rows, lk, vkeys, max_w, horizontal=False):
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np

    labels = [_humanize_label(str(r.get(lk, ""))[:22]) for r in rows[:12]]
    n      = len(labels)
    series_data = []
    for vk in vkeys:
        try:
            vals = [float(str(r.get(vk, 0) or 0).replace(",", "")) for r in rows[:12]]
        except (TypeError, ValueError):
            vals = [0.0] * n
        series_data.append(vals)

    pk, pd_, sk, sd = _split_series_by_scale(vkeys, series_data)
    has_secondary = bool(sk)
    ns_primary    = max(1, len(pk))
    bar_w         = min(0.6, 0.7 / ns_primary)
    all_primary   = [v for s in pd_ for v in s]
    max_pv        = max(abs(v) for v in all_primary) if all_primary else 1
    min_pv        = min(all_primary) if all_primary else 0

    if horizontal:
        fig_h = max(3.0, 0.38 * n + 0.8)
        fig, ax = plt.subplots(figsize=(6.5, min(fig_h, 5.0)))
        ax2     = ax.twiny() if has_secondary else None
        y_base  = np.arange(n)
        offsets = np.linspace(-(ns_primary - 1) * bar_w / 2,
                               (ns_primary - 1) * bar_w / 2, ns_primary)

        for i, (vk, vals, offset) in enumerate(zip(pk, pd_, offsets)):
            color = CHART_HEX[i % len(CHART_HEX)]
            bars  = ax.barh(y_base[::-1] + offset, vals[::-1],
                            height=bar_w, color=color,
                            label=vk.replace("_", " ").title(), zorder=3)
            for bar, val in zip(bars, vals[::-1]):
                if abs(val) > max_pv * 0.01:
                    x_pos, ha = (bar.get_width() + max_pv * 0.005, "left") \
                                if val >= 0 else \
                                (bar.get_width() - max_pv * 0.005, "right")
                    ax.text(x_pos, bar.get_y() + bar.get_height() / 2,
                            _fmt_value(val), ha=ha, va="center",
                            fontsize=5.5, fontweight="bold", clip_on=True)

        ax.set_yticks(y_base)
        ax.set_yticklabels(labels[::-1], fontsize=7)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
        x_margin = max_pv * 0.22
        ax.set_xlim(min(0, min_pv) - x_margin * 0.3, max_pv + x_margin)
        ax.axvline(0, color="#9ca3af", linewidth=0.6, zorder=1)

        if ax2 and sk:
            all_sec = [v for s in sd for v in s]
            max_sv  = max(abs(v) for v in all_sec) if all_sec else 1
            min_sv  = min(all_sec) if all_sec else 0
            for i, (vk, vals) in enumerate(zip(sk, sd)):
                ax2.barh(y_base[::-1], vals[::-1], height=bar_w * 0.6,
                         color=CHART_HEX[(len(pk) + i) % len(CHART_HEX)],
                         alpha=0.75, label=vk.replace("_", " ").title(), zorder=2)
            ax2.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
            sv_margin = max_sv * 0.25
            ax2.set_xlim(min(0, min_sv) - sv_margin * 0.3, max_sv + sv_margin)
            ax2.tick_params(axis="x", labelsize=6.5, colors=CHART_HEX[len(pk) % len(CHART_HEX)])

        handles, lbls = ax.get_legend_handles_labels()
        if ax2:
            h2, l2 = ax2.get_legend_handles_labels()
            handles += h2; lbls += l2
        ax.legend(handles, lbls, fontsize=6.5, loc="upper right",
                  bbox_to_anchor=(1.0, -0.04), ncol=min(3, len(handles)),
                  framealpha=0.85, borderpad=0.4)

    else:
        fig, ax = plt.subplots(figsize=(6.5, min(4.0, max(3.0, 0.55 * n + 1.2))))
        ax2     = ax.twinx() if has_secondary else None
        x_base  = np.arange(n)
        offsets = np.linspace(-(ns_primary - 1) * bar_w / 2,
                               (ns_primary - 1) * bar_w / 2, ns_primary)

        for i, (vk, vals, offset) in enumerate(zip(pk, pd_, offsets)):
            color = CHART_HEX[i % len(CHART_HEX)]
            bars  = ax.bar(x_base + offset, vals, width=bar_w,
                           color=color, label=vk.replace("_", " ").title(), zorder=3)
            for bar, val in zip(bars, vals):
                if abs(val) > max_pv * 0.01:
                    y_pos = bar.get_height() + max_pv * 0.01 if val >= 0 \
                            else bar.get_height() - max_pv * 0.04
                    ax.text(bar.get_x() + bar.get_width() / 2, y_pos,
                            _fmt_value(val), ha="center", va="bottom",
                            fontsize=5.5, fontweight="bold", clip_on=True)

        ax.set_xticks(x_base)
        ax.set_xticklabels(labels, fontsize=7.5, rotation=20 if n > 3 else 0, ha="right")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
        if min_pv < 0:
            ax.axhline(0, color="#9ca3af", linewidth=0.8, zorder=2)

        if ax2 and sk:
            all_sec = [v for s in sd for v in s]
            max_sv  = max(abs(v) for v in all_sec) if all_sec else 1
            min_sv  = min(all_sec) if all_sec else 0
            for i, (vk, vals) in enumerate(zip(sk, sd)):
                ax2.bar(x_base, vals, width=bar_w * 0.5,
                        color=CHART_HEX[(len(pk) + i) % len(CHART_HEX)],
                        alpha=0.75, label=vk.replace("_", " ").title(), zorder=2)
            ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: _fmt_value(x)))
            ax2.tick_params(axis="y", labelsize=6.5, colors=CHART_HEX[len(pk) % len(CHART_HEX)])
            if min_sv < 0:
                ax2.axhline(0, color="#d1d5db", linewidth=0.5, zorder=1)

        handles, lbls = ax.get_legend_handles_labels()
        if ax2:
            h2, l2 = ax2.get_legend_handles_labels()
            handles += h2; lbls += l2
        ax.legend(handles, lbls, fontsize=7, loc="upper right", framealpha=0.85)

    _style_ax(fig, ax)
    plt.tight_layout(pad=0.5)
    return _chart_to_rl_image(fig, max_w)


def _donut_img(rows, lk, vk, max_w):
    import matplotlib.pyplot as plt

    labels = [_humanize_label(str(r.get(lk, ""))[:22]) for r in rows[:7]]
    try:
        values = [float(str(r.get(vk, 0) or 0).replace(",", "")) for r in rows[:7]]
    except (TypeError, ValueError):
        return None
    palette = [CHART_HEX[i % len(CHART_HEX)] for i in range(len(labels))]
    fig, ax = plt.subplots(figsize=(5.5, 2.9))
    fig.patch.set_facecolor("#ffffff")
    wedges, _, autotexts = ax.pie(
        values, labels=None, colors=palette, autopct="%1.1f%%", startangle=90,
        wedgeprops={"linewidth": 1.5, "edgecolor": "#ffffff"}, pctdistance=0.77,
    )
    for at in autotexts:
        at.set_fontsize(7); at.set_color("#ffffff"); at.set_fontweight("bold")
    ax.add_patch(plt.Circle((0, 0), 0.5, fc="#ffffff"))
    ax.legend(wedges, [f"{lbl}  {_fmt_value(v)}" for lbl, v in zip(labels, values)],
              loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=7.5, frameon=False)
    ax.set_aspect("equal")
    plt.tight_layout(pad=0.3)
    return _chart_to_rl_image(fig, max_w)


def _style_ax(fig, ax) -> None:
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.tick_params(axis="both", labelsize=7.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#e5e7eb")
    ax.yaxis.grid(True, color="#f3f4f6", zorder=0)
    ax.set_axisbelow(True)


# ══════════════════════════════════════════════════════════════════════
#  Table builder
# ══════════════════════════════════════════════════════════════════════

def _data_table(rows: list[dict], max_rows: int = 12) -> Table | None:
    if not rows:
        return None
    st   = _st()
    hdrs = list(rows[0].keys())[:7]
    cw   = CONTENT_W / len(hdrs)

    def _hdr_label(h: str) -> str:
        # Humanise numeric month column if needed
        return _humanize_label(str(h).replace("_", " ").title())

    data = [[Paragraph(_esc(_hdr_label(h)), st["th"]) for h in hdrs]]
    for row in rows[:max_rows]:
        data.append([
            Paragraph(_esc(_fmt_cell(_trunc(str(row.get(h, "")), 35))), st["td"])
            for h in hdrs
        ])
    tbl = Table(data, colWidths=[cw] * len(hdrs), repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_PRIMARY),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, C_BG_ALT]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, C_BORDER),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ══════════════════════════════════════════════════════════════════════
#  KPI row
# ══════════════════════════════════════════════════════════════════════

def _kpi_row(kpis: list[tuple[str, str, str]]) -> Table:
    cw   = CONTENT_W / len(kpis)
    vrow = [
        Paragraph(
            f'<font color="{col}"><b>{_esc(val)}</b></font>',
            ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=13,
                           textColor=HexColor(col), alignment=TA_CENTER),
        )
        for val, _, col in kpis
    ]
    lrow = [
        Paragraph(
            _esc(lbl),
            ParagraphStyle("kl", fontName="Helvetica", fontSize=7.5,
                           textColor=C_MUTED, alignment=TA_CENTER),
        )
        for _, lbl, _ in kpis
    ]
    tbl = Table([vrow, lrow], colWidths=[cw] * len(kpis))
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), HexColor("#eff6ff")),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.5, C_BORDER),
        ("BOX",           (0, 0), (-1, -1), 0.7, C_BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTRE"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ══════════════════════════════════════════════════════════════════════
#  Session highlights
# ══════════════════════════════════════════════════════════════════════

def _qa_pair_block(question: str, answer: str) -> KeepTogether:
    st = _st()
    return KeepTogether([
        Paragraph(f"Q: {_esc(_trunc(question, 200))}", st["transcript_q"]),
        Paragraph(f"A: {_esc(_trunc(answer,   400))}", st["transcript_a"]),
    ])


def _build_index_paired_messages(messages: list[dict]) -> list[tuple[dict, dict]]:
    pairs = []
    for i, m in enumerate(messages):
        if m.get("role") == "user" and i + 1 < len(messages):
            nxt = messages[i + 1]
            if nxt.get("role") == "assistant":
                pairs.append((m, nxt))
    return pairs


def _is_low_quality_answer(ans: str) -> bool:
    """Return True for answers that should be excluded from highlights."""
    lo = ans.lower().strip()
    return (
        len(ans) < 20
        or _is_boilerplate(ans)
        or "could not find matching rows" in lo
        or "could not map" in lo
        or lo.startswith("i could not")
        or lo.startswith("i was unable")
        or lo.startswith("i don't have")
        or lo.startswith("i do not have")
        or "null value" in lo
    )


def _build_session_highlights(
    messages: list[dict],
    important_pairs: list[dict] | None,
) -> list:
    st    = _st()
    story: list = []

    if important_pairs:
        # FIX v9: filter LLM-supplied pairs for quality too
        pairs = [
            p for p in important_pairs
            if p.get("question") and p.get("answer")
            and not _is_low_quality_answer(str(p.get("answer", "")))
        ]
    else:
        def _score(ans: str) -> int:
            return len(re.findall(r"[\$\d][,\d]*\.?\d*[KMB%]?", ans)) + len(ans) // 50

        raw_pairs = _build_index_paired_messages(messages)

        scored = []
        for u, a in raw_pairs:
            ans = str(a.get("content", "")).strip()
            if _is_low_quality_answer(ans):
                continue
            scored.append((_score(ans), u, a))

        top    = sorted(scored, key=lambda x: x[0], reverse=True)[:6]
        top_qs = {str(u.get("content", "")) for _, u, _ in top}
        ordered = [(u, a) for u, a in raw_pairs if str(u.get("content", "")) in top_qs]

        pairs = [
            {
                "question": str(u.get("content", "")).strip(),
                "answer":   str(a.get("content", "")).strip(),
            }
            for u, a in ordered
        ]

    story.append(Paragraph(
        "Key exchanges from this session — questions that produced the most significant insights.",
        st["sub"],
    ))
    story.append(Spacer(1, 3 * mm))

    for pair in pairs[:8]:
        q = str(pair.get("question") or "").strip()
        a = str(pair.get("answer")   or "").strip()
        if q and a:
            story.append(_qa_pair_block(q, a))

    return story


# ══════════════════════════════════════════════════════════════════════
#  Visualization deduplication & explanation lookup
# ══════════════════════════════════════════════════════════════════════

def _rows_fingerprint(rows: list[dict]) -> str:
    snippet = json.dumps(rows[:3], sort_keys=True, default=str)
    return hashlib.md5(snippet.encode()).hexdigest()


def _build_viz_explanation_map(messages: list[dict]) -> dict[int, str]:
    result:  dict[int, str] = {}
    seen:    set[str]       = set()
    viz_idx: int            = 0

    for m in messages:
        if m.get("role") != "assistant" or not m.get("viz_data"):
            continue
        try:
            payload = json.loads(m["viz_data"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        fp   = _rows_fingerprint(rows)
        if fp in seen:
            continue
        seen.add(fp)
        viz_idx += 1
        content = _strip_boilerplate_prefix(str(m.get("content") or "").strip())
        if content and not _is_boilerplate(content):
            result[viz_idx] = content

    return result


# ══════════════════════════════════════════════════════════════════════
#  Main PDF builder
# ══════════════════════════════════════════════════════════════════════

def _build_pdf_reportlab(*, session: dict, narrative: dict[str, Any]) -> bytes:
    messages  = session.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "user"]
    asst_msgs = [m for m in messages if m.get("role") == "assistant"]
    visuals   = _visual_payloads(messages)
    gen_at    = datetime.now().strftime("%d %b %Y, %H:%M")

    raw_title = str(narrative.get("title") or session.get("title") or "DataSage Analytics Report")
    title     = _clean_title(raw_title)

    st              = _st()
    viz_explain_map = _build_viz_explanation_map(messages)

    # ── Per-page decoration ───────────────────────────────────────────
    def _on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_PRIMARY_DARK)
        canvas.rect(0, PAGE_H - MARGIN_TOP + 2, PAGE_W, MARGIN_TOP - 2, fill=1, stroke=0)
        canvas.setFillColor(C_PRIMARY)
        canvas.rect(0, PAGE_H - 1.5, PAGE_W, 1.5, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 10.5)
        canvas.drawString(MARGIN_H, PAGE_H - 12 * mm, "DATASAGE AI")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(HexColor("#93c5fd"))
        canvas.drawString(MARGIN_H, PAGE_H - 18 * mm, "AI-Powered Analytics Platform")
        canvas.setFillColor(HexColor("#93c5fd"))
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(PAGE_W / 2, PAGE_H - 18 * mm, f"Generated: {gen_at}")
        badge_w, badge_h = 60, 10
        badge_x = PAGE_W - MARGIN_H - badge_w
        band_h  = MARGIN_TOP - 2
        badge_y = PAGE_H - MARGIN_TOP + 2 + (band_h - badge_h) / 2
        canvas.setFillColor(HexColor("#fef3c7"))
        canvas.roundRect(badge_x, badge_y, badge_w, badge_h, 3, fill=1, stroke=0)
        canvas.setFillColor(HexColor("#92400e"))
        canvas.setFont("Helvetica-Bold", 6)
        canvas.drawCentredString(badge_x + badge_w / 2, badge_y + 3, "CONFIDENTIAL")
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_H, MARGIN_BOT + 3, PAGE_W - MARGIN_H, MARGIN_BOT + 3)
        canvas.setFillColor(C_MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(MARGIN_H, MARGIN_BOT - 2, "DataSage AI  -  Confidential Analytics Report")
        canvas.drawRightString(PAGE_W - MARGIN_H, MARGIN_BOT - 2, f"Page {doc.page}")
        canvas.restoreState()

    # ── Document setup ────────────────────────────────────────────────
    buf  = io.BytesIO()
    doc  = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN_H, rightMargin=MARGIN_H,
        topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOT + 6 * mm,
    )
    frame    = Frame(
        MARGIN_H, MARGIN_BOT + 6 * mm,
        CONTENT_W, PAGE_H - MARGIN_TOP - MARGIN_BOT - 6 * mm,
        id="main",
    )
    template = PageTemplate(id="main", frames=[frame], onPage=_on_page)
    doc.addPageTemplates([template])

    story: list[Any] = []

    # ── Title block ───────────────────────────────────────────────────
    n_vis    = len(visuals)
    subtitle = (
        f"{len(user_msgs)} queries  -  "
        f"{n_vis} visualization{'s' if n_vis != 1 else ''}  -  "
        f"{len(asst_msgs)} AI responses"
    )
    story.append(_TitleBlock(
        title, subtitle,
        [(str(len(user_msgs)), "Queries"),
         (str(len(asst_msgs)), "AI Responses"),
         (str(n_vis),          "Charts")],
    ))
    story.append(Spacer(1, 5 * mm))

    # ── KPI row ───────────────────────────────────────────────────────
    story.append(_kpi_row([
        (str(len(user_msgs)),  "User Messages",  "#1a56db"),
        (str(len(asst_msgs)),  "AI Responses",   "#10b981"),
        (str(n_vis),           "Visualizations", "#f97316"),
        (gen_at.split(",")[0], "Report Date",    "#8b5cf6"),
    ]))
    story.append(Spacer(1, 6 * mm))

    # ── Executive Summary ─────────────────────────────────────────────
    exec_summary = str(narrative.get("executive_summary") or "No summary available.")
    story.append(KeepTogether([
        _SectionHeader("Executive Summary"),
        Spacer(1, 3 * mm),
        _CalloutBox(exec_summary),
    ]))
    story.append(Spacer(1, 5 * mm))

    # ── Key Findings ──────────────────────────────────────────────────
    findings = narrative.get("key_findings") or []
    if findings:
        story.append(KeepTogether([
            _SectionHeader("Key Findings"),
            Spacer(1, 3 * mm),
            Paragraph(f"*  {_esc(str(findings[0]))}", st["bullet"]),
        ]))
        for item in findings[1:]:
            story.append(Paragraph(f"*  {_esc(str(item))}", st["bullet"]))
        story.append(Spacer(1, 5 * mm))

    # ── Recommendations ───────────────────────────────────────────────
    recs = narrative.get("recommendations") or []
    if recs:
        story.append(KeepTogether([
            _SectionHeader("Recommendations"),
            Spacer(1, 3 * mm),
            Paragraph(f"*  {_esc(str(recs[0]))}", st["bullet"]),
        ]))
        for item in recs[1:]:
            story.append(Paragraph(f"*  {_esc(str(item))}", st["bullet"]))
        story.append(Spacer(1, 5 * mm))

    # ── Limitations ───────────────────────────────────────────────────
    limits = narrative.get("limitations") or []
    if limits:
        story.append(KeepTogether([
            _SectionHeader("Limitations & Notes"),
            Spacer(1, 3 * mm),
            Paragraph(f"*  {_esc(str(limits[0]))}", st["bullet"]),
        ]))
        for item in limits[1:]:
            story.append(Paragraph(f"*  {_esc(str(item))}", st["bullet"]))
        story.append(Spacer(1, 5 * mm))

    # ── Visualizations ────────────────────────────────────────────────
    if visuals:
        if len(story) > 8:
            story.append(PageBreak())

        story.append(_SectionHeader(f"Visualizations & Data  ({n_vis} charts)"))
        story.append(Spacer(1, 4 * mm))

        for idx, payload in enumerate(visuals[:8], 1):
            rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []

            # FIX v9: strip boilerplate from chart title before rendering
            _raw_vtitle = str(
                payload.get("explanation") or payload.get("summary") or f"Analysis {idx}"
            )
            _clean_vtitle = _strip_boilerplate_prefix(_raw_vtitle)
            vtitle = _trunc(_clean_vtitle or f"Analysis {idx}", 100)

            ctype      = str(payload.get("chart_type") or "bar").upper()
            lk_det     = _detect_label_key(rows)
            vkeys_det  = _detect_value_keys(rows, lk_det)

            diff_keys_det = [k for k in vkeys_det if _is_diff_key(k)]
            if diff_keys_det and len(vkeys_det) > 1:
                chart_type_label = "BAR+LINE"
            elif ctype == "LINE" and len(vkeys_det) > 1:
                chart_type_label = "LINE (multi-series)"
            else:
                chart_type_label = ctype

            series_lbl = f"{len(vkeys_det)} series  -  " if len(vkeys_det) > 1 else ""

            hdr = Table(
                [[
                    Paragraph(f"<b>{_esc(vtitle)}</b>",
                              ParagraphStyle("vh", fontName="Helvetica-Bold", fontSize=9,
                                             textColor=C_TEXT)),
                    Paragraph(
                        f'<font color="#6b7280">{chart_type_label}  -  {series_lbl}{len(rows)} rows</font>',
                        ParagraphStyle("vt", fontName="Helvetica", fontSize=7.5,
                                       textColor=C_MUTED, alignment=TA_RIGHT)),
                ]],
                colWidths=[CONTENT_W * 0.68, CONTENT_W * 0.32],
            )
            hdr.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), HexColor("#eff6ff")),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("BOX",           (0, 0), (-1, -1), 0.5, C_PRIMARY),
                ("LINEBEFORE",    (0, 0), (0,  -1), 3,   C_PRIMARY),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ]))

            chart_img = _render_chart(payload, CONTENT_W - 8)

            if chart_img:
                img_wrap = Table([[chart_img]], colWidths=[CONTENT_W])
                img_wrap.setStyle(TableStyle([
                    ("ALIGN",         (0, 0), (-1, -1), "CENTRE"),
                    ("BACKGROUND",    (0, 0), (-1, -1), white),
                    ("BOX",           (0, 0), (-1, -1), 0.4, C_BORDER),
                    ("TOPPADDING",    (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(KeepTogether([hdr, Spacer(1, 2 * mm)]))
                story.append(img_wrap)
            else:
                story.append(hdr)

            explanation_text = viz_explain_map.get(idx) or _strip_boilerplate_prefix(
                str(payload.get("explanation") or payload.get("summary") or "")
            )
            if explanation_text and not _is_boilerplate(explanation_text):
                story.append(Paragraph(
                    _esc(_trunc(explanation_text, 600)), st["viz_explain"]
                ))

            dtbl = _data_table(rows, max_rows=12)
            if dtbl:
                story.append(Spacer(1, 2 * mm))
                story.append(dtbl)

            story.append(Spacer(1, 7 * mm))

    # ── Session Highlights ────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_SectionHeader("Session Highlights"))
    story.append(Spacer(1, 3 * mm))
    important_pairs = narrative.get("important_qa_pairs") or None
    story.extend(_build_session_highlights(messages, important_pairs))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════
#  Shared helpers
# ══════════════════════════════════════════════════════════════════════

def _visual_payloads(messages: list[dict]) -> list[dict[str, Any]]:
    payloads: list[dict] = []
    seen:     set[str]   = set()
    for m in messages:
        if m.get("role") != "assistant":
            continue
        raw = m.get("viz_data")
        if not raw:
            continue
        try:
            p = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(p, dict):
            continue
        rows = p.get("rows") if isinstance(p.get("rows"), list) else []
        fp   = _rows_fingerprint(rows)
        if fp in seen:
            continue
        seen.add(fp)
        payloads.append(p)
    return payloads


def _visual_summaries(messages: list[dict]) -> list[dict[str, Any]]:
    result = []
    for p in _visual_payloads(messages):
        rows = p.get("rows") if isinstance(p.get("rows"), list) else []
        result.append({
            "title":       p.get("summary") or p.get("explanation"),
            "chart_type":  p.get("chart_type"),
            "row_count":   len(rows),
            "sample_rows": rows[:3],
        })
    return result


# ══════════════════════════════════════════════════════════════════════
#  ReportService
# ══════════════════════════════════════════════════════════════════════

class ReportService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.db       = get_database()

    async def generate_chat_report(self, *, user_id: str, session_id: str) -> tuple[bytes, str]:
        session = await self.db.sessions.find_one(
            {"_id": ObjectId(session_id), "user_id": user_id}
        )
        if not session:
            raise ValueError("Session not found.")
        messages = session.get("messages", [])
        if not messages:
            raise ValueError("This chat has no messages to report yet.")
        user_msg_count = sum(1 for m in messages if m.get("role") == "user")
        if user_msg_count < MIN_REPORT_USER_MESSAGES:
            remaining = MIN_REPORT_USER_MESSAGES - user_msg_count
            suffix    = "" if remaining == 1 else "s"
            raise ValueError(
                f"Send {remaining} more message{suffix} before generating a report."
            )
        narrative = await self._generate_report_narrative(session)
        pdf_bytes = _build_pdf_reportlab(session=session, narrative=narrative)
        filename  = self._safe_filename(
            str(narrative.get("title") or session.get("title") or "datasage-report")
        ) + ".pdf"
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
        messages      = session.get("messages", [])
        transcript    = self._compact_transcript(messages)
        visuals       = _visual_summaries(messages)
        system_prompt = (
            "You generate concise analytics report content as JSON only. "
            "Return exactly these keys: "
            "title, executive_summary, key_findings, recommendations, limitations, important_qa_pairs.\n"
            "Rules:\n"
            "- title: a professional report title derived from the session's analytical topic "
            "  (e.g. 'Nexora OpEx Analysis - 2023'). NEVER use a raw user question as the title.\n"
            "- key_findings, recommendations, limitations: arrays of short strings.\n"
            "- Use only plain ASCII punctuation: hyphens (-) not em/en dashes, "
            "  straight quotes not curly quotes, ... not ellipsis character.\n"
            "- executive_summary: 3-5 sentences covering what was analysed, outcomes, open issues. "
            "  CRITICAL: if the total annual variance is positive (actual > budget), call it a "
            "  'cost overrun' or 'over-budget spending'. NEVER call a positive variance an "
            "  'underrun'. Only use 'under budget' when actual < budget.\n"
            "- important_qa_pairs: the 6 most insightful user/assistant exchanges as "
            "  [{question, answer}]; keep each answer under 300 chars. Ensure the question "
            "  and answer are actually about the same topic. Exclude any pair where the "
            "  assistant said it could not find data or could not answer.\n"
            "Output raw JSON only - no markdown fences, no preamble."
        )
        user_prompt = (
            f"Session title: {session.get('title') or 'DataSage report'}\n\n"
            f"Transcript:\n{transcript}\n\n"
            f"Visualization summaries:\n{json.dumps(visuals, ensure_ascii=False)}"
        )
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.openrouter_report_api_key}",
                    "Content-Type":  "application/json",
                    "HTTP-Referer":  "http://127.0.0.1:3000",
                    "X-Title":       "DataSage Report Generator",
                },
                json={
                    "model":    self.settings.openrouter_report_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens":  1200,
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._extract_json(content)

    def _fallback_narrative(self, session: dict) -> dict[str, Any]:
        messages  = session.get("messages", [])
        user_msgs = [m for m in messages if m.get("role") == "user"]
        asst_msgs = [m for m in messages if m.get("role") == "assistant"]
        visuals   = _visual_summaries(messages)
        title     = _clean_title(str(session.get("title") or "DataSage Analytics Report"))

        total_variance: float | None = None
        for v in visuals:
            for row in v.get("sample_rows", []):
                for k, val in row.items():
                    if _is_diff_key(k) and _is_numeric_str(str(val)):
                        try:
                            total_variance = float(str(val).replace(",", ""))
                        except ValueError:
                            pass

        variance_desc = ""
        if total_variance is not None:
            variance_desc = f" Overall the data shows spending {_variance_label(total_variance)}."

        summary_parts = [
            f"This report covers a DataSage session analysing '{title}' with "
            f"{len(user_msgs)} user requests and {len(asst_msgs)} AI responses.",
            "The conversation examined the connected data source, producing insights, charts, and structured answers."
            + variance_desc,
        ]
        if visuals:
            s = "s" if len(visuals) != 1 else ""
            summary_parts.append(f"The session generated {len(visuals)} unique visualisation{s}.")

        def _score(text: str) -> int:
            return len(re.findall(r"[\$\d][,\d]*\.?\d*[KMB%]?", text))

        candidates: list[tuple[int, str]] = []
        for m in asst_msgs:
            content = str(m.get("content", "")).strip()
            if not content or _is_low_quality_answer(content):
                continue
            sentences = [s.strip() for s in content.replace("\n", " ").split(".") if len(s.strip()) > 30]
            for sent in sentences[:6]:
                if not _is_boilerplate(sent):
                    candidates.append((_score(sent), _trunc(sent, 200)))

        seen_f: set[str] = set()
        findings: list[str] = []
        for _, text in sorted(candidates, key=lambda x: x[0], reverse=True):
            if text not in seen_f:
                seen_f.add(text)
                findings.append(text)
            if len(findings) >= 8:
                break
        if not findings:
            findings = ["No key findings captured - check session for data quality issues."]

        raw_pairs    = _build_index_paired_messages(messages)
        scored_pairs = []
        for u, a in raw_pairs:
            ans = str(a.get("content", "")).strip()
            if _is_low_quality_answer(ans):
                continue
            scored_pairs.append((_score(ans) + len(ans) // 50, u, a))

        top_pairs = sorted(scored_pairs, key=lambda x: x[0], reverse=True)[:6]
        top_qs    = {str(u.get("content", "")) for _, u, _ in top_pairs}
        important_qa = [
            {
                "question": _trunc(str(u.get("content", "")), 200),
                "answer":   _trunc(str(a.get("content", "")), 350),
            }
            for u, a in raw_pairs
            if str(u.get("content", "")) in top_qs
        ]

        return self._normalize_narrative({
            "title":             title,
            "executive_summary": " ".join(summary_parts),
            "key_findings":      findings,
            "recommendations": [
                "Validate AI-generated findings against source data before external use.",
                "Use exact column names and time ranges for sharper follow-up queries.",
                "Regenerate this report after resolving any failed or low-confidence queries.",
            ],
            "limitations": [
                "Report is derived solely from the saved chat transcript and viz payloads.",
                "Failed or rate-limited queries may produce incomplete findings.",
                "AI interpretations are probabilistic; verify critical figures in the source system.",
            ],
            "important_qa_pairs": important_qa,
        }, session)

    def _normalize_narrative(self, narrative: dict[str, Any], session: dict) -> dict[str, Any]:
        raw_title = str(
            narrative.get("title") or session.get("title") or "DataSage Analytics Report"
        )
        title   = _clean_title(raw_title)
        summary = str(narrative.get("executive_summary") or "").strip() or (
            "This report summarises the main analysis requests, responses, and follow-up items "
            "from the DataSage chat session."
        )

        def listify(v: Any, fallback: str) -> list[str]:
            if isinstance(v, list):
                items = [str(i).strip() for i in v if str(i).strip()]
            elif isinstance(v, str) and v.strip():
                items = [v.strip()]
            else:
                items = []
            return items or [fallback]

        qa_pairs = narrative.get("important_qa_pairs")
        if not isinstance(qa_pairs, list):
            qa_pairs = []

        return {
            "title":              title,
            "executive_summary":  summary,
            "key_findings":       listify(narrative.get("key_findings"),    "No key findings captured."),
            "recommendations":    listify(narrative.get("recommendations"), "Continue with a specific question."),
            "limitations":        listify(narrative.get("limitations"),     "Report uses information from this session only."),
            "important_qa_pairs": qa_pairs,
        }

    def _compact_transcript(self, messages: list[dict]) -> str:
        return "\n\n".join(
            f"{str(m.get('role', ''))}: {_trunc(str(m.get('content', '')), 800)}"
            for m in messages[-24:]
        )

    def _extract_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if "```" in cleaned:
            parts   = [p.strip() for p in cleaned.split("```") if p.strip()]
            cleaned = next((p.removeprefix("json").strip() for p in parts if "{" in p), cleaned)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", cleaned, re.S)
            payload = json.loads(m.group(0)) if m else {}
        return payload if isinstance(payload, dict) else {}

    def _safe_filename(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
        return cleaned[:80] or "datasage-report"