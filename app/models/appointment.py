from datetime import UTC, datetime
from sqlmodel import Field, SQLModel


def _utc_naive_now() -> datetime:
    """Naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    guest_email: str | None = Field(default=None, index=True)
    guest_full_name: str | None = None
    slot_start_utc: datetime = Field(unique=True, index=True)  # no overlapping slots
    message: str | None = None
    contact_mode: str | None = Field(default=None, max_length=50)
    created_at: datetime = Field(default_factory=_utc_naive_now)


class AppointmentCreate(SQLModel):
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None


class AppointmentPublic(SQLModel):
    id: int
    user_id: int | None = None
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None
    created_at: datetime


class AppointmentAdminPublic(SQLModel):
    id: int
    user_id: int | None = None
    user_email: str
    user_full_name: str | None = None
    slot_start_utc: datetime
    message: str | None = None
    contact_mode: str | None = None
    created_at: datetime
