from datetime import UTC, datetime
from sqlmodel import Field, SQLModel


def _naive_utc(dt: datetime) -> datetime:
    """For TIMESTAMP WITHOUT TIME ZONE: store as naive UTC."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.replace(tzinfo=None)


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    jti: str = Field(unique=True, index=True)
    expires_at: datetime = Field(index=True)
    revoked: bool = False

    def model_post_init(self, __context: object) -> None:
        """Ensure expires_at is naive UTC for asyncpg TIMESTAMP WITHOUT TIME ZONE."""
        if self.expires_at is not None:
            self.expires_at = _naive_utc(self.expires_at)


class RefreshTokenCreate(SQLModel):
    user_id: int
    jti: str
    expires_at: datetime
