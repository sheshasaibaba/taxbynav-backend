from datetime import datetime

from pydantic import BaseModel


class SlotInfo(BaseModel):
    start_utc: datetime
    end_utc: datetime
    available: bool
    start_cst: str | None = None  # Formatted Saskatoon local time e.g. "09:00 AM CST"
    end_cst: str | None = None


class AvailableSlotsResponse(BaseModel):
    date: str  # YYYY-MM-DD
    timezone: str = "America/Regina"
    slots: list[SlotInfo]


class BookAppointmentRequest(BaseModel):
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None
    service_type: str | None = None
    phone_number: str | None = None


class AdminBookAppointmentRequest(BaseModel):
    """Admin creates a booking for a user by email (account or guest)."""

    guest_email: str
    slot_start_utc: datetime
    guest_full_name: str | None = None
    message: str | None = None
    contact_mode: str | None = None
    service_type: str | None = None
    phone_number: str | None = None


class AppointmentRescheduleRequest(BaseModel):
    slot_start_utc: datetime


class AppointmentStatusUpdateRequest(BaseModel):
    status: str  # scheduled, completed, cancelled, no_show
