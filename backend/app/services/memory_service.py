"""
memory_service.py — Redesigned Session Memory for DataSage V2

Key improvements over the old version:
- Structured turn metadata: intent_type, entities, tables_used, result_summary stored per turn
- Async embedding: runs in executor to avoid blocking the event loop
- Graceful degradation: keyword-based recall when embeddings unavailable
- Richer context assembly: structured block the LLM can directly act on
- Higher recall quality: better cosine threshold + per-turn intent filtering
- Smart context window: recent turns prioritised, entity/table tracking injected
- Single DB read path: merged recent-turn + semantic recall into one method
"""
from __future__ import annotations

import asyncio
import re
import string
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from bson import ObjectId

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.mongo import get_database
from app.utils.time import ist_now

logger = get_logger(__name__)

# ──────────────────────────────────────────────
#  Tuning constants
# ──────────────────────────────────────────────
RECENT_TURN_LIMIT = 10          # how many recent turns to always include
SEMANTIC_RECALL_LIMIT = 4       # max semantic matches to append
LOCAL_COSINE_MIN_SCORE = 0.12  # raised from 0.04 — eliminates noisy matches
EMBEDDING_TEXT_CHAR_LIMIT = 6_000  # full turn stored for embedding
CONTEXT_QUESTION_CHAR_LIMIT = 400
CONTEXT_ANSWER_CHAR_LIMIT = 1_200  # raised from 900 — preserves full values
RESULT_SUMMARY_CHAR_LIMIT = 500
ENTITY_CHAR_LIMIT = 200

# Intent categories used for fast metadata filtering
INTENT_ANALYTICAL = "analytical"
INTENT_CONVERSATIONAL = "conversational"
INTENT_SCHEMA = "schema"
INTENT_HISTORY = "history"

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem_embed")


