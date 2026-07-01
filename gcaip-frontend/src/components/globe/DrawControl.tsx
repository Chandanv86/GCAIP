/**
 * DrawControl — custom MapLibre GL drawing implementation for rectangular AOI selection and interaction mode management.
 */
import { useEffect, useState } from 'react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import { Navigation, MapPin, Square, X } from 'lucide-react'
import { useAnalysisStore } from '@/store/analysisStore'

interface Props {
  map: MapLibreMap
  onAOISubmit: (geojson: GeoJSON.Feature, presetZone?: any) => void
}

export default function DrawControl({ map, onAOISubmit }: Props) {
  const interactionMode = useAnalysisStore((s) => s.interactionMode)
  const setInteractionMode = useAnalysisStore((s) => s.setInteractionMode)
  
  const [points, setPoints] = useState<[number, number][]>([])
  const [tempPoint, setTempPoint] = useState<[number, number] | null>(null)

  // Initialize sources and layers once
  useEffect(() => {
    if (!map) return

    if (!map.getSource('draw-polygon-source')) {
      map.addSource('draw-polygon-source', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: []
        }
      })

      map.addLayer({
        id: 'draw-polygon-fill',
        type: 'fill',
        source: 'draw-polygon-source',
        paint: {
          'fill-color': '#2DD4BF', // terra (teal)
          'fill-opacity': 0.15
        },
        filter: ['==', '$type', 'Polygon']
      })

      map.addLayer({
        id: 'draw-polygon-stroke',
        type: 'line',
        source: 'draw-polygon-source',
        paint: {
          'line-color': '#2DD4BF',
          'line-width': 2
        },
        filter: ['in', '$type', 'LineString', 'Polygon']
      })

      map.addLayer({
        id: 'draw-polygon-vertices',
        type: 'circle',
        source: 'draw-polygon-source',
        paint: {
          'circle-radius': 5,
          'circle-color': '#E8ECF4', // ink (white)
          'circle-stroke-color': '#2DD4BF',
          'circle-stroke-width': 2
        },
        filter: ['==', '$type', 'Point']
      })
    }

    return () => {
      // Clean up drawing on unmount
      const source = map.getSource('draw-polygon-source')
      if (source) {
        if (map.getLayer('draw-polygon-fill')) map.removeLayer('draw-polygon-fill')
        if (map.getLayer('draw-polygon-stroke')) map.removeLayer('draw-polygon-stroke')
        if (map.getLayer('draw-polygon-vertices')) map.removeLayer('draw-polygon-vertices')
        map.removeSource('draw-polygon-source')
      }
    }
  }, [map])

  // Bind map interactions during drawing mode
  useEffect(() => {
    if (interactionMode !== 'rectangle' || !map) return

    // Disable double click zoom while drawing
    const prevDoublePressZoom = map.doubleClickZoom.isEnabled()
    map.doubleClickZoom.disable()

    const onClick = (e: any) => {
      const lngLat: [number, number] = [e.lngLat.lng, e.lngLat.lat]
      
      setPoints((prev) => {
        if (prev.length === 0) {
          return [lngLat]
        } else {
          // Second click completes the rectangle
          const p1 = prev[0]
          const p2 = lngLat
          const polyCoords = [
            [p1[0], p1[1]],
            [p2[0], p1[1]],
            [p2[0], p2[1]],
            [p1[0], p2[1]],
            [p1[0], p1[1]]
          ]
          const feature: GeoJSON.Feature = {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Polygon',
              coordinates: [polyCoords]
            }
          }
          // Submit the rectangular AOI
          onAOISubmit(feature)
          
          // Reset interaction state
          setInteractionMode('navigate')
          setTempPoint(null)
          clearSource()
          return []
        }
      })
    }

    const onMouseMove = (e: any) => {
      // Only show preview if we have started drawing (first click done)
      setTempPoint([e.lngLat.lng, e.lngLat.lat])
    }

    map.on('click', onClick)
    map.on('mousemove', onMouseMove)

    const canvas = map.getCanvasContainer()
    canvas.style.cursor = 'crosshair'

    return () => {
      map.off('click', onClick)
      map.off('mousemove', onMouseMove)
      canvas.style.cursor = ''
      if (prevDoublePressZoom) {
        map.doubleClickZoom.enable()
      }
    }
  }, [interactionMode, map, onAOISubmit, setInteractionMode])

  // Update GeoJSON source representation
  useEffect(() => {
    if (!map) return
    const source = map.getSource('draw-polygon-source') as any
    if (!source) return

    const features: any[] = []

    if (points.length === 1 && tempPoint) {
      const p1 = points[0]
      const p2 = tempPoint
      const rectCoords = [
        [p1[0], p1[1]],
        [p2[0], p1[1]],
        [p2[0], p2[1]],
        [p1[0], p2[1]],
        [p1[0], p1[1]]
      ]
      features.push({
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [rectCoords]
        },
        properties: {}
      })
      
      // Vertices
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: p1 },
        properties: {}
      })
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: p2 },
        properties: {}
      })
    }

    source.setData({
      type: 'FeatureCollection',
      features
    })
  }, [points, tempPoint, map])

  const clearSource = () => {
    const source = map.getSource('draw-polygon-source') as any
    if (source) {
      source.setData({
        type: 'FeatureCollection',
        features: []
      })
    }
  }

  const handleCancel = () => {
    setInteractionMode('navigate')
    setPoints([])
    setTempPoint(null)
    clearSource()
  }

  return (
    <div className="absolute left-6 top-24 z-10 flex flex-col gap-3">
      {/* Premium Toolbar */}
      <div className="glass-panel flex flex-col items-center gap-1.5 p-2 shadow-lg pointer-events-auto border border-white/10 rounded-xl bg-slate-900/60 backdrop-blur-md">
        <button
          onClick={() => { setPoints([]); setTempPoint(null); clearSource(); setInteractionMode('navigate'); }}
          title="Navigate & Orbit"
          className={`p-2 rounded-lg transition-all ${
            interactionMode === 'navigate'
              ? 'bg-terra text-slate-900 shadow-md scale-105'
              : 'text-muted hover:text-ink hover:bg-white/5'
          }`}
        >
          <Navigation size={18} />
        </button>

        <button
          onClick={() => { setPoints([]); setTempPoint(null); clearSource(); setInteractionMode('point'); }}
          title="Inspect Single Point"
          className={`p-2 rounded-lg transition-all ${
            interactionMode === 'point'
              ? 'bg-terra text-slate-900 shadow-md scale-105'
              : 'text-muted hover:text-ink hover:bg-white/5'
          }`}
        >
          <MapPin size={18} />
        </button>

        <button
          onClick={() => { setPoints([]); setTempPoint(null); clearSource(); setInteractionMode('rectangle'); }}
          title="Draw Rectangular AOI"
          className={`p-2 rounded-lg transition-all ${
            interactionMode === 'rectangle'
              ? 'bg-terra text-slate-900 shadow-md scale-105'
              : 'text-muted hover:text-ink hover:bg-white/5'
          }`}
        >
          <Square size={18} />
        </button>
      </div>

      {/* Mode-specific user guidelines */}
      {interactionMode === 'point' && (
        <div className="glass-panel px-3 py-2 text-[11px] leading-tight text-terra/90 shadow-md border border-terra/20 rounded-lg max-w-[200px] pointer-events-none animate-pulse bg-slate-900/60 backdrop-blur-md">
          Click any location on the globe to inspect and analyze it.
        </div>
      )}

      {interactionMode === 'rectangle' && (
        <div className="glass-panel p-3 shadow-md border border-white/10 rounded-lg max-w-[220px] pointer-events-auto flex flex-col gap-2 bg-slate-900/60 backdrop-blur-md">
          <p className="text-[11px] leading-snug text-muted">
            {points.length === 0
              ? 'Click once on the map to set the first corner of your rectangular area.'
              : 'Move mouse to size, and click again to analyze the rectangle.'}
          </p>
          <button
            onClick={handleCancel}
            className="flex items-center justify-center gap-1 rounded-md bg-white/5 py-1 text-[10px] font-medium text-muted transition-colors hover:bg-white/10"
          >
            <X size={10} /> Cancel
          </button>
        </div>
      )}
    </div>
  )
}
