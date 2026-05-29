from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


LlmProvider = Literal["groq", "deepseek"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    llm_provider: LlmProvider | None = None


ChartType = Literal["bar", "horizontal_bar", "line", "donut", "3d_bar", "radar", "table"]

# Map of common invalid chart_type values LLMs produce → closest valid value
_CHART_TYPE_ALIASES: dict[str, str] = {
    "pie": "donut",
    "pie_chart": "donut",
    "bar_chart": "bar",
    "bar chart": "bar",
    "horizontal bar": "horizontal_bar",
    "horizontal_bar_chart": "horizontal_bar",
    "line_chart": "line",
    "line chart": "line",
    "radar_chart": "radar",
    "donut_chart": "donut",
    "doughnut": "donut",
    "area": "line",
    "scatter": "bar",
    "histogram": "bar",
    "stacked_bar": "bar",
    "grouped_bar": "bar",
    "3d bar": "3d_bar",
    "3d_bar_chart": "3d_bar",
    "single_value": "table",
    "number": "table",
    "metric": "table",
    "kpi": "table",
    "none": "table",
    "null": "table",
    "n/a": "table",
    "text": "table",
    "summary": "table",
}

VALID_CHART_TYPES = {"bar", "horizontal_bar", "line", "donut", "3d_bar", "radar", "table"}


def normalize_chart_type(raw: str | None) -> str | None:
    """Coerce an LLM-produced chart_type into a valid ChartType value."""
    if raw is None:
        return None
    cleaned = str(raw).strip().lower().replace(" ", "_")
    if cleaned in VALID_CHART_TYPES:
        return cleaned
    # Try the alias map (also check the lowercase-space version)
    mapped = _CHART_TYPE_ALIASES.get(cleaned) or _CHART_TYPE_ALIASES.get(str(raw).strip().lower())
    if mapped:
        return mapped
    # Last resort: default to table for unknown values
    return "table"


ConfidenceLevel = Literal["high", "medium", "low"]


class SqlAnalysisPlan(BaseModel):
    query: str = Field(min_length=1)
    chart_type: ChartType | None = None
    notes: str | None = None
    confidence: ConfidenceLevel | None = None

    @field_validator("chart_type", mode="before")
    @classmethod
    def _normalize_chart_type(cls, v: object) -> str | None:
        return normalize_chart_type(v) if isinstance(v, str) else v


class MongoAnalysisPlan(BaseModel):
    collection: str | None = None
    pipeline: list[dict[str, Any]] = Field(default_factory=list)
    chart_type: ChartType | None = None
    notes: str | None = None
    confidence: ConfidenceLevel | None = None

    @field_validator("chart_type", mode="before")
    @classmethod
    def _normalize_chart_type(cls, v: object) -> str | None:
        return normalize_chart_type(v) if isinstance(v, str) else v


class ChatIntent(BaseModel):
    intent: Literal["analysis", "source_overview", "conversation"]
    reason: str | None = None


class AnalysisAnswerPayload(BaseModel):
    answer: str = Field(min_length=1)
    needs_visualization: bool = False
    chart_type: ChartType | None = None
    chart_title: str | None = None
    summary: str | None = None
    query_preview: str | None = None

    @field_validator("chart_type", mode="before")
    @classmethod
    def _normalize_chart_type(cls, v: object) -> str | None:
        return normalize_chart_type(v) if isinstance(v, str) else v
