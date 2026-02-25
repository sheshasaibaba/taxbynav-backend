import logging
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def get_google_authorization_url(state: str | None = None, redirect_uri: str | None = None) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    # State: if redirect_uri given, encode it so callback can redirect there with tokens
    if redirect_uri:
        import base64
        params["state"] = base64.urlsafe_b64encode(redirect_uri.encode()).decode().rstrip("=")
    elif state:
        params["state"] = state
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict | None:
    if not settings.google_client_id or not settings.google_client_secret:
        logger.warning("Google OAuth not configured")
        return None
    if not settings.google_redirect_uri:
        logger.warning("GOOGLE_REDIRECT_URI not set")
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            logger.warning(
                "Google token exchange failed: status=%s body=%s redirect_uri=%s",
                resp.status_code,
                resp.text[:500],
                settings.google_redirect_uri,
            )
            return None
        return resp.json()


async def get_google_user_info(access_token: str) -> dict | None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            return None
        return resp.json()


async def get_or_create_google_user(
    session: AsyncSession, email: str, name: str | None
) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        if not user.is_google_account:
            user.is_google_account = True
            session.add(user)
            await session.flush()
        return user
    user = User(
        email=email,
        full_name=name or email.split("@")[0],
        hashed_password=None,
        is_google_account=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user
