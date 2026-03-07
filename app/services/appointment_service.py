from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment, AppointmentCreate
from app.models.user import User
from app.services.slot_service import (
    get_booked_slot_starts,
    get_guest_appointment_count_on_date,
    get_user_appointment_count_on_date,
)


def _to_naive_utc(dt: datetime) -> datetime:
    """Convert to naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


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
        )
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment)
    return appointment


async def link_guest_appointments_to_user(
    session: AsyncSession, user_id: int, email: str
) -> int:
    """
    Link all guest appointments with this email to the user. Returns count updated.
    """
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
    q = select(Appointment).where(
        (Appointment.user_id == user_id)
        | (
            (Appointment.user_id.is_(None))
            & (func.lower(Appointment.guest_email) == email_lower)
        )
    ).order_by(Appointment.slot_start_utc)
    if from_date:
        start = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
        q = q.where(Appointment.slot_start_utc >= start)
    result = await session.execute(q)
    return list(result.scalars().all())


async def list_all_appointments_with_users(
    session: AsyncSession,
) -> list[tuple[Appointment, User | None]]:
    """
    Return all appointments with their user if any (left join so guest rows have User=None).
    """
    q = (
        select(Appointment, User)
        .outerjoin(User, User.id == Appointment.user_id)
        .order_by(Appointment.slot_start_utc)
    )
    result = await session.execute(q)
    return list(result.all())


async def cancel_appointment(
    session: AsyncSession,
    appointment_id: int,
    user_id: int,
    user_email: str | None = None,
) -> bool:
    """Cancel if appointment is owned by user_id or by guest_email (when user_email provided)."""
    result = await session.execute(
        select(Appointment).where(Appointment.id == appointment_id)
    )
    appointment = result.scalar_one_or_none()
    if not appointment:
        return False
    if appointment.user_id is not None:
        if appointment.user_id != user_id:
            return False
    else:
        if not user_email or func.lower(appointment.guest_email or "") != user_email.lower():
            return False
    await session.delete(appointment)
    await session.flush()
    return True


def _utc_naive_now() -> datetime:
    """Naive UTC for comparison with TIMESTAMP WITHOUT TIME ZONE."""
    return datetime.now(UTC).replace(tzinfo=None)


async def delete_appointments_older_than(
    session: AsyncSession, days: int
) -> int:
    """Delete appointments booked more than `days` ago (by created_at). Returns count deleted."""
    cutoff = _utc_naive_now() - timedelta(days=days)
    result = await session.execute(delete(Appointment).where(Appointment.created_at < cutoff))
    await session.flush()
    return result.rowcount or 0
