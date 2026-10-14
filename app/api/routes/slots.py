from datetime import date, timedelta

from app.api.deps import get_session
from app.api.schemas.appointment import AvailableSlotsResponse, SlotInfo
from app.core.time_utils import format_cst_time
from app.services.settings_service import get_or_create_settings
from app.services.slot_service import get_available_slots_for_date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("/available", response_model=AvailableSlotsResponse)
async def available_slots(
    date_param: date = Query(..., alias="date"),
    session: AsyncSession = Depends(get_session),
) -> AvailableSlotsResponse:
    """Return all slots for the given date in Saskatoon CST. Each slot has start_utc, end_utc, available, and CST formatted labels."""
    site_settings = await get_or_create_settings(session)
    duration = site_settings.slot_duration_minutes
    slots_with_availability = await get_available_slots_for_date(session, date_param, user_id=None)

    slot_infos = [
        SlotInfo(
            start_utc=s,
            end_utc=s + timedelta(minutes=duration),
            available=avail,
            start_cst=format_cst_time(s),
            end_cst=format_cst_time(s + timedelta(minutes=duration)),
        )
        for s, avail in slots_with_availability
    ]
    return AvailableSlotsResponse(
        date=date_param.isoformat(),
        timezone="America/Regina",
        slots=slot_infos,
    )
