from functools import lru_cache
from typing import Any

from bson import ObjectId

from app.core.config import get_settings
from app.db.mongo import get_database
from app.utils.time import ist_now

RECENT_CONTEXT_TURN_LIMIT = 8
LOCAL_COSINE_MIN_SCORE = 0.04
EMBEDDING_ANSWER_CHAR_LIMIT = 4_000
CONTEXT_QUESTION_CHAR_LIMIT = 320
CONTEXT_ANSWER_CHAR_LIMIT = 900


@lru_cache(maxsize=4)
def _load_sentence_transformer(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


class SessionMemoryService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.db = get_database()
        self.collection = self.db.chat_vectors
        self.dimensions = self.settings.memory_embedding_dimensions
        self.embedding_model_name = self.settings.memory_embedding_model

    async def remember_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        answer: str,
    ) -> None:
        question_text = question.strip()
        answer_text = answer.strip()
        embedding_answer = self._truncate(answer_text, EMBEDDING_ANSWER_CHAR_LIMIT)
        content = f"User: {question_text}\nAssistant: {embedding_answer}".strip()
        if len(content) < 24:
            return

        now = ist_now()
        await self.collection.insert_one(
            {
                "user_id": user_id,
                "session_id": session_id,
                "kind": "chat_turn",
                "question": question_text,
                "answer": answer_text,
                "content": content,
                "embedding": self.embed(content),
                "embedding_model": self.embedding_model_name,
                "created_at": now,
            }
        )
        await self._trim_session_memory(user_id=user_id, session_id=session_id)

    async def recall_context(self, *, user_id: str, session_id: str, question: str) -> str:
        recent_context = await self._recent_turn_context(user_id=user_id, session_id=session_id)
        memories = await self.recall(user_id=user_id, session_id=session_id, query=question)

        sections = []
        if recent_context:
            sections.append(recent_context)

        if memories:
            lines = [
                "--- SEMANTIC_MEMORY_MATCHES ---",
                "Order: highest embedding relevance first. These may be older than the recent turns above.",
            ]
            for index, memory in enumerate(memories, start=1):
                question_text = self._truncate(str(memory.get("question") or ""), CONTEXT_QUESTION_CHAR_LIMIT)
                answer_text = self._truncate(str(memory.get("answer") or ""), CONTEXT_ANSWER_CHAR_LIMIT)
                lines.append(f"[MATCH {index}]")
                lines.append(f"User: {question_text}")
                lines.append(f"Assistant: {answer_text}")
            lines.append("--- END SEMANTIC_MEMORY_MATCHES ---")
            sections.append("\n".join(lines))

        if not sections:
            return ""
        return "\n".join(
            [
                "=== SESSION MEMORY CONTEXT ===",
                "Use recent turns before semantic matches when resolving follow-up wording.",
                *sections,
                "=== END SESSION MEMORY CONTEXT ===",
            ]
        )

    async def recall(self, *, user_id: str, session_id: str, query: str) -> list[dict[str, Any]]:
        query_vector = self.embed(query)
        limit = self.settings.memory_recall_limit
        vector_results = await self._recall_with_vector_search(
            user_id=user_id,
            session_id=session_id,
            query_vector=query_vector,
            limit=limit,
        )
        if vector_results:
            return vector_results
        return await self._recall_with_local_cosine(
            user_id=user_id,
            session_id=session_id,
            query_vector=query_vector,
            limit=limit,
        )

    def embed(self, text: str) -> list[float]:
        normalized_text = " ".join(text.split())
        if not normalized_text:
            return [0.0] * self.dimensions

        try:
            model = _load_sentence_transformer(self.embedding_model_name)
        except Exception as exc:
            raise RuntimeError(
                f"Unable to load SentenceTransformer model '{self.embedding_model_name}'. "
                "Install backend requirements and make sure the model is available locally or downloadable from Hugging Face."
            ) from exc
        embedding = model.encode(
            normalized_text,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vector = [round(float(value), 6) for value in embedding.tolist()]
        if len(vector) != self.dimensions:
            raise ValueError(
                f"SentenceTransformer model '{self.embedding_model_name}' returned {len(vector)} dimensions, "
                f"but MEMORY_EMBEDDING_DIMENSIONS is set to {self.dimensions}."
            )
        return vector

    async def _recall_with_vector_search(
        self,
        *,
        user_id: str,
        session_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self.settings.memory_vector_index_name,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(25, limit * 8),
                    "limit": limit,
                    "filter": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "embedding_model": self.embedding_model_name,
                    },
                }
            },
            {"$project": {"question": 1, "answer": 1, "created_at": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]
        try:
            return await self.collection.aggregate(pipeline).to_list(length=limit)
        except Exception:
            return []

    async def _recall_with_local_cosine(
        self,
        *,
        user_id: str,
        session_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        cursor = (
            self.collection.find(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "embedding_model": self.embedding_model_name,
                },
                {"question": 1, "answer": 1, "embedding": 1, "created_at": 1},
            )
            .sort("created_at", -1)
            .limit(80)
        )
        memories = await cursor.to_list(length=80)
        scored = []
        for memory in memories:
            score = self._dot(query_vector, memory.get("embedding") or [])
            if score >= LOCAL_COSINE_MIN_SCORE:
                memory["score"] = score
                scored.append(memory)
        scored.sort(key=lambda item: item.get("score", 0), reverse=True)
        return scored[:limit]

    async def _trim_session_memory(self, *, user_id: str, session_id: str) -> None:
        max_turns = self.settings.memory_max_turns_per_session
        if max_turns <= 0:
            return
        cursor = (
            self.collection.find({"user_id": user_id, "session_id": session_id}, {"_id": 1})
            .sort("created_at", -1)
            .skip(max_turns)
        )
        stale_ids = [item["_id"] for item in await cursor.to_list(length=1000)]
        if stale_ids:
            await self.collection.delete_many({"_id": {"$in": stale_ids}})

    async def _recent_turn_context(self, *, user_id: str, session_id: str) -> str:
        try:
            session_object_id = ObjectId(session_id)
        except Exception:
            return ""

        session = await self.db.sessions.find_one(
            {"_id": session_object_id, "user_id": user_id},
            {"messages": {"$slice": -RECENT_CONTEXT_TURN_LIMIT * 2}},
        )
        if not session:
            return ""

        messages = session.get("messages", [])
        if not messages:
            return ""

        turns: list[tuple[str, str]] = []
        pending_user: str | None = None
        for message in messages:
            role = message.get("role")
            if role == "user":
                content = self._truncate(str(message.get("content") or ""), CONTEXT_QUESTION_CHAR_LIMIT)
                if pending_user:
                    turns.append((pending_user, ""))
                pending_user = content
            elif role == "assistant" and pending_user:
                content = self._truncate(str(message.get("content") or ""), CONTEXT_ANSWER_CHAR_LIMIT)
                turns.append((pending_user, content))
                pending_user = None

        if pending_user:
            turns.append((pending_user, ""))

        if not turns:
            return ""

        selected_turns = list(reversed(turns[-RECENT_CONTEXT_TURN_LIMIT:]))
        lines = [
            "--- RECENT_SESSION_TURNS ---",
            "Order: newest to oldest. [TURN 1] is the most recent completed exchange.",
        ]
        for index, (question_text, answer_text) in enumerate(selected_turns, start=1):
            recency_label = "newest" if index == 1 else f"{index - 1} turn(s) before newest"
            lines.append(f"[TURN {index} - {recency_label}]")
            lines.append(f"User: {question_text}")
            if answer_text:
                lines.append(f"Assistant: {answer_text}")
        lines.append("--- END RECENT_SESSION_TURNS ---")
        return "\n".join(lines)

    def _dot(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return 0.0
        return sum(a * b for a, b in zip(left, right))

    def _truncate(self, text: str, max_chars: int) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 3].rstrip()}..."
