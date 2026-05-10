from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers.auth import router as auth_router
from app.api.routers.chat import router as chat_router
from app.api.routers.connectors import router as connectors_router
from app.api.routers.sessions import router as sessions_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.mongo import close_db, init_db


settings = get_settings()
configure_logging(settings.debug)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    await init_db()
    logger.info("Application startup complete.")
    yield
    await close_db()
    logger.info("Application shutdown complete.")


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    start = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # pragma: no cover - defensive middleware
        logger.exception("Unhandled request error [%s] %s", request_id, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error.", "request_id": request_id},
        )

    duration_ms = round((perf_counter() - start) * 1000, 2)
    response.headers["x-request-id"] = request_id
    logger.info(
        "HTTP %s %s -> %s in %sms [%s]",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


@app.get("/health")
async def health():
    return {"success": True, "message": "ok"}


app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(connectors_router)
app.include_router(chat_router)
