from typing import Any, Literal

from pydantic import BaseModel, Field


LlmProvider = Literal["gemini", "groq"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    llm_provider: LlmProvider | None = None


ChartType = Literal["bar", "horizontal_bar", "line", "donut", "3d_bar", "radar", "table"]


class SqlAnalysisPlan(BaseModel):
    query: str = Field(min_length=1)
    chart_type: ChartType | None = None
    notes: str | None = None


class MongoAnalysisPlan(BaseModel):
    collection: str = Field(min_length=1)
    pipeline: list[dict[str, Any]] = Field(default_factory=list)
    chart_type: ChartType | None = None
    notes: str | None = None


class AnalysisAnswerPayload(BaseModel):
    answer: str = Field(min_length=1)
    needs_visualization: bool = False
    chart_type: ChartType | None = None
    chart_title: str | None = None
    summary: str | None = None
    query_preview: str | None = None
