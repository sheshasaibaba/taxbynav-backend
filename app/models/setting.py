from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SiteSettings(SQLModel, table=True):
    __tablename__ = "site_settings"
    id: int = Field(default=1, primary_key=True)
    # Timings in Saskatoon Local Time (CST / America/Regina)
    business_start_hour: int = Field(default=9)
    business_end_hour: int = Field(default=18)
    slot_duration_minutes: int = Field(default=30)
    # Working days: comma-separated 0-6 where 0=Monday, 6=Sunday
    # Default: Monday to Saturday ("0,1,2,3,4,5")
    working_days: str = Field(default="0,1,2,3,4,5")
    # Comma-separated ISO date strings (YYYY-MM-DD) for closures/holidays
    blackout_dates: str = Field(default="")
    timezone: str = Field(default="America/Regina")
    # Contact & Display Details
    contact_address: str = Field(default="Saskatoon, Saskatchewan")
    contact_phone: str = Field(default="306-381-4864")
    contact_email: str = Field(default="jattanaservices@outlook.com")
    map_url: str = Field(default="https://maps.app.goo.gl/U6UWUMCzqQNeqXTs6?g_st=ic")
    updated_at: datetime = Field(default_factory=_utc_now)

    def model_post_init(self, __context: object) -> None:
        if self.updated_at is not None and self.updated_at.tzinfo is None:
            self.updated_at = self.updated_at.replace(tzinfo=UTC)


class SiteSettingsPublic(SQLModel):
    business_start_hour: int
    business_end_hour: int
    slot_duration_minutes: int
    working_days: str
    blackout_dates: str
    timezone: str
    contact_address: str
    contact_phone: str
    contact_email: str
    map_url: str


class SiteSettingsAdmin(SiteSettingsPublic):
    id: int
    updated_at: datetime


class SiteSettingsUpdate(SQLModel):
    business_start_hour: int | None = None
    business_end_hour: int | None = None
    slot_duration_minutes: int | None = None
    working_days: str | None = None
    blackout_dates: str | None = None
    timezone: str | None = None
    contact_address: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    map_url: str | None = None
