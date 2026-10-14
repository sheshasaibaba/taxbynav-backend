from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.models.setting import SiteSettings, SiteSettingsUpdate


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def get_or_create_settings(session: AsyncSession) -> SiteSettings:
    """Retrieve the single SiteSettings record (id=1) or create with defaults."""
    result = await session.execute(select(SiteSettings).where(SiteSettings.id == 1))
    item = result.scalar_one_or_none()
    if item:
        return item

    # Initialize default settings
    item = SiteSettings(
        id=1,
        business_start_hour=app_settings.business_start_hour,
        business_end_hour=app_settings.business_end_hour,
        slot_duration_minutes=app_settings.slot_duration_minutes,
        working_days="0,1,2,3,4,5",  # Mon-Sat default
        blackout_dates="",
        timezone="America/Regina",
        contact_address=app_settings.contact_address,
        contact_phone=app_settings.contact_phone,
        contact_email=app_settings.contact_email,
        map_url="https://maps.app.goo.gl/U6UWUMCzqQNeqXTs6?g_st=ic",
        updated_at=_utc_now(),
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item


async def update_settings(session: AsyncSession, data: SiteSettingsUpdate) -> SiteSettings:
    """Update settings fields."""
    item = await get_or_create_settings(session)
    updates = data.model_dump(exclude_unset=True)
    for field, val in updates.items():
        if val is not None:
            setattr(item, field, val)
    item.updated_at = _utc_now()
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item
