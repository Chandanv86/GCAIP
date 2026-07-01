import { Satellite, Activity } from 'lucide-react'
import { useAnalysisStore } from '@/store/analysisStore'

export default function TopBar() {
  const isAnalyzing = useAnalysisStore((s) => s.isAnalyzing)

  return (
    <header className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-6 py-4 pointer-events-none">
      <div className="flex items-center gap-3 pointer-events-auto">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sentinel/15 ring-1 ring-sentinel/30">
          <Satellite size={18} className="text-sentinel" strokeWidth={2} />
        </div>
        <div>
          <h1 className="font-display text-base font-semibold tracking-tight text-ink">
            GCAIP
          </h1>
          <p className="text-[11px] leading-none text-muted">
            Climate Adaptation Intelligence
          </p>
        </div>
      </div>

      {isAnalyzing && (
        <div className="pointer-events-auto flex items-center gap-2 rounded-full bg-panel/90 backdrop-blur-xl px-4 py-2 ring-1 ring-white/5">
          <Activity size={14} className="text-sentinel animate-pulse" />
          <span className="text-xs font-mono text-muted">
            Analyzing 7 satellite themes...
          </span>
        </div>
      )}
    </header>
  )
}
