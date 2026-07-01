import { useState } from 'react'
import GlobeView from '@/components/globe/GlobeView'
import AnalysisPanel from '@/components/analysis/AnalysisPanel'
import TopBar from '@/components/shared/TopBar'
import WelcomeOverlay from '@/components/shared/WelcomeOverlay'
import { useAnalysisStore } from '@/store/analysisStore'

export default function App() {
  const [showWelcome, setShowWelcome] = useState(true)
  const selectedAOI = useAnalysisStore((s) => s.selectedAOI)
  const activeRunId = useAnalysisStore((s) => s.activeRunId)
  const error = useAnalysisStore((s) => s.error)

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-abyss">
      <TopBar />

      {/* Globe fills the viewport; analysis panel slides in from the right */}
      <GlobeView />

      {(selectedAOI || activeRunId || error) && <AnalysisPanel />}

      {showWelcome && !selectedAOI && (
        <WelcomeOverlay onDismiss={() => setShowWelcome(false)} />
      )}
    </div>
  )
}
