import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, appointments, slots
from app.core.config import settings, _ENV_FILE
from app.core.db import async_session_maker
from app.services.appointment_service import delete_appointments_older_than

if os.getenv("ENV") != "production":
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
    )
logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours


async def _run_appointment_cleanup() -> None:
    """Delete appointments older than appointment_retention_days (e.g. 3 days after booking)."""
    try:
        async with async_session_maker() as session:
            try:
                n = await delete_appointments_older_than(session, settings.appointment_retention_days)
                await session.commit()
                if n:
                    logger.info("Appointment cleanup: deleted %d record(s) older than %d days", n, settings.appointment_retention_days)
            except Exception:
                await session.rollback()
                raise
    except Exception as e:
        logger.exception("Appointment cleanup failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run cleanup once
    await _run_appointment_cleanup()
    # Background: run every 24h
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        await _run_appointment_cleanup()


app = FastAPI(
    title="TaxByNav API",
    description="Backend for TaxByNav: auth, slots, appointments",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Refresh-Token"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(slots.router, prefix="/api/v1")
app.include_router(appointments.router, prefix="/api/v1")


def _cors_headers(origin: str | None) -> dict[str, str]:
    """Add CORS headers to error responses so the browser doesn't block them."""
    headers = {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Refresh-Token",
    }
    if origin and origin in settings.cors_origins_list:
        headers["Access-Control-Allow-Origin"] = origin
    elif settings.cors_origins_list:
        headers["Access-Control-Allow-Origin"] = settings.cors_origins_list[0]
    return headers


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return actual error in JSON; include CORS so 500 responses are not blocked by browser."""
    origin = request.headers.get("origin")
    headers = _cors_headers(origin)
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )
    logger.exception("Unhandled exception: %s", exc)
    detail = f"{type(exc).__name__}: {str(exc)}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
        headers=headers,
    )


@app.on_event("startup")
def startup_log() -> None:
    logger.info("Loading .env from: %s (exists: %s)", _ENV_FILE, _ENV_FILE.exists())
    logger.info("Appointment retention: %d days (cleanup on startup and every 24h)", settings.appointment_retention_days)
    if settings.google_client_id and settings.google_redirect_uri:
        logger.info("Google OAuth: configured (GOOGLE_CLIENT_ID set)")
    else:
        logger.warning(
            "Google OAuth: NOT configured. Set GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI in %s",
            _ENV_FILE,
        )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
