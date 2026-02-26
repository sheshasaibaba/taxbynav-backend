from datetime import UTC, datetime
from sqlmodel import Field, SQLModel


def _utc_naive_now() -> datetime:
    """Naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class Appointment(SQLModel, table=True):
    __tablename__ = "appointments"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    slot_start_utc: datetime = Field(unique=True, index=True)  # no overlapping slots
    message: str | None = None
    created_at: datetime = Field(default_factory=_utc_naive_now)


class AppointmentCreate(SQLModel):
    slot_start_utc: datetime
    message: str | None = None


class AppointmentPublic(SQLModel):
    id: int
    user_id: int
    slot_start_utc: datetime
    message: str | None = None
    created_at: datetime


class AppointmentAdminPublic(SQLModel):
    id: int
    user_id: int
    user_email: str
    user_full_name: str | None = None
    slot_start_utc: datetime
    message: str | None = None
    created_at: datetime
