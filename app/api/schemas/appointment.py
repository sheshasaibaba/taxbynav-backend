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
