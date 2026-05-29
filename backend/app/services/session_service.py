import re

from bson import ObjectId

from app.db.mongo import get_database
from app.schemas.session import DataSourceInfoOut, MessageOut, SessionCreateRequest, SessionDetailOut, SessionOut, SourceConfigOut
from app.utils.time import ist_now


class SessionService:
    def __init__(self) -> None:
        self.db = get_database()

    async def create_session(self, user_id: str, payload: SessionCreateRequest) -> SessionOut:
        now = ist_now()
        title = payload.title.strip() if payload.title else "Untitled analysis"
        document = {
            "user_id": user_id,
            "title": title,
            "draft": bool(payload.draft),
            "messages": [],
            "data_source": None,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.db.sessions.insert_one(document)
        document["_id"] = result.inserted_id
        return self._session_out(document)

    async def list_sessions(self, user_id: str) -> list[SessionOut]:
        cursor = self.db.sessions.find({"user_id": user_id, "draft": False}).sort("updated_at", -1)
        sessions = await cursor.to_list(length=100)
        return [self._session_out(session) for session in sessions]

    async def get_session(self, user_id: str, session_id: str) -> SessionDetailOut:
        session = await self._fetch_owned_session(user_id, session_id)
        return self._session_detail_out(session)

    async def delete_session(self, user_id: str, session_id: str) -> None:
        session = await self._fetch_owned_session(user_id, session_id)
        await self.db.sessions.delete_one({"_id": session["_id"]})
        await self.db.chat_vectors.delete_many({"user_id": user_id, "session_id": session_id})

    async def append_messages(
        self,
        user_id: str,
        session_id: str,
        user_message: dict,
        assistant_message: dict,
    ) -> None:
        now = ist_now()
        session = await self._fetch_owned_session(user_id, session_id)
        title = self._resolve_session_title(session, pending_user_content=str(user_message.get("content") or ""))

        await self.db.sessions.update_one(
            {"_id": session["_id"]},
            {
                "$push": {"messages": {"$each": [user_message, assistant_message]}},
                "$set": {
                    "draft": False,
                    "title": title,
                    "updated_at": now,
                },
            },
        )

    async def promote_draft(self, user_id: str, session_id: str, title: str | None = None) -> None:
        session = await self._fetch_owned_session(user_id, session_id)
        await self.db.sessions.update_one(
            {"_id": session["_id"]},
            {
                "$set": {
                    "draft": False,
                    "title": title.strip() if title else self._resolve_session_title(session),
                    "updated_at": ist_now(),
                }
            },
        )

    async def update_data_source(self, user_id: str, session_id: str, data_source: dict | None) -> dict:
        session = await self._fetch_owned_session(user_id, session_id)
        now = ist_now()
        update_fields = {"data_source": data_source, "updated_at": now}
        if data_source:
            data_source.setdefault("last_connected_at", now)
            data_source["updated_at"] = now
            update_fields["last_data_source"] = data_source
        await self.db.sessions.update_one(
            {"_id": session["_id"]},
            {"$set": update_fields},
        )
        session["data_source"] = data_source
        if data_source:
            session["last_data_source"] = data_source
        return session

    async def get_last_data_source(self, user_id: str, session_id: str) -> dict | None:
        session = await self._fetch_owned_session(user_id, session_id)
        return session.get("last_data_source")

    async def get_data_source(self, user_id: str, session_id: str) -> dict | None:
        session = await self._fetch_owned_session(user_id, session_id)
        return session.get("data_source")

    async def get_messages(self, user_id: str, session_id: str) -> list[dict]:
        session = await self._fetch_owned_session(user_id, session_id)
        return list(session.get("messages", []))

    async def disconnect_all_user_sessions(self, user_id: str) -> None:
        """Null out data_source on every session for this user (called on logout)."""
        await self.db.sessions.update_many(
            {"user_id": user_id, "data_source": {"$ne": None}},
            {"$set": {"data_source": None, "updated_at": ist_now()}},
        )

    async def touch_data_source_last_used(self, user_id: str, session_id: str) -> None:
        """Stamp data_source.last_used_at with current time after a successful query."""
        now = ist_now()
        await self.db.sessions.update_one(
            {"_id": ObjectId(session_id), "user_id": user_id, "data_source": {"$ne": None}},
            {"$set": {"data_source.last_used_at": now, "last_data_source.last_used_at": now, "updated_at": now}},
        )

    async def _fetch_owned_session(self, user_id: str, session_id: str) -> dict:
        session = await self.db.sessions.find_one({"_id": ObjectId(session_id), "user_id": user_id})
        if not session:
            raise ValueError("Session not found.")
        return session

    def _message_out(self, message: dict) -> MessageOut:
        return MessageOut(
            role=message["role"],
            content=message["content"],
            viz_data=message.get("viz_data"),
            created_at=message.get("created_at"),
        )

    def _data_source_info_out(self, source: dict | None) -> DataSourceInfoOut | None:
        """Build a lightweight session-card summary from an embedded data_source dict."""
        if not source:
            return None
        source_type = source.get("type", "")
        # Prefer database_name; fall back to file_name
        display_name = (
            source.get("database_name")
            or source.get("file_name")
            or source_type
        )
        return DataSourceInfoOut(
            type=source_type,
            display_name=str(display_name),
            masked_uri=source.get("connection_uri_masked"),
            last_used_at=source.get("last_used_at"),
            last_connected_at=source.get("last_connected_at") or source.get("updated_at") or source.get("created_at"),
        )

    def _source_out(self, source: dict | None) -> SourceConfigOut | None:
        if not source:
            return None
        return SourceConfigOut(
            type=source["type"],
            file_name=source.get("file_name"),
            database_name=source.get("database_name"),
            connection_uri=source.get("connection_uri_masked"),
            selected_tables=source.get("selected_tables", []),
            database_description=source.get("database_description"),
            table_descriptions=source.get("table_descriptions", {}),
            field_descriptions=source.get("field_descriptions", {}),
        )

    def _session_out(self, session: dict) -> SessionOut:
        return SessionOut(
            id=str(session["_id"]),
            title=self._resolve_session_title(session),
            draft=bool(session.get("draft")),
            created_at=session.get("created_at"),
            updated_at=session.get("updated_at"),
            data_source_info=self._data_source_info_out(session.get("data_source")),
            last_data_source_info=self._data_source_info_out(session.get("last_data_source")),
        )

    def _session_detail_out(self, session: dict) -> SessionDetailOut:
        base = self._session_out(session)
        return SessionDetailOut(
            **base.model_dump(),
            messages=[self._message_out(message) for message in session.get("messages", [])],
            data_source=self._source_out(session.get("data_source")),
        )

    def _resolve_session_title(self, session: dict, pending_user_content: str | None = None) -> str:
        current_title = str(session.get("title") or "").strip()
        if current_title and not self._is_placeholder_title(current_title):
            return current_title

        if pending_user_content:
            pending_title = self._title_from_text(pending_user_content)
            if pending_title:
                return pending_title

        for message in session.get("messages", []):
            if message.get("role") != "user":
                continue
            message_title = self._title_from_text(str(message.get("content") or ""))
            if message_title:
                return message_title

        return "Untitled analysis"

    def _is_placeholder_title(self, title: str) -> bool:
        return title.strip().lower() in {"", "untitled analysis", "untitled_analysis", "new conversation"}

    def _title_from_text(self, text: str) -> str | None:
        normalized = " ".join(text.split())
        if not normalized:
            return None

        sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0].strip()
        sentence = sentence.rstrip(" .!?")
        if not sentence:
            sentence = normalized[:96].strip()

        if len(sentence) <= 96:
            return sentence

        truncated = sentence[:93].rstrip()
        last_space = truncated.rfind(" ")
        if last_space >= 48:
            truncated = truncated[:last_space]
        return f"{truncated}..."
