/**
 * ThemeLayerManager — adds/removes MapLibre raster sources for each theme's
 * GEE tile_url as results stream in. Visibility toggled via mapLayerVisible store.
 */
import { useEffect, useRef } from 'react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import { useAnalysisStore } from '@/store/analysisStore'
import type { ThemeId } from '@/types/theme'

interface Props {
  map: MapLibreMap
}

export default function ThemeLayerManager({ map }: Props) {
  const themeResults = useAnalysisStore((s) => s.themeResults)
  const mapLayerVisible = useAnalysisStore((s) => s.mapLayerVisible)
  const addedLayersRef = useRef<Set<ThemeId>>(new Set())

  useEffect(() => {
    if (!map) return

    Object.entries(themeResults).forEach(([themeKey, result]) => {
      const theme = themeKey as ThemeId
      if (!result?.tile_url || result.error_message) return

      const sourceId = `gee-${theme}`
      const layerId = `gee-layer-${theme}`

      if (!addedLayersRef.current.has(theme)) {
        // Defensive: only add if map style is loaded
        if (!map.isStyleLoaded()) return

        try {
          map.addSource(sourceId, {
            type: 'raster',
            tiles: [result.tile_url],
            tileSize: 256,
          })
          map.addLayer({
            id: layerId,
            type: 'raster',
            source: sourceId,
            paint: { 'raster-opacity': 0.75 },
          })
          addedLayersRef.current.add(theme)
        } catch (err) {
          console.warn(`Failed to add layer for ${theme}:`, err)
        }
      }

      // Sync visibility
      if (map.getLayer(layerId)) {
        const visible = mapLayerVisible[theme] ?? true
        map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
      }
    })
  }, [map, themeResults, mapLayerVisible])

  // Cleanup all GEE layers when AOI resets (themeResults goes empty)
  useEffect(() => {
    if (!map) return
    if (Object.keys(themeResults).length === 0) {
      addedLayersRef.current.forEach((theme) => {
        const layerId = `gee-layer-${theme}`
        const sourceId = `gee-${theme}`
        if (map.getLayer(layerId)) map.removeLayer(layerId)
        if (map.getSource(sourceId)) map.removeSource(sourceId)
      })
      addedLayersRef.current.clear()
    }
  }, [map, themeResults])

  return null
}
