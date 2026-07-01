"""
AOI endpoints — create, read, list, delete areas of interest.
AOI size enforcement: 500km² anonymous, 2000km² registered.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape, mapping
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from config import settings
from models.aoi import AOI
from schemas.aoi import AOICreateRequest, AOIListResponse, AOIResponse

router = APIRouter()


async def _geojson_to_shape(geojson: dict):
    """Convert GeoJSON to Shapely shape, handling Feature wrapper."""
    geo = geojson
    if geo.get("type") == "Feature":
        geo = geo["geometry"]
    elif geo.get("type") == "FeatureCollection":
        features = geo.get("features", [])
        if not features:
            raise HTTPException(400, "FeatureCollection has no features")
        geo = features[0]["geometry"]
    return shape(geo)


@router.post("/aoi", response_model=AOIResponse, status_code=201)
async def create_aoi(
    body: AOICreateRequest,
    db: AsyncSession = Depends(get_db),
) -> AOIResponse:
    """
    Create a new Area of Interest from GeoJSON.
    Computes area, enforces size limits, stores geometry in PostGIS.
    """
    geom_shape = await _geojson_to_shape(body.geojson)

    # Area check (rough degrees → km² via haversine is complex; use UTM-projected area)
    # Shapely uses degrees for WGS84; multiply by ~111km per degree for crude estimate
    # For production, use pyproj CRS transform. This is a sufficient MVP estimate.
    bounds = geom_shape.bounds
    lat_mid = (bounds[1] + bounds[3]) / 2
    import math
    km_per_deg_lon = 111.32 * math.cos(math.radians(lat_mid))
    km_per_deg_lat = 111.0
    width_km = (bounds[2] - bounds[0]) * km_per_deg_lon
    height_km = (bounds[3] - bounds[1]) * km_per_deg_lat
    area_km2 = geom_shape.area * km_per_deg_lon * km_per_deg_lat

    max_area = settings.GEE_AOI_MAX_KM2_ANON  # TODO: use user tier
    if area_km2 > max_area:
        raise HTTPException(
            400,
            f"AOI area {area_km2:.0f} km² exceeds limit of {max_area:.0f} km².",
        )

    # Reverse geocode for admin metadata (non-blocking best-effort)
    country_code, admin1, admin2 = None, None, None
    try:
        from integrations.nominatim import reverse_geocode
        centroid = geom_shape.centroid
        geo_info = await reverse_geocode(centroid.y, centroid.x)
        country_code = geo_info.get("country_code", "").upper()[:2]
        admin1 = geo_info.get("state") or geo_info.get("region")
        admin2 = geo_info.get("county") or geo_info.get("district")
    except Exception:
        pass  # Admin info is nice-to-have, not required

    aoi = AOI(
        name=body.name,
        geom=from_shape(geom_shape, srid=4326),
        bbox=from_shape(geom_shape.envelope, srid=4326),
        area_km2=round(area_km2, 2),
        country_code=country_code,
        admin_level1=admin1,
        admin_level2=admin2,
        is_public=False,
    )
    db.add(aoi)
    await db.commit()
    await db.refresh(aoi)

    return _aoi_to_response(aoi)


@router.get("/aoi/{aoi_id}", response_model=AOIResponse)
async def get_aoi(
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AOIResponse:
    """Fetch a single AOI by ID."""
    result = await db.execute(select(AOI).where(AOI.id == aoi_id))
    aoi = result.scalar_one_or_none()
    if not aoi:
        raise HTTPException(404, f"AOI {aoi_id} not found")
    return _aoi_to_response(aoi)


@router.get("/aoi", response_model=AOIListResponse)
async def list_aois(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
) -> AOIListResponse:
    """List AOIs (paginated). Future: filter by user."""
    offset = (page - 1) * page_size
    count_result = await db.execute(select(func.count(AOI.id)))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(AOI).order_by(AOI.created_at.desc()).offset(offset).limit(page_size)
    )
    aois = result.scalars().all()

    return AOIListResponse(
        items=[_aoi_to_response(a) for a in aois],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/aoi/{aoi_id}", status_code=204)
async def delete_aoi(
    aoi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(AOI).where(AOI.id == aoi_id))
    aoi = result.scalar_one_or_none()
    if not aoi:
        raise HTTPException(404, f"AOI {aoi_id} not found")
    await db.delete(aoi)
    await db.commit()


def _aoi_to_response(aoi: AOI) -> AOIResponse:
    geojson = None
    if aoi.geom is not None:
        try:
            geojson = mapping(to_shape(aoi.geom))
        except Exception:
            pass
    return AOIResponse(
        aoi_id=aoi.id,
        name=aoi.name,
        area_km2=aoi.area_km2,
        country_code=aoi.country_code,
        admin_level1=aoi.admin_level1,
        admin_level2=aoi.admin_level2,
        created_at=aoi.created_at,
        geojson=geojson,
    )
