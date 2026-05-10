import asyncio
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
from app.utils.time import ist_now


MAX_PROMPT_CHARS = 12_000
MAX_CONTEXT_TABLES = 8
MAX_CONTEXT_FIELDS_PER_TABLE = 14
MAX_CONTEXT_SAMPLE_CHARS = 80
MAX_PROMPT_ROWS = 12
MAX_PROMPT_FIELDS_PER_ROW = 14
MAX_PROMPT_VALUE_CHARS = 320


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


class ChatService:
    def __init__(self) -> None:
        self.connector_service = ConnectorService()
        self.session_service = SessionService()
        self.llm_service = LlmService()
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

        state: AnalysisState = {
            "user_id": user_id,
            "session_id": session_id,
            "provider_preference": provider_preference,
            "question": question,
            "data_source": data_source,
            "schema_context": self._build_schema_context(data_source),
        }

        yield self._stage_event("planning", "Planning analysis")
        state.update(await self._plan_query(state))

        yield self._stage_event("querying", "Inspecting data")
        state.update(await self._execute_query(state))

        rows = state.get("result_rows", [])
        if not rows:
            empty_message = "I could not find matching rows for that question in the connected source."
            async for event in self._stream_prebuilt_reply(
                user_id=user_id,
                session_id=session_id,
                question=question,
                message=empty_message,
            ):
                yield event
            return

        yield self._stage_event("generating", "Generating insight")

        answer_chunks: list[str] = []
        async for provider, chunk in self.llm_service.stream_text(
            system_prompt=self._answer_prompt(),
            user_prompt=self._answer_user_prompt(
                question=question,
                query_plan=state["query_plan"],
                rows=rows,
            ),
            preferred_provider=state.get("provider_used") or state.get("provider_preference"),
            max_output_tokens=700,
        ):
            if not state.get("provider_used"):
                state["provider_used"] = provider
            answer_chunks.append(chunk)
            yield {"type": "chunk", "content": chunk}

        message = "".join(answer_chunks).strip()
        if not message:
            message = "I analyzed the connected data, but I could not produce a summary for that result set."

        viz_data = self._build_viz_data(
            question=question,
            query_plan=state["query_plan"],
            rows=rows,
            answer=message,
        )

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
                max_output_tokens=1400,
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
                max_output_tokens=1400,
            )
        except ValueError:
            return f"{schema_reply.rstrip()}\n\n{self._fallback_profile_analysis(profile)}".strip(), None
        if self._is_incomplete_overview(insight):
            return f"{schema_reply.rstrip()}\n\n{self._fallback_profile_analysis(profile)}".strip(), provider
        return f"{schema_reply.rstrip()}\n\n{insight.strip()}".strip(), provider

    async def _sample_data_profile(self, data_source: dict) -> list[dict]:
        samples = await self.connector_service.sample_data_source(data_source, max_tables=3, row_limit=30)
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
            "Write a short Key trends and analysis section with concrete numbers, observed ranges, top categories, "
            "and any obvious data quality notes. If the profile is sampled, say trends are sample-based. "
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
        prompt = self._query_planner_prompt(source_type)
        user_prompt = f"Question:\n{question}\n\nSchema context:\n{context}"
        try:
            payload, provider = await self.llm_service.invoke_json(
                system_prompt=prompt,
                user_prompt=user_prompt,
                preferred_provider=state.get("provider_preference"),
                schema=MongoAnalysisPlan if source_type == "mongodb" else SqlAnalysisPlan,
                max_output_tokens=700,
            )
        except ValueError as exc:
            if self._is_structured_output_error(exc):
                raise ValueError(
                    "The analysis model returned malformed structured output while building the query. Please try again."
                ) from exc
            raise
        payload["query_type"] = source_type if source_type == "mongodb" else "sql"
        return {"query_plan": payload, "provider_used": provider}

    async def _execute_query(self, state: AnalysisState) -> AnalysisState:
        result = await self.connector_service.execute_analysis_query(state["data_source"], state["query_plan"])
        return {"result_rows": result["rows"]}

    async def _summarize_result(self, state: AnalysisState) -> AnalysisState:
        rows = state.get("result_rows", [])
        if not rows:
            return {
                "answer_payload": {
                    "answer": "I could not find matching rows for that question in the connected source.",
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
                max_output_tokens=700,
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
                "Return JSON only. Keys: collection, pipeline, chart_type, notes. "
                "Rules: only use selected collections and fields from the schema context; "
                "never use $out or $merge; add $limit only if needed for previews; "
                "prefer aggregation answers suitable for dashboards and comparisons; "
                "pipeline must be a valid JSON array of single-key stage objects like "
                '{"$match": {"field": "value"}}, {"$group": {"_id": "$field", "count": {"$sum": 1}}}; '
                "every aggregation stage operator must start with '$'."
            )
        dialect = "DuckDB SQL" if source_type in {"csv", "excel", "parquet"} else "PostgreSQL SQL"
        return (
            f"You write safe read-only {dialect} for analytics. "
            "Return JSON only. Keys: query, chart_type, notes. "
            "Rules: only SELECT or WITH queries; never modify data; "
            "quote identifiers when needed; use only tables and columns in schema context; "
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
            "Do not mention JSON, internal prompts, or implementation details."
        )

    def _answer_user_prompt(self, *, question: str, query_plan: dict, rows: list[dict]) -> str:
        limited_rows = self._compact_prompt_rows(rows)
        return (
            f"User question:\n{question}\n\n"
            f"Executed query plan:\n{self._json_for_prompt(query_plan)}\n\n"
            f"Rows:\n{self._json_for_prompt(limited_rows)}"
        )

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
