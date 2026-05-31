"""
history_service.py — Query history and saved prompts for DataSage users.
Stores every analytical question in MongoDB with metadata, supports favorites.
"""
from __future__ import annotations

from bson import ObjectId

from app.db.mongo import get_database
from app.utils.time import ist_now


class HistoryService:
    """CRUD for per-user query history stored in the `query_history` collection."""

    MAX_HISTORY = 200  # keep last 200 queries per user

    def __init__(self) -> None:
        self.db = get_database()

    async def save_query(
        self,
        *,
        user_id: str,
        session_id: str,
        question: str,
        answer_preview: str = "",
    ) -> str:
        """Persist a query. Returns the inserted document ID."""
        # Truncate answer preview for storage efficiency
        preview = answer_preview.strip()[:300] if answer_preview else ""
        doc = {
            "user_id": user_id,
            "session_id": session_id,
            "question": question.strip(),
            "answer_preview": preview,
            "is_favorite": False,
            "created_at": ist_now(),
        }
        result = await self.db.query_history.insert_one(doc)

        # Prune old records beyond MAX_HISTORY (keep newest)
        count = await self.db.query_history.count_documents(
            {"user_id": user_id, "is_favorite": False}
        )
        if count > self.MAX_HISTORY:
            oldest_cursor = (
                self.db.query_history.find(
                    {"user_id": user_id, "is_favorite": False},
                    {"_id": 1},
                )
                .sort("created_at", 1)
                .limit(count - self.MAX_HISTORY)
            )
            oldest = await oldest_cursor.to_list(length=count - self.MAX_HISTORY)
            if oldest:
                ids_to_delete = [doc["_id"] for doc in oldest]
                await self.db.query_history.delete_many({"_id": {"$in": ids_to_delete}})

        return str(result.inserted_id)

    async def list_recent(self, user_id: str, limit: int = 20) -> list[dict]:
        """Return the most recent `limit` queries for the user."""
        cursor = (
            self.db.query_history.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [self._serialize(doc) for doc in docs]

    async def list_favorites(self, user_id: str) -> list[dict]:
        """Return all favorited queries for the user."""
        cursor = (
            self.db.query_history.find({"user_id": user_id, "is_favorite": True})
            .sort("created_at", -1)
            .limit(50)
        )
        docs = await cursor.to_list(length=50)
        return [self._serialize(doc) for doc in docs]

    async def toggle_favorite(self, user_id: str, query_id: str) -> bool:
        """Toggle favorite status. Returns the new is_favorite value."""
        doc = await self.db.query_history.find_one(
            {"_id": ObjectId(query_id), "user_id": user_id}
        )
        if not doc:
            raise ValueError("Query not found.")
        new_status = not doc.get("is_favorite", False)
        await self.db.query_history.update_one(
            {"_id": ObjectId(query_id)},
            {"$set": {"is_favorite": new_status}},
        )
        return new_status

    async def delete_query(self, user_id: str, query_id: str) -> None:
        """Delete a single query history record."""
        result = await self.db.query_history.delete_one(
            {"_id": ObjectId(query_id), "user_id": user_id}
        )
        if result.deleted_count == 0:
            raise ValueError("Query not found.")

    def _serialize(self, doc: dict) -> dict:
        return {
            "id": str(doc["_id"]),
            "session_id": doc.get("session_id", ""),
            "question": doc.get("question", ""),
            "answer_preview": doc.get("answer_preview", ""),
            "is_favorite": bool(doc.get("is_favorite")),
            "created_at": doc.get("created_at"),
        }
