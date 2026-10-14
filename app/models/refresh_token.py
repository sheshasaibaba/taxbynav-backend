from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime has UTC timezone for asyncpg TIMESTAMPTZ."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    jti: str = Field(unique=True, index=True)
    expires_at: datetime = Field(index=True)
    revoked: bool = False

    def model_post_init(self, __context: object) -> None:
        """Ensure expires_at has UTC tzinfo for asyncpg TIMESTAMP WITH TIME ZONE."""
        if self.expires_at is not None:
            self.expires_at = _ensure_utc(self.expires_at)


class RefreshTokenCreate(SQLModel):
    user_id: int
    jti: str
    expires_at: datetime
