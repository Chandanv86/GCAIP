/**
 * AnalysisPanel — the right-side sliding panel showing:
 *   1. AOI summary header
 *   2. Composite risk score (appears once all themes complete)
 *   3. Cross-theme insights (compound risk alerts)
 *   4. 7 theme cards, each populated progressively via SSE
 */
import { X } from 'lucide-react'
import { useAnalysisStore } from '@/store/analysisStore'
import { useSSEStream } from '@/hooks/useSSEStream'
import { ACTIVE_THEMES } from '@/types/theme'
import RiskScoreHeader from './RiskScoreHeader'
import CrossInsightsList from './CrossInsightsList'
import ThemeCard from '../themes/ThemeCard'
import ThemeCardSkeleton from '../themes/ThemeCardSkeleton'
import ValidationPanel from './ValidationPanel'

export default function AnalysisPanel() {
  const activeRunId = useAnalysisStore((s) => s.activeRunId)
  const selectedAOI = useAnalysisStore((s) => s.selectedAOI)
  const themeResults = useAnalysisStore((s) => s.themeResults)
  const riskScore = useAnalysisStore((s) => s.riskScore)
  const isAnalyzing = useAnalysisStore((s) => s.isAnalyzing)
  const error = useAnalysisStore((s) => s.error)
  const reset = useAnalysisStore((s) => s.reset)
  const selectedPresetZone = useAnalysisStore((s) => s.selectedPresetZone)

  // Connect to the SSE stream for the active run
  useSSEStream(activeRunId)

  return (
    <aside className="absolute right-0 top-0 z-20 flex h-full w-full max-w-md flex-col bg-panel/95 backdrop-blur-2xl ring-1 ring-white/5 animate-in slide-in-from-right duration-300">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/5 px-5 py-4">
        <div>
          <h2 className="font-display text-sm font-semibold text-ink">
            {selectedAOI?.name || 'Selected Area'}
          </h2>
          {selectedAOI && (
            <p className="text-[11px] text-muted">
              {selectedAOI.area_km2?.toFixed(1)} km²
              {selectedAOI.admin_level1 ? ` · ${selectedAOI.admin_level1}` : ''}
              {selectedAOI.country_code ? `, ${selectedAOI.country_code}` : ''}
            </p>
          )}
        </div>
        <button
          onClick={reset}
          className="rounded-lg p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-ink"
          aria-label="Close panel"
        >
          <X size={18} />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-5 py-5">
        {error && (
          <div className="mb-4 rounded-xl bg-signal-critical/10 px-4 py-3 text-sm text-signal-critical ring-1 ring-signal-critical/20">
            {error}
          </div>
        )}

        {riskScore && (
          <div className="mb-5">
            <RiskScoreHeader score={riskScore} />
          </div>
        )}

        {riskScore && riskScore.cross_insights.length > 0 && (
          <div className="mb-5">
            <CrossInsightsList insights={riskScore.cross_insights} />
          </div>
        )}

        <div className="space-y-3">
          <h3 className="px-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
            Theme Analysis
          </h3>
          {ACTIVE_THEMES.map((theme) => {
            const result = themeResults[theme]
            if (!result) {
              return isAnalyzing ? (
                <ThemeCardSkeleton key={theme} theme={theme} />
              ) : null
            }
            return <ThemeCard key={theme} result={result} />
          })}
        </div>

        {selectedPresetZone && !isAnalyzing && Object.keys(themeResults).length >= 1 && (
          <ValidationPanel preset={selectedPresetZone} themeResults={themeResults} />
        )}
      </div>
    </aside>
  )
}
