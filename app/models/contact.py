from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utc_naive_now() -> datetime:
    """Naive UTC for TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class ContactInquiry(SQLModel, table=True):
    __tablename__ = "contact_inquiries"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    email: str = Field(index=True, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    subject: str = Field(max_length=255)
    message: str
    status: str = Field(default="new", max_length=50)  # new, read, resolved
    created_at: datetime = Field(default_factory=_utc_naive_now)


class ContactInquiryCreate(SQLModel):
    name: str
    email: str
    phone: str | None = None
    subject: str
    message: str


class ContactInquiryPublic(SQLModel):
    id: int
    name: str
    email: str
    phone: str | None = None
    subject: str
    message: str
    status: str
    created_at: datetime


class ContactInquiryStatusUpdate(SQLModel):
    status: str  # new, read, resolved
