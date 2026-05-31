from pydantic import BaseModel

from fastapi import APIRouter, File, Query, UploadFile

from app.api.deps import CurrentUser
from app.schemas.connector import ConnectDatabaseRequest, SchemaContextUpdateRequest
from app.services.connector_service import ConnectorService
from app.utils.api import error_response, ok


router = APIRouter(prefix="/connectors", tags=["connectors"])
service = ConnectorService()


class GoogleSheetRequest(BaseModel):
    sheet_url: str


@router.get("/library")
async def list_saved_sources(current_user: CurrentUser):
    items = await service.list_saved_sources(str(current_user["_id"]))
    return ok([item.model_dump() for item in items])


@router.post("/{session_id}/connect")
async def connect_source(session_id: str, payload: ConnectDatabaseRequest, current_user: CurrentUser):
    try:
        result = await service.connect_database(str(current_user["_id"]), session_id, payload)
    except ValueError as exc:
        msg = str(exc)
        if "session not found" in msg.lower():
            return error_response(msg, status_code=404, error_code="SESSION_NOT_FOUND")
        return error_response(msg, status_code=400, error_code="CONNECTOR_ERROR")
    return ok(result, "Source connected.")


@router.post("/{session_id}/connect/saved/{saved_source_id}")
async def connect_saved_source(session_id: str, saved_source_id: str, current_user: CurrentUser):
    try:
        result = await service.connect_saved_source(str(current_user["_id"]), session_id, saved_source_id)
    except ValueError as exc:
        msg = str(exc)
        if "session not found" in msg.lower():
            return error_response(msg, status_code=404, error_code="SESSION_NOT_FOUND")
        return error_response(msg, status_code=400, error_code="CONNECTOR_ERROR")
    return ok(result, "Saved source connected.")


@router.post("/{session_id}/upload")
async def upload_source(session_id: str, current_user: CurrentUser, file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        result = await service.upload_file(str(current_user["_id"]), session_id, file.filename or "upload.csv", file_bytes)
    except ValueError as exc:
        msg = str(exc)
        if "session not found" in msg.lower():
            return error_response(msg, status_code=404, error_code="SESSION_NOT_FOUND")
        return error_response(msg, status_code=400, error_code="CONNECTOR_ERROR")
    return ok(result, "File uploaded.")


@router.post("/{session_id}/connect/last")
async def reconnect_last_source(session_id: str, current_user: CurrentUser):
    try:
        result = await service.reconnect_last_source(str(current_user["_id"]), session_id)
    except ValueError as exc:
        return error_response(str(exc), status_code=400, error_code="CONNECTOR_ERROR")
    return ok(result, "Previous source connected.")


@router.get("/{session_id}/schema")
async def get_schema(session_id: str, current_user: CurrentUser):
    try:
        schema = await service.get_schema(str(current_user["_id"]), session_id)
    except ValueError as exc:
        return error_response(str(exc), status_code=400, error_code="NO_CONNECTION")
    return ok(schema.model_dump())


@router.get("/{session_id}/preview/{table_name}")
async def get_preview_rows(
    session_id: str,
    table_name: str,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=500),
):
    try:
        rows = await service.get_preview_rows(str(current_user["_id"]), session_id, table_name, limit)
    except ValueError as exc:
        return error_response(str(exc), status_code=400, error_code="CONNECTOR_ERROR")
    return ok(rows.model_dump())


@router.patch("/{session_id}/schema-context")
async def update_schema_context(
    session_id: str,
    payload: SchemaContextUpdateRequest,
    current_user: CurrentUser,
):
    try:
        schema = await service.update_schema_context(str(current_user["_id"]), session_id, payload)
    except ValueError as exc:
        return error_response(str(exc), status_code=400, error_code="CONNECTOR_ERROR")
    return ok(schema.model_dump(), "Schema context saved.")


@router.delete("/{session_id}/disconnect")
async def disconnect_source(session_id: str, current_user: CurrentUser):
    await service.disconnect(str(current_user["_id"]), session_id)
    return ok(message="Source disconnected.")


@router.post("/{session_id}/google-sheet")
async def import_google_sheet(session_id: str, payload: GoogleSheetRequest, current_user: CurrentUser):
    """Download a public Google Sheet and connect it as a CSV data source."""
    try:
        result = await service.import_google_sheet(
            str(current_user["_id"]), session_id, payload.sheet_url
        )
    except ValueError as exc:
        return error_response(str(exc), status_code=400, error_code="CONNECTOR_ERROR")
    return ok(result, "Google Sheet connected.")


@router.get("/{session_id}/quality")
async def get_quality_report(session_id: str, current_user: CurrentUser):
    """Return the dataset quality report for the active file data source."""
    try:
        report = await service.get_quality_report(str(current_user["_id"]), session_id)
    except ValueError as exc:
        return error_response(str(exc), status_code=400, error_code="NO_CONNECTION")
    return ok(report)
