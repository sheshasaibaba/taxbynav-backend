import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    appointments,
    auth,
    contact,
    reviews,
    slots,
)
from app.api.routes import (
    settings as settings_routes,
)
from app.core.config import _ENV_FILE, settings
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
    """Delete appointments older than appointment_retention_days (by slot_start_utc)."""
    try:
        async with async_session_maker() as session:
            try:
                n = await delete_appointments_older_than(
                    session, settings.appointment_retention_days
                )
                await session.commit()
                if n:
                    logger.info(
                        "Appointment cleanup: deleted %d record(s) older than %d days",
                        n,
                        settings.appointment_retention_days,
                    )
            except Exception:
                await session.rollback()
                raise
    except Exception as e:
        logger.exception("Appointment cleanup failed: %s", e)


def _run_migrations() -> None:
    """Apply Alembic migrations to ensure all tables and columns exist in PostgreSQL."""
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations executed successfully.")
    except Exception as e:
        logger.warning("Database migration startup warning: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: apply migrations and run initial cleanup
    _run_migrations()
    await _run_appointment_cleanup()
    # Background: run every 24h
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        await _run_appointment_cleanup()


app = FastAPI(
    title="TaxByNav API",
    description="Backend for TaxByNav: auth, slots, appointments, settings, and contact",
    version="0.2.0",
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
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(settings_routes.router, prefix="/api/v1")
app.include_router(contact.router, prefix="/api/v1")


def _cors_headers(origin: str | None) -> dict[str, str]:
    """Add CORS headers to error responses so the browser doesn't block them."""
    headers = {
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Refresh-Token",
    }
    if origin:
        is_allowed = (
            origin in settings.cors_origins_list
            or origin.endswith("taxbynav.com")
            or "localhost" in origin
            or "127.0.0.1" in origin
        )
        if is_allowed:
            headers["Access-Control-Allow-Origin"] = origin
            return headers
    if settings.cors_origins_list:
        headers["Access-Control-Allow-Origin"] = settings.cors_origins_list[0]
    return headers


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format validation errors into clear, friendly sentences for end users."""
    origin = request.headers.get("origin")
    headers = _cors_headers(origin)

    messages = []
    for error in exc.errors():
        msg = error.get("msg", "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        loc = error.get("loc", ())
        field = loc[-1] if loc else "field"

        if field == "email":
            messages.append("Please enter a valid email address.")
        elif field == "password":
            messages.append(msg if msg else "Please enter a valid password.")
        else:
            clean_field = str(field).replace("_", " ").capitalize()
            messages.append(f"{clean_field}: {msg}")

    detail = " ".join(messages) if messages else "Invalid input details provided. Please review and try again."
    return JSONResponse(
        status_code=422,
        content={"detail": detail},
        headers=headers,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions cleanly while exposing the actual error detail for diagnosis."""
    origin = request.headers.get("origin")
    headers = _cors_headers(origin)
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )

    # Log full traceback internally for operations
    logger.exception("Unhandled server exception: %s", exc)

    err_detail = f"{type(exc).__name__}: {str(exc)}"
    return JSONResponse(
        status_code=500,
        content={"detail": err_detail},
        headers=headers,
    )


@app.on_event("startup")
def startup_log() -> None:
    logger.info("Loading .env from: %s (exists: %s)", _ENV_FILE, _ENV_FILE.exists())
    logger.info(
        "Appointment retention: %d days (cleanup on startup and every 24h)",
        settings.appointment_retention_days,
    )
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
