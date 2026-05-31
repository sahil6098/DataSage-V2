from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.services.history_service import HistoryService
from app.utils.api import error_response, ok


router = APIRouter(prefix="/history", tags=["history"])
service = HistoryService()


@router.get("")
async def list_recent_queries(current_user: CurrentUser):
    """Return the 20 most recent queries for the authenticated user."""
    items = await service.list_recent(str(current_user["_id"]), limit=20)
    return ok(items)


@router.get("/favorites")
async def list_favorite_queries(current_user: CurrentUser):
    """Return all favorited queries for the authenticated user."""
    items = await service.list_favorites(str(current_user["_id"]))
    return ok(items)


@router.post("/{query_id}/favorite")
async def toggle_favorite(query_id: str, current_user: CurrentUser):
    """Toggle the favorite status of a query history item."""
    try:
        new_status = await service.toggle_favorite(str(current_user["_id"]), query_id)
    except ValueError as exc:
        return error_response(str(exc), status_code=404, error_code="NOT_FOUND")
    return ok({"is_favorite": new_status})


@router.delete("/{query_id}")
async def delete_query(query_id: str, current_user: CurrentUser):
    """Delete a single query history record."""
    try:
        await service.delete_query(str(current_user["_id"]), query_id)
    except ValueError as exc:
        return error_response(str(exc), status_code=404, error_code="NOT_FOUND")
    return ok(message="Query deleted.")
