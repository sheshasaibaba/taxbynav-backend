from datetime import datetime
from pydantic import BaseModel


class SlotInfo(BaseModel):
    start_utc: datetime
    end_utc: datetime
    available: bool


class AvailableSlotsResponse(BaseModel):
    date: str  # YYYY-MM-DD
    slots: list[SlotInfo]


class BookAppointmentRequest(BaseModel):
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None
    phone_number: str | None = None


class AdminBookAppointmentRequest(BaseModel):
    """Admin creates a booking for a user by email (account or guest)."""
    guest_email: str
    slot_start_utc: datetime
    guest_full_name: str | None = None
    message: str | None = None
    contact_mode: str | None = None
