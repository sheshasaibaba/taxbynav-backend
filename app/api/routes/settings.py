import logging

from app.api.deps import get_current_admin_user, get_session
from app.models.setting import (
    SiteSettingsAdmin,
    SiteSettingsPublic,
    SiteSettingsUpdate,
)
from app.models.user import User
from app.services.settings_service import (
    get_or_create_settings,
    update_settings,
)
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/public", response_model=SiteSettingsPublic)
async def get_public_settings(
    session: AsyncSession = Depends(get_session),
) -> SiteSettingsPublic:
    """Public endpoint returning business address, contact, and working hours for display."""
    item = await get_or_create_settings(session)
    return SiteSettingsPublic(
        business_start_hour=item.business_start_hour,
        business_end_hour=item.business_end_hour,
        slot_duration_minutes=item.slot_duration_minutes,
        working_days=item.working_days,
        blackout_dates=item.blackout_dates,
        timezone=item.timezone,
        contact_address=item.contact_address,
        contact_phone=item.contact_phone,
        contact_email=item.contact_email,
        map_url=item.map_url,
    )


@router.get("/admin", response_model=SiteSettingsAdmin)
async def get_admin_settings(
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_current_admin_user),
) -> SiteSettingsAdmin:
    """Admin endpoint to view full business and availability settings."""
    item = await get_or_create_settings(session)
    return SiteSettingsAdmin(
        id=item.id,
        business_start_hour=item.business_start_hour,
        business_end_hour=item.business_end_hour,
        slot_duration_minutes=item.slot_duration_minutes,
        working_days=item.working_days,
        blackout_dates=item.blackout_dates,
        timezone=item.timezone,
        contact_address=item.contact_address,
        contact_phone=item.contact_phone,
        contact_email=item.contact_email,
        map_url=item.map_url,
        updated_at=item.updated_at,
    )


@router.put("/admin", response_model=SiteSettingsAdmin)
async def update_admin_settings(
    body: SiteSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_current_admin_user),
) -> SiteSettingsAdmin:
    """Admin endpoint to update business address, phone, and time availability."""
    item = await update_settings(session, body)
    logger.info(
        "Admin updated site settings: start=%s, end=%s, address=%s",
        item.business_start_hour,
        item.business_end_hour,
        item.contact_address,
    )
    return SiteSettingsAdmin(
        id=item.id,
        business_start_hour=item.business_start_hour,
        business_end_hour=item.business_end_hour,
        slot_duration_minutes=item.slot_duration_minutes,
        working_days=item.working_days,
        blackout_dates=item.blackout_dates,
        timezone=item.timezone,
        contact_address=item.contact_address,
        contact_phone=item.contact_phone,
        contact_email=item.contact_email,
        map_url=item.map_url,
        updated_at=item.updated_at,
    )
