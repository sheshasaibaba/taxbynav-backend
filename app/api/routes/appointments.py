import logging
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.schemas.appointment import BookAppointmentRequest
from app.core.config import settings
from app.models.appointment import Appointment, AppointmentCreate, AppointmentPublic
from app.models.user import User
from app.services.appointment_service import (
    cancel_appointment,
    create_appointment,
    list_appointments_for_user,
)
from app.services.email_service import send_appointment_confirmation_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/appointments", tags=["appointments"])

# Fallback for NULL or missing datetimes from DB
_FALLBACK_DATETIME = datetime(2020, 1, 1, 0, 0, 0)


def _to_public(a: Appointment) -> AppointmentPublic:
    """Build public response; ensure id and datetimes are plain Python types for JSON."""
    aid = int(a.id) if a.id is not None else 0
    slot = a.slot_start_utc
    created = a.created_at
    if slot is None:
        slot = _FALLBACK_DATETIME
    elif isinstance(slot, datetime) and slot.tzinfo is not None:
        slot = slot.replace(tzinfo=None)
    if created is None:
        created = _FALLBACK_DATETIME
    elif isinstance(created, datetime) and created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    return AppointmentPublic(
        id=aid,
        user_id=a.user_id,
        slot_start_utc=slot,
        message=a.message,
        created_at=created,
    )


@router.post("", response_model=AppointmentPublic, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    body: BookAppointmentRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppointmentPublic:
    data = AppointmentCreate(slot_start_utc=body.slot_start_utc, message=body.message)
    appointment = await create_appointment(session, current_user.id, data)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slot not available or you already have a session booked for this day (max one 30-min session per day).",
        )
    # Send confirmation email in background (uses sync SMTP)
    background_tasks.add_task(
        send_appointment_confirmation_email,
        to_email=current_user.email,
        recipient_name=current_user.full_name,
        slot_start_utc=appointment.slot_start_utc,
        duration_minutes=settings.slot_duration_minutes,
        message=appointment.message,
    )
    return _to_public(appointment)


@router.get("", response_model=list[AppointmentPublic])
async def list_my_appointments(
    from_date: date | None = Query(None, alias="from_date"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AppointmentPublic]:
    try:
        appointments = await list_appointments_for_user(session, current_user.id, from_date=from_date)
        return [_to_public(a) for a in appointments]
    except Exception as e:
        logger.exception("List appointments failed: %s", e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_my_appointment(
    appointment_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    ok = await cancel_appointment(session, appointment_id, current_user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found or not yours",
        )
