import { api } from './client'
import type { AOI } from '@/types/theme'

export async function createAOI(geojson: GeoJSON.Feature | GeoJSON.Geometry, name?: string): Promise<AOI> {
  return api.post<AOI>('/aoi', { geojson, name })
}

export async function getAOI(aoiId: string): Promise<AOI> {
  return api.get<AOI>(`/aoi/${aoiId}`)
}

export async function listAOIs(page = 1, pageSize = 20): Promise<{ items: AOI[]; total: number }> {
  return api.get(`/aoi?page=${page}&page_size=${pageSize}`)
}

export async function deleteAOI(aoiId: string): Promise<void> {
  return api.delete(`/aoi/${aoiId}`)
}
