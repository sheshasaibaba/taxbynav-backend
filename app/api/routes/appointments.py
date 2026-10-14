import logging
from datetime import date, datetime, timedelta

from app.api.deps import get_current_admin_user, get_current_user, get_optional_user, get_session
from app.api.schemas.appointment import (
    AdminBookAppointmentRequest,
    AppointmentRescheduleRequest,
    AppointmentStatusUpdateRequest,
    BookAppointmentRequest,
)
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
    get_appointment_by_id,
    list_all_appointments_with_users,
    list_appointments_for_user,
    reschedule_appointment,
    update_appointment_status,
)
from app.services.auth_service import get_user_by_email_insensitive
from app.services.calendar_service import build_ics_content
from app.services.email_service import (
    send_admin_appointment_notification_email,
    send_appointment_confirmation_email,
)
from app.services.settings_service import get_or_create_settings
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/appointments", tags=["appointments"])

_FALLBACK_DATETIME = datetime(2020, 1, 1, 0, 0, 0)


def _to_public(a: Appointment) -> AppointmentPublic:
    """Build public response with safe types."""
    aid = int(a.id) if a.id is not None else 0
    slot = a.slot_start_utc or _FALLBACK_DATETIME
    created = a.created_at or _FALLBACK_DATETIME
    if isinstance(slot, datetime) and slot.tzinfo is not None:
        slot = slot.replace(tzinfo=None)
    if isinstance(created, datetime) and created.tzinfo is not None:
        created = created.replace(tzinfo=None)
    return AppointmentPublic(
        id=aid,
        user_id=a.user_id,
        slot_start_utc=slot,
        message=a.message,
        contact_mode=a.contact_mode,
        service_type=a.service_type,
        phone_number=a.phone_number,
        status=a.status or "scheduled",
        created_at=created,
    )


def _to_admin_public(a: Appointment, user: User | None) -> AppointmentAdminPublic:
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
        service_type=a.service_type,
        phone_number=a.phone_number,
        status=a.status or "scheduled",
        created_at=created,
    )


@router.post("", response_model=AppointmentPublic, status_code=status.HTTP_201_CREATED)
async def book_appointment(
    body: BookAppointmentRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppointmentPublic:
    site_settings = await get_or_create_settings(session)
    data = AppointmentCreate(
        slot_start_utc=body.slot_start_utc,
        message=body.message,
        contact_mode=body.contact_mode,
        service_type=body.service_type,
        phone_number=body.phone_number,
    )
    appointment = await create_appointment(session, current_user.id, data)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slot not available or you already have a session booked for this day (max one 30-min session per day).",
        )

    # Send confirmation email with CST time, calendar button and .ics
    background_tasks.add_task(
        send_appointment_confirmation_email,
        to_email=current_user.email,
        recipient_name=current_user.full_name,
        slot_start_utc=appointment.slot_start_utc,
        duration_minutes=site_settings.slot_duration_minutes,
        message=appointment.message,
        contact_mode=appointment.contact_mode,
        service_type=appointment.service_type,
        contact_address=site_settings.contact_address,
        contact_phone=site_settings.contact_phone,
    )

    # Notify admin
    admin_email = settings.admin_email_for_auth or settings.smtp_user
    if admin_email:
        background_tasks.add_task(
            send_admin_appointment_notification_email,
            admin_email=admin_email,
            slot_start_utc=appointment.slot_start_utc,
            duration_minutes=site_settings.slot_duration_minutes,
            message=appointment.message,
            contact_mode=appointment.contact_mode,
            service_type=appointment.service_type,
            phone_number=appointment.phone_number,
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
    _admin: User = Depends(get_current_admin_user),
) -> AppointmentPublic:
    site_settings = await get_or_create_settings(session)
    user = await get_user_by_email_insensitive(session, body.guest_email.strip())
    appointment = await create_appointment_for_email(
        session,
        email=body.guest_email.strip(),
        slot_start_utc=body.slot_start_utc,
        guest_full_name=body.guest_full_name,
        message=body.message,
        contact_mode=body.contact_mode,
        service_type=body.service_type,
        phone_number=body.phone_number,
        user_if_exists=user,
    )
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Slot not available or this user/guest already has a session booked for this day.",
        )

    recipient_email = user.email if user else (appointment.guest_email or body.guest_email.strip())
    recipient_name = user.full_name if user else body.guest_full_name

    if recipient_email:
        background_tasks.add_task(
            send_appointment_confirmation_email,
            to_email=recipient_email,
            recipient_name=recipient_name,
            slot_start_utc=appointment.slot_start_utc,
            duration_minutes=site_settings.slot_duration_minutes,
            message=appointment.message,
            contact_mode=appointment.contact_mode,
            service_type=appointment.service_type,
            contact_address=site_settings.contact_address,
            contact_phone=site_settings.contact_phone,
        )

    return _to_public(appointment)


