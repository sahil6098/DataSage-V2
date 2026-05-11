import asyncio
import hashlib
import json
import re
import string
from collections import Counter
from collections.abc import AsyncIterator
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.chat import AnalysisAnswerPayload, MongoAnalysisPlan, SqlAnalysisPlan
from app.services.connector_service import ConnectorService
from app.services.llm_service import LlmService
from app.services.session_service import SessionService
from app.core.logging import get_logger
from app.utils.time import ist_now

logger = get_logger(__name__)


MAX_PROMPT_CHARS = 8_000
MAX_CONTEXT_TABLES = 8
MAX_CONTEXT_FIELDS_PER_TABLE = 12
MAX_CONTEXT_SAMPLE_CHARS = 60
MAX_PROMPT_ROWS = 10
MAX_PROMPT_FIELDS_PER_ROW = 12
MAX_PROMPT_VALUE_CHARS = 200
MAX_QUERY_RETRIES = 1

SQL_KEYWORDS = {
    "select", "from", "where", "and", "or", "not", "in", "is", "null",
    "like", "between", "as", "on", "join", "left", "right", "inner",
    "outer", "cross", "group", "by", "order", "asc", "desc", "having",
    "limit", "offset", "union", "all", "distinct", "case", "when",
    "then", "else", "end", "exists", "count", "sum", "avg", "min",
    "max", "with", "true", "false", "cast", "coalesce", "nullif",
    "ilike", "upper", "lower", "trim", "length", "substring",
    "extract", "date", "timestamp", "interval", "over", "partition",
    "row_number", "rank", "dense_rank", "lag", "lead",
    "public", "table", "into", "values", "set", "using", "recursive",
    "fetch", "first", "next", "rows", "only", "percent", "ties",
}


class AnalysisState(TypedDict, total=False):
    user_id: str
    session_id: str
    provider_preference: str | None
    provider_used: str | None
    question: str
    data_source: dict
    schema_context: str
    query_plan: dict
    result_rows: list[dict]
    answer_payload: dict
    validation_warnings: list[str]
    execution_error: str | None
    retry_count: int
    low_confidence: bool


class QueryPlanCache:
    """In-memory cache keyed by normalized question + schema hash."""

    def __init__(self, max_size: int = 200) -> None:
        self._cache: dict[str, dict] = {}
        self._max_size = max_size

    def _make_key(self, question: str, schema_context: str) -> str:
        normalized_q = " ".join(question.lower().split())
        schema_hash = hashlib.md5(schema_context.encode()).hexdigest()[:8]
        return f"{normalized_q}|{schema_hash}"

    def get(self, question: str, schema_context: str) -> dict | None:
        return self._cache.get(self._make_key(question, schema_context))

    def put(self, question: str, schema_context: str, plan: dict) -> None:
        if len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[self._make_key(question, schema_context)] = plan


