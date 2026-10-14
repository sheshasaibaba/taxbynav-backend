from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    guest_email: str | None = Field(default=None, index=True)
    guest_full_name: str | None = None
    slot_start_utc: datetime = Field(unique=True, index=True)  # no overlapping slots
    message: str | None = None
    contact_mode: str | None = Field(default=None, max_length=50)
    service_type: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=50)
    status: str = Field(
        default="scheduled", max_length=50
    )  # scheduled, rescheduled, completed, cancelled, no_show
    created_at: datetime = Field(default_factory=_utc_now)

    def model_post_init(self, __context: object) -> None:
        if self.slot_start_utc is not None and self.slot_start_utc.tzinfo is None:
            self.slot_start_utc = self.slot_start_utc.replace(tzinfo=UTC)
        if self.created_at is not None and self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)


class AppointmentCreate(SQLModel):
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None
    service_type: str | None = None
    phone_number: str | None = None


class AppointmentPublic(SQLModel):
    id: int
    user_id: int | None = None
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None
    service_type: str | None = None
    phone_number: str | None = None
    status: str = "scheduled"
    created_at: datetime


class AppointmentAdminPublic(SQLModel):
    id: int
    user_id: int | None = None
    user_email: str
    user_full_name: str | None = None
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None
    service_type: str | None = None
    phone_number: str | None = None
    status: str = "scheduled"
    created_at: datetime


class AppointmentRescheduleRequest(SQLModel):
    slot_start_utc: datetime


class AppointmentStatusUpdateRequest(SQLModel):
    status: str  # scheduled, completed, cancelled, no_show
