import asyncio
from unittest.mock import patch

import httpx

from app.services.connector_service import ConnectorService


class _FakeGoogleSheetClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def __aenter__(self) -> "_FakeGoogleSheetClient":
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def get(self, url: str) -> httpx.Response:
        self.calls.append(url)
        return self.responses.pop(0)


def _response(status_code: int, content: bytes, content_type: str = "text/csv") -> httpx.Response:
    return httpx.Response(
        status_code,
        content=content,
        headers={"content-type": content_type},
        request=httpx.Request("GET", "https://docs.google.com"),
    )


def test_google_sheet_url_without_gid_uses_default_export_before_gid_zero() -> None:
    service = object.__new__(ConnectorService)

    urls = service._google_sheet_csv_export_urls("sheet123", None)

    assert urls[0] == "https://docs.google.com/spreadsheets/d/sheet123/export?format=csv"
    assert urls[1] == "https://docs.google.com/spreadsheets/d/sheet123/gviz/tq?tqx=out:csv"
    assert urls[2].endswith("gid=0")


def test_google_sheet_url_parser_reads_fragment_gid() -> None:
    service = object.__new__(ConnectorService)

    sheet_id, gid = service._parse_google_sheet_url(
        "https://docs.google.com/spreadsheets/d/sheet123/edit?usp=sharing#gid=987654"
    )

    assert sheet_id == "sheet123"
    assert gid == "987654"


def test_google_sheet_download_falls_back_to_gviz_csv() -> None:
    service = object.__new__(ConnectorService)
    client = _FakeGoogleSheetClient(
        [
            _response(400, b"Bad request", "text/html"),
            _response(200, b"name,value\nA,1\n"),
        ]
    )

    with patch("app.services.connector_service.httpx.AsyncClient", return_value=client):
        content = asyncio.run(service._download_public_google_sheet_csv("sheet123", None))

    assert content == b"name,value\nA,1\n"
    assert client.calls == [
        "https://docs.google.com/spreadsheets/d/sheet123/export?format=csv",
        "https://docs.google.com/spreadsheets/d/sheet123/gviz/tq?tqx=out:csv",
    ]
