/**
 * GlobeView — MapLibre GL JS globe projection, the primary interaction surface.
 *
 * User flow:
 *   1. Click anywhere → creates a ~10km buffered circle AOI, triggers analysis
 *   2. Or use the draw tool → custom polygon AOI
 *   3. Theme tile overlays render on top as SSE results stream in
 *   4. AOI polygon renders on map with fill + dashed outline + centroid label
 */
import { useEffect, useRef, useCallback } from 'react'
import maplibregl, { Map as MapLibreMap, LngLatBoundsLike } from 'maplibre-gl'
import { useAnalysisStore } from '@/store/analysisStore'
import { createAOI } from '@/api/aoi'
import { triggerAnalysis } from '@/api/analysis'
import type { AOI } from '@/types/theme'
import ThemeLayerManager from './ThemeLayerManager'
import DrawControl from './DrawControl'
import TestZonesPanel from './TestZonesPanel'

const STYLE_OBJECT = {
  version: 8,
  sources: {
    'esri-satellite': {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
      ],
      tileSize: 256,
      attribution: 'Esri'
    },
    'esri-labels': {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'
      ],
      tileSize: 256
    }
  },
  layers: [
    {
      id: 'satellite-layer',
      type: 'raster',
      source: 'esri-satellite',
      minzoom: 0,
      maxzoom: 19
    },
    {
      id: 'labels-layer',
      type: 'raster',
      source: 'esri-labels',
      minzoom: 0,
      maxzoom: 19,
      paint: {
        'raster-opacity': 0.65
      }
    }
  ]
}

// ─── AOI Visualization Helpers ───────────────────────────────────────────────

const AOI_SOURCE = 'aoi-source'
const AOI_FILL = 'aoi-fill'
const AOI_OUTLINE = 'aoi-outline'
const AOI_LABEL = 'aoi-label'

/** Remove any existing AOI layers + source from the map */
function clearAOIFromMap(map: MapLibreMap) {
  for (const layerId of [AOI_LABEL, AOI_OUTLINE, AOI_FILL]) {
    if (map.getLayer(layerId)) map.removeLayer(layerId)
  }
  if (map.getSource(AOI_SOURCE)) map.removeSource(AOI_SOURCE)
}

/** Compute the centroid of a polygon's first ring */
function computeCentroid(coords: number[][]): [number, number] {
  let sumLng = 0, sumLat = 0
  // Exclude last point (duplicate of first in closed ring)
  const ring = coords.length > 1 && coords[0][0] === coords[coords.length - 1][0]
    && coords[0][1] === coords[coords.length - 1][1]
    ? coords.slice(0, -1)
    : coords
  for (const [lng, lat] of ring) {
    sumLng += lng
    sumLat += lat
  }
  return [sumLng / ring.length, sumLat / ring.length]
}

/** Compute the bounding box from a polygon's coordinates */
function computeBounds(coords: number[][]): [[number, number], [number, number]] {
  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity
  for (const [lng, lat] of coords) {
    if (lng < minLng) minLng = lng
    if (lat < minLat) minLat = lat
    if (lng > maxLng) maxLng = lng
    if (lat > maxLat) maxLat = lat
  }
  return [[minLng, minLat], [maxLng, maxLat]]
}

/** Render the AOI polygon on the map with fill, dashed outline, and centroid label */
function renderAOIOnMap(map: MapLibreMap, aoi: AOI) {
  clearAOIFromMap(map)

  // Resolve geometry — aoi.geojson can be a Feature or Geometry
  const geojson = aoi.geojson
  if (!geojson) return

  const geometry = 'type' in geojson && geojson.type === 'Feature'
    ? (geojson as GeoJSON.Feature).geometry
    : geojson as GeoJSON.Geometry

  if (geometry.type !== 'Polygon' && geometry.type !== 'MultiPolygon') return

  const coords = geometry.type === 'Polygon'
    ? geometry.coordinates[0]
    : geometry.coordinates[0][0]

  const centroid = computeCentroid(coords as number[][])
  const bounds = computeBounds(coords as number[][])

  // Build label text
  const adminLabel = aoi.admin_level1 || aoi.country_code || ''
  const areaLabel = aoi.area_km2 != null ? `${aoi.area_km2.toFixed(1)} km²` : ''
  const labelText = [areaLabel, adminLabel].filter(Boolean).join(' · ')

  // Add GeoJSON source with both the polygon and centroid point
  map.addSource(AOI_SOURCE, {
    type: 'geojson',
    data: {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry
        },
        {
          type: 'Feature',
          properties: { label: labelText },
          geometry: { type: 'Point', coordinates: centroid }
        }
      ]
    }
  })

  // Fill layer — semi-transparent blue
  map.addLayer({
    id: AOI_FILL,
    type: 'fill',
    source: AOI_SOURCE,
    filter: ['==', '$type', 'Polygon'],
    paint: {
      'fill-color': 'rgba(30, 136, 229, 0.15)',
    }
  })

  // Outline layer — dashed sentinel blue
  map.addLayer({
    id: AOI_OUTLINE,
    type: 'line',
    source: AOI_SOURCE,
    filter: ['==', '$type', 'Polygon'],
    paint: {
      'line-color': '#1E88E5',
      'line-width': 2,
      'line-dasharray': [6, 3],
    }
  })

  // Label layer — centroid text
  map.addLayer({
    id: AOI_LABEL,
    type: 'symbol',
    source: AOI_SOURCE,
    filter: ['==', '$type', 'Point'],
    layout: {
      'text-field': ['get', 'label'],
      'text-size': 12,
      'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
      'text-anchor': 'top',
      'text-offset': [0, 0.8],
      'text-allow-overlap': true,
    },
    paint: {
      'text-color': '#E3F2FD',
      'text-halo-color': 'rgba(0, 0, 0, 0.7)',
      'text-halo-width': 1.5,
    }
  })

  // Structured console log
  console.log('[GCAIP AOI]', {
    aoi_id: aoi.aoi_id,
    name: aoi.name,
    area_km2: aoi.area_km2,
    bounds: [bounds[0][0], bounds[0][1], bounds[1][0], bounds[1][1]],
    centroid: [centroid[0], centroid[1]],
    admin: `${aoi.admin_level1 || '—'}, ${aoi.country_code || '—'}`,
  })

  // Auto-fit map to AOI bounds
  map.fitBounds(bounds as LngLatBoundsLike, {
    padding: 80,
    duration: 800,
  })
}

