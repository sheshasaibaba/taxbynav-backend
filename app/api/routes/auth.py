import base64
import logging
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

from app.api.deps import get_current_user, refresh_header
from app.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)
from app.core.db import get_session
from app.core.security import decode_refresh_token
from app.models.user import User, UserPublic
from app.services.auth_service import (
    login_user,
    signup_user,
    refresh_tokens,
    revoke_refresh_token,
    user_to_public,
)
from app.services.google_auth_service import (
    exchange_code_for_tokens,
    get_google_authorization_url,
    get_google_user_info,
    get_or_create_google_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    pair = await login_user(session, body.email, body.password)
    if not pair:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    user, access, refresh, expires_in = pair
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
    )


@router.post("/signup", response_model=TokenPair)
async def signup(
    body: SignupRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    full_name = body.full_name or body.name
    pair = await signup_user(
        session, body.email, body.password, full_name
    )
    if not pair:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    user, access, refresh, expires_in = pair
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    session: AsyncSession = Depends(get_session),
    x_refresh_token: str | None = Depends(refresh_header),
    body: RefreshRequest | None = None,
) -> TokenPair:
    token = x_refresh_token or (body.refresh_token if body else None)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required (header X-Refresh-Token or body refresh_token)",
        )
    pair = await refresh_tokens(session, token)
    if not pair:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user, access, refresh, expires_in = pair
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
    )


@router.post("/logout")
async def logout(
    session: AsyncSession = Depends(get_session),
    x_refresh_token: str | None = Depends(refresh_header),
    body: RefreshRequest | None = None,
) -> dict:
    token = x_refresh_token or (body.refresh_token if body else None)
    if token:
        _, jti = decode_refresh_token(token)
        if jti:
            await revoke_refresh_token(session, jti)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return user_to_public(current_user)


# --- Google SSO ---

def _is_allowed_redirect_uri(redirect_uri: str) -> bool:
    """Allow only redirect URIs under configured CORS origins."""
    for origin in settings.cors_origins_list:
        if redirect_uri == origin or redirect_uri.startswith(origin.rstrip("/") + "/"):
            return True
    return False


def _decode_redirect_uri(state: str | None) -> str | None:
    """Decode state (base64url) to frontend redirect_uri; validate against CORS origins."""
    if not state:
        return None
    try:
        padded = state + "=" * (4 - len(state) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        redirect_uri = decoded.decode()
    except Exception:
        return None
    return redirect_uri if _is_allowed_redirect_uri(redirect_uri) else None


@router.get("/google")
async def google_login(
    redirect_uri: str | None = Query(None, alias="redirect_uri"),
    state: str | None = Query(None),
):
    # If redirect_uri given and allowed, redirect to Google (for browser / button flow)
    if redirect_uri and _is_allowed_redirect_uri(redirect_uri):
        url = get_google_authorization_url(redirect_uri=redirect_uri)
        return RedirectResponse(url=url, status_code=302)
    url = get_google_authorization_url(
        redirect_uri=redirect_uri,
        state=state or str(uuid4()) if not redirect_uri else None,
    )
    return {"authorization_url": url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., alias="code"),
    state: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    try:
        logger.info("Google callback: step 1 exchange_code_for_tokens")
        tokens = await exchange_code_for_tokens(code)
        if not tokens:
            logger.warning("Google token exchange failed or returned None")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code with Google. Check GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI match Google Console.",
            )
        access_token = tokens.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token from Google",
            )
        logger.info("Google callback: step 2 get_google_user_info")
        info = await get_google_user_info(access_token)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google",
            )
        email = info.get("email")
        name = info.get("name")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account has no email",
            )
        logger.info("Google callback: step 3 get_or_create_google_user email=%s", email)
        user = await get_or_create_google_user(session, email=email, name=name)
        from app.services.auth_service import make_token_pair, store_refresh_token

        logger.info("Google callback: step 4 make_token_pair user_id=%s", getattr(user, "id", None))
        access, refresh, expires_in = make_token_pair(user.id)
        await store_refresh_token(session, user_id=user.id, refresh_token=refresh)

        logger.info("Google callback: step 5 redirect")
        frontend_redirect = _decode_redirect_uri(state)
        if frontend_redirect:
            fragment = urlencode({
                "access_token": access,
                "refresh_token": refresh,
                "expires_in": str(expires_in),
            })
            return RedirectResponse(url=f"{frontend_redirect}#{fragment}", status_code=302)

        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=expires_in,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Google OAuth callback error: %s", e)
        detail = f"Google sign-in failed: {type(e).__name__}: {str(e)}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        ) from e
