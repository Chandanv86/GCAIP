import { AlertTriangle } from 'lucide-react'
import type { RiskScore } from '@/types/theme'
import clsx from 'clsx'

interface Props {
  score: RiskScore
}

const LABEL_STYLES: Record<RiskScore['overall_label'], { bg: string; text: string; ring: string }> = {
  LOW: { bg: 'bg-signal-low/10', text: 'text-signal-low', ring: 'ring-signal-low/30' },
  MODERATE: { bg: 'bg-signal-watch/10', text: 'text-signal-watch', ring: 'ring-signal-watch/30' },
  HIGH: { bg: 'bg-signal-warning/10', text: 'text-signal-warning', ring: 'ring-signal-warning/30' },
  CRITICAL: { bg: 'bg-signal-critical/10', text: 'text-signal-critical', ring: 'ring-signal-critical/30' },
}

const COMPONENTS: Array<{ key: keyof RiskScore; label: string }> = [
  { key: 'flood_risk', label: 'Flood' },
  { key: 'erosion_risk', label: 'Erosion' },
  { key: 'water_stress', label: 'Water Stress' },
  { key: 'vegetation_health', label: 'Vegetation' },
  { key: 'landuse_pressure', label: 'Land Use' },
]

export default function RiskScoreHeader({ score }: Props) {
  const style = LABEL_STYLES[score.overall_label]

  return (
    <div className={clsx('rounded-2xl p-5 ring-1', style.bg, style.ring)}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted">
            Composite Risk Score
          </p>
          <div className="mt-1 flex items-baseline gap-2">
            <span className={clsx('font-display text-4xl font-bold', style.text)}>
              {Math.round(score.overall_score)}
            </span>
            <span className="text-sm text-muted">/100</span>
          </div>
        </div>
        <div
          className={clsx(
            'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold',
            style.bg,
            style.text,
          )}
        >
          {score.overall_label === 'CRITICAL' && <AlertTriangle size={13} />}
          {score.overall_label}
        </div>
      </div>

      {score.population_at_risk != null && score.population_at_risk > 0 && (
        <p className="mt-2 text-xs text-muted">
          <strong className="text-ink">
            {formatPopulation(score.population_at_risk)}
          </strong>{' '}
          people in this area
        </p>
      )}

      <div className="mt-4 space-y-2">
        {COMPONENTS.map(({ key, label }) => {
          const value = score[key] as number | null
          if (value == null) return null
          return (
            <div key={key} className="flex items-center gap-2">
              <span className="w-24 shrink-0 text-[11px] text-muted">{label}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                <div
                  className={clsx('h-full rounded-full', barColor(value))}
                  style={{ width: `${Math.min(100, value)}%` }}
                />
              </div>
              <span className="w-7 shrink-0 text-right text-[11px] font-mono text-muted">
                {Math.round(value)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function barColor(value: number): string {
  if (value >= 75) return 'bg-signal-critical'
  if (value >= 50) return 'bg-signal-warning'
  if (value >= 25) return 'bg-signal-watch'
  return 'bg-signal-low'
}

function formatPopulation(count: number): string {
  if (count >= 10_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 100_000) return `${(count / 100_000).toFixed(1)} lakh`
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`
  return count.toLocaleString()
}
