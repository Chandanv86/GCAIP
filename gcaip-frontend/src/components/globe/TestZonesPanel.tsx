/**
 * TestZonesPanel — floating collapsible panel with predefined extreme climate
 * zones for validation testing. Positioned bottom-left, above the DrawControl.
 */
import { useState, useEffect } from 'react'
import { FlaskConical, ChevronDown, MapPin } from 'lucide-react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import { PRESET_ZONES, type PresetZone } from '@/data/presetZones'

interface Props {
  map: MapLibreMap
  onAOISubmit: (geojson: GeoJSON.Feature, presetZone?: PresetZone) => void
}

const TAG_COLORS: Record<string, string> = {
  flood: 'bg-blue-500/20 text-blue-300',
  rainfall: 'bg-cyan-500/20 text-cyan-300',
  landuse: 'bg-amber-500/20 text-amber-300',
  drought: 'bg-orange-500/20 text-orange-300',
  erosion: 'bg-red-500/20 text-red-300',
}

export default function TestZonesPanel({ onAOISubmit }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  // Auto-dismiss toast after 5 seconds
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(timer)
  }, [toast])

  const handleSelect = (zone: PresetZone) => {
    // Build GeoJSON Feature from preset polygon
    const feature: GeoJSON.Feature = {
      type: 'Feature',
      properties: { preset_id: zone.id, name: zone.name },
      geometry: zone.geojson,
    }

    // Submit through the same code path as draw/click
    // Pass preset zone as second arg so handleAOISubmit can restore it after reset()
    onAOISubmit(feature, zone)

    // Show validation toast
    setToast(zone.theme_focus)

    // Auto-collapse panel
    setExpanded(false)
  }

  return (
    <>
      {/* Panel — positioned bottom-left, above DrawControl toolbar */}
      <div className="absolute left-6 bottom-8 z-10 pointer-events-auto" style={{ maxWidth: 280 }}>
        {/* Toggle header button */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className={`
            flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium
            transition-all duration-200 shadow-lg border
            ${expanded
              ? 'bg-slate-800/90 border-cyan-500/30 text-cyan-300'
              : 'bg-slate-900/70 border-white/10 text-muted hover:text-ink hover:border-white/20'
            }
            backdrop-blur-md
          `}
        >
          <FlaskConical size={14} />
          <span>Test Zones</span>
          <ChevronDown
            size={12}
            className={`transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
          />
        </button>

        {/* Expanded zone list */}
        {expanded && (
          <div className="mt-2 rounded-xl bg-slate-900/90 backdrop-blur-xl border border-white/10 shadow-2xl overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
            <div className="px-3 py-2 border-b border-white/5">
              <p className="text-[10px] text-muted uppercase tracking-wider font-semibold">
                Predefined Validation Zones
              </p>
            </div>
            <div className="max-h-[320px] overflow-y-auto">
              {PRESET_ZONES.map((zone) => (
                <ZoneCard key={zone.id} zone={zone} onSelect={handleSelect} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Validation toast — bottom center */}
      {toast && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-30 pointer-events-auto animate-in fade-in slide-in-from-bottom-3 duration-300">
          <div className="flex items-start gap-2.5 px-4 py-3 rounded-xl bg-slate-800/95 backdrop-blur-xl border border-cyan-500/20 shadow-2xl max-w-lg">
            <FlaskConical size={14} className="text-cyan-400 mt-0.5 shrink-0" />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400 mb-0.5">
                Validation Note
              </p>
              <p className="text-xs text-slate-300 leading-relaxed">{toast}</p>
            </div>
            <button
              onClick={() => setToast(null)}
              className="text-muted hover:text-ink text-xs ml-2 shrink-0"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Zone Card ───────────────────────────────────────────────────────────────

function ZoneCard({ zone, onSelect }: { zone: PresetZone; onSelect: (z: PresetZone) => void }) {
  return (
    <div className="px-3 py-2.5 border-b border-white/[0.03] hover:bg-white/[0.03] transition-colors group">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-ink truncate">{zone.name}</p>
          <p className="text-[10px] text-muted leading-snug mt-0.5">{zone.description}</p>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {zone.tags.map((tag) => (
              <span
                key={tag}
                className={`px-1.5 py-0.5 rounded text-[9px] font-medium uppercase tracking-wider ${
                  TAG_COLORS[tag] || 'bg-white/10 text-muted'
                }`}
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
        <button
          onClick={() => onSelect(zone)}
          className="shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg bg-cyan-500/10 text-cyan-400 text-[10px] font-medium
                     hover:bg-cyan-500/20 transition-colors opacity-70 group-hover:opacity-100"
        >
          <MapPin size={10} />
          Select
        </button>
      </div>
    </div>
  )
}
