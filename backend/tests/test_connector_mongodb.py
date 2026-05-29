import asyncio
from unittest import TestCase
from unittest.mock import patch

from app.services.connector_service import ConnectorService


class _FakeMongoDatabase:
    def __init__(self, collection_names: list[str]) -> None:
        self._collection_names = collection_names

    def command(self, _command: str) -> dict:
        return {"ok": 1}

    def list_collection_names(self) -> list[str]:
        return self._collection_names


class _FakeMongoClient:
    databases = {"business finance": ["transactions"]}

    def __init__(self, *_args, **_kwargs) -> None:
        self.closed = False

    def __getitem__(self, database_name: str) -> _FakeMongoDatabase:
        return _FakeMongoDatabase(self.databases.get(database_name, []))

    def list_database_names(self) -> list[str]:
        return ["admin", *self.databases.keys()]

    def close(self) -> None:
        self.closed = True


class ConnectorMongoDBTests(TestCase):
    def test_mongodb_schema_requires_exact_database_name(self) -> None:
        service = object.__new__(ConnectorService)

        with patch("app.services.connector_service.MongoClient", _FakeMongoClient):
            with self.assertRaises(ValueError) as context:
                asyncio.run(service._build_mongodb_schema("mongodb+srv://example", "business financ", None))

        message = str(context.exception)
        self.assertIn("business financ", message)
        self.assertIn("business finance", message)
