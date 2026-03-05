from fastapi import APIRouter, HTTPException

from app.services.reviews_service import get_google_reviews

router = APIRouter(tags=["reviews"])


@router.get("/reviews")
async def reviews():
    """Return Google Place reviews (cached 1 h). No auth required."""
    try:
        return await get_google_reviews()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch Google reviews: {exc}",
        )
