/**
 * ThemeDetailPanel — renders the raw stats dict and enrichment context
 * for an expanded theme card. Theme-specific rendering for key fields,
 * generic fallback for the rest.
 *
 * When the AOI came from a preset zone, shows an "Expected signal" reference
 * row so the user can visually validate GEE output against known ground truth.
 */
import type { ThemeResult } from '@/types/theme'
import { useAnalysisStore } from '@/store/analysisStore'
import { PRESET_ZONES } from '@/data/presetZones'

interface Props {
  result: ThemeResult
}

export default function ThemeDetailPanel({ result }: Props) {
  const { stats, enrichment } = result
  const selectedPresetId = useAnalysisStore((s) => s.selectedPresetId)

  // Look up the matching preset zone for validation reference
  const matchedPreset = selectedPresetId
    ? PRESET_ZONES.find((z) => z.id === selectedPresetId)
    : null

  return (
    <div className="space-y-3">
      {/* Validation helper — only visible when AOI came from a preset */}
      {matchedPreset && (
        <div className="flex items-start gap-2 rounded-lg bg-cyan-500/[0.06] px-2.5 py-2 ring-1 ring-cyan-500/15">
          <span className="text-sm shrink-0 mt-px">🔍</span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400 mb-0.5">
              Expected Signal
            </p>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              {matchedPreset.theme_focus}
            </p>
          </div>
        </div>
      )}

      {/* Enrichment — population & infrastructure impact */}
      {enrichment && 'population_affected' in enrichment && (
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Population" value={enrichment.population_label} />
          <Stat label="Schools at risk" value={String(enrichment.schools_at_risk)} />
          <Stat label="Hospitals at risk" value={String(enrichment.hospitals_at_risk)} />
          <Stat label="Roads affected" value={`${enrichment.roads_km_affected} km`} />
        </div>
      )}

      {/* Trajectories — infrastructure impact timeline */}
      {enrichment && 'trajectories' in enrichment && enrichment.trajectories.length > 0 && (
        <div>
          <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted">
            Impact Timeline
          </p>
          <div className="space-y-1">
            {enrichment.trajectories.slice(0, 5).map((t, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-ink">{t.asset}</span>
                <span className="font-mono text-signal-warning">
                  ~{t.years_to_impact.toFixed(1)}y ({t.impact_year})
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Raw stats grid */}
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(stats)
          .filter(([key, val]) => typeof val !== 'object' && key !== 'is_active')
          .slice(0, 8)
          .map(([key, val]) => (
            <Stat key={key} label={formatKey(key)} value={formatValue(val)} />
          ))}
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-2.5 py-2">
      <p className="text-[10px] text-muted">{label}</p>
      <p className="mt-0.5 font-mono text-xs text-ink">{value}</p>
    </div>
  )
}

function formatKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(val: unknown): string {
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'number') return Number.isInteger(val) ? String(val) : val.toFixed(2)
  if (val === null || val === undefined) return '—'
  return String(val)
}
