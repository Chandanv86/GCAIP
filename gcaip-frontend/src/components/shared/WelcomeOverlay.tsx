import { MousePointerClick, PenTool, X } from 'lucide-react'

interface Props {
  onDismiss: () => void
}

export default function WelcomeOverlay({ onDismiss }: Props) {
  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
      <div className="glass-panel pointer-events-auto max-w-md p-8 text-center shadow-2xl">
        <button
          onClick={onDismiss}
          className="absolute right-4 top-4 text-muted hover:text-ink transition-colors"
          aria-label="Dismiss"
        >
          <X size={16} />
        </button>

        <h2 className="font-display text-2xl font-semibold text-ink">
          Click anywhere on Earth
        </h2>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          GCAIP analyzes any location across 7 climate themes using free
          satellite data — flood extent, rainfall anomaly, reservoir status,
          mangrove health, coastal erosion, vegetation buffers, and land use
          change. Results stream back in real time.
        </p>

        <div className="mt-6 flex items-center justify-center gap-6 text-xs text-muted">
          <div className="flex items-center gap-2">
            <MousePointerClick size={16} className="text-sentinel" />
            <span>Click a point</span>
          </div>
          <div className="flex items-center gap-2">
            <PenTool size={16} className="text-terra" />
            <span>or draw an area</span>
          </div>
        </div>
      </div>
    </div>
  )
}
