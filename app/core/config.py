from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from backend project root (taxbynav-backend/) so it loads regardless of cwd
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str

    # JWT
    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # Slot/appointment business rules
    slot_duration_minutes: int = 30
    business_start_hour: int = 9
    business_end_hour: int = 17  # exclusive, so last slot ends at 17:00
    max_slots_per_user_per_day: int = 1
    # Delete appointments 3 days after booking so no excess data remains
    appointment_retention_days: int = 3

    # Env
    env: str = "development"

    # Email (Gmail SMTP). Leave smtp_host empty to disable sending.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str = ""
    from_name: str = "TaxByNav"
    # Public URL for logo in emails (e.g. https://yoursite.com/assets/images/logoNoName.PNG)
    email_logo_url: str = ""
    # Branding and contact in footer
    site_name: str = "TaxByNav"
    contact_email: str = "contact@taxbynav.com"
    contact_phone: str = "306-381-4864"
    contact_address: str = "Saskatoon, Saskatchewan"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.from_email)


settings = Settings()
