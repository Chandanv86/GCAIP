/**
 * Pipeline search API — fetches OSM/Overpass pipeline vector geometries
 * for a given bounding box from the backend /api/v1/pipelines/search endpoint.
 */
import { api } from './client'

export interface PipelineSearchParams {
  min_lon: number
  min_lat: number
  max_lon: number
  max_lat: number
}

/**
 * Search for pipeline geometries within a bounding box.
 * Returns a GeoJSON FeatureCollection of pipeline centerlines.
 * Results are cached server-side for 24h via Overpass + Redis.
 */
export async function searchPipelines(
  params: PipelineSearchParams,
): Promise<GeoJSON.FeatureCollection> {
  const q = new URLSearchParams({
    min_lon: String(params.min_lon),
    min_lat: String(params.min_lat),
    max_lon: String(params.max_lon),
    max_lat: String(params.max_lat),
  })
  return api.get<GeoJSON.FeatureCollection>(`/pipelines/search?${q}`)
}
