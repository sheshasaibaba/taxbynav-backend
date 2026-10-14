import urllib.parse
from datetime import UTC, datetime
from uuid import uuid4

from app.core.time_utils import ensure_utc


def format_utc_for_calendar(dt: datetime) -> str:
    """Format UTC datetime as YYYYMMDDTHHmmssZ."""
    aware = ensure_utc(dt)
    return aware.strftime("%Y%m%dT%H%M%SZ")


def build_google_calendar_url(
    title: str,
    start_utc: datetime,
    end_utc: datetime,
    details: str,
    location: str,
) -> str:
    """Generate a direct Google Calendar 'Add to Calendar' URL."""
    start_fmt = format_utc_for_calendar(start_utc)
    end_fmt = format_utc_for_calendar(end_utc)
    dates_param = f"{start_fmt}/{end_fmt}"

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_param,
        "details": details,
        "location": location,
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def build_ics_content(
    title: str,
    start_utc: datetime,
    end_utc: datetime,
    details: str,
    location: str,
    uid: str | None = None,
) -> str:
    """Generate standard RFC 5545 iCalendar (.ics) format."""
    event_uid = uid or f"taxbynav-{uuid4()}@taxbynav.com"
    dtstamp = format_utc_for_calendar(datetime.now(UTC))
    dtstart = format_utc_for_calendar(start_utc)
    dtend = format_utc_for_calendar(end_utc)

    # Escape special characters in text for ics format
    def ics_escape(s: str) -> str:
        return (
            s.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n")
        )

    clean_title = ics_escape(title)
    clean_details = ics_escape(details)
    clean_location = ics_escape(location)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TaxByNav//Appointment Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{clean_title}",
        f"DESCRIPTION:{clean_details}",
        f"LOCATION:{clean_location}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