// ─── Buffer Point Helper ─────────────────────────────────────────────────────

// Approximate a circular polygon around a clicked point (in degrees)
function bufferPoint(lon: number, lat: number, radiusKm = 10): GeoJSON.Feature {
  const points = 48
  const coords: [number, number][] = []
  const earthRadiusKm = 6371
  for (let i = 0; i <= points; i++) {
    const angle = (i / points) * 2 * Math.PI
    const dx = (radiusKm / earthRadiusKm) * Math.cos(angle) * (180 / Math.PI)
    const dy = (radiusKm / earthRadiusKm) * Math.sin(angle) * (180 / Math.PI)
    coords.push([lon + dx / Math.cos((lat * Math.PI) / 180), lat + dy])
  }
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'Polygon', coordinates: [coords] },
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function GlobeView() {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)

  const setSelectedAOI = useAnalysisStore((s) => s.setSelectedAOI)
  const startAnalysis = useAnalysisStore((s) => s.startAnalysis)
  const setError = useAnalysisStore((s) => s.setError)
  const reset = useAnalysisStore((s) => s.reset)
  const setSelectedPreset = useAnalysisStore((s) => s.setSelectedPreset)

  const handleAOISubmit = useCallback(
    async (geojson: GeoJSON.Feature, presetZone?: import('@/data/presetZones').PresetZone) => {
      try {
        reset()

        // Restore preset zone AFTER reset (reset clears it)
        if (presetZone) {
          setSelectedPreset(presetZone)
        } else {
          setSelectedPreset(null)
        }

        console.log('[GCAIP] createAOI request:', { type: geojson.type, geometry_type: geojson.geometry?.type })
        const aoi = await createAOI(geojson)
        console.log('[GCAIP] createAOI response:', { aoi_id: aoi.aoi_id, area_km2: aoi.area_km2 })
        setSelectedAOI(aoi)

        // Render the AOI on the map
        if (mapRef.current) {
          renderAOIOnMap(mapRef.current, aoi)
        }

        console.log('[GCAIP] triggerAnalysis request:', { aoi_id: aoi.aoi_id })
        const { job_id } = await triggerAnalysis({ aoi_id: aoi.aoi_id })
        console.log('[GCAIP] triggerAnalysis response:', { job_id })
        startAnalysis(job_id)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to start analysis'
        console.error('[GCAIP] handleAOISubmit error:', message, err)
        setError(message)
      }
    },
    [reset, setSelectedAOI, startAnalysis, setError, setSelectedPreset],
  )

  // Clean up AOI layers when the analysis panel is closed (reset)
  useEffect(() => {
    const unsub = useAnalysisStore.subscribe((state, prevState) => {
      // Detect reset: selectedAOI went from non-null to null
      if (prevState.selectedAOI && !state.selectedAOI && mapRef.current) {
        clearAOIFromMap(mapRef.current)
      }
    })
    return unsub
  }, [])

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: STYLE_OBJECT as any,
      center: [78.9629, 20.5937], // Default: India — adjust per deployment
      zoom: 3,
      projection: 'globe' as any, // MapLibre v4 globe projection
      attributionControl: false,
    } as any)

    map.on('style.load', () => {
      // MapLibre v4 fog for globe atmosphere effect
      ;(map as any).setFog?.({
        range: [0.5, 10],
        color: '#08101C',
        'horizon-blend': 0.1,
        'high-color': '#112244',
        'space-color': '#030710',
        'star-intensity': 0.4,
      })
    })

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'bottom-right')

    // Click-to-AOI: single click creates a 10km buffer circle if in 'point' mode
    map.on('click', (e) => {
      const target = e.originalEvent.target as HTMLElement
      // Ignore clicks on draw tool vertices/controls
      if (target.closest('.maplibregl-ctrl')) return
      
      const mode = useAnalysisStore.getState().interactionMode
      if (mode === 'point') {
        const feature = bufferPoint(e.lngLat.lng, e.lngLat.lat, 10)
        handleAOISubmit(feature)
        useAnalysisStore.getState().setInteractionMode('navigate')
      }
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="absolute inset-0">
      <div ref={mapContainerRef} className="h-full w-full" />
      {mapRef.current && (
        <>
          <DrawControl map={mapRef.current} onAOISubmit={handleAOISubmit} />
          <TestZonesPanel map={mapRef.current} onAOISubmit={handleAOISubmit} />
          <ThemeLayerManager map={mapRef.current} />
        </>
      )}
    </div>
  )
}
