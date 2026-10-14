from datetime import UTC, datetime, timedelta
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """Hash password with bcrypt; safely truncates to 72 bytes per bcrypt standard."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash; safely handles byte encoding and truncation."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


def create_access_token(subject: str | int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": str(subject), "exp": expire, "type": "access"}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str | int) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid4()),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "access":
            return None
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None


def decode_refresh_token(token: str) -> tuple[str | None, str | None]:
    """Returns (user_id_str, jti) or (None, None)."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "refresh":
            return None, None
        return payload.get("sub"), payload.get("jti")
    except JWTError:
        return None, None