class ChatService:
    def __init__(self) -> None:
        self.connector_service = ConnectorService()
        self.session_service = SessionService()
        self.llm_service = LlmService()
        self.query_cache = QueryPlanCache()
        self.graph = self._build_graph()

    async def process_message_stream(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        provider_preference: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        question = question.strip()
        self.llm_service.ensure_user_message_limit(question)
        data_source = await self.session_service.get_data_source(user_id, session_id)

        yield self._stage_event("thinking", "Thinking")

        small_talk_reply = self._small_talk_reply(question, has_data_source=bool(data_source))
        if small_talk_reply:
            async for event in self._stream_prebuilt_reply(
                user_id=user_id,
                session_id=session_id,
                question=question,
                message=small_talk_reply,
            ):
                yield event
            return

        data_source_reply = self._data_source_reply(question, data_source)
        if data_source_reply:
            if data_source and self._wants_data_overview_analysis(question):
                async for event in self._stream_data_source_overview(
                    user_id=user_id,
                    session_id=session_id,
                    question=question,
                    data_source=data_source,
                    schema_reply=data_source_reply,
                    provider_preference=provider_preference,
                ):
                    yield event
            else:
                async for event in self._stream_prebuilt_reply(
                    user_id=user_id,
                    session_id=session_id,
                    question=question,
                    message=data_source_reply,
                ):
                    yield event
            return

        if not data_source:
            raise ValueError("No data source connected to this session.")

        schema_context = self._build_schema_context(data_source)
        state: AnalysisState = {
            "user_id": user_id,
            "session_id": session_id,
            "provider_preference": provider_preference,
            "question": question,
            "data_source": data_source,
            "schema_context": schema_context,
        }

        # --- Tier 4: Check query plan cache ---
        cached_plan = self.query_cache.get(question, schema_context)
        if cached_plan:
            logger.info("Cache hit for question in session %s", session_id)
            state["query_plan"] = cached_plan
            state["provider_used"] = cached_plan.get("_cached_provider")
            yield self._stage_event("planning", "Using cached plan")
        else:
            yield self._stage_event("planning", "Planning analysis")
            state.update(await self._plan_query(state))

        # --- Tier 1C: Handle execution errors gracefully ---
        yield self._stage_event("querying", "Inspecting data")
        state.update(await self._execute_query(state))

        execution_error = state.get("execution_error")
        if execution_error:
            error_message = self._format_query_error(execution_error, state.get("validation_warnings"))
            async for event in self._stream_prebuilt_reply(
                user_id=user_id,
                session_id=session_id,
                question=question,
                message=error_message,
            ):
                yield event
            return

        rows = state.get("result_rows", [])
        if not rows:
            empty_message = "I could not find matching rows for that question in the connected source."
            if state.get("low_confidence"):
                empty_message += (
                    "\n\nNote: the analysis model had low confidence in the generated query. "
                    "Try rephrasing your question or check that the right tables and columns are selected."
                )
            async for event in self._stream_prebuilt_reply(
                user_id=user_id,
                session_id=session_id,
                question=question,
                message=empty_message,
            ):
                yield event
            return

        # --- Tier 1B: Sanity check results ---
        sanity_warnings = self._sanity_check_results(question, state["query_plan"], rows)

        yield self._stage_event("generating", "Generating insight")

        answer_chunks: list[str] = []
        async for provider, chunk in self.llm_service.stream_text(
            system_prompt=self._answer_prompt(),
            user_prompt=self._answer_user_prompt(
                question=question,
                query_plan=state["query_plan"],
                rows=rows,
                sanity_warnings=sanity_warnings,
            ),
            preferred_provider=state.get("provider_used") or state.get("provider_preference"),
            max_output_tokens=500,
        ):
            if not state.get("provider_used"):
                state["provider_used"] = provider
            answer_chunks.append(chunk)
            yield {"type": "chunk", "content": chunk}

        message = "".join(answer_chunks).strip()
        if not message:
            message = "I analyzed the connected data, but I could not produce a summary for that result set."

        # Append sanity disclaimer if warnings exist
        if sanity_warnings:
            disclaimer = "\n\n⚠️ *Note: " + "; ".join(sanity_warnings) + " Double-check the result if it seems off.*"
            message += disclaimer

        viz_data = self._build_viz_data(
            question=question,
            query_plan=state["query_plan"],
            rows=rows,
            answer=message,
        )

        # --- Tier 4: Cache successful plan ---
        if not cached_plan and rows:
            plan_to_cache = {**state["query_plan"], "_cached_provider": state.get("provider_used")}
            self.query_cache.put(question, schema_context, plan_to_cache)

        now = ist_now()
        await self.session_service.append_messages(
            user_id,
            session_id,
            {"role": "user", "content": question, "created_at": now},
            {"role": "assistant", "content": message, "viz_data": viz_data, "created_at": now},
        )

        yield {
            "type": "final",
            "payload": {
                "message": message,
                "viz_data": viz_data,
                "provider_used": state.get("provider_used"),
            },
        }

    async def process_message(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        provider_preference: str | None = None,
    ) -> dict:
        question = question.strip()
        self.llm_service.ensure_user_message_limit(question)
        data_source = await self.session_service.get_data_source(user_id, session_id)
        small_talk_reply = self._small_talk_reply(question, has_data_source=bool(data_source))
        if small_talk_reply:
            now = ist_now()
            await self.session_service.append_messages(
                user_id,
                session_id,
                {"role": "user", "content": question, "created_at": now},
                {"role": "assistant", "content": small_talk_reply, "viz_data": None, "created_at": now},
            )
            return {
                "message": small_talk_reply,
                "viz_data": None,
                "provider_used": None,
            }

        data_source_reply = self._data_source_reply(question, data_source)
        if data_source_reply:
            if data_source and self._wants_data_overview_analysis(question):
                message, provider_used = await self._build_data_source_overview(
                    question=question,
                    data_source=data_source,
                    schema_reply=data_source_reply,
                    provider_preference=provider_preference,
                )
                now = ist_now()
                await self.session_service.append_messages(
                    user_id,
                    session_id,
                    {"role": "user", "content": question, "created_at": now},
                    {"role": "assistant", "content": message, "viz_data": None, "created_at": now},
                )
                return {
                    "message": message,
                    "viz_data": None,
                    "provider_used": provider_used,
                }

            now = ist_now()
            await self.session_service.append_messages(
                user_id,
                session_id,
                {"role": "user", "content": question, "created_at": now},
                {"role": "assistant", "content": data_source_reply, "viz_data": None, "created_at": now},
            )
            return {
                "message": data_source_reply,
                "viz_data": None,
                "provider_used": None,
            }

        if not data_source:
            raise ValueError("No data source connected to this session.")

        schema_context = self._build_schema_context(data_source)
        state = await self.graph.ainvoke(
            {
                "user_id": user_id,
                "session_id": session_id,
                "provider_preference": provider_preference,
                "question": question,
                "data_source": data_source,
                "schema_context": schema_context,
            }
        )

        answer_payload = state["answer_payload"]
        message = answer_payload["answer"].strip()
        viz_data = None
        if answer_payload.get("needs_visualization") and state.get("result_rows"):
            viz_payload = {
                "rows": state["result_rows"],
                "chart_type": answer_payload.get("chart_type"),
                "explanation": answer_payload.get("chart_title") or answer_payload.get("summary"),
                "query": answer_payload.get("query_preview") or state["query_plan"].get("query"),
                "query_type": state["query_plan"].get("query_type"),
            }
            viz_data = json.dumps(viz_payload, ensure_ascii=False)

        now = ist_now()
        await self.session_service.append_messages(
            user_id,
            session_id,
            {"role": "user", "content": question, "created_at": now},
            {"role": "assistant", "content": message, "viz_data": viz_data, "created_at": now},
        )

        return {
            "message": message,
            "viz_data": viz_data,
            "provider_used": state.get("provider_used"),
        }

    def _small_talk_reply(self, question: str, *, has_data_source: bool) -> str | None:
        normalized = question.lower().translate(str.maketrans("", "", string.punctuation))
        normalized = " ".join(normalized.split())

        greeting_messages = {
            "hi",
            "hii",
            "hiii",
            "hello",
            "hey",
            "heyy",
            "good morning",
            "good afternoon",
            "good evening",
        }
        if normalized in greeting_messages:
            if has_data_source:
                return (
                    "Hi! Your source is connected, so you can ask for counts, trends, comparisons, "
                    "or a chart whenever you're ready."
                )
            return (
                "Hi! Connect a file or database and then ask a question about the data. "
                "I can summarize trends, compare metrics, and build charts."
            )

        if normalized in {"thanks", "thank you", "thx"}:
            if has_data_source:
                return "You're welcome. Ask another question about the connected data whenever you're ready."
            return "You're welcome. Connect a source whenever you're ready, and I'll help analyze it."

        if normalized in {"how are you", "how are you doing", "whats up", "sup"}:
            if has_data_source:
                return "I'm ready and your source is connected. Ask me for a summary, count, comparison, or chart."
            return "I'm ready. Connect a data source first, and then I can analyze it with you."

        if normalized in {"who are you", "what are you", "what is your name", "are you there"}:
            if has_data_source:
                return (
                    "I'm DataSage, your data-analysis assistant. Your source is connected, so I can answer "
                    "questions about its selected tables and help build charts."
                )
            return (
                "I'm DataSage, your data-analysis assistant. Connect a source first, then I can describe it "
                "and answer questions about its rows, fields, and trends."
            )

        if normalized in {"help", "what can you do", "how can you help", "what should i ask"}:
            if has_data_source:
                return (
                    "You can ask things like total counts, top categories, trends over time, comparisons, "
                    "or request a chart from the connected source."
                )
            return (
                "I can analyze uploaded files or connected databases. Connect a source first, then ask "
                "for summaries, comparisons, trends, or charts."
            )

        return None

    def _data_source_reply(self, question: str, data_source: dict | None) -> str | None:
        if not self._is_data_source_question(question):
            return None

        if not data_source:
            return (
                "No data source is connected to this session yet. Connect a CSV, Excel, parquet file, "
                "MongoDB Atlas database, or Supabase PostgreSQL database, then I can describe its tables and fields."
            )

        return self._describe_data_source(data_source, include_columns=self._is_column_request(question))

    def _is_data_source_question(self, question: str) -> bool:
        normalized = question.lower().translate(str.maketrans("", "", string.punctuation))
        normalized = " ".join(normalized.split())
        words = set(normalized.split())

        exact_phrases = {
            "describe my data source",
            "describe data source",
            "describe datasource",
            "what is my data source",
            "what datasource is connected",
            "what data source is connected",
            "which data source is connected",
            "show schema",
            "show me schema",
            "describe schema",
            "list tables",
            "show tables",
            "list collections",
            "show collections",
            "list columns",
            "show columns",
            "list fields",
            "show fields",
            "what data do you have",
            "what data is connected",
            "tell me about my data",
            "tell me about this data",
            "describe my data",
            "describe this data",
            "explain my data",
            "explain this data",
            "explain dataset",
        }
        if normalized in exact_phrases:
            return True

        source_phrases = (
            "data source",
            "datasource",
            "connected source",
            "connected database",
            "connected db",
            "connected file",
            "my database",
            "my dataset",
            "this dataset",
            "the dataset",
            "my data",
            "this data",
            "the data",
            "its data",
        )
        schema_words = {"schema", "tables", "table", "collections", "collection", "columns", "column", "fields", "field"}
        source_actions = {"describe", "explain", "show", "list", "what", "which", "tell", "summarize", "summary"}

        if any(phrase in normalized for phrase in source_phrases) and words.intersection(source_actions):
            return True
        return bool(words.intersection(schema_words) and words.intersection(source_actions))

    def _is_column_request(self, question: str) -> bool:
        normalized = question.lower().translate(str.maketrans("", "", string.punctuation))
        words = set(normalized.split())
        return bool(words.intersection({"schema", "columns", "column", "fields", "field", "structure", "describe"}))

    def _wants_data_overview_analysis(self, question: str) -> bool:
        normalized = question.lower().translate(str.maketrans("", "", string.punctuation))
        normalized = " ".join(normalized.split())
        words = set(normalized.split())

        if normalized in {
            "what data do you have",
            "what data is connected",
            "tell me about my data",
            "tell me about this data",
            "describe my data source",
            "describe data source",
            "describe datasource",
            "describe my data",
            "describe this data",
            "explain my data",
            "explain this data",
            "explain dataset",
        }:
            return True
        if words.intersection({"describe", "explain", "summarize", "summary", "overview", "analyze", "analyse"}):
            return bool(words.intersection({"data", "dataset", "database", "source", "schema"}))
        return False

    def _describe_data_source(self, data_source: dict, *, include_columns: bool) -> str:
        schema = data_source.get("schema_cache", {})
        selected = set(data_source.get("selected_tables", []))
        all_tables = schema.get("tables", [])
        visible_tables = [table for table in all_tables if not selected or table.get("name") in selected]
        hidden_tables = [table for table in all_tables if selected and table.get("name") not in selected]

        source_label = self._source_label(data_source)
        table_label = self._table_label(data_source["type"], plural=True)
        lines = [f"You're connected to {source_label}."]

        description = data_source.get("database_description")
        if description:
            lines.append(f"Description: {description}")

        if not visible_tables:
            lines.append(f"I found the source, but no {table_label} are currently selected for chat.")
            return "\n".join(lines)

        lines.append(
            f"Selected {table_label}: "
            + ", ".join(self._table_summary(table) for table in visible_tables)
            + "."
        )

        if hidden_tables:
            lines.append(
                f"Also detected but not selected: "
                + ", ".join(str(table.get("name", "unknown")) for table in hidden_tables)
                + "."
            )

        if include_columns:
            lines.append("Fields I can use:")
            for table in visible_tables[:8]:
                table_name = str(table.get("name", "unknown"))
                fields = [str(field.get("name")) for field in table.get("fields", []) if field.get("name")]
                field_text = ", ".join(fields[:16]) if fields else "no fields detected"
                if len(fields) > 16:
                    field_text = f"{field_text}, and {len(fields) - 16} more"
                lines.append(f"- {table_name}: {field_text}")
            if len(visible_tables) > 8:
                lines.append(f"- Plus {len(visible_tables) - 8} more selected {table_label}.")

        lines.append("You can ask for counts, row summaries, comparisons, trends, or charts from these selected tables.")
        return "\n".join(lines)

    async def _stream_data_source_overview(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        data_source: dict,
        schema_reply: str,
        provider_preference: str | None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield self._stage_event("profiling", "Profiling data")
        profile = await self._sample_data_profile(data_source)

        yield self._stage_event("generating", "Generating insight")
        provider_used = None
        answer_chunks = [schema_reply.rstrip(), "\n\n"]
        for chunk in self._split_stream_text(answer_chunks[0] + "\n\n"):
            yield {"type": "chunk", "content": chunk}
            await asyncio.sleep(0.02)

        try:
            async for provider, chunk in self.llm_service.stream_text(
                system_prompt=self._data_overview_prompt(),
                user_prompt=self._data_overview_user_prompt(
                    question=question,
                    schema_reply=schema_reply,
                    profile=profile,
                ),
                preferred_provider=provider_preference,
                max_output_tokens=900,
            ):
                if not provider_used:
                    provider_used = provider
                answer_chunks.append(chunk)
                yield {"type": "chunk", "content": chunk}
        except ValueError:
            fallback = self._fallback_profile_analysis(profile)
            answer_chunks = [schema_reply.rstrip(), "\n\n", fallback]
            for chunk in self._split_stream_text(f"\n\n{fallback}"):
                yield {"type": "chunk", "content": chunk}
                await asyncio.sleep(0.02)

        insight = "".join(answer_chunks[1:]).strip()
        if self._is_incomplete_overview(insight):
            fallback = self._fallback_profile_analysis(profile)
            answer_chunks = [schema_reply.rstrip(), "\n\n", fallback]
            for chunk in self._split_stream_text(f"\n\n{fallback}"):
                yield {"type": "chunk", "content": chunk}
                await asyncio.sleep(0.02)

        message = "".join(answer_chunks).strip()
        now = ist_now()
        await self.session_service.append_messages(
            user_id,
            session_id,
            {"role": "user", "content": question, "created_at": now},
            {"role": "assistant", "content": message, "viz_data": None, "created_at": now},
        )
        yield {"type": "final", "payload": {"message": message, "viz_data": None, "provider_used": provider_used}}

    async def _build_data_source_overview(
        self,
        *,
        question: str,
        data_source: dict,
        schema_reply: str,
        provider_preference: str | None,
    ) -> tuple[str, str | None]:
        profile = await self._sample_data_profile(data_source)
        try:
            insight, provider = await self.llm_service.invoke_text(
                system_prompt=self._data_overview_prompt(),
                user_prompt=self._data_overview_user_prompt(
                    question=question,
                    schema_reply=schema_reply,
                    profile=profile,
                ),
                preferred_provider=provider_preference,
                max_output_tokens=900,
            )
        except ValueError:
            return f"{schema_reply.rstrip()}\n\n{self._fallback_profile_analysis(profile)}".strip(), None
        if self._is_incomplete_overview(insight):
            return f"{schema_reply.rstrip()}\n\n{self._fallback_profile_analysis(profile)}".strip(), provider
        return f"{schema_reply.rstrip()}\n\n{insight.strip()}".strip(), provider

    async def _sample_data_profile(self, data_source: dict) -> list[dict]:
        selected_count = len(data_source.get("selected_tables", []))
        table_limit = max(3, min(selected_count, MAX_CONTEXT_TABLES))
        samples = await self.connector_service.sample_data_source(data_source, max_tables=table_limit, row_limit=20)
        table_rows_by_name = {
            str(table.get("name")): table
            for table in data_source.get("schema_cache", {}).get("tables", [])
            if table.get("name")
        }
        return [
            self._profile_rows(table_name, rows, table_rows_by_name.get(table_name, {}))
            for table_name, rows in samples.items()
        ]

    def _profile_rows(self, table_name: str, rows: list[dict], table_schema: dict) -> dict:
        columns: dict[str, list[Any]] = {}
        for row in rows:
            for key, value in row.items():
                if value is not None:
                    columns.setdefault(str(key), []).append(value)

        numeric_summaries = []
        category_summaries = []
        for key, values in columns.items():
            numeric_values = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
            if numeric_values:
                numeric_summaries.append(
                    {
                        "field": key,
                        "min": min(numeric_values),
                        "max": max(numeric_values),
                        "average": round(sum(numeric_values) / len(numeric_values), 2),
                    }
                )
                continue

            text_values = [
                self._truncate_text(str(value), 80)
                for value in values
                if isinstance(value, (str, bool)) and str(value).strip()
            ]
            if text_values:
                category_summaries.append(
                    {
                        "field": key,
                        "top_values": Counter(text_values).most_common(3),
                    }
                )

        return {
            "table": table_name,
            "declared_row_count": table_schema.get("row_count"),
            "sampled_rows": len(rows),
            "field_count": len(table_schema.get("fields", [])),
            "numeric_fields": numeric_summaries[:8],
            "categorical_fields": category_summaries[:8],
            "sample_rows": [self._compact_prompt_row(row) for row in rows[:3]],
        }

    def _data_overview_prompt(self) -> str:
        return (
            "You are a careful data analyst describing a connected data source. "
            "Use only the schema summary and sampled profile. "
            "Describe ALL tables/collections present in the data — their purpose, key fields, and relationships. "
            "Then write a short Key trends and analysis section with concrete numbers, observed ranges, top categories, "
            "and any obvious data quality notes. If the profile is sampled, say trends are sample-based. "
            "Always refer to items by human-readable names, never by raw IDs. "
            "Do not repeat the full schema and do not invent fields or conclusions."
        )

    def _data_overview_user_prompt(self, *, question: str, schema_reply: str, profile: list[dict]) -> str:
        return (
            f"User question:\n{question}\n\n"
            f"Schema summary already shown to user:\n{schema_reply}\n\n"
            f"Sampled profile:\n{self._json_for_prompt(profile, max_chars=MAX_PROMPT_CHARS)}"
        )

    def _fallback_profile_analysis(self, profile: list[dict]) -> str:
        if not profile:
            return "Key trends and analysis:\n- I could describe the schema, but I could not sample rows for trend analysis."

        lines = ["Key trends and analysis:"]
        for table in profile:
            table_name = table["table"]
            sampled_rows = table["sampled_rows"]
            declared_rows = table.get("declared_row_count")
            row_text = f"{sampled_rows} sampled rows"
            if isinstance(declared_rows, int):
                row_text += f" from {declared_rows} total rows"
            lines.append(f"- {table_name}: profiled {row_text}.")

            for item in table.get("numeric_fields", [])[:2]:
                lines.append(
                    f"- {table_name}.{item['field']} ranges from {item['min']} to {item['max']} "
                    f"with an average of {item['average']} in the sample."
                )
            for item in table.get("categorical_fields", [])[:2]:
                top_values = ", ".join(f"{value} ({count})" for value, count in item.get("top_values", []))
                if top_values:
                    lines.append(f"- {table_name}.{item['field']} is led by {top_values} in the sample.")
        return "\n".join(lines)

    def _is_incomplete_overview(self, insight: str) -> bool:
        normalized = insight.strip()
        if not normalized:
            return True

        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if not lines:
            return True

        last_line = re.sub(r"[*_`#>\s]+", "", lines[-1]).strip()
        if not last_line:
            return True

        heading_only = re.match(r"^(#+\s*)?(key trends|analysis|summary|overview)\b.*:?\s*$", lines[-1], re.I)
        has_list_item = any(line.startswith(("- ", "* ")) or re.match(r"^\d+\.\s+", line) for line in lines)
        if heading_only and not has_list_item:
            return True

        if lines[-1].startswith(("-", "*")) and len(lines[-1]) <= 3:
            return True

        if normalized.endswith((",", ":", ";", "-", "(", "[", "{")):
            return True

        dangling_words = r"\b(and|or|with|including|such as|among|between|from|to|of|for|by|via)$"
        return bool(re.search(dangling_words, last_line, re.I))

    def _source_label(self, data_source: dict) -> str:
        source_type = data_source["type"]
        if source_type == "mongodb":
            name = data_source.get("database_name") or "database"
            return f"MongoDB database `{name}`"
        if source_type == "postgresql":
            name = data_source.get("database_name") or "database"
            return f"PostgreSQL database `{name}`"
        file_name = data_source.get("file_name") or data_source.get("database_name") or "uploaded file"
        return f"{source_type.upper()} file `{file_name}`"

    def _table_label(self, source_type: str, *, plural: bool) -> str:
        if source_type == "mongodb":
            return "collections" if plural else "collection"
        return "tables" if plural else "table"

    def _table_summary(self, table: dict) -> str:
        name = str(table.get("name", "unknown"))
        row_count = table.get("row_count")
        field_count = len(table.get("fields", []))
        row_text = f"{row_count} rows" if isinstance(row_count, int) else "unknown rows"
        return f"{name} ({row_text}, {field_count} fields)"

    async def _stream_prebuilt_reply(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        message: str,
        viz_data: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield self._stage_event("generating", "Generating insight")
        for chunk in self._split_stream_text(message):
            yield {"type": "chunk", "content": chunk}
            await asyncio.sleep(0.02)

        now = ist_now()
        await self.session_service.append_messages(
            user_id,
            session_id,
            {"role": "user", "content": question, "created_at": now},
            {"role": "assistant", "content": message, "viz_data": viz_data, "created_at": now},
        )
        yield {"type": "final", "payload": {"message": message, "viz_data": viz_data}}

    def _build_graph(self):
        graph = StateGraph(AnalysisState)
        graph.add_node("plan_query", self._plan_query)
        graph.add_node("execute_query", self._execute_query)
        graph.add_node("summarize_result", self._summarize_result)
        graph.add_edge(START, "plan_query")
        graph.add_edge("plan_query", "execute_query")
        graph.add_edge("execute_query", "summarize_result")
        graph.add_edge("summarize_result", END)
        return graph.compile()

    async def _plan_query(self, state: AnalysisState) -> AnalysisState:
        source_type = state["data_source"]["type"]
        question = state["question"]
        context = state["schema_context"]
        retry_count = state.get("retry_count", 0)
        prompt = self._query_planner_prompt(source_type)
        user_prompt = f"Question:\n{question}\n\nSchema context:\n{context}"

        # --- Tier 3A: Inject previous validation errors on retry ---
        prev_warnings = state.get("validation_warnings", [])
        if retry_count > 0 and prev_warnings:
            user_prompt += (
                "\n\nYour previous query attempt had these problems:\n"
                + "\n".join(f"- {w}" for w in prev_warnings)
                + "\nPlease fix these issues and only use fields that exist in the schema."
            )

        try:
            payload, provider = await self.llm_service.invoke_json(
                system_prompt=prompt,
                user_prompt=user_prompt,
                preferred_provider=state.get("provider_preference"),
                schema=MongoAnalysisPlan if source_type == "mongodb" else SqlAnalysisPlan,
                max_output_tokens=500,
            )
        except ValueError as exc:
            if self._is_structured_output_error(exc):
                raise ValueError(
                    "The analysis model returned malformed structured output while building the query. Please try again."
                ) from exc
            raise
        payload["query_type"] = source_type if source_type == "mongodb" else "sql"

        # --- Tier 1A: Validate plan against schema ---
        warnings = self._validate_query_plan_against_schema(payload, state["data_source"])

        # --- Tier 2A: Check confidence ---
        low_confidence = payload.get("confidence") == "low"
        if low_confidence:
            logger.info("LLM reported low confidence for question: %s", question[:100])

        result: AnalysisState = {
            "query_plan": payload,
            "provider_used": provider,
            "validation_warnings": warnings,
            "retry_count": retry_count + 1,
            "low_confidence": low_confidence,
        }

        # --- Tier 3A: Retry once if validation found issues ---
        if warnings and retry_count < MAX_QUERY_RETRIES:
            logger.warning(
                "Query plan validation found issues (attempt %d): %s",
                retry_count + 1,
                "; ".join(warnings),
            )
            retry_state: AnalysisState = {**state, **result}
            return await self._plan_query(retry_state)

        if warnings:
            logger.warning("Proceeding with validation warnings after max retries: %s", "; ".join(warnings))

        return result

    async def _execute_query(self, state: AnalysisState) -> AnalysisState:
        try:
            result = await self.connector_service.execute_analysis_query(state["data_source"], state["query_plan"])
            return {"result_rows": result["rows"]}
        except (ValueError, Exception) as exc:
            error_msg = str(exc)
            logger.warning("Query execution failed: %s", error_msg)
            return {"result_rows": [], "execution_error": error_msg}

    async def _summarize_result(self, state: AnalysisState) -> AnalysisState:
        # --- Tier 1C: Handle execution error from graph path ---
        execution_error = state.get("execution_error")
        if execution_error:
            return {
                "answer_payload": {
                    "answer": self._format_query_error(execution_error, state.get("validation_warnings")),
                    "needs_visualization": False,
                    "chart_type": None,
                    "chart_title": None,
                    "summary": "Query execution failed",
                }
            }

        rows = state.get("result_rows", [])
        if not rows:
            empty_msg = "I could not find matching rows for that question in the connected source."
            if state.get("low_confidence"):
                empty_msg += (
                    "\n\nNote: the analysis model had low confidence in the generated query. "
                    "Try rephrasing your question or check that the right tables and columns are selected."
                )
            return {
                "answer_payload": {
                    "answer": empty_msg,
                    "needs_visualization": False,
                    "chart_type": None,
                    "chart_title": None,
                    "summary": "No matching rows",
                }
            }

        prompt = (
            "You are a careful data analyst. Use only the query result provided. "
            "Return compact JSON with keys: answer, needs_visualization, chart_type, chart_title, summary, query_preview. "
            "Keep answer concise, highlight numbers clearly, and avoid claiming anything not in the rows. "
            "IMPORTANT: In your answer, always refer to items by their human-readable name, title, or label. "
            "Never display raw IDs, ObjectIds, UUIDs, or numeric foreign keys to the user. "
            "If the data has both an ID and a name column, use only the name in your answer text and chart_title. "
            "Choose chart_type from: bar, horizontal_bar, line, donut, 3d_bar, radar, table. "
            "needs_visualization must be true only when a visual would genuinely help."
        )
        limited_rows = self._compact_prompt_rows(rows)
        user_prompt = (
            f"User question:\n{state['question']}\n\n"
            f"Query plan:\n{self._json_for_prompt(state['query_plan'])}\n\n"
            f"Rows:\n{self._json_for_prompt(limited_rows)}"
        )
        try:
            payload, provider = await self.llm_service.invoke_json(
                system_prompt=prompt,
                user_prompt=user_prompt,
                preferred_provider=state.get("provider_used") or state.get("provider_preference"),
                schema=AnalysisAnswerPayload,
                max_output_tokens=500,
            )
        except ValueError as exc:
            if self._is_structured_output_error(exc):
                raise ValueError(
                    "The analysis model returned malformed structured output while summarizing the result. Please try again."
                ) from exc
            raise
        payload.setdefault("needs_visualization", self._rows_are_chartable(rows))
        payload.setdefault("chart_type", "bar")
        payload.setdefault("summary", "Query result")
        if provider:
            return {"answer_payload": payload, "provider_used": provider}
        return {"answer_payload": payload}

    def _build_schema_context(self, data_source: dict) -> str:
        schema = data_source.get("schema_cache", {})
        selected = set(data_source.get("selected_tables", []))
        database_description = data_source.get("database_description") or ""
        lines = [f"Source type: {data_source['type']}"]
        if data_source.get("database_name"):
            lines.append(f"Database name: {data_source['database_name']}")
        if data_source.get("file_name"):
            lines.append(f"File name: {data_source['file_name']}")
        if database_description:
            lines.append(f"Database description: {database_description}")

        included_tables = 0
        skipped_tables = 0
        for table in schema.get("tables", []):
            table_name = table["name"]
            if selected and table_name not in selected:
                continue
            if included_tables >= MAX_CONTEXT_TABLES:
                skipped_tables += 1
                continue
            included_tables += 1
            table_description = data_source.get("table_descriptions", {}).get(table_name)
            lines.append(f"\nTable: {table_name}")
            if table_description:
                lines.append(f"Table description: {self._truncate_text(table_description, 240)}")
            lines.append(f"Row count: {table.get('row_count', 'unknown')}")
            fields = table.get("fields", [])
            for field in fields[:MAX_CONTEXT_FIELDS_PER_TABLE]:
                description = data_source.get("field_descriptions", {}).get(table_name, {}).get(field["name"])
                sample_text = ", ".join(
                    self._truncate_text(str(sample), MAX_CONTEXT_SAMPLE_CHARS)
                    for sample in field.get("samples", [])[:2]
                )
                lines.append(
                    f"- {field['name']} ({field.get('type', 'unknown')})"
                    + (f": {self._truncate_text(description, 180)}" if description else "")
                    + (f" | samples: {sample_text}" if sample_text else "")
                )
            if len(fields) > MAX_CONTEXT_FIELDS_PER_TABLE:
                lines.append(f"- ... {len(fields) - MAX_CONTEXT_FIELDS_PER_TABLE} more fields omitted")
        if skipped_tables:
            lines.append(f"\n... {skipped_tables} more selected tables omitted from prompt context")
        return self._truncate_text("\n".join(lines), MAX_PROMPT_CHARS)

    def _query_planner_prompt(self, source_type: str) -> str:
        if source_type == "mongodb":
            return (
                "You write safe MongoDB aggregation queries for analytics. "
                "Return JSON only. Keys: collection, pipeline, chart_type, notes, confidence. "
                "Rules: only use selected collections and fields from the schema context; "
                "never use $out or $merge; add $limit only if needed for previews; "
                "IMPORTANT: Before writing the pipeline, verify every field name you reference "
                "exists in the schema context provided. If you cannot confidently answer the question "
                "with the available schema, set confidence to 'low' and explain in notes what is missing. "
                "Set confidence to 'high' when the schema clearly supports the query, 'medium' if some assumptions are made. "
                "CRITICAL: When grouping by an ID field (like _id, category_id, product_id, user_id, etc.), "
                "always use $lookup to join with the related collection and $project to include the human-readable "
                "name/title/label field instead of showing raw IDs. The result rows must contain readable names, not IDs. "
                "If there is a 'name', 'title', or 'label' field in the same collection, group by that instead of the ID. "
                "prefer aggregation answers suitable for dashboards and comparisons; "
                "pipeline must be a valid JSON array of single-key stage objects like "
                '{"$match": {"field": "value"}}, {"$group": {"_id": "$field", "count": {"$sum": 1}}}; '
                "every aggregation stage operator must start with '$'."
            )
        dialect = "DuckDB SQL" if source_type in {"csv", "excel", "parquet"} else "PostgreSQL SQL"
        return (
            f"You write safe read-only {dialect} for analytics. "
            "Return JSON only. Keys: query, chart_type, notes, confidence. "
            "Rules: only SELECT or WITH queries; never modify data; "
            "quote identifiers when needed; use only tables and columns in schema context; "
            "IMPORTANT: Before writing the query, verify every column and table name you reference "
            "exists in the schema context provided. If you cannot confidently answer the question "
            "with the available schema, set confidence to 'low' and explain in notes what is missing. "
            "Set confidence to 'high' when the schema clearly supports the query, 'medium' if some assumptions are made. "
            "CRITICAL: When the result would show an ID column (like id, category_id, product_id, user_id, etc.), "
            "always JOIN with the related table and SELECT the human-readable name/title/label column instead. "
            "The result rows must contain readable names, not numeric or UUID IDs. "
            "If there is a 'name', 'title', or 'label' column in the same table, select that instead of the ID. "
            "keep results compact and analysis-ready; prefer grouped comparisons for finance questions."
        )

    def _rows_are_chartable(self, rows: list[dict]) -> bool:
        if len(rows) < 2:
            return False
        numeric_keys = set()
        for row in rows:
            for key, value in row.items():
                if isinstance(value, (int, float)):
                    numeric_keys.add(key)
        return bool(numeric_keys)

    def _answer_prompt(self) -> str:
        return (
            "You are a careful data analyst. Answer using only the provided query result. "
            "Be concise, natural, and confident without overstating certainty. "
            "Lead with the most important finding, mention concrete numbers, and use short bullets only when it helps clarity. "
            "IMPORTANT: Always refer to data items by their human-readable name, title, or label. "
            "Never show raw IDs, ObjectIds, UUIDs, or numeric foreign keys in your answer. "
            "If the data contains both an ID and a name field, always use the name. "
            "When the user asks to describe, explain, or summarize connected data, describe ALL tables/collections "
            "and their relationships, field purposes, and key data patterns. "
            "Do not mention JSON, internal prompts, or implementation details."
        )

    def _answer_user_prompt(
        self,
        *,
        question: str,
        query_plan: dict,
        rows: list[dict],
        sanity_warnings: list[str] | None = None,
    ) -> str:
        limited_rows = self._compact_prompt_rows(rows)
        prompt = (
            f"User question:\n{question}\n\n"
            f"Executed query plan:\n{self._json_for_prompt(query_plan)}\n\n"
            f"Rows:\n{self._json_for_prompt(limited_rows)}"
        )
        if sanity_warnings:
            prompt += (
                "\n\nWarnings about this result (mention relevant caveats in your answer): "
                + "; ".join(sanity_warnings)
            )
        return prompt

    def _build_viz_data(
        self,
        *,
        question: str,
        query_plan: dict,
        rows: list[dict],
        answer: str,
    ) -> str | None:
        if not self._rows_are_chartable(rows):
            return None

        query_preview = query_plan.get("query")
        if not query_preview and query_plan.get("pipeline") is not None:
            query_preview = json.dumps(query_plan["pipeline"], ensure_ascii=False)

        viz_payload = {
            "rows": rows,
            "chart_type": query_plan.get("chart_type") or "bar",
            "explanation": answer,
            "query": query_preview,
            "query_type": query_plan.get("query_type"),
            "summary": self._compact_question(question),
        }
        return json.dumps(viz_payload, ensure_ascii=False)

    def _compact_question(self, question: str) -> str:
        normalized = " ".join(question.split()).rstrip(" ?")
        if len(normalized) <= 96:
            return normalized
        return f"{normalized[:93].rstrip()}..."

    def _compact_prompt_rows(self, rows: list[dict]) -> list[dict]:
        return [self._compact_prompt_row(row) for row in rows[:MAX_PROMPT_ROWS]]

    def _compact_prompt_row(self, row: dict) -> dict:
        compact: dict[str, Any] = {}
        for index, (key, value) in enumerate(row.items()):
            if index >= MAX_PROMPT_FIELDS_PER_ROW:
                compact["..."] = f"{len(row) - MAX_PROMPT_FIELDS_PER_ROW} more fields omitted"
                break
            compact[str(key)] = self._compact_prompt_value(value)
        return compact

    def _compact_prompt_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._compact_prompt_value(item)
                for key, item in list(value.items())[:MAX_PROMPT_FIELDS_PER_ROW]
            }
        if isinstance(value, list):
            return [self._compact_prompt_value(item) for item in value[:5]]
        if isinstance(value, str):
            return self._truncate_text(value, MAX_PROMPT_VALUE_CHARS)
        return value

    def _json_for_prompt(self, payload: Any, *, max_chars: int = MAX_PROMPT_CHARS) -> str:
        return self._truncate_text(json.dumps(payload, ensure_ascii=False), max_chars)

    def _truncate_text(self, value: str, max_chars: int) -> str:
        text = str(value)
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3].rstrip()}..."

    def _split_stream_text(self, text: str, chunk_size: int = 160) -> list[str]:
        if not text:
            return [""]

        chunks: list[str] = []
        for index in range(0, len(text), chunk_size):
            chunks.append(text[index : index + chunk_size])
        return chunks

    def _stage_event(self, stage: str, label: str) -> dict[str, str]:
        return {"type": "stage", "stage": stage, "label": label}

    def _is_structured_output_error(self, error: Exception) -> bool:
        lowered = str(error).lower()
        return (
            "invalid json" in lowered
            or "structured output" in lowered
            or "malformed" in lowered
            or "validation error" in lowered
            or "field required" in lowered
        )

    # ------------------------------------------------------------------ #
    #  Tier 1A: Schema validation (zero LLM cost)                        #
    # ------------------------------------------------------------------ #

    def _validate_query_plan_against_schema(self, query_plan: dict, data_source: dict) -> list[str]:
        """Validate the LLM-generated query plan against the known schema. Returns warnings."""
        warnings: list[str] = []
        schema = data_source.get("schema_cache", {})
        selected = set(data_source.get("selected_tables", []))
        known_tables = {str(t["name"]) for t in schema.get("tables", []) if t.get("name")}
        known_fields: dict[str, set[str]] = {}
        for t in schema.get("tables", []):
            known_fields[str(t["name"])] = {str(f["name"]) for f in t.get("fields", []) if f.get("name")}

        source_type = data_source["type"]
        if source_type == "mongodb":
            collection = query_plan.get("collection", "")
            if collection and collection not in known_tables:
                warnings.append(f"Collection '{collection}' not found in schema.")
            if selected and collection and collection not in selected:
                warnings.append(f"Collection '{collection}' is not in selected tables.")
            # Check field references in pipeline
            pipeline = query_plan.get("pipeline", [])
            if pipeline and collection and collection in known_fields:
                mongo_refs = self._extract_mongo_field_refs(pipeline)
                table_fields = known_fields[collection]
                # Also include _id as it's always present
                table_fields_lower = {f.lower() for f in table_fields} | {"_id", "id"}
                for ref in mongo_refs:
                    if ref.lower() not in table_fields_lower:
                        warnings.append(f"Field '${ref}' not found in collection '{collection}'.")
        else:
            query = query_plan.get("query", "")
            if query:
                referenced = self._extract_sql_identifiers(query)
                all_known_cols: set[str] = set()
                for fields in known_fields.values():
                    all_known_cols.update(f.lower() for f in fields)
                all_known_tables_lower = {t.lower() for t in known_tables}
                # Also include common SQL aliases and functions
                ignore_idents = {"t", "t1", "t2", "a", "b", "c", "sub", "cte", "total", "result"}
                for ident in referenced:
                    ident_lower = ident.lower()
                    if (
                        ident_lower not in all_known_cols
                        and ident_lower not in all_known_tables_lower
                        and ident_lower not in ignore_idents
                        and ident_lower not in SQL_KEYWORDS
                    ):
                        warnings.append(f"Identifier '{ident}' not found in schema.")

        return warnings[:5]  # Cap to avoid overwhelming retry prompt

    def _extract_sql_identifiers(self, query: str) -> set[str]:
        """Extract non-keyword identifiers from SQL for validation."""
        # Remove string literals
        cleaned = re.sub(r"'[^']*'", "", query)
        # Remove numbers
        cleaned = re.sub(r"\b\d+(\.\d+)?\b", "", cleaned)
        # Remove quoted identifiers but keep the name
        cleaned = re.sub(r'"([^"]+)"', r"\1", cleaned)
        # Extract word-like identifiers
        tokens = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", cleaned)
        return {t for t in tokens if t.lower() not in SQL_KEYWORDS}

    def _extract_mongo_field_refs(self, pipeline: list) -> set[str]:
        """Extract field references (e.g. $fieldName) from a MongoDB pipeline."""
        refs: set[str] = set()

        def _walk(obj: object) -> None:
            if isinstance(obj, str) and obj.startswith("$") and not obj.startswith("$$"):
                field = obj.lstrip("$").split(".")[0]
                if field and not field.startswith("$"):
                    refs.add(field)
            elif isinstance(obj, dict):
                for value in obj.values():
                    _walk(value)
            elif isinstance(obj, list):
                for item in obj:
                    _walk(item)

        _walk(pipeline)
        return refs

    # ------------------------------------------------------------------ #
    #  Tier 1B: Result sanity checks (zero LLM cost)                     #
    # ------------------------------------------------------------------ #

    def _sanity_check_results(self, question: str, query_plan: dict, rows: list[dict]) -> list[str]:
        """Lightweight heuristic checks on query results. Returns warnings."""
        warnings: list[str] = []
        if not rows:
            return warnings

        # Check: single-row result for a question that implies multiple
        plural_signals = {"all", "each", "every", "list", "compare", "by", "per", "breakdown", "top", "distribution"}
        q_words = set(question.lower().split())
        if len(rows) == 1 and q_words.intersection(plural_signals):
            warnings.append("Query returned only 1 row but the question implies multiple results.")

        # Check: result has only null/zero values in all numeric columns
        numeric_values = [v for row in rows for v in row.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if numeric_values and all(v == 0 for v in numeric_values):
            warnings.append("All numeric values in the result are zero.")

        # Check: returned columns don't overlap with anything in the question
        if len(rows[0]) > 1:
            result_keys = set()
            for k in rows[0].keys():
                result_keys.update(k.lower().replace("_", " ").split())
            q_lower = question.lower()
            meaningful_q_words = {w for w in q_words if len(w) > 3}
            has_match = any(
                word in q_lower or any(qw in word for qw in meaningful_q_words)
                for word in result_keys
                if len(word) > 2
            )
            if not has_match and meaningful_q_words:
                warnings.append("Result columns don't appear related to the question.")

        return warnings[:3]

    # ------------------------------------------------------------------ #
    #  Tier 1C: Error formatting                                         #
    # ------------------------------------------------------------------ #

    def _format_query_error(self, error: str, validation_warnings: list[str] | None = None) -> str:
        """Format a query execution error into a user-friendly message."""
        # Simplify common DB error messages
        error_lower = error.lower()
        if "column" in error_lower and "does not exist" in error_lower:
            hint = "The generated query referenced a column that doesn't exist in the database."
        elif "relation" in error_lower and "does not exist" in error_lower:
            hint = "The generated query referenced a table that doesn't exist in the database."
        elif "syntax error" in error_lower:
            hint = "The generated query had a syntax error."
        elif "permission denied" in error_lower:
            hint = "The database denied permission to run this query."
        elif "timeout" in error_lower or "timed out" in error_lower:
            hint = "The query took too long to execute."
        else:
            hint = f"The generated query could not be executed: {error}"

        parts = [hint]
        if validation_warnings:
            parts.append("Detected issues: " + "; ".join(validation_warnings) + ".")
        parts.append("Try rephrasing your question, or check that the right tables and columns are selected in the source preview.")
        return "\n\n".join(parts)

