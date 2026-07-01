/**
 * SSE Stream Hook — connects to the backend's EventSource endpoint and
 * dispatches incoming events into the Zustand analysis store.
 *
 * This is the mechanism that makes theme cards "stream in" progressively
 * rather than waiting for all 7 GEE analyses to complete.
 */
import { useEffect, useRef } from 'react'
import { useAnalysisStore } from '@/store/analysisStore'
import { API_BASE } from '@/api/client'
import type { SSEEvent, ThemeId, ThemeResult } from '@/types/theme'

export function useSSEStream(runId: string | null): void {
  const setThemeResult = useAnalysisStore((s) => s.setThemeResult)
  const setRiskScore = useAnalysisStore((s) => s.setRiskScore)
  const completeAnalysis = useAnalysisStore((s) => s.completeAnalysis)
  const setError = useAnalysisStore((s) => s.setError)

  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!runId) return

    const url = `${API_BASE}/analyze/${runId}/stream`
    const source = new EventSource(url)
    eventSourceRef.current = source

    source.onmessage = (rawEvent: MessageEvent<string>) => {
      try {
        const payload: SSEEvent = JSON.parse(rawEvent.data)
        handleEvent(payload)
      } catch (err) {
        console.error('SSE parse error', err, rawEvent.data)
      }
    }

    source.onerror = () => {
      // EventSource auto-reconnects on transient errors. Only treat as fatal
      // if the connection is fully closed (readyState === CLOSED).
      if (source.readyState === EventSource.CLOSED) {
        setError('Connection to analysis stream lost. Please retry.')
        source.close()
      }
    }

    function handleEvent(payload: SSEEvent) {
      switch (payload.event) {
        case 'connected':
          break
        case 'theme_complete':
        case 'theme_error': {
          const theme = payload.theme as ThemeId
          const result = payload.result as ThemeResult
          setThemeResult(theme, result)
          break
        }
        case 'risk_score':
          setRiskScore(payload.score)
          break
        case 'analysis_complete':
          completeAnalysis()
          source.close()
          break
        case 'error':
          setError(payload.message)
          source.close()
          break
      }
    }

    return () => {
      source.close()
      eventSourceRef.current = null
    }
  }, [runId, setThemeResult, setRiskScore, completeAnalysis, setError])
}
