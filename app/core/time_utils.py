from datetime import datetime
from zoneinfo import ZoneInfo

SASKATOON_TZ = ZoneInfo("America/Regina")
UTC_TZ = ZoneInfo("UTC")


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is aware and in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)


def to_naive_utc(dt: datetime) -> datetime:
    """Convert any datetime to naive UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC_TZ).replace(tzinfo=None)
    return dt


def to_saskatoon_cst(dt: datetime) -> datetime:
    """Convert naive or aware UTC datetime to Saskatoon CST (America/Regina)."""
    aware_utc = ensure_utc(dt)
    return aware_utc.astimezone(SASKATOON_TZ)


def format_cst_time(dt: datetime) -> str:
    """Format time as '09:00 AM CST'."""
    cst = to_saskatoon_cst(dt)
    return cst.strftime("%I:%M %p CST").lstrip("0")


def format_cst_full(dt: datetime) -> str:
    """Format full date and time as 'Wednesday, October 14, 2026 at 9:00 AM CST'."""
    cst = to_saskatoon_cst(dt)
    date_str = cst.strftime("%A, %B %d, %Y")
    time_str = cst.strftime("%I:%M %p CST").lstrip("0")
    return f"{date_str} at {time_str}"
