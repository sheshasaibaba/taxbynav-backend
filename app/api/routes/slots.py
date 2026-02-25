from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.appointment import AvailableSlotsResponse, SlotInfo
from app.core.config import settings
from app.services.slot_service import get_available_slots_for_date

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("/available", response_model=AvailableSlotsResponse)
async def available_slots(
    date_param: date = Query(..., alias="date"),
    session: AsyncSession = Depends(get_session),
) -> AvailableSlotsResponse:
    """Return all slots for the given date (UTC). Each slot has start_utc, end_utc, and available (bool)."""
    slots_with_availability = await get_available_slots_for_date(session, date_param, user_id=None)
    slot_infos = [
        SlotInfo(
            start_utc=s,
            end_utc=s + timedelta(minutes=settings.slot_duration_minutes),
            available=avail,
        )
        for s, avail in slots_with_availability
    ]
    return AvailableSlotsResponse(
        date=date_param.isoformat(),
        slots=slot_infos,
    )