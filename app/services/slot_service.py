from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import SASKATOON_TZ, UTC_TZ
from app.models.appointment import Appointment
from app.models.setting import SiteSettings
from app.services.settings_service import get_or_create_settings


def _parse_working_days(working_days_str: str) -> set[int]:
    """Parse comma-separated days e.g. '0,1,2,3,4,5' into set of ints (0=Mon, 6=Sun)."""
    res = set()
    for part in working_days_str.split(","):
        part = part.strip()
        if part.isdigit():
            res.add(int(part))
    return res or {0, 1, 2, 3, 4, 5}


def _parse_blackout_dates(blackout_str: str) -> set[str]:
    """Parse comma-separated date strings (YYYY-MM-DD)."""
    return {p.strip() for p in blackout_str.split(",") if p.strip()}


def _slot_times_for_date_cst(d: date, site_settings: SiteSettings) -> list[datetime]:
    """
    Generate slot start times in naive UTC for the given calendar date in Saskatoon CST.
    Respects active working days and blackout dates.
    """
    # 1. Check working days (0=Mon, 6=Sun)
    allowed_days = _parse_working_days(site_settings.working_days)
    if d.weekday() not in allowed_days:
        return []

    # 2. Check blackout dates
    blackouts = _parse_blackout_dates(site_settings.blackout_dates)
    if d.isoformat() in blackouts:
        return []

    slots_utc: list[datetime] = []
    # Business hours in Saskatoon CST
    start_cst = datetime(
        d.year, d.month, d.day, site_settings.business_start_hour, 0, 0, tzinfo=SASKATOON_TZ
    )
    end_cst = datetime(
        d.year, d.month, d.day, site_settings.business_end_hour, 0, 0, tzinfo=SASKATOON_TZ
    )
    delta = timedelta(minutes=site_settings.slot_duration_minutes)

    current_cst = start_cst
    while current_cst < end_cst:
        # Convert each slot start to aware UTC
        slot_utc = current_cst.astimezone(UTC_TZ)
        slots_utc.append(slot_utc)
        current_cst += delta

    return slots_utc


async def get_booked_slot_starts(
    session: AsyncSession, start_inclusive: datetime, end_exclusive: datetime
) -> set[datetime]:
    start_dt = start_inclusive if start_inclusive.tzinfo is not None else start_inclusive.replace(tzinfo=UTC_TZ)
    end_dt = end_exclusive if end_exclusive.tzinfo is not None else end_exclusive.replace(tzinfo=UTC_TZ)
    result = await session.execute(
        select(Appointment.slot_start_utc).where(
            Appointment.slot_start_utc >= start_dt,
            Appointment.slot_start_utc < end_dt,
            Appointment.status != "cancelled",  # Cancelled appointments free up their slot!
        )
    )
    return {row[0] for row in result.all()}


def _get_cst_day_utc_bounds(d: date) -> tuple[datetime, datetime]:
    """Get UTC start and end bounds corresponding to a full calendar day in Saskatoon CST."""
    start_cst = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=SASKATOON_TZ)
    end_cst = start_cst + timedelta(days=1)
    return (
        start_cst.astimezone(UTC_TZ),
        end_cst.astimezone(UTC_TZ),
    )


async def get_user_appointment_count_on_date(session: AsyncSession, user_id: int, d: date) -> int:
    start_utc, end_utc = _get_cst_day_utc_bounds(d)
    result = await session.execute(
        select(Appointment).where(
            Appointment.user_id == user_id,
            Appointment.slot_start_utc >= start_utc,
            Appointment.slot_start_utc < end_utc,
            Appointment.status != "cancelled",
        )
    )
    return len(result.scalars().all())


async def get_guest_appointment_count_on_date(
    session: AsyncSession, guest_email: str, d: date
) -> int:
    """Count active appointments for this guest email on the given date (case-insensitive)."""
    start_utc, end_utc = _get_cst_day_utc_bounds(d)
    email_lower = guest_email.lower()
    result = await session.execute(
        select(Appointment).where(
            func.lower(Appointment.guest_email) == email_lower,
            Appointment.slot_start_utc >= start_utc,
            Appointment.slot_start_utc < end_utc,
            Appointment.status != "cancelled",
        )
    )
    return len(result.scalars().all())


async def get_available_slots_for_date(
    session: AsyncSession, d: date, user_id: int | None = None
) -> list[tuple[datetime, bool]]:
    """Returns list of (slot_start_utc, available) using dynamic business settings."""
    site_settings = await get_or_create_settings(session)
    slots = _slot_times_for_date_cst(d, site_settings)
    if not slots:
        return []
    start_inclusive = min(slots)
    end_exclusive = max(slots) + timedelta(minutes=site_settings.slot_duration_minutes)
    booked = await get_booked_slot_starts(session, start_inclusive, end_exclusive)
    out: list[tuple[datetime, bool]] = []
    for s in slots:
        out.append((s, s not in booked))
    return out
