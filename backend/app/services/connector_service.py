import asyncio
import copy
import re
from difflib import get_close_matches
from hashlib import sha256
from pathlib import Path
from typing import Any

import duckdb
from bson import ObjectId
from pymongo import MongoClient
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_text, encrypt_text
from app.db.mongo import get_database
from app.schemas.connector import (
    ConnectDatabaseRequest,
    PreviewRowsResponse,
    SavedSourceOut,
    SchemaContextUpdateRequest,
    SchemaResponse,
)
from app.services.session_service import SessionService
from app.utils.mongo_docs import collection_schema_from_samples, normalize_documents
from app.utils.serialization import normalize_value
from app.utils.tabular import dataframe_preview_fields, dataframe_rows, detect_source_type, load_tabular_source
from app.utils.time import ist_now, to_ist_iso
from app.utils.uri_validation import ConnectionValidationError, ParsedConnection, validate_connection_uri


logger = get_logger(__name__)


class ConnectorService:
    def __init__(self) -> None:
        self.db = get_database()
        self.session_service = SessionService()
        self.settings = get_settings()

    async def list_saved_sources(self, user_id: str) -> list[SavedSourceOut]:
        cursor = self.db.saved_sources.find({"user_id": user_id}).sort("updated_at", -1)
        items = await cursor.to_list(length=100)
        return [
            SavedSourceOut(
                id=str(item["_id"]),
                source_type=item["source_type"],
                display_name=item["display_name"],
                database_name=item.get("database_name"),
                masked_uri=item["masked_uri"],
                updated_at=to_ist_iso(item.get("updated_at")),
            )
            for item in items
        ]

    async def connect_database(self, user_id: str, session_id: str, payload: ConnectDatabaseRequest) -> dict:
        try:
            parsed = validate_connection_uri(payload.type, payload.connection_uri, payload.database_name)
        except ConnectionValidationError as exc:
            raise ValueError(str(exc)) from exc

        schema = await self._build_live_schema(parsed, None)
        database_name = schema.get("database_name") or parsed.database_name
        selected_tables = [table["name"] for table in schema["tables"]]
        data_source = {
            "type": parsed.source_type,
            "database_name": database_name,
            "connection_uri_encrypted": encrypt_text(parsed.normalized_uri),
            "connection_uri_masked": parsed.masked_uri,
            "file_name": None,
            "file_path": None,
            "selected_tables": selected_tables,
            "database_description": None,
            "table_descriptions": {},
            "field_descriptions": {},
            "schema_cache": schema,
            "saved_source_id": None,
            "created_at": ist_now(),
            "updated_at": ist_now(),
        }

        saved_source_id = None
        if payload.save_to_library:
            saved_source_id = await self._upsert_saved_source(user_id, parsed)
            await self.db.saved_sources.update_one(
                {"_id": ObjectId(saved_source_id)},
                {"$set": {"database_name": database_name, "display_name": database_name}},
            )
            data_source["saved_source_id"] = saved_source_id

        await self.session_service.update_data_source(user_id, session_id, data_source)
        logger.info("Connected %s source for user %s session %s", parsed.source_type, user_id, session_id)
        return {
            "source_type": parsed.source_type,
            "database_name": database_name,
            "connection_uri": parsed.masked_uri,
            "saved_source_id": saved_source_id,
        }

    async def connect_saved_source(self, user_id: str, session_id: str, saved_source_id: str) -> dict:
        source = await self.db.saved_sources.find_one({"_id": ObjectId(saved_source_id), "user_id": user_id})
        if not source:
            raise ValueError("Saved source not found.")

        parsed = ParsedConnection(
            source_type=source["source_type"],
            normalized_uri=decrypt_text(source["encrypted_uri"]),
            masked_uri=source["masked_uri"],
            database_name=source["database_name"],
            host=source["host"],
            display_name=source["display_name"],
        )
        schema = await self._build_live_schema(parsed, None)
        database_name = schema.get("database_name") or parsed.database_name
        selected_tables = [table["name"] for table in schema["tables"]]
        data_source = {
            "type": parsed.source_type,
            "database_name": database_name,
            "connection_uri_encrypted": source["encrypted_uri"],
            "connection_uri_masked": parsed.masked_uri,
            "file_name": None,
            "file_path": None,
            "selected_tables": selected_tables,
            "database_description": None,
            "table_descriptions": {},
            "field_descriptions": {},
            "schema_cache": schema,
            "saved_source_id": saved_source_id,
            "created_at": ist_now(),
            "updated_at": ist_now(),
        }
        await self.session_service.update_data_source(user_id, session_id, data_source)
        await self.db.saved_sources.update_one(
            {"_id": source["_id"]},
            {
                "$set": {
                    "database_name": database_name,
                    "display_name": database_name,
                    "updated_at": ist_now(),
                    "last_connected_at": ist_now(),
                }
            },
        )
        return {
            "source_type": parsed.source_type,
            "database_name": database_name,
            "connection_uri": parsed.masked_uri,
            "saved_source_id": saved_source_id,
        }

    async def upload_file(self, user_id: str, session_id: str, file_name: str, file_bytes: bytes) -> dict:
        if len(file_bytes) > self.settings.max_upload_size_mb * 1024 * 1024:
            raise ValueError(f"File exceeds {self.settings.max_upload_size_mb} MB limit.")

        original_path = Path(file_name)
        source_type = detect_source_type(original_path)
        safe_name = f"{user_id}_{str(ObjectId())}_{original_path.name}"
        target_path = self.settings.upload_path / safe_name
        target_path.write_bytes(file_bytes)

        schema = await self._build_file_schema(target_path, display_file_name=original_path.name)
        data_source = {
            "type": source_type,
            "database_name": None,
            "connection_uri_encrypted": None,
            "connection_uri_masked": None,
            "file_name": original_path.name,
            "file_path": str(target_path),
            "selected_tables": [table["name"] for table in schema["tables"]],
            "database_description": None,
            "table_descriptions": {},
            "field_descriptions": {},
            "schema_cache": schema,
            "saved_source_id": None,
            "created_at": ist_now(),
            "updated_at": ist_now(),
        }
        await self.session_service.update_data_source(user_id, session_id, data_source)
        return {"source_type": source_type, "file_name": original_path.name}

    async def get_schema(self, user_id: str, session_id: str) -> SchemaResponse:
        data_source = await self.session_service.get_data_source(user_id, session_id)
        if not data_source:
            raise ValueError("No data source connected to this session.")

        cached_schema = data_source.get("schema_cache")
        if cached_schema and cached_schema.get("tables"):
            schema = self._apply_context(copy.deepcopy(cached_schema), data_source)
            if schema.get("database_name") and data_source.get("saved_source_id"):
                await self.db.saved_sources.update_one(
                    {"_id": ObjectId(data_source["saved_source_id"])},
                    {"$set": {"database_name": schema["database_name"], "display_name": schema["database_name"]}},
                )
            return SchemaResponse(**schema)

        source_type = data_source["type"]
        if source_type in {"mongodb", "postgresql"}:
            parsed = ParsedConnection(
                source_type=source_type,
                normalized_uri=decrypt_text(data_source["connection_uri_encrypted"]),
                masked_uri=data_source["connection_uri_masked"],
                database_name=data_source["database_name"],
                host="",
                display_name=data_source.get("database_name") or "source",
            )
            schema = await self._build_live_schema(parsed, data_source)
        else:
            file_path = Path(data_source["file_path"])
            schema = await self._build_file_schema(file_path, data_source, display_file_name=data_source.get("file_name"))

        data_source["schema_cache"] = schema
        if schema.get("database_name"):
            data_source["database_name"] = schema["database_name"]
            if data_source.get("saved_source_id"):
                await self.db.saved_sources.update_one(
                    {"_id": ObjectId(data_source["saved_source_id"])},
                    {"$set": {"database_name": schema["database_name"], "display_name": schema["database_name"]}},
                )
        data_source["updated_at"] = ist_now()
        await self.session_service.update_data_source(user_id, session_id, data_source)
        return SchemaResponse(**schema)

    async def get_preview_rows(self, user_id: str, session_id: str, table_name: str, limit: int) -> PreviewRowsResponse:
        data_source = await self.session_service.get_data_source(user_id, session_id)
        if not data_source:
            raise ValueError("No data source connected to this session.")

        row_limit = max(1, min(limit, self.settings.preview_row_limit))
        source_type = data_source["type"]
        if source_type == "mongodb":
            rows = await self._fetch_mongodb_rows(
                decrypt_text(data_source["connection_uri_encrypted"]),
                data_source["database_name"],
                table_name,
                row_limit,
            )
        elif source_type == "postgresql":
            rows = await self._fetch_postgres_rows(
                decrypt_text(data_source["connection_uri_encrypted"]),
                table_name,
                row_limit,
            )
        else:
            rows = await self._fetch_file_rows(Path(data_source["file_path"]), table_name, row_limit, data_source)
        return PreviewRowsResponse(table_name=table_name, rows=rows)

    async def update_schema_context(
        self,
        user_id: str,
        session_id: str,
        payload: SchemaContextUpdateRequest,
    ) -> SchemaResponse:
        data_source = await self.session_service.get_data_source(user_id, session_id)
        if not data_source:
            raise ValueError("No data source connected to this session.")

        data_source["selected_tables"] = payload.selected_tables
        data_source["database_description"] = payload.database_description
        data_source["table_descriptions"] = payload.table_descriptions
        data_source["field_descriptions"] = payload.field_descriptions
        data_source["updated_at"] = ist_now()

        await self.session_service.update_data_source(user_id, session_id, data_source)
        return await self.get_schema(user_id, session_id)

    async def disconnect(self, user_id: str, session_id: str) -> None:
        await self.session_service.update_data_source(user_id, session_id, None)

    async def _upsert_saved_source(self, user_id: str, parsed: ParsedConnection) -> str:
        fingerprint = sha256(f"{parsed.source_type}:{parsed.normalized_uri}".encode("utf-8")).hexdigest()
        now = ist_now()
        update = {
            "$set": {
                "user_id": user_id,
                "source_type": parsed.source_type,
                "display_name": parsed.display_name,
                "database_name": parsed.database_name,
                "masked_uri": parsed.masked_uri,
                "encrypted_uri": encrypt_text(parsed.normalized_uri),
                "uri_fingerprint": fingerprint,
                "host": parsed.host,
                "updated_at": now,
                "last_connected_at": now,
            },
            "$setOnInsert": {"created_at": now},
        }
        result = await self.db.saved_sources.find_one_and_update(
            {"user_id": user_id, "uri_fingerprint": fingerprint},
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result:
            return str(result["_id"])

        created = await self.db.saved_sources.find_one({"user_id": user_id, "uri_fingerprint": fingerprint})
        if not created:
            raise ValueError("Could not save source metadata.")
        return str(created["_id"])

    def _apply_context(self, schema: dict, data_source: dict | None) -> dict:
        selected_tables = set((data_source or {}).get("selected_tables", []))
        table_descriptions = (data_source or {}).get("table_descriptions", {})
        field_descriptions = (data_source or {}).get("field_descriptions", {})
        database_description = (data_source or {}).get("database_description")

        tables = []
        for table in schema["tables"]:
            table_name = table["name"]
            table_fields = []
            for field in table.get("fields", []):
                table_fields.append(
                    {
                        **field,
                        "description": field_descriptions.get(table_name, {}).get(field["name"]),
                    }
                )
            tables.append(
                {
                    **table,
                    "selected": table_name in selected_tables if selected_tables else True,
                    "description": table_descriptions.get(table_name),
                    "fields": table_fields,
                }
            )

        schema["tables"] = tables
        schema["database_description"] = database_description
        schema["selected_table_count"] = sum(1 for table in tables if table.get("selected"))
        return schema

    async def _build_live_schema(self, parsed: ParsedConnection, data_source: dict | None) -> dict:
        if parsed.source_type == "mongodb":
            schema = await self._build_mongodb_schema(parsed.normalized_uri, parsed.database_name, data_source)
        elif parsed.source_type == "postgresql":
            schema = await self._build_postgres_schema(parsed.normalized_uri, parsed.database_name, data_source)
        else:
            raise ValueError("Unsupported data source type.")
        return self._apply_context(schema, data_source)

    async def _build_file_schema(
        self,
        file_path: Path,
        data_source: dict | None = None,
        display_file_name: str | None = None,
    ) -> dict:
        def _read():
            tables = []
            for table_name, dataframe in load_tabular_source(file_path, display_file_name).items():
                field_map = (data_source or {}).get("field_descriptions", {}).get(table_name, {})
                tables.append(
                    {
                        "name": table_name,
                        "row_count": int(len(dataframe.index)),
                        "fields": dataframe_preview_fields(dataframe, field_map),
                    }
                )
            return {
                "source_type": detect_source_type(file_path),
                "database_name": file_path.name,
                "database_description": None,
                "selected_table_count": len(tables),
                "tables": tables,
            }

        schema = await asyncio.to_thread(_read)
        return self._apply_context(schema, data_source)

    async def _build_mongodb_schema(self, connection_uri: str, database_name: str, data_source: dict | None) -> dict:
        field_descriptions = (data_source or {}).get("field_descriptions", {})

        def _read():
            client = MongoClient(connection_uri, serverSelectionTimeoutMS=10_000)
            try:
                database = client[database_name]
                database.command("ping")
                collection_names = database.list_collection_names()
                if not collection_names:
                    available_databases = [
                        name
                        for name in client.list_database_names()
                        if name not in {"admin", "config", "local"}
                    ]
                    suggested = get_close_matches(database_name, available_databases, n=1, cutoff=0.82)
                    if suggested:
                        database_name_to_use = suggested[0]
                        logger.info(
                            "Using close MongoDB database name match '%s' for requested '%s'.",
                            database_name_to_use,
                            database_name,
                        )
                        database = client[database_name_to_use]
                        collection_names = database.list_collection_names()
                    else:
                        database_name_to_use = database_name
                else:
                    database_name_to_use = database_name

                if not collection_names:
                    available_text = ", ".join(available_databases[:10]) if "available_databases" in locals() else ""
                    hint = f" Available databases: {available_text}." if available_text else ""
                    raise ValueError(f"MongoDB database '{database_name}' has no collections or was not found.{hint}")

                tables = []
                for collection_name in collection_names:
                    collection = database[collection_name]
                    sample_documents = list(collection.find({}, limit=5))
                    row_count = collection.estimated_document_count()
                    tables.append(
                        {
                            "name": collection_name,
                            "row_count": int(row_count),
                            "fields": collection_schema_from_samples(
                                sample_documents,
                                field_descriptions=field_descriptions.get(collection_name, {}),
                            ),
                        }
                    )
                return {
                    "source_type": "mongodb",
                    "database_name": database_name_to_use,
                    "database_description": None,
                    "selected_table_count": len(tables),
                    "tables": tables,
                }
            finally:
                client.close()

        try:
            return await asyncio.to_thread(_read)
        except PyMongoError as exc:
            raise ValueError(self._mongodb_error_message(exc)) from exc

    async def _build_postgres_schema(self, connection_uri: str, database_name: str, data_source: dict | None) -> dict:
        field_descriptions = (data_source or {}).get("field_descriptions", {})

        def _read():
            engine = create_engine(connection_uri, pool_pre_ping=True)
            try:
                inspector = inspect(engine)
                tables = []
                for table_name in inspector.get_table_names(schema="public"):
                    columns = inspector.get_columns(table_name, schema="public")
                    fields = []
                    for column in columns:
                        column_name = str(column["name"])
                        fields.append(
                            {
                                "name": column_name,
                                "type": str(column.get("type")),
                                "nullable": bool(column.get("nullable", True)),
                                "samples": [],
                                "description": field_descriptions.get(table_name, {}).get(column_name),
                            }
                        )
                    with engine.connect() as connection:
                        row_count = connection.execute(text(f'SELECT COUNT(*) FROM public."{table_name}"')).scalar() or 0
                        sample_rows = connection.execute(text(f'SELECT * FROM public."{table_name}" LIMIT 3')).mappings().all()
                    for field in fields:
                        field["samples"] = [
                            str(normalize_value(row.get(field["name"])))
                            for row in sample_rows
                            if row.get(field["name"]) is not None
                        ][:3]
                    tables.append({"name": table_name, "row_count": int(row_count), "fields": fields})

                return {
                    "source_type": "postgresql",
                    "database_name": database_name,
                    "database_description": None,
                    "selected_table_count": len(tables),
                    "tables": tables,
                }
            finally:
                engine.dispose()

        try:
            return await asyncio.to_thread(_read)
        except PyMongoError as exc:
            raise ValueError(self._mongodb_error_message(exc)) from exc

    async def _fetch_file_rows(
        self,
        file_path: Path,
        table_name: str,
        limit: int,
        data_source: dict | None = None,
    ) -> list[dict]:
        def _read():
            tables = self._load_file_tables_for_query(file_path, data_source)
            if table_name not in tables:
                raise ValueError("Table not found in uploaded file.")
            return dataframe_rows(tables[table_name], limit)

        return await asyncio.to_thread(_read)

    async def _fetch_mongodb_rows(
        self,
        connection_uri: str,
        database_name: str,
        collection_name: str,
        limit: int,
    ) -> list[dict]:
        def _read():
            client = MongoClient(connection_uri, serverSelectionTimeoutMS=10_000)
            try:
                collection = client[database_name][collection_name]
                documents = list(collection.find({}, limit=limit))
                return normalize_documents(documents)
            finally:
                client.close()

        return await asyncio.to_thread(_read)

    async def _fetch_postgres_rows(self, connection_uri: str, table_name: str, limit: int) -> list[dict]:
        def _read():
            engine = create_engine(connection_uri, pool_pre_ping=True)
            try:
                query = text(f'SELECT * FROM public."{table_name}" LIMIT :limit')
                with engine.connect() as connection:
                    rows = connection.execute(query, {"limit": limit}).mappings().all()
                return [{key: normalize_value(value) for key, value in row.items()} for row in rows]
            finally:
                engine.dispose()

        return await asyncio.to_thread(_read)

    async def execute_analysis_query(self, data_source: dict, compiled_query: dict, row_limit: int | None = None) -> dict[str, Any]:
        row_limit = row_limit or self.settings.max_chat_result_rows
        source_type = data_source["type"]
        if source_type == "mongodb":
            rows = await self._run_mongodb_pipeline(data_source, compiled_query, row_limit)
        elif source_type == "postgresql":
            rows = await self._run_postgres_query(data_source, compiled_query["query"], row_limit)
        else:
            rows = await self._run_file_query(data_source, compiled_query["query"], row_limit)
        return {"rows": rows}

    async def sample_data_source(
        self,
        data_source: dict,
        *,
        max_tables: int = 3,
        row_limit: int = 100,
    ) -> dict[str, list[dict]]:
        schema = data_source.get("schema_cache", {})
        selected = set(data_source.get("selected_tables", []))
        table_names = [
            str(table.get("name"))
            for table in schema.get("tables", [])
            if table.get("name") and (not selected or table.get("name") in selected)
        ][:max_tables]

        samples: dict[str, list[dict]] = {}
        source_type = data_source["type"]
        for table_name in table_names:
            if source_type == "mongodb":
                rows = await self._fetch_mongodb_rows(
                    decrypt_text(data_source["connection_uri_encrypted"]),
                    data_source["database_name"],
                    table_name,
                    row_limit,
                )
            elif source_type == "postgresql":
                rows = await self._fetch_postgres_rows(
                    decrypt_text(data_source["connection_uri_encrypted"]),
                    table_name,
                    row_limit,
                )
            else:
                rows = await self._fetch_file_rows(Path(data_source["file_path"]), table_name, row_limit, data_source)
            samples[table_name] = rows
        return samples

    async def _run_postgres_query(self, data_source: dict, sql_query: str, row_limit: int) -> list[dict]:
        query = self._validate_sql(sql_query)
        connection_uri = decrypt_text(data_source["connection_uri_encrypted"])

        def _run():
            engine = create_engine(connection_uri, pool_pre_ping=True)
            try:
                with engine.connect() as connection:
                    rows = connection.execute(text(query)).mappings().all()
                return [{key: normalize_value(value) for key, value in row.items()} for row in rows[:row_limit]]
            finally:
                engine.dispose()

        return await asyncio.to_thread(_run)

    async def _run_file_query(self, data_source: dict, sql_query: str, row_limit: int) -> list[dict]:
        query = self._prepare_file_sql_query(data_source, self._validate_sql(sql_query))
        file_path = Path(data_source["file_path"])

        def _run():
            connection = duckdb.connect(database=":memory:")
            try:
                for table_name, dataframe in self._load_file_tables_for_query(file_path, data_source).items():
                    connection.register(table_name, dataframe)
                rows = connection.execute(query).fetch_df().head(row_limit)
                return dataframe_rows(rows, row_limit)
            finally:
                connection.close()

        return await asyncio.to_thread(_run)

    async def _run_mongodb_pipeline(self, data_source: dict, compiled_query: dict, row_limit: int) -> list[dict]:
        collection_name = compiled_query.get("collection")
        pipeline = compiled_query.get("pipeline")
        if not collection_name:
            collection_name = self._infer_mongodb_collection(data_source)
            if collection_name:
                compiled_query["collection"] = collection_name
        if not collection_name:
            raise ValueError("MongoDB analysis request is missing a collection.")
        if pipeline is None:
            pipeline = []
        if not isinstance(pipeline, list):
            raise ValueError("MongoDB analysis pipeline must be a JSON array.")

        pipeline = self._normalize_mongodb_pipeline(pipeline, row_limit, data_source, collection_name)
        compiled_query["pipeline"] = pipeline

        connection_uri = decrypt_text(data_source["connection_uri_encrypted"])
        database_name = data_source["database_name"]

        def _run():
            client = MongoClient(connection_uri, serverSelectionTimeoutMS=10_000)
            try:
                collection = client[database_name][collection_name]
                rows = list(collection.aggregate(pipeline, allowDiskUse=False))
                return normalize_documents(rows[:row_limit])
            finally:
                client.close()

        try:
            return await asyncio.to_thread(_run)
        except PyMongoError as exc:
            raise ValueError(self._mongodb_error_message(exc)) from exc

    def _normalize_mongodb_pipeline(
        self,
        pipeline: list,
        row_limit: int,
        data_source: dict | None = None,
        collection_name: str | None = None,
    ) -> list[dict]:
        normalized: list[dict] = []
        forbidden_stages = {"$out", "$merge"}
        stage_operator_names = {
            "addFields",
            "bucket",
            "bucketAuto",
            "count",
            "densify",
            "documents",
            "facet",
            "fill",
            "geoNear",
            "graphLookup",
            "group",
            "limit",
            "lookup",
            "match",
            "project",
            "redact",
            "replaceRoot",
            "replaceWith",
            "sample",
            "search",
            "searchMeta",
            "set",
            "setWindowFields",
            "skip",
            "sort",
            "sortByCount",
            "unset",
            "unwind",
            "vectorSearch",
        }

        self._validate_mongodb_collection(data_source, collection_name)

        for stage in pipeline:
            if not isinstance(stage, dict):
                raise ValueError("MongoDB aggregation stages must be JSON objects.")
            if not stage:
                continue

            stage_items = []
            for raw_key, value in stage.items():
                key = str(raw_key)
                if not key.startswith("$"):
                    if key in stage_operator_names:
                        logger.warning("Repairing MongoDB aggregation stage operator missing '$': %s", key)
                        key = f"${key}"
                    else:
                        raise ValueError("MongoDB aggregation stage operators must start with '$'.")
                stage_items.append((key, value))

            if len(stage_items) > 1:
                logger.warning(
                    "Splitting MongoDB aggregation stage with multiple operators: %s",
                    ", ".join(str(key) for key, _ in stage_items),
                )

            for key, value in stage_items:
                if key in forbidden_stages:
                    raise ValueError("MongoDB write stages are not allowed.")
                if key == "$limit":
                    try:
                        value = max(1, min(int(value), row_limit))
                    except (TypeError, ValueError) as exc:
                        raise ValueError("MongoDB $limit stage must be a positive integer.") from exc
                normalized.append({key: self._sanitize_mongodb_stage(key, value)})

        if not any("$limit" in stage for stage in normalized):
            normalized.append({"$limit": row_limit})
        self._validate_mongodb_pipeline_fields(normalized, data_source, collection_name)
        return normalized

    def _validate_mongodb_collection(self, data_source: dict | None, collection_name: str | None) -> None:
        if not data_source or not collection_name:
            return
        known = {
            str(table.get("name"))
            for table in data_source.get("schema_cache", {}).get("tables", [])
            if table.get("name")
        }
        selected = {str(name) for name in data_source.get("selected_tables", []) if name}
        if known and collection_name not in known:
            raise ValueError(f"MongoDB collection '{collection_name}' is not present in the connected schema.")
        if selected and collection_name not in selected:
            raise ValueError(f"MongoDB collection '{collection_name}' is not selected for analysis.")

    def _sanitize_mongodb_stage(self, stage_operator: str, value: Any) -> Any:
        if stage_operator == "$sort":
            if not isinstance(value, dict):
                raise ValueError("MongoDB $sort stage must be an object.")
            sanitized_sort = {}
            for field, direction in value.items():
                if not isinstance(field, str) or field.startswith("$"):
                    raise ValueError("MongoDB $sort fields must be plain field names.")
                try:
                    sort_direction = int(direction)
                except (TypeError, ValueError) as exc:
                    raise ValueError("MongoDB $sort directions must be 1 or -1.") from exc
                if sort_direction not in {-1, 1}:
                    raise ValueError("MongoDB $sort directions must be 1 or -1.")
                sanitized_sort[field] = sort_direction
            return sanitized_sort
        if stage_operator == "$unwind":
            return self._sanitize_mongodb_unwind_stage(value)
        if stage_operator in {"$match", "$limit", "$skip", "$sample", "$lookup", "$unset"}:
            return value
        return self._sanitize_mongodb_expression(value)

    def _sanitize_mongodb_unwind_stage(self, value: Any) -> Any:
        if isinstance(value, str):
            if not value.startswith("$") or value in {"$", "$$"}:
                raise ValueError("MongoDB $unwind path must be a field reference like '$items'.")
            return value
        if not isinstance(value, dict):
            raise ValueError("MongoDB $unwind stage must be a field path string or an options object.")

        repaired: dict[str, Any] = {}
        allowed_options = {"path", "includeArrayIndex", "preserveNullAndEmptyArrays"}
        option_aliases = {
            "$path": "path",
            "$includeArrayIndex": "includeArrayIndex",
            "$preserveNullAndEmptyArrays": "preserveNullAndEmptyArrays",
        }
        for raw_key, raw_value in value.items():
            key = option_aliases.get(str(raw_key), str(raw_key))
            if key not in allowed_options:
                raise ValueError(f"MongoDB $unwind option '{raw_key}' is not supported.")
            if key == "path":
                if not isinstance(raw_value, str) or not raw_value.startswith("$") or raw_value in {"$", "$$"}:
                    raise ValueError("MongoDB $unwind path must be a field reference like '$items'.")
                repaired[key] = raw_value
            elif key == "includeArrayIndex":
                if not isinstance(raw_value, str) or raw_value.startswith("$"):
                    raise ValueError("MongoDB $unwind includeArrayIndex must be a plain field name.")
                repaired[key] = raw_value
            else:
                repaired[key] = bool(raw_value)

        if "path" not in repaired:
            raise ValueError("MongoDB $unwind options must include a path.")
        return repaired

    def _sanitize_mongodb_expression(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._sanitize_mongodb_expression(item) for item in value]
        if not isinstance(value, dict):
            return value

        if len(value) == 1:
            raw_key, raw_value = next(iter(value.items()))
            key = str(raw_key)
            item = self._sanitize_mongodb_expression(raw_value)
            if key == "$dateFromString" and isinstance(item, dict):
                return {key: self._sanitize_mongodb_date_from_string(item)}
            if key == "$cond":
                return {key: self._sanitize_mongodb_cond_expression(item)}
            if key == "$concat" and isinstance(item, list):
                return {key: [self._mongodb_string_expression(operand) for operand in item]}
            if key == "$divide" and isinstance(item, list) and len(item) == 2:
                numerator = self._mongodb_numeric_expression(item[0])
                denominator = self._mongodb_numeric_expression(item[1])
                return {
                    "$cond": [
                        {"$in": [denominator, [0, None]]},
                        None,
                        {"$divide": [numerator, denominator]},
                    ]
                }
            if key in {"$sum", "$avg"}:
                return {key: self._mongodb_numeric_expression(item)}
            if key in {"$add", "$multiply", "$subtract"} and isinstance(item, list):
                return {key: [self._mongodb_numeric_expression(operand) for operand in item]}

        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            item = self._sanitize_mongodb_expression(raw_value)
            if key == "$dateFromString" and isinstance(item, dict):
                item = self._sanitize_mongodb_date_from_string(item)
            elif key == "$cond":
                item = self._sanitize_mongodb_cond_expression(item)
            elif key == "$concat" and isinstance(item, list):
                item = [self._mongodb_string_expression(operand) for operand in item]
            elif key in {"$sum", "$avg"}:
                item = self._mongodb_numeric_expression(item)
            elif key in {"$add", "$multiply", "$subtract"} and isinstance(item, list):
                item = [self._mongodb_numeric_expression(operand) for operand in item]
            sanitized[key] = item
        return sanitized

    def _sanitize_mongodb_date_from_string(self, value: dict[str, Any]) -> dict[str, Any]:
        item = dict(value)
        if "dateFormat" in item and "format" not in item:
            logger.warning("Repairing MongoDB $dateFromString option 'dateFormat' to 'format'.")
            item["format"] = item.pop("dateFormat")

        if item.get("format") is None or item.get("format") == "":
            item.pop("format", None)

        date_string = item.get("dateString")
        if isinstance(date_string, str):
            month_match = re.fullmatch(r"(\d{4})-(\d{1,2})", date_string.strip())
            year_match = re.fullmatch(r"(\d{4})", date_string.strip())
            if month_match:
                year, month = month_match.groups()
                item["dateString"] = f"{year}-{int(month):02d}-01"
            elif year_match:
                item["dateString"] = f"{year_match.group(1)}-01-01"
            elif date_string.startswith("$"):
                date_string_expr = self._mongodb_string_expression(date_string)
                item["dateString"] = {
                    "$cond": [
                        {"$regexMatch": {"input": date_string_expr, "regex": r"^\d{4}-\d{1,2}$"}},
                        {"$concat": [date_string_expr, "-01"]},
                        date_string_expr,
                    ]
                }
        item.setdefault("onError", None)
        item.setdefault("onNull", None)
        return item

    def _sanitize_mongodb_cond_expression(self, value: Any) -> Any:
        if isinstance(value, list):
            if len(value) != 3:
                raise ValueError("MongoDB $cond expressions must contain exactly 3 arguments.")
            return value
        if isinstance(value, dict):
            missing = {"if", "then", "else"} - set(value)
            if missing:
                raise ValueError("MongoDB $cond expressions must include if, then, and else.")
            return value
        raise ValueError("MongoDB $cond expression must be an array or object.")

    def _mongodb_numeric_expression(self, value: Any) -> Any:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.startswith("$"):
            return {"$convert": {"input": value, "to": "double", "onError": None, "onNull": None}}
        if isinstance(value, dict):
            sanitized = self._sanitize_mongodb_expression(value)
            # If the expression is already a $convert to double, don't double-wrap
            if "$convert" in sanitized and sanitized.get("$convert", {}).get("to") == "double":
                return sanitized
            return {"$convert": {"input": sanitized, "to": "double", "onError": None, "onNull": None}}
        if isinstance(value, list):
            # Lists in aggregation accumulator expressions (e.g., $sum [expr])
            return [self._mongodb_numeric_expression(item) for item in value]
        return value

    def _mongodb_string_expression(self, value: Any) -> Any:
        if isinstance(value, str) and not value.startswith("$"):
            return value
        if value is None:
            return ""
        return {
            "$convert": {
                "input": self._sanitize_mongodb_expression(value),
                "to": "string",
                "onError": "",
                "onNull": "",
            }
        }

    def _validate_mongodb_pipeline_fields(
        self,
        pipeline: list[dict],
        data_source: dict | None,
        collection_name: str | None,
    ) -> None:
        if not data_source or not collection_name:
            return
        schema_tables = data_source.get("schema_cache", {}).get("tables", [])
        table = next((table for table in schema_tables if table.get("name") == collection_name), None)
        if not table:
            return
        available = {str(field.get("name")).split(".")[0] for field in table.get("fields", []) if field.get("name")}
        available.update({"_id", "id"})
        for stage in pipeline:
            if not stage:
                continue
            operator, value = next(iter(stage.items()))
            refs = self._extract_mongodb_field_refs(value)
            if operator in {"$match", "$sort"} and isinstance(value, dict):
                refs.update(
                    str(key).split(".")[0]
                    for key in value
                    if isinstance(key, str) and key and not key.startswith("$")
                )
            missing = sorted(ref for ref in refs if ref not in available)
            if missing:
                raise ValueError(
                    "MongoDB analysis pipeline references fields not present in the selected collection: "
                    + ", ".join(f"${field}" for field in missing[:5])
                )
            if operator in {"$project", "$addFields", "$set"} and isinstance(value, dict):
                projected = {str(key).split(".")[0] for key in value if isinstance(key, str) and not key.startswith("$")}
                if operator == "$project":
                    available = projected | {"_id"}
                else:
                    available.update(projected)
            elif operator == "$group" and isinstance(value, dict):
                available = {"_id"} | {str(key) for key in value if isinstance(key, str) and key != "_id"}
            elif operator == "$lookup" and isinstance(value, dict) and value.get("as"):
                available.add(str(value["as"]).split(".")[0])
            elif operator == "$unwind":
                path = value.get("path") if isinstance(value, dict) else value
                if isinstance(path, str) and path.startswith("$"):
                    available.add(path.lstrip("$").split(".")[0])
            elif operator in {"$replaceRoot", "$replaceWith"}:
                # After $replaceRoot the available fields change completely;
                # we cannot statically determine them, so allow everything.
                available = None  # type: ignore[assignment]
            if available is None:
                # Once we lose field tracking (e.g. after $replaceRoot), skip further checks
                break

    def _extract_mongodb_field_refs(self, value: Any) -> set[str]:
        refs: set[str] = set()

        def _walk(obj: Any) -> None:
            if isinstance(obj, str) and obj.startswith("$") and not obj.startswith("$$"):
                field = obj.lstrip("$").split(".")[0]
                if field and not field.startswith("$"):
                    refs.add(field)
            elif isinstance(obj, dict):
                for key, nested in obj.items():
                    if key == "$literal":
                        # $literal values are constants, skip entirely
                        continue
                    if key == "$dateFromString" and isinstance(nested, str):
                        # Bare string value for $dateFromString is a literal date, skip
                        continue
                    # For $dateFromString dict values, recurse into the
                    # sub-keys (dateString may be a $field reference)
                    _walk(nested)
            elif isinstance(obj, list):
                for nested in obj:
                    _walk(nested)

        _walk(value)
        return refs

    def _infer_mongodb_collection(self, data_source: dict) -> str | None:
        selected = [str(name) for name in data_source.get("selected_tables", []) if name]
        if len(selected) == 1:
            return selected[0]

        tables = [
            str(table.get("name"))
            for table in data_source.get("schema_cache", {}).get("tables", [])
            if table.get("name")
        ]
        if len(tables) == 1:
            return tables[0]
        return None

    def _mongodb_error_message(self, error: PyMongoError) -> str:
        message = str(error)
        if "ServerSelectionTimeoutError" in error.__class__.__name__ or "No replica set members found" in message:
            return (
                "Could not reach the MongoDB cluster. Check that the connection string is correct, "
                "your current IP address is allowed in MongoDB Atlas, and the cluster is online."
            )
        if "Authentication failed" in message or "auth failed" in message.lower():
            return "MongoDB authentication failed. Check the username, password, and database permissions."
        return f"MongoDB query failed: {message}"

    def _load_file_tables_for_query(self, file_path: Path, data_source: dict | None) -> dict[str, Any]:
        tables = load_tabular_source(file_path, (data_source or {}).get("file_name"))
        if len(tables) != 1:
            return tables

        dataframe = next(iter(tables.values()))
        aliases = dict(tables)
        for table in (data_source or {}).get("schema_cache", {}).get("tables", []):
            table_name = table.get("name")
            if table_name:
                aliases[str(table_name)] = dataframe
        return aliases

    def _prepare_file_sql_query(self, data_source: dict, sql_query: str) -> str:
        query = sql_query
        # Strip PostgreSQL-style public. schema prefix — DuckDB tables are registered directly
        query = re.sub(r'\bpublic\."', '"', query, flags=re.IGNORECASE)
        query = re.sub(r'\bpublic\.(?=[A-Za-z_])', '', query, flags=re.IGNORECASE)
        table_names = {
            str(table.get("name"))
            for table in data_source.get("schema_cache", {}).get("tables", [])
            if table.get("name")
        }
        table_names.update(
            self._load_file_tables_for_query(Path(data_source["file_path"]), data_source).keys()
        )
        for table_name in sorted(table_names, key=len, reverse=True):
            query = self._quote_unquoted_identifier(query, table_name)
        return query

    def _quote_unquoted_identifier(self, query: str, identifier: str) -> str:
        if not identifier or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
            return query

        quoted = '"' + identifier.replace('"', '""') + '"'
        pattern = re.compile(rf'(?<!["A-Za-z0-9_]){re.escape(identifier)}(?!["A-Za-z0-9_])')
        return pattern.sub(quoted, query)

    def _validate_sql(self, sql_query: str) -> str:
        query = sql_query.strip().rstrip(";")
        lowered = query.lower()
        if not lowered.startswith(("select", "with")):
            raise ValueError("Only read-only SQL queries are allowed.")
        # Strip string literals before checking for forbidden keywords
        # to prevent false positives (e.g. WHERE status = 'inserted')
        literals_removed = re.sub(r"'(?:''|[^'])*'", " ", lowered)
        forbidden_keywords = {"insert", "update", "delete", "drop", "alter", "truncate", "create"}
        normalized_words = {
            fragment.strip("(),")
            for fragment in literals_removed.replace("\n", " ").replace("\t", " ").split(" ")
            if fragment.strip("(),")
        }
        if normalized_words.intersection(forbidden_keywords):
            raise ValueError("Unsafe SQL keywords detected.")
        return query
