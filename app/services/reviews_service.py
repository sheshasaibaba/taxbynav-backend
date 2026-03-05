"""
Fetches Google Place reviews via the Places Details API and caches the result
in-memory for CACHE_TTL seconds so we don't burn API quota on every page load.
"""
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL = 3600  # 1 hour

_cache: dict[str, Any] = {}
_cache_ts: float = 0.0


async def get_google_reviews() -> dict[str, Any]:
    global _cache, _cache_ts

    now = time.monotonic()
    if _cache and (now - _cache_ts) < CACHE_TTL:
        return _cache

    if not settings.google_places_api or not settings.google_places_id:
        logger.warning("Google Places not configured; returning empty reviews.")
        return {"rating": None, "user_ratings_total": 0, "reviews": []}

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": settings.google_places_id,
        "fields": "rating,user_ratings_total,reviews",
        "reviews_sort": "most_relevant",
        "key": settings.google_places_api,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    status = data.get("status")
    if status != "OK":
        error_msg = data.get("error_message", "no details")
        logger.error("Google Places API error — status: %s, message: %s", status, error_msg)
        return {"rating": None, "user_ratings_total": 0, "reviews": []}

    result = data.get("result", {})
    reviews_raw = result.get("reviews", [])

    reviews = [
        {
            "author_name": r.get("author_name", ""),
            "author_url": r.get("author_url", ""),
            "profile_photo_url": r.get("profile_photo_url", ""),
            "rating": r.get("rating", 0),
            "text": r.get("text", ""),
            "relative_time_description": r.get("relative_time_description", ""),
            "time": r.get("time", 0),
        }
        for r in reviews_raw
    ]

    _cache = {
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total", 0),
        "reviews": reviews,
    }
    _cache_ts = now
    logger.info(
        "Google Reviews refreshed: %.1f stars, %d reviews",
        _cache["rating"] or 0,
        len(reviews),
    )
    return _cache
