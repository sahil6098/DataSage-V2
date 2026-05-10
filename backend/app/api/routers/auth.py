from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest
from app.services.auth_service import AuthService
from app.utils.api import error_response, ok


router = APIRouter(prefix="/auth", tags=["auth"])
service = AuthService()


@router.post("/register")
async def register(payload: RegisterRequest):
    try:
        tokens = await service.register(payload)
    except ValueError as exc:
        return error_response(str(exc), status_code=400)
    return ok(tokens.model_dump(), "Registration successful.")


@router.post("/login")
async def login(payload: LoginRequest):
    try:
        tokens = await service.login(payload)
    except ValueError as exc:
        return error_response(str(exc), status_code=401)
    return ok(tokens.model_dump(), "Login successful.")


@router.post("/refresh")
async def refresh(payload: RefreshRequest):
    try:
        tokens = await service.refresh(payload.refresh_token)
    except ValueError as exc:
        return error_response(str(exc), status_code=401)
    return ok(tokens.model_dump(), "Token refreshed.")


@router.get("/me")
async def me(current_user: CurrentUser):
    user = await service.get_user(current_user)
    return ok(user.model_dump())
