/**
 * Core type definitions — must stay in sync with backend Pydantic schemas
 * (schemas/analysis.py) and dataclasses (gee/processors/base.py, services/*.py).
 */

export type ThemeId =
  | 'flood'
  | 'rainfall'
  | 'reservoir'
  | 'mangrove'
  | 'erosion'
  | 'vegetation'
  | 'landuse'
  | 'effluent_plume'
  | 'coastal_outfall'
  | 'pipeline_corridor'

export type ThemeStatus = 'pending' | 'running' | 'complete' | 'failed' | 'skipped'

export type Severity = 'INFO' | 'WATCH' | 'WARNING' | 'EMERGENCY'

export type RiskLabel = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'

export interface VisParams {
  min: number
  max: number
  palette: string[]
}

export interface ThemeResult {
  theme: ThemeId
  result_id?: string
  status: ThemeStatus
  tile_url: string | null
  tile_url_expires_at: string | null
  vis_params: VisParams | null
  metric_value: number | null
  metric_unit: string | null
  metric_label: string | null
  stats: Record<string, unknown>
  enrichment: EnrichedContext | Record<string, never>
  anomaly_score: number | null
  confidence: number | null
  data_age_hours: number | null
  data_source: string | null
  error_message: string | null
  error_class?: 'transient' | 'not_applicable' | 'data_gap' | null
}

export interface EnrichedContext {
  population_affected: number
  population_label: string
  schools_at_risk: number
  hospitals_at_risk: number
  roads_km_affected: number
  trajectories: AssetTrajectory[]
}

export interface AssetTrajectory {
  asset: string
  type: string
  distance_m?: number
  years_to_impact: number
  impact_year: number
}

export interface CrossInsight {
  insight_id: string
  insight_text: string
  severity: Severity
  theme_ids: ThemeId[]
  recommended_action: string
}

export interface RiskScore {
  overall_score: number
  overall_label: RiskLabel
  flood_risk: number | null
  erosion_risk: number | null
  water_stress: number | null
  vegetation_health: number | null
  landuse_pressure: number | null
  cross_insights: CrossInsight[]
  population_in_aoi: number | null
  population_at_risk: number | null
  scored_at: string
}

export interface AOI {
  aoi_id: string
  name: string | null
  area_km2: number | null
  country_code: string | null
  admin_level1: string | null
  admin_level2: string | null
  created_at: string
  geojson: GeoJSON.Feature | GeoJSON.Geometry | null
}

export interface AnalyzeResponse {
  job_id: string
  aoi_id: string
  status: string
  sse_url: string
  estimated_seconds: number
}

export interface RunStatus {
  run_id: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  themes_complete: number
  themes_total: number
  theme_statuses: Record<ThemeId, ThemeStatus>
  started_at: string | null
  completed_at: string | null
}

export interface Alert {
  id: string
  aoi_id: string
  severity: Severity
  theme: ThemeId
  alert_type: string
  title: string
  message: string
  metric_value: number | null
  metric_unit: string | null
  tile_url: string | null
  status: 'active' | 'resolved' | 'false_positive'
  triggered_at: string
  expires_at: string | null
  email_sent: boolean
}

// SSE event payloads
export type SSEEvent =
  | { event: 'connected'; run_id: string }
  | { event: 'theme_complete'; theme: ThemeId; result: ThemeResult }
  | { event: 'theme_error'; theme: ThemeId; result: ThemeResult }
  | { event: 'risk_score'; score: RiskScore }
  | { event: 'analysis_complete'; run_id: string }
  | { event: 'error'; message: string }

export const THEME_LABELS: Record<ThemeId, string> = {
  flood: 'Flood Extent',
  rainfall: 'Rainfall Anomaly',
  reservoir: 'Reservoir Status',
  mangrove: 'Mangrove Restoration',
  erosion: 'Coastal Erosion',
  vegetation: 'Vegetation Buffer',
  landuse: 'Land Use Change',
  effluent_plume: 'Effluent Plume',
  coastal_outfall: 'Coastal Outfall Plume',
  pipeline_corridor: 'Pipeline Corridor',
}

export const THEME_ORDER: ThemeId[] = [
  'flood', 'rainfall', 'reservoir', 'mangrove', 'erosion', 'vegetation', 'landuse',
  'effluent_plume', 'coastal_outfall', 'pipeline_corridor',
]

/**
 * Active themes dispatched by the orchestrator by default.
 * CANONICAL DEFINITION: gcaip-backend/services/theme_registry.py::ALL_THEMES
 * Keep this list manually in sync with that file. The backend validates all
 * theme IDs against the registry -- if you add a theme here without adding it
 * to theme_registry.py, the backend will reject the request with a 422 error.
 */
export const ACTIVE_THEMES: ThemeId[] = [
  'rainfall', 'landuse',
  'effluent_plume', 'coastal_outfall', 'pipeline_corridor',
]
