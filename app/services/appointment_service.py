from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.time_utils import to_naive_utc
from app.models.appointment import Appointment, AppointmentCreate
from app.models.user import User
from app.services.slot_service import (
    get_booked_slot_starts,
    get_guest_appointment_count_on_date,
    get_user_appointment_count_on_date,
)


def _to_naive_utc(dt: datetime) -> datetime:
    return to_naive_utc(dt)


async def create_appointment(
    session: AsyncSession, user_id: int, data: AppointmentCreate
) -> Appointment | None:
    slot_start = _to_naive_utc(data.slot_start_utc)
    # Enforce no overlapping: slot must not be already booked
    booked = await get_booked_slot_starts(
        session, slot_start, slot_start + timedelta(minutes=settings.slot_duration_minutes)
    )
    if booked:
        return None
    # Enforce one 30-min session per user per day
    d = slot_start.date()
    count = await get_user_appointment_count_on_date(session, user_id, d)
    if count >= settings.max_slots_per_user_per_day:
        return None
    appointment = Appointment(
        user_id=user_id,
        slot_start_utc=slot_start,
        message=data.message,
        contact_mode=data.contact_mode,
        service_type=data.service_type,
        phone_number=data.phone_number,
        status="scheduled",
    )
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment)
    return appointment


async def create_appointment_for_email(
    session: AsyncSession,
    email: str,
    slot_start_utc: datetime,
    guest_full_name: str | None = None,
    message: str | None = None,
    contact_mode: str | None = None,
    service_type: str | None = None,
    phone_number: str | None = None,
    user_if_exists: User | None = None,
) -> Appointment | None:
    """
    Create an appointment for a user by email. If user_if_exists is provided (user found by
    email), create with user_id; otherwise create as guest (guest_email, guest_full_name).
    Enforces slot availability and one slot per user/guest per day.
    """
    slot_start = _to_naive_utc(slot_start_utc)
    booked = await get_booked_slot_starts(
        session, slot_start, slot_start + timedelta(minutes=settings.slot_duration_minutes)
    )
    if booked:
        return None
    d = slot_start.date()
    if user_if_exists is not None:
        count = await get_user_appointment_count_on_date(session, user_if_exists.id, d)
        if count >= settings.max_slots_per_user_per_day:
            return None
        appointment = Appointment(
            user_id=user_if_exists.id,
            slot_start_utc=slot_start,
            message=message,
            contact_mode=contact_mode,
            service_type=service_type,
            phone_number=phone_number,
            status="scheduled",
        )
    else:
        count = await get_guest_appointment_count_on_date(session, email, d)
        if count >= settings.max_slots_per_user_per_day:
            return None
        appointment = Appointment(
            user_id=None,
            guest_email=email.strip().lower(),
            guest_full_name=guest_full_name,
            slot_start_utc=slot_start,
            message=message,
            contact_mode=contact_mode,
            service_type=service_type,
            phone_number=phone_number,
            status="scheduled",
        )
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment)
    return appointment


async def reschedule_appointment(
    session: AsyncSession,
    appointment_id: int,
    new_slot_start_utc: datetime,
    user_id: int | None = None,
    user_email: str | None = None,
    is_admin: bool = False,
) -> Appointment | None:
    """Reschedule an existing appointment to a new slot."""
    result = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        return None

    # Check permission
    if not is_admin:
        if appointment.user_id is not None:
            if appointment.user_id != user_id:
                return None
        else:
            if not user_email or (appointment.guest_email or "").lower() != user_email.lower():
                return None

    new_slot_utc = _to_naive_utc(new_slot_start_utc)
    # Check if target slot is already booked by another appointment
    booked = await get_booked_slot_starts(
        session, new_slot_utc, new_slot_utc + timedelta(minutes=settings.slot_duration_minutes)
    )
    if booked:
        return None

    appointment.slot_start_utc = new_slot_utc
    appointment.status = "rescheduled"
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment)
    return appointment


async def update_appointment_status(
    session: AsyncSession,
    appointment_id: int,
    new_status: str,
) -> Appointment | None:
    """Admin updates appointment status (scheduled, completed, cancelled, no_show)."""
    result = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        return None
    appointment.status = new_status
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment)
    return appointment


async def link_guest_appointments_to_user(session: AsyncSession, user_id: int, email: str) -> int:
    """Link all guest appointments with this email to the user. Returns count updated."""
    email_lower = email.lower()
    stmt = (
        update(Appointment)
        .where(
            Appointment.user_id.is_(None),
            func.lower(Appointment.guest_email) == email_lower,
        )
        .values(user_id=user_id, guest_email=None, guest_full_name=None)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount or 0


async def list_appointments_for_user(
    session: AsyncSession,
    user_id: int,
    user_email: str,
    from_date: date | None = None,
) -> list[Appointment]:
    """Return appointments owned by user_id or guest bookings for user_email (case-insensitive)."""
    email_lower = user_email.lower()
    q = (
        select(Appointment)
        .where(
            (Appointment.user_id == user_id)
            | (
                (Appointment.user_id.is_(None))
                & (func.lower(Appointment.guest_email) == email_lower)
            )
        )
        .order_by(Appointment.slot_start_utc.desc())
    )
    if from_date:
        start = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
        q = q.where(Appointment.slot_start_utc >= start)
    result = await session.execute(q)
    return list(result.scalars().all())


async def list_all_appointments_with_users(
    session: AsyncSession,
) -> list[tuple[Appointment, User | None]]:
    """Return all appointments with their user if any (left join so guest rows have User=None)."""
    q = (
        select(Appointment, User)
        .outerjoin(User, User.id == Appointment.user_id)
        .order_by(Appointment.slot_start_utc.desc())
    )
    result = await session.execute(q)
    return list(result.all())


async def get_appointment_by_id(
    session: AsyncSession,
    appointment_id: int,
) -> Appointment | None:
    result = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
    return result.scalar_one_or_none()


async def cancel_appointment(
    session: AsyncSession,
    appointment_id: int,
    user_id: int,
    user_email: str | None = None,
    is_admin: bool = False,
) -> bool:
    """Mark appointment as cancelled (or delete). Cancelled frees the slot in slot_service."""
    result = await session.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        return False
    if not is_admin:
        if appointment.user_id is not None:
            if appointment.user_id != user_id:
                return False
        else:
            if not user_email or (appointment.guest_email or "").lower() != user_email.lower():
                return False
    appointment.status = "cancelled"
    session.add(appointment)
    await session.flush()
    return True


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def delete_appointments_older_than(session: AsyncSession, days: int) -> int:
    """Delete appointments older than `days` ago (by slot_start_utc). Returns count deleted."""
    cutoff = _utc_naive_now() - timedelta(days=days)
    result = await session.execute(delete(Appointment).where(Appointment.slot_start_utc < cutoff))
    await session.flush()
    return result.rowcount or 0
