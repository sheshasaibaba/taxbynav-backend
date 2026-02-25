from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment, AppointmentCreate
from app.services.slot_service import get_booked_slot_starts, get_user_appointment_count_on_date


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
    )
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment)
    return appointment


async def list_appointments_for_user(
    session: AsyncSession, user_id: int, from_date: date | None = None
) -> list[Appointment]:
    q = select(Appointment).where(Appointment.user_id == user_id).order_by(Appointment.slot_start_utc)
    if from_date:
        start = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)
        q = q.where(Appointment.slot_start_utc >= start)
    result = await session.execute(q)
    return list(result.scalars().all())


async def cancel_appointment(session: AsyncSession, appointment_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.user_id == user_id,
        )
    )
    appointment = result.scalar_one_or_none()
    if not appointment:
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
