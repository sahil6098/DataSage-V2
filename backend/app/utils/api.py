from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.schemas.common import ApiEnvelope, ErrorEnvelope


def ok(data=None, message: str | None = None) -> JSONResponse:
    payload = ApiEnvelope(success=True, data=data, message=message).model_dump()
    return JSONResponse(content=jsonable_encoder(payload))


def error_response(message: str, status_code: int = 400, error_code: str | None = None) -> JSONResponse:
    payload = ErrorEnvelope(message=message, error_code=error_code).model_dump()
    return JSONResponse(status_code=status_code, content=payload)
