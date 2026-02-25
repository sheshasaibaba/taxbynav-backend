from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserCreate, UserPublic


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        is_google_account=False,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


def user_to_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_google_account=user.is_google_account,
    )


def make_token_pair(user_id: int) -> tuple[str, str, int]:
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    expires_in = settings.access_token_expire_minutes * 60
    return access, refresh, expires_in


def _utc_naive() -> datetime:
    """Naive UTC datetime for DB columns that are TIMESTAMP WITHOUT TIME ZONE."""
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(dt: datetime) -> datetime:
    """Ensure datetime is naive UTC for DB (strip or convert to UTC and strip)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.replace(tzinfo=None)


async def store_refresh_token(
    session: AsyncSession, user_id: int, refresh_token: str
) -> None:
    user_id_str, jti = decode_refresh_token(refresh_token)
    if not user_id_str or not jti:
        return
    expires_at = _naive_utc(datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days))
    token_row = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
    session.add(token_row)
    await session.flush()


async def login_user(
    session: AsyncSession, email: str, password: str
) -> tuple[User, str, str, int] | None:
    user = await get_user_by_email(session, email)
    if not user or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    access, refresh, expires_in = make_token_pair(user.id)
    await store_refresh_token(session, user_id=user.id, refresh_token=refresh)
    return user, access, refresh, expires_in


async def signup_user(
    session: AsyncSession, email: str, password: str, full_name: str | None = None
) -> tuple[User, str, str, int] | None:
    existing = await get_user_by_email(session, email)
    if existing:
        return None
    user = await create_user(
        session, UserCreate(email=email, password=password, full_name=full_name)
    )
    access, refresh, expires_in = make_token_pair(user.id)
    await store_refresh_token(session, user_id=user.id, refresh_token=refresh)
    return user, access, refresh, expires_in


async def revoke_refresh_token(session: AsyncSession, jti: str) -> None:
    result = await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    row = result.scalar_one_or_none()
    if row:
        row.revoked = True
        session.add(row)


async def refresh_tokens(
    session: AsyncSession, refresh_token: str
) -> tuple[User, str, str, int] | None:
    user_id_str, jti = decode_refresh_token(refresh_token)
    if not user_id_str or not jti:
        return None
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.jti == jti,
            RefreshToken.revoked == False,  # noqa: E712
            RefreshToken.expires_at > _utc_naive(),
        )
    )
    token_row = result.scalar_one_or_none()
    if not token_row:
        return None
    result = await session.execute(select(User).where(User.id == int(user_id_str)))
    user = result.scalar_one_or_none()
    if not user:
        return None
    token_row.revoked = True
    session.add(token_row)
    access, refresh, expires_in = make_token_pair(user.id)
    await store_refresh_token(session, user_id=user.id, refresh_token=refresh)
    return user, access, refresh, expires_in
