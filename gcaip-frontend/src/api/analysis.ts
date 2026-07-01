import { api } from './client'
import type { AnalyzeResponse, RunStatus, RiskScore, ThemeResult, ThemeId } from '@/types/theme'

export interface AnalyzeRequestBody {
  aoi_id: string
  date_range?: { start: string; end: string }
  themes?: ThemeId[]
}

export async function triggerAnalysis(body: AnalyzeRequestBody): Promise<AnalyzeResponse> {
  return api.post<AnalyzeResponse>('/analyze', body)
}

export async function getRunStatus(runId: string): Promise<RunStatus> {
  return api.get<RunStatus>(`/analyze/${runId}/status`)
}

export interface FullResults {
  run_id: string
  aoi_id: string
  status: string
  risk_score: RiskScore | null
  themes: Record<ThemeId, ThemeResult>
  cross_insights: unknown[]
  date_range_start: string
  date_range_end: string
  completed_at: string | null
}

export async function getFullResults(runId: string): Promise<FullResults> {
  return api.get<FullResults>(`/analyze/${runId}/results`)
}

export async function requestReport(runId: string): Promise<{ task_id: string }> {
  return api.post(`/reports/${runId}`)
}
