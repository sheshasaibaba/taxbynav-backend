import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Password must be between 8 and 72 characters",
    )
    full_name: str | None = None
    name: str | None = None  # frontend sends "name"; prefer over full_name if both absent

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must include at least one lowercase letter")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must include at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must include at least one number")
        return v


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleCallbackQuery(BaseModel):
    code: str
    state: str | None = None