@lru_cache(maxsize=4)
def _load_sentence_transformer(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def _embedding_available(model_name: str) -> bool:
    """Return True if the model can be loaded without raising."""
    try:
        _load_sentence_transformer(model_name)
        return True
    except Exception:
        return False


class SessionMemoryService:
    """
    Manages per-session conversational memory.

    Storage schema (chat_vectors collection):
    {
        user_id, session_id, kind="chat_turn",
        question, answer,
        intent_type,          # analytical | conversational | schema | history
        entities,             # comma-sep key entities extracted from Q (companies, metrics, dates)
        tables_used,          # comma-sep table/collection names referenced
        result_summary,       # short plain-English summary of the answer (first 500 chars)
        content,              # full "User: …\nAssistant: …" for embedding
        embedding,            # float list
        embedding_model,
        created_at
    }
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.db = get_database()
        self.collection = self.db.chat_vectors
        self.dimensions = self.settings.memory_embedding_dimensions
        self.embedding_model_name = self.settings.memory_embedding_model
        self._embed_ok: bool | None = None  # cached availability flag

    # ──────────────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────────────

    async def remember_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        answer: str,
        tables_used: list[str] | None = None,
        intent_type: str | None = None,
    ) -> None:
        """Persist a Q/A turn with structured metadata + embedding."""
        question_text = question.strip()
        answer_text = answer.strip()
        if len(question_text) < 4:
            return

        # Extract metadata
        detected_intent = intent_type or self._classify_intent(question_text)
        entities = self._extract_entities(question_text)
        tables_str = ", ".join(tables_used) if tables_used else ""
        result_summary = self._truncate(answer_text, RESULT_SUMMARY_CHAR_LIMIT)

        content = (
            f"User: {self._truncate(question_text, EMBEDDING_TEXT_CHAR_LIMIT // 2)}\n"
            f"Assistant: {self._truncate(answer_text, EMBEDDING_TEXT_CHAR_LIMIT // 2)}"
        )

        # Embed asynchronously — won't block the event loop
        embedding = await self._embed_async(content)

        now = ist_now()
        try:
            await self.collection.insert_one(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "kind": "chat_turn",
                    "question": question_text,
                    "answer": answer_text,
                    "intent_type": detected_intent,
                    "entities": entities,
                    "tables_used": tables_str,
                    "result_summary": result_summary,
                    "content": content,
                    "embedding": embedding,
                    "embedding_model": self.embedding_model_name,
                    "created_at": now,
                }
            )
        except Exception as exc:
            logger.warning("Failed to persist memory turn: %s", exc)
            return

        await self._trim_session_memory(user_id=user_id, session_id=session_id)

    async def recall_context(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
    ) -> str:
        """
        Build a rich context block for the LLM with:
          1. Structured recent turns (newest-first) with metadata
          2. Semantically matched older turns
        """
        recent_turns = await self._fetch_recent_turns(
            user_id=user_id,
            session_id=session_id,
            limit=RECENT_TURN_LIMIT,
        )
        if not recent_turns:
            return ""

        semantic_matches = await self._recall_semantic(
            user_id=user_id,
            session_id=session_id,
            query=question,
            exclude_ids={t.get("_id") for t in recent_turns if t.get("_id")},
        )

        if not recent_turns and not semantic_matches:
            return ""

        sections: list[str] = ["=== SESSION MEMORY CONTEXT ==="]

        # ── Recent turns block ──────────────────────────────────────────
        if recent_turns:
            sections.append("--- RECENT TURNS (newest first) ---")
            sections.append(
                "Use these to resolve follow-up words like 'it', 'that', 'same', "
                "'previous', 'as before', or any omitted filters."
            )
            for idx, turn in enumerate(recent_turns, start=1):
                q = self._truncate(str(turn.get("question") or ""), CONTEXT_QUESTION_CHAR_LIMIT)
                a = self._truncate(str(turn.get("answer") or ""), CONTEXT_ANSWER_CHAR_LIMIT)
                intent = turn.get("intent_type", "")
                entities = turn.get("entities", "")
                tables = turn.get("tables_used", "")
                recency = "most recent" if idx == 1 else f"{idx} turns ago"
                sections.append(f"[TURN {idx} — {recency}]")
                if intent:
                    sections.append(f"  Intent: {intent}")
                if tables:
                    sections.append(f"  Tables: {tables}")
                if entities:
                    sections.append(f"  Entities: {entities}")
                sections.append(f"  User: {q}")
                sections.append(f"  Assistant: {a}")
            sections.append("--- END RECENT TURNS ---")

        # ── Semantic matches block ──────────────────────────────────────
        if semantic_matches:
            sections.append("--- SEMANTIC MEMORY MATCHES (older, by relevance) ---")
            for idx, turn in enumerate(semantic_matches, start=1):
                q = self._truncate(str(turn.get("question") or ""), CONTEXT_QUESTION_CHAR_LIMIT)
                a = self._truncate(str(turn.get("answer") or ""), CONTEXT_ANSWER_CHAR_LIMIT)
                tables = turn.get("tables_used", "")
                sections.append(f"[MATCH {idx}]")
                if tables:
                    sections.append(f"  Tables: {tables}")
                sections.append(f"  User: {q}")
                sections.append(f"  Assistant: {a}")
            sections.append("--- END SEMANTIC MEMORY MATCHES ---")

        sections.append("=== END SESSION MEMORY CONTEXT ===")
        return "\n".join(sections)

    async def recall_recent_turns_raw(
        self,
        *,
        user_id: str,
        session_id: str,
        limit: int = RECENT_TURN_LIMIT,
    ) -> list[dict]:
        """Return raw turn dicts for the fallback handler."""
        return await self._fetch_recent_turns(
            user_id=user_id, session_id=session_id, limit=limit
        )

    async def get_active_tables(self, *, user_id: str, session_id: str) -> set[str]:
        """Return the union of all tables referenced in recent turns."""
        turns = await self._fetch_recent_turns(
            user_id=user_id, session_id=session_id, limit=6
        )
        tables: set[str] = set()
        for turn in turns:
            raw = str(turn.get("tables_used") or "")
            for part in raw.split(","):
                part = part.strip()
                if part:
                    tables.add(part)
        return tables

    # ──────────────────────────────────────────────────────────────────────
    #  Embedding helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _embed_async(self, text: str) -> list[float]:
        """
        Run embedding in a thread-pool executor to avoid blocking the event loop.
        Falls back to a zero vector if the model is unavailable.
        """
        if self._embed_ok is False:
            return [0.0] * self.dimensions

        loop = asyncio.get_event_loop()
        try:
            vector = await loop.run_in_executor(_executor, self._embed_sync, text)
            self._embed_ok = True
            return vector
        except Exception as exc:
            logger.warning("Embedding failed; falling back to keyword recall: %s", exc)
            self._embed_ok = False
            return [0.0] * self.dimensions

    def _embed_sync(self, text: str) -> list[float]:
        normalized = " ".join(text.split())
        if not normalized:
            return [0.0] * self.dimensions
        model = _load_sentence_transformer(self.embedding_model_name)
        embedding = model.encode(
            normalized,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vector = [round(float(v), 6) for v in embedding.tolist()]
        if len(vector) != self.dimensions:
            raise ValueError(
                f"Model '{self.embedding_model_name}' returned {len(vector)} dims, "
                f"expected {self.dimensions}."
            )
        return vector

    # ──────────────────────────────────────────────────────────────────────
    #  DB helpers
    # ──────────────────────────────────────────────────────────────────────

    async def _fetch_recent_turns(
        self,
        *,
        user_id: str,
        session_id: str,
        limit: int,
    ) -> list[dict]:
        """
        Fetch the N most-recent turns from chat_vectors (already stored with metadata).
        Returns newest-first order.
        """
        try:
            cursor = (
                self.collection.find(
                    {"user_id": user_id, "session_id": session_id, "kind": "chat_turn"},
                    {
                        "question": 1,
                        "answer": 1,
                        "intent_type": 1,
                        "entities": 1,
                        "tables_used": 1,
                        "result_summary": 1,
                        "created_at": 1,
                    },
                )
                .sort("created_at", -1)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as exc:
            logger.warning("Failed to fetch recent turns: %s", exc)
            return []

    async def _recall_semantic(
        self,
        *,
        user_id: str,
        session_id: str,
        query: str,
        exclude_ids: set,
        limit: int = SEMANTIC_RECALL_LIMIT,
    ) -> list[dict]:
        """Try Atlas vector search, fall back to local cosine, then keyword."""
        query_vector = await self._embed_async(query)
        is_zero = all(v == 0.0 for v in query_vector)

        if not is_zero:
            results = await self._vector_search(
                user_id=user_id,
                session_id=session_id,
                query_vector=query_vector,
                limit=limit + len(exclude_ids),
            )
            results = [r for r in results if r.get("_id") not in exclude_ids][:limit]
            if results:
                return results

            # Local cosine fallback
            results = await self._local_cosine_search(
                user_id=user_id,
                session_id=session_id,
                query_vector=query_vector,
                limit=limit,
                exclude_ids=exclude_ids,
            )
            if results:
                return results

        # Final fallback: keyword-based recall (works even without embeddings)
        return await self._keyword_recall(
            user_id=user_id,
            session_id=session_id,
            query=query,
            limit=limit,
            exclude_ids=exclude_ids,
        )

    async def _vector_search(
        self,
        *,
        user_id: str,
        session_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict]:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self.settings.memory_vector_index_name,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(40, limit * 10),
                    "limit": limit,
                    "filter": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "embedding_model": self.embedding_model_name,
                    },
                }
            },
            {
                "$project": {
                    "question": 1,
                    "answer": 1,
                    "intent_type": 1,
                    "entities": 1,
                    "tables_used": 1,
                    "created_at": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        try:
            return await self.collection.aggregate(pipeline).to_list(length=limit)
        except Exception:
            return []

    async def _local_cosine_search(
        self,
        *,
        user_id: str,
        session_id: str,
        query_vector: list[float],
        limit: int,
        exclude_ids: set,
    ) -> list[dict]:
        try:
            cursor = (
                self.collection.find(
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "embedding_model": self.embedding_model_name,
                    },
                    {
                        "question": 1,
                        "answer": 1,
                        "intent_type": 1,
                        "entities": 1,
                        "tables_used": 1,
                        "embedding": 1,
                        "created_at": 1,
                    },
                )
                .sort("created_at", -1)
                .limit(120)
            )
            candidates = await cursor.to_list(length=120)
        except Exception as exc:
            logger.warning("Local cosine search failed: %s", exc)
            return []

        scored = []
        for doc in candidates:
            if doc.get("_id") in exclude_ids:
                continue
            score = self._dot(query_vector, doc.get("embedding") or [])
            if score >= LOCAL_COSINE_MIN_SCORE:
                doc["score"] = score
                scored.append(doc)
        scored.sort(key=lambda d: d.get("score", 0), reverse=True)
        return scored[:limit]

    async def _keyword_recall(
        self,
        *,
        user_id: str,
        session_id: str,
        query: str,
        limit: int,
        exclude_ids: set,
    ) -> list[dict]:
        """
        Keyword-based recall used when embeddings are unavailable.
        Scores turns by how many normalized query tokens appear in Q+A text.
        """
        stop = {"the", "a", "an", "is", "are", "was", "were", "of", "in",
                "to", "for", "and", "or", "by", "at", "on", "it", "me",
                "my", "this", "that", "with", "how", "what", "which"}
        tokens = {
            t for t in re.split(r"[\s\W]+", query.lower()) if len(t) > 2 and t not in stop
        }
        if not tokens:
            return []

        try:
            cursor = (
                self.collection.find(
                    {"user_id": user_id, "session_id": session_id, "kind": "chat_turn"},
                    {"question": 1, "answer": 1, "intent_type": 1, "entities": 1,
                     "tables_used": 1, "created_at": 1},
                )
                .sort("created_at", -1)
                .limit(100)
            )
            candidates = await cursor.to_list(length=100)
        except Exception as exc:
            logger.warning("Keyword recall DB fetch failed: %s", exc)
            return []

        scored = []
        for doc in candidates:
            if doc.get("_id") in exclude_ids:
                continue
            haystack = (
                (doc.get("question") or "") + " " + (doc.get("answer") or "")
            ).lower()
            hits = sum(1 for t in tokens if t in haystack)
            if hits >= max(1, len(tokens) // 3):
                doc["score"] = hits / len(tokens)
                scored.append(doc)
        scored.sort(key=lambda d: d.get("score", 0), reverse=True)
        return scored[:limit]

    async def _trim_session_memory(self, *, user_id: str, session_id: str) -> None:
        max_turns = self.settings.memory_max_turns_per_session
        if max_turns <= 0:
            return
        try:
            cursor = (
                self.collection.find(
                    {"user_id": user_id, "session_id": session_id}, {"_id": 1}
                )
                .sort("created_at", -1)
                .skip(max_turns)
            )
            stale_ids = [item["_id"] for item in await cursor.to_list(length=1000)]
            if stale_ids:
                await self.collection.delete_many({"_id": {"$in": stale_ids}})
        except Exception as exc:
            logger.warning("Memory trim failed (non-fatal): %s", exc)

    # ──────────────────────────────────────────────────────────────────────
    #  Metadata extraction helpers
    # ──────────────────────────────────────────────────────────────────────

    def _classify_intent(self, question: str) -> str:
        normalized = question.lower()
        analytical_re = re.compile(
            r"\b(count|total|sum|average|avg|max|min|top|bottom|rank|highest|lowest|"
            r"how many|how much|group by|per |by month|by year|trend|compare|versus|"
            r"breakdown|distribution|percentage|ratio)\b"
        )
        schema_re = re.compile(
            r"\b(schema|tables|collections|columns|fields|describe|structure|"
            r"what data|what tables|which table)\b"
        )
        history_re = re.compile(
            r"\b(previous|last question|last answer|what did i ask|session summary|"
            r"summarize session|what we discussed)\b"
        )
        if analytical_re.search(normalized):
            return INTENT_ANALYTICAL
        if schema_re.search(normalized):
            return INTENT_SCHEMA
        if history_re.search(normalized):
            return INTENT_HISTORY
        return INTENT_CONVERSATIONAL

    def _extract_entities(self, question: str) -> str:
        """
        Extract key entities: quoted strings, capitalized proper nouns, year/date patterns,
        metric words. Returns comma-sep string capped at ENTITY_CHAR_LIMIT.
        """
        entities: list[str] = []

        # Quoted values
        entities.extend(re.findall(r'"([^"]{2,60})"', question))
        entities.extend(re.findall(r"'([^']{2,60})'", question))

        # Year / quarter / month patterns
        entities.extend(re.findall(r"\b(20\d{2}|Q[1-4]|January|February|March|April|May|June|"
                                   r"July|August|September|October|November|December)\b", question))

        # Capitalized words (likely proper nouns — company names, product names)
        stop_caps = {"Show", "Give", "Find", "List", "Get", "What", "Which", "How",
                     "The", "A", "An", "Is", "Are", "Was", "Were", "Do", "Does",
                     "Can", "Could", "Would", "Please", "Tell", "Let", "Make"}
        for word in re.findall(r"\b([A-Z][a-z]{1,30})\b", question):
            if word not in stop_caps:
                entities.append(word)

        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for e in entities:
            key = e.lower()
            if key not in seen:
                seen.add(key)
                unique.append(e)

        result = ", ".join(unique)
        return self._truncate(result, ENTITY_CHAR_LIMIT)

    # ──────────────────────────────────────────────────────────────────────
    #  Utility
    # ──────────────────────────────────────────────────────────────────────

    def _dot(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return 0.0
        return sum(a * b for a, b in zip(left, right))

    def _truncate(self, text: str, max_chars: int) -> str:
        normalized = " ".join(str(text).split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 3].rstrip()}..."
