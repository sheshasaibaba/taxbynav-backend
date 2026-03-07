import logging
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.schemas.appointment import AdminBookAppointmentRequest, BookAppointmentRequest
from app.core.config import settings
from app.models.appointment import (
    Appointment,
    AppointmentAdminPublic,
    AppointmentCreate,
    AppointmentPublic,
)
from app.models.user import User
from app.services.appointment_service import (
    cancel_appointment,
    create_appointment,
    create_appointment_for_email,
    list_all_appointments_with_users,
    list_appointments_for_user,
)
from app.services.auth_service import get_user_by_email_insensitive
from app.services.email_service import (
    send_admin_appointment_notification_email,
    send_appointment_confirmation_email,
)

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
        contact_mode=a.contact_mode,
        created_at=created,
    )


def _to_admin_public(a: Appointment, user: User | None) -> AppointmentAdminPublic:
    """Public shape for admin listing; use user details or guest_email/guest_full_name."""
    aid = int(a.id) if a.id is not None else 0
    slot = a.slot_start_utc or _FALLBACK_DATETIME
    created = a.created_at or _FALLBACK_DATETIME
    if isinstance(slot, datetime) and slot.tzinfo is not None:
        slot = slot.replace(tzinfo=None)
    if isinstance(created, datetime) and created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    if user is not None:
        email, full_name = user.email, user.full_name
    else:
        email = a.guest_email or ""
        full_name = a.guest_full_name
    return AppointmentAdminPublic(
        id=aid,
        user_id=a.user_id,
        user_email=email,
        user_full_name=full_name,
        slot_start_utc=slot,
        message=a.message,
        contact_mode=a.contact_mode,
        created_at=created,
    )


@router.post("", response_model=AppointmentPublic, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    body: BookAppointmentRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppointmentPublic:
    data = AppointmentCreate(
        slot_start_utc=body.slot_start_utc,
        message=body.message,
        contact_mode=body.contact_mode,
    )
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
        contact_mode=appointment.contact_mode,
    )
    # Notify admin of new booking (uses configured contact email if set)
    admin_email = settings.contact_email or settings.from_email
    if admin_email:
        background_tasks.add_task(
            send_admin_appointment_notification_email,
            admin_email=admin_email,
            slot_start_utc=appointment.slot_start_utc,
            duration_minutes=settings.slot_duration_minutes,
            message=appointment.message,
            contact_mode=appointment.contact_mode,
            phone_number=body.phone_number,
            user=current_user,
        )
    return _to_public(appointment)


@router.get("", response_model=list[AppointmentPublic])
async def list_my_appointments(
    from_date: date | None = Query(None, alias="from_date"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AppointmentPublic]:
    try:
        appointments = await list_appointments_for_user(
            session, current_user.id, current_user.email, from_date=from_date
        )
        return [_to_public(a) for a in appointments]
    except Exception as e:
        logger.exception("List appointments failed: %s", e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


@router.post(
    "/admin",
    response_model=AppointmentPublic,
    status_code=status.HTTP_201_CREATED,
)
async def admin_book_appointment(
    body: AdminBookAppointmentRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppointmentPublic:
    """
    Admin endpoint: create a booking for a user by email.
    If the email has an account, the appointment is linked to that user.
    If not, a guest booking is created; when they register with that email later,
    the appointment will appear under their account.
    """
    admin_email = settings.contact_email or settings.from_email
    if not admin_email or current_user.email.lower() != admin_email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create appointments for others",
        )
    user = await get_user_by_email_insensitive(session, body.guest_email.strip())
    appointment = await create_appointment_for_email(
        session,
        email=body.guest_email.strip(),
        slot_start_utc=body.slot_start_utc,
        guest_full_name=body.guest_full_name,
        message=body.message,
        contact_mode=body.contact_mode,
        user_if_exists=user,
    )
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slot not available or this user/guest already has a session booked for this day.",
        )
    # Always send confirmation to the user/guest (not the admin) so they receive the booking details
    if user is not None:
        recipient_email = user.email
        recipient_name = user.full_name
    else:
        recipient_email = appointment.guest_email or body.guest_email.strip()
        recipient_name = body.guest_full_name
    if recipient_email:
        background_tasks.add_task(
            send_appointment_confirmation_email,
            to_email=recipient_email,
            recipient_name=recipient_name,
            slot_start_utc=appointment.slot_start_utc,
            duration_minutes=settings.slot_duration_minutes,
            message=appointment.message,
            contact_mode=appointment.contact_mode,
        )
    admin_email_to = settings.contact_email or settings.from_email
    if admin_email_to:
        background_tasks.add_task(
            send_admin_appointment_notification_email,
            admin_email=admin_email_to,
            slot_start_utc=appointment.slot_start_utc,
            duration_minutes=settings.slot_duration_minutes,
            message=appointment.message,
            contact_mode=appointment.contact_mode,
            user=user,
            guest_email=appointment.guest_email if not user else None,
            guest_full_name=appointment.guest_full_name if not user else None,
        )
    return _to_public(appointment)


@router.get("/admin", response_model=list[AppointmentAdminPublic])
async def list_all_appointments_admin(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[AppointmentAdminPublic]:
    """
    Admin endpoint: list all appointments with user details.
    Only allowed for the admin email (TaxByNav contact email / from_email).
    """
    admin_email = settings.contact_email or settings.from_email
    if not admin_email or current_user.email.lower() != admin_email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view all appointments",
        )
    try:
        rows = await list_all_appointments_with_users(session)
        return [_to_admin_public(a, u) for a, u in rows]  # u is None for guest rows
    except Exception as e:
        logger.exception("Admin list appointments failed: %s", e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_my_appointment(
    appointment_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    ok = await cancel_appointment(
        session, appointment_id, current_user.id, user_email=current_user.email
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found or not yours",
        )
