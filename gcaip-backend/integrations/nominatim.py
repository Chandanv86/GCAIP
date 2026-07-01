"""Nominatim reverse geocoder — admin boundary lookup for AOI creation."""
import httpx
from config import settings


async def reverse_geocode(lat: float, lon: float) -> dict:
    """
    Reverse geocode a point to get admin info.
    Uses OpenStreetMap Nominatim (free, no API key).
    """
    url = f"{settings.NOMINATIM_BASE_URL}/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "addressdetails": 1,
    }
    headers = {"User-Agent": "GCAIP/1.0 (contact@gcaip.io)"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        address = data.get("address", {})
        return {
            "country_code": address.get("country_code", "").upper(),
            "country": address.get("country"),
            "state": address.get("state") or address.get("region"),
            "county": address.get("county") or address.get("district"),
            "display_name": data.get("display_name", ""),
        }
