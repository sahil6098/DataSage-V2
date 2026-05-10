from bson import ObjectId
from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.session import SessionCreateRequest
from app.services.session_service import SessionService
from app.utils.api import error_response, ok


router = APIRouter(prefix="/sessions", tags=["sessions"])
service = SessionService()


@router.post("")
async def create_session(payload: SessionCreateRequest, current_user: CurrentUser):
    session = await service.create_session(str(current_user["_id"]), payload)
    return ok(session.model_dump(), "Session created.")


@router.get("")
async def list_sessions(current_user: CurrentUser):
    sessions = await service.list_sessions(str(current_user["_id"]))
    return ok([session.model_dump() for session in sessions])


@router.get("/{session_id}")
async def get_session(session_id: str, current_user: CurrentUser):
    try:
        ObjectId(session_id)
        session = await service.get_session(str(current_user["_id"]), session_id)
    except Exception:
        return error_response("Session not found.", status_code=404)
    return ok(session.model_dump())


@router.delete("/{session_id}")
async def delete_session(session_id: str, current_user: CurrentUser):
    try:
        ObjectId(session_id)
        await service.delete_session(str(current_user["_id"]), session_id)
    except Exception:
        return error_response("Session not found.", status_code=404)
    return ok(message="Session deleted.")
