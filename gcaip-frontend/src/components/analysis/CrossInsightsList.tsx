import { AlertOctagon, AlertTriangle, Eye, Info } from 'lucide-react'
import clsx from 'clsx'
import type { CrossInsight, Severity } from '@/types/theme'

interface Props {
  insights: CrossInsight[]
}

const SEVERITY_CONFIG: Record<Severity, { icon: typeof Info; color: string; bg: string; ring: string }> = {
  INFO: { icon: Info, color: 'text-signal-info', bg: 'bg-signal-info/10', ring: 'ring-signal-info/20' },
  WATCH: { icon: Eye, color: 'text-signal-watch', bg: 'bg-signal-watch/10', ring: 'ring-signal-watch/20' },
  WARNING: { icon: AlertTriangle, color: 'text-signal-warning', bg: 'bg-signal-warning/10', ring: 'ring-signal-warning/20' },
  EMERGENCY: { icon: AlertOctagon, color: 'text-signal-critical', bg: 'bg-signal-critical/10', ring: 'ring-signal-critical/20' },
}

export default function CrossInsightsList({ insights }: Props) {
  return (
    <div>
      <h3 className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
        Compound Risk Insights
      </h3>
      <div className="space-y-2">
        {insights.map((insight) => {
          const config = SEVERITY_CONFIG[insight.severity]
          const Icon = config.icon
          return (
            <div
              key={insight.insight_id}
              className={clsx('rounded-xl p-3.5 ring-1', config.bg, config.ring)}
            >
              <div className="flex items-start gap-2.5">
                <Icon size={16} className={clsx('mt-0.5 shrink-0', config.color)} />
                <div className="min-w-0">
                  <p className="text-sm leading-snug text-ink">{insight.insight_text}</p>
                  <p className="mt-1.5 text-xs leading-snug text-muted">
                    <span className={clsx('font-medium', config.color)}>Action: </span>
                    {insight.recommended_action}
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