@router.get("/admin", response_model=list[AppointmentAdminPublic])
async def admin_list_appointments(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_current_admin_user),
) -> list[AppointmentAdminPublic]:
    rows = await list_all_appointments_with_users(session)
    return [_to_admin_public(apt, user) for apt, user in rows]


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentPublic)
async def reschedule_appointment_route(
    appointment_id: int,
    body: AppointmentRescheduleRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AppointmentPublic:
    """Client or Admin reschedules an appointment to a new slot."""
    site_settings = await get_or_create_settings(session)
    is_admin = bool(
        settings.admin_email_for_auth
        and current_user.email.lower() == settings.admin_email_for_auth.lower()
    )
    apt = await reschedule_appointment(
        session,
        appointment_id=appointment_id,
        new_slot_start_utc=body.slot_start_utc,
        user_id=current_user.id,
        user_email=current_user.email,
        is_admin=is_admin,
    )
    if not apt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not reschedule: slot may be unavailable or appointment not found.",
        )

    # Send updated email to user/guest
    recipient_email = current_user.email if apt.user_id == current_user.id else apt.guest_email
    recipient_name = (
        current_user.full_name if apt.user_id == current_user.id else apt.guest_full_name
    )

    if recipient_email:
        background_tasks.add_task(
            send_appointment_confirmation_email,
            to_email=recipient_email,
            recipient_name=recipient_name,
            slot_start_utc=apt.slot_start_utc,
            duration_minutes=site_settings.slot_duration_minutes,
            message=apt.message,
            contact_mode=apt.contact_mode,
            service_type=apt.service_type,
            contact_address=site_settings.contact_address,
            contact_phone=site_settings.contact_phone,
        )

    # Notify admin
    admin_email = settings.admin_email_for_auth or settings.smtp_user
    if admin_email:
        background_tasks.add_task(
            send_admin_appointment_notification_email,
            admin_email=admin_email,
            slot_start_utc=apt.slot_start_utc,
            duration_minutes=site_settings.slot_duration_minutes,
            message=apt.message,
            contact_mode=apt.contact_mode,
            service_type=apt.service_type,
            phone_number=apt.phone_number,
            user=current_user if apt.user_id == current_user.id else None,
            guest_email=apt.guest_email,
            guest_full_name=apt.guest_full_name,
            is_reschedule=True,
        )

    return _to_public(apt)


@router.patch("/{appointment_id}/status", response_model=AppointmentPublic)
async def update_status_route(
    appointment_id: int,
    body: AppointmentStatusUpdateRequest,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_current_admin_user),
) -> AppointmentPublic:
    """Admin updates appointment status (scheduled, completed, cancelled, no_show)."""
    apt = await update_appointment_status(session, appointment_id, body.status)
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _to_public(apt)


@router.delete("/{appointment_id}")
async def cancel_my_appointment(
    appointment_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    is_admin = bool(
        settings.admin_email_for_auth
        and current_user.email.lower() == settings.admin_email_for_auth.lower()
    )
    ok = await cancel_appointment(
        session,
        appointment_id,
        current_user.id,
        user_email=current_user.email,
        is_admin=is_admin,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found or not owned by you.",
        )
    return {"message": "Appointment cancelled"}


@router.get("/{appointment_id}/ics")
async def download_ics(
    appointment_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_optional_user),
) -> Response:
    """Download standard .ics iCalendar file for this appointment."""
    site_settings = await get_or_create_settings(session)
    apt = await get_appointment_by_id(session, appointment_id)
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    service_name = apt.service_type or "Tax & Advisory Consultation"
    end_utc = apt.slot_start_utc + timedelta(minutes=site_settings.slot_duration_minutes)
    loc = site_settings.contact_address
    if apt.contact_mode == "online":
        loc = "Online Video / Phone Consultation"

    details = f"Consultation with TaxByNav for {service_name}. Mode: {apt.contact_mode or 'Online'}"
    if apt.message:
        details += f"\n\nNotes: {apt.message}"

    ics_data = build_ics_content(
        title=f"TaxByNav: {service_name}",
        start_utc=apt.slot_start_utc,
        end_utc=end_utc,
        details=details,
        location=loc,
        uid=f"appointment-{apt.id}@taxbynav.com",
    )
    return Response(
        content=ics_data,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="taxbynav-appointment-{apt.id}.ics"'
        },
    )
