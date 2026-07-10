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

  const matchedPreset = selectedPresetId
    ? PRESET_ZONES.find((z) => z.id === selectedPresetId)
    : null

  // Retrieve theme-specific expected note if defined in the preset
  const expectedInfo = matchedPreset?.expected?.[result.theme as keyof typeof matchedPreset.expected]
  const expectedNote = expectedInfo 
    ? ('anomaly_note' in expectedInfo ? expectedInfo.anomaly_note : 'changed_area_note' in expectedInfo ? expectedInfo.changed_area_note : 'signal_note' in expectedInfo ? expectedInfo.signal_note : null)
    : null

  return (
    <div className="space-y-3">
      {/* Validation helper — only visible when AOI came from a preset and has expected note */}
      {!!matchedPreset && !!expectedNote && (
        <div className="flex items-start gap-2 rounded-lg bg-cyan-500/[0.06] px-2.5 py-2 ring-1 ring-cyan-500/15">
          <span className="text-sm shrink-0 mt-px">🔍</span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400 mb-0.5">
              Expected Signal
            </p>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              {expectedNote}
            </p>
          </div>
        </div>
      )}

      {/* Fallback & Source details */}
      {stats && !!(stats.cloud_threshold_used || stats.pipeline_vector_source) && (
        <div className="flex flex-wrap gap-1.5">
          {!!stats.cloud_threshold_used && Number(stats.cloud_threshold_used) > 40 && (
            <span className="inline-flex items-center rounded bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-amber-500 ring-1 ring-amber-500/20">
              ⚠️ Coarse Cloud Masking ({String(stats.cloud_threshold_used)}%)
            </span>
          )}
          {!!stats.pipeline_vector_source && (
            <span className="inline-flex items-center rounded bg-blue-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-blue-400 ring-1 ring-blue-500/20">
              Vector: {String(stats.pipeline_vector_source).toUpperCase()}
            </span>
          )}
        </div>
      )}

      {/* Caveats section */}
      {stats && 'caveats' in stats && Array.isArray(stats.caveats) && stats.caveats.length > 0 && (
        <div className="rounded-lg bg-yellow-500/[0.03] px-2.5 py-2 ring-1 ring-yellow-500/10">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-yellow-500/80 mb-1">
            Data Caveats & Limitations
          </p>
          <ul className="list-disc pl-3.5 space-y-0.5">
            {(stats.caveats as string[]).map((c, i) => (
              <li key={i} className="text-[10px] text-slate-400 leading-relaxed">
                {c}
              </li>
            ))}
          </ul>
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
