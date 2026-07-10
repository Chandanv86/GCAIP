/**
 * ThemeLayerManager — adds/removes MapLibre raster sources for each theme's
 * GEE tile_url as results stream in. Visibility toggled via mapLayerVisible store.
 */
import { useEffect, useRef } from 'react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import { useAnalysisStore } from '@/store/analysisStore'
import type { ThemeId, ThemeResult } from '@/types/theme'
import { API_BASE } from '@/api/client'

interface Props {
  map: MapLibreMap
}

export default function ThemeLayerManager({ map }: Props) {
  const themeResults = useAnalysisStore((s) => s.themeResults)
  const mapLayerVisible = useAnalysisStore((s) => s.mapLayerVisible)
  const setThemeResult = useAnalysisStore((s) => s.setThemeResult)
  const addedLayersRef = useRef<Map<ThemeId, string>>(new Map())

  // Tile expiry check loop
  useEffect(() => {
    const interval = setInterval(() => {
      Object.entries(useAnalysisStore.getState().themeResults).forEach(([themeKey, result]) => {
        if (!result || !result.tile_url || !result.tile_url_expires_at || !result.result_id) return
        
        const expiry = new Date(result.tile_url_expires_at).getTime()
        const now = Date.now()
        // If expiring in < 5 minutes, refresh
        if (expiry - now < 5 * 60 * 1000) {
           fetch(`${API_BASE}/themes/${themeKey}/tile_url/${result.result_id}`)
             .then(r => r.json())
             .then(data => {
                if (data.fresh && data.tile_url) {
                   const storeState = useAnalysisStore.getState();
                   const currentResult = storeState.themeResults[themeKey as ThemeId];
                   if (currentResult) {
                     setThemeResult(themeKey as ThemeId, {
                       ...currentResult,
                       tile_url: data.tile_url,
                       tile_url_expires_at: data.expires_at
                     })
                   }
                }
             })
             .catch(e => console.warn(`Failed to refresh tile for ${themeKey}:`, e))
        }
      })
    }, 60 * 1000) // check every minute

    return () => clearInterval(interval)
  }, [setThemeResult])

  useEffect(() => {
    if (!map) return

    Object.entries(themeResults).forEach(([themeKey, result]) => {
      const theme = themeKey as ThemeId
      if (!result?.tile_url || result.error_message) return

      const sourceId = `gee-${theme}`
      const layerId = `gee-layer-${theme}`

      const prevUrl = addedLayersRef.current.get(theme)
      if (prevUrl !== result.tile_url) {
        // Defensive: only add if map style is loaded
        if (!map.isStyleLoaded()) return

        try {
          if (prevUrl) {
            // Remove old layer/source before adding new one
            if (map.getLayer(layerId)) map.removeLayer(layerId)
            if (map.getSource(sourceId)) map.removeSource(sourceId)
          }

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
          addedLayersRef.current.set(theme, result.tile_url)
        } catch (err) {
          console.warn(`Failed to add/update layer for ${theme}:`, err)
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
      addedLayersRef.current.forEach((url, theme) => {
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
