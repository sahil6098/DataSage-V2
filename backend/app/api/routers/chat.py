import json

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService


router = APIRouter(prefix="/chat", tags=["chat"])
service = ChatService()
logger = get_logger(__name__)


@router.post("/{session_id}/stream")
async def stream_chat(
    session_id: str,
    payload: ChatRequest,
    current_user: CurrentUser,
    x_llm_provider: str | None = Header(default=None),
):
    async def event_stream():
        try:
            async for event in service.process_message_stream(
                user_id=str(current_user["_id"]),
                session_id=session_id,
                question=payload.message,
                provider_preference=payload.llm_provider or x_llm_provider,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            message = str(exc)
            error_code = "NO_CONNECTION" if "No data source connected" in message else "CHAT_ERROR"
            if error_code == "CHAT_ERROR":
                logger.warning("Chat stream value error for session %s: %s", session_id, message, exc_info=True)
            yield (
                f"data: {json.dumps({'type': 'error', 'message': message, 'error_code': error_code}, ensure_ascii=False)}\n\n"
            )
        except Exception:
            logger.exception("Unhandled chat stream error for session %s", session_id)
            yield (
                f"data: {json.dumps({'type': 'error', 'message': 'An error occurred while generating the response.', 'error_code': 'CHAT_ERROR'}, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
