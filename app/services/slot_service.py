from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.appointment import Appointment


def _slot_times_for_date(d: date) -> list[datetime]:
    """Generate slot start times as naive UTC for the given date (business hours 9-17 UTC)."""
    slots: list[datetime] = []
    start = datetime(d.year, d.month, d.day, settings.business_start_hour, 0, 0)
    end = datetime(d.year, d.month, d.day, settings.business_end_hour, 0, 0)
    delta = timedelta(minutes=settings.slot_duration_minutes)
    current = start
    while current < end:
        slots.append(current)
        current += delta
    return slots


async def get_booked_slot_starts(
    session: AsyncSession, start_inclusive: datetime, end_exclusive: datetime
) -> set[datetime]:
    result = await session.execute(
        select(Appointment.slot_start_utc).where(
            Appointment.slot_start_utc >= start_inclusive,
            Appointment.slot_start_utc < end_exclusive,
        )
    )
    return {row[0] for row in result.all()}


async def get_user_appointment_count_on_date(
    session: AsyncSession, user_id: int, d: date
) -> int:
    start = datetime(d.year, d.month, d.day, 0, 0, 0)
    end = start + timedelta(days=1)
    result = await session.execute(
        select(Appointment).where(
            Appointment.user_id == user_id,
            Appointment.slot_start_utc >= start,
            Appointment.slot_start_utc < end,
        )
    )
    return len(result.scalars().all())


async def get_available_slots_for_date(
    session: AsyncSession, d: date, user_id: int | None = None
) -> list[tuple[datetime, bool]]:
    """Returns list of (slot_start_utc, available). If user_id given, slots already
    booked by this user on this day are still marked unavailable for double-booking."""
    slots = _slot_times_for_date(d)
    if not slots:
        return []
    start_inclusive = slots[0]
    end_exclusive = slots[-1] + timedelta(minutes=settings.slot_duration_minutes)
    booked = await get_booked_slot_starts(session, start_inclusive, end_exclusive)
    out: list[tuple[datetime, bool]] = []
    for s in slots:
        out.append((s, s not in booked))
    return out
