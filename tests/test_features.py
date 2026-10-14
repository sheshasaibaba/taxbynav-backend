from datetime import UTC, date, datetime

from app.core.time_utils import format_cst_full, format_cst_time, to_saskatoon_cst
from app.models.setting import SiteSettings
from app.services.calendar_service import build_google_calendar_url, build_ics_content
from app.services.slot_service import _slot_times_for_date_cst


def test_saskatoon_cst_time_conversion():
    # 2026-10-15 15:00:00 UTC corresponds to 09:00:00 CST in Saskatoon (UTC-6)
    utc_dt = datetime(2026, 10, 15, 15, 0, 0, tzinfo=UTC)
    cst_dt = to_saskatoon_cst(utc_dt)
    assert cst_dt.hour == 9
    assert cst_dt.minute == 0
    formatted = format_cst_time(utc_dt)
    assert "9:00 AM CST" in formatted

    full_fmt = format_cst_full(utc_dt)
    assert "Thursday, October 15, 2026" in full_fmt
    assert "9:00 AM CST" in full_fmt


def test_calendar_service_google_url():
    start = datetime(2026, 10, 15, 15, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 15, 15, 30, 0, tzinfo=UTC)
    url = build_google_calendar_url(
        title="TaxByNav Consultation: Personal Tax",
        start_utc=start,
        end_utc=end,
        details="Discussion about personal tax returns.",
        location="Saskatoon, Saskatchewan",
    )
    assert "https://calendar.google.com/calendar/render" in url
    assert "action=TEMPLATE" in url
    assert (
        "20261015T150000Z%2F20261015T153000Z" in url or "20261015T150000Z/20261015T153000Z" in url
    )
    assert "TaxByNav" in url


def test_calendar_service_ics_content():
    start = datetime(2026, 10, 15, 15, 0, 0, tzinfo=UTC)
    end = datetime(2026, 10, 15, 15, 30, 0, tzinfo=UTC)
    ics = build_ics_content(
        title="TaxByNav Consultation: Personal Tax",
        start_utc=start,
        end_utc=end,
        details="Discussion about personal tax returns.",
        location="Saskatoon, Saskatchewan",
        uid="test-appointment-1@taxbynav.com",
    )
    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "END:VEVENT" in ics
    assert "UID:test-appointment-1@taxbynav.com" in ics
    assert "DTSTART:20261015T150000Z" in ics
    assert "DTEND:20261015T153000Z" in ics
    assert "SUMMARY:TaxByNav Consultation: Personal Tax" in ics


def test_dynamic_slot_generation_cst():
    settings = SiteSettings(
        business_start_hour=9,  # 9 AM CST
        business_end_hour=11,  # 11 AM CST -> 4 slots: 9:00, 9:30, 10:00, 10:30
        slot_duration_minutes=30,
        working_days="0,1,2,3,4",  # Mon-Fri
        blackout_dates="2026-10-16",  # Friday closed
        timezone="America/Regina",
    )
    # Thursday, Oct 15 2026 (weekday = 3, allowed)
    d_thurs = date(2026, 10, 15)
    slots = _slot_times_for_date_cst(d_thurs, settings)
    assert len(slots) == 4
    # First slot should be 9:00 AM CST which is 15:00 UTC
    assert slots[0] == datetime(2026, 10, 15, 15, 0, 0)
    # Last slot should be 10:30 AM CST which is 16:30 UTC
    assert slots[-1] == datetime(2026, 10, 15, 16, 30, 0)

    # Friday, Oct 16 2026 (in blackout dates)
    d_fri = date(2026, 10, 16)
    assert len(_slot_times_for_date_cst(d_fri, settings)) == 0

    # Sunday, Oct 18 2026 (weekday = 6, not in working days)
    d_sun = date(2026, 10, 18)
    assert len(_slot_times_for_date_cst(d_sun, settings)) == 0
