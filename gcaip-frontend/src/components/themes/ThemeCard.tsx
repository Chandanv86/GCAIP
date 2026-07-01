/**
 * ThemeCard — displays a completed (or failed) theme result.
 * Shows: metric label, confidence badge, data age, layer toggle, and
 * an expandable detail section with raw stats + enrichment context.
 */
import { useState } from 'react'
import { ChevronDown, Eye, EyeOff, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import type { ThemeResult } from '@/types/theme'
import { THEME_LABELS } from '@/types/theme'
import { useAnalysisStore } from '@/store/analysisStore'
import { themeIcon } from './themeIcons'
import ThemeDetailPanel from './ThemeDetailPanel'

interface Props {
  result: ThemeResult
}

export default function ThemeCard({ result }: Props) {
  const [expanded, setExpanded] = useState(false)
  const mapLayerVisible = useAnalysisStore((s) => s.mapLayerVisible)
  const toggleLayerVisibility = useAnalysisStore((s) => s.toggleLayerVisibility)

  const Icon = themeIcon(result.theme)
  const hasError = Boolean(result.error_message)
  const isVisible = mapLayerVisible[result.theme] ?? true
  const confidencePct = result.confidence != null ? Math.round(result.confidence * 100) : null

  return (
    <div
      className={clsx(
        'rounded-xl ring-1 transition-colors',
        hasError ? 'bg-signal-critical/5 ring-signal-critical/20' : 'bg-panel-light ring-white/5',
      )}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        <div
          className={clsx(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
            hasError ? 'bg-signal-critical/10' : 'bg-sentinel/10',
          )}
        >
          {hasError ? (
            <AlertCircle size={15} className="text-signal-critical" />
          ) : (
            <Icon size={15} className="text-sentinel" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-ink">{THEME_LABELS[result.theme]}</p>
          <p className={clsx('truncate text-xs', hasError ? 'text-signal-critical' : 'text-muted')}>
            {hasError ? result.error_message : result.metric_label}
          </p>
        </div>

        {!hasError && confidencePct != null && (
          <ConfidenceBadge value={confidencePct} />
        )}

        <ChevronDown
          size={15}
          className={clsx('shrink-0 text-muted transition-transform', expanded && 'rotate-180')}
        />
      </button>

      {expanded && !hasError && (
        <div className="border-t border-white/5 px-4 pb-4 pt-3">
          <div className="mb-3 flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted">
              {result.data_source}
              {result.data_age_hours != null && (
                <> · {formatAge(result.data_age_hours)} old</>
              )}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation()
                toggleLayerVisibility(result.theme)
              }}
              className="flex items-center gap-1 rounded-md bg-white/5 px-2 py-1 text-[11px] text-muted hover:bg-white/10"
            >
              {isVisible ? <Eye size={12} /> : <EyeOff size={12} />}
              {isVisible ? 'On map' : 'Hidden'}
            </button>
          </div>

          <ThemeDetailPanel result={result} />
        </div>
      )}
    </div>
  )
}

function ConfidenceBadge({ value }: { value: number }) {
  const color =
    value >= 75 ? 'text-signal-low' : value >= 50 ? 'text-signal-watch' : 'text-signal-warning'
  return (
    <span className={clsx('shrink-0 font-mono text-[10px]', color)}>
      {value}%
    </span>
  )
}

function formatAge(hours: number): string {
  if (hours < 1) return '< 1h'
  if (hours < 24) return `${Math.round(hours)}h`
  return `${Math.round(hours / 24)}d`
}
