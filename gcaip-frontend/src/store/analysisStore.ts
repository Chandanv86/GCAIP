/**
 * Analysis state store — tracks the active AOI, run, and streamed theme results.
 * SSE events from useSSEStream mutate this store as they arrive.
 */
import { create } from 'zustand'
import type { ThemeId, ThemeResult, RiskScore, AOI } from '@/types/theme'
import type { PresetZone } from '@/data/presetZones'

interface AnalysisState {
  // Current AOI selection
  selectedAOI: AOI | null
  drawnGeoJSON: GeoJSON.Feature | null

  // Active analysis run
  activeRunId: string | null
  isAnalyzing: boolean

  // Streamed results — keyed by theme
  themeResults: Partial<Record<ThemeId, ThemeResult>>
  riskScore: RiskScore | null

  // UI state
  selectedTheme: ThemeId | null
  mapLayerVisible: Partial<Record<ThemeId, boolean>>
  error: string | null
  isDrawing: boolean
  interactionMode: 'navigate' | 'point' | 'rectangle'

  // Preset validation state — survives reset() for validation continuity
  selectedPresetId: string | null
  selectedPresetZone: PresetZone | null

  // Actions
  setSelectedAOI: (aoi: AOI | null) => void
  setDrawnGeoJSON: (geojson: GeoJSON.Feature | null) => void
  startAnalysis: (runId: string) => void
  setThemeResult: (theme: ThemeId, result: ThemeResult) => void
  setRiskScore: (score: RiskScore) => void
  completeAnalysis: () => void
  setError: (message: string | null) => void
  selectTheme: (theme: ThemeId | null) => void
  toggleLayerVisibility: (theme: ThemeId) => void
  setIsDrawing: (val: boolean) => void
  setInteractionMode: (mode: 'navigate' | 'point' | 'rectangle') => void
  setSelectedPresetId: (id: string | null) => void
  setSelectedPreset: (preset: PresetZone | null) => void
  reset: () => void
}

const initialState = {
  selectedAOI: null,
  drawnGeoJSON: null,
  activeRunId: null,
  isAnalyzing: false,
  themeResults: {},
  riskScore: null,
  selectedTheme: null,
  mapLayerVisible: {},
  error: null,
  isDrawing: false,
  interactionMode: 'navigate' as const,
  selectedPresetId: null,
  selectedPresetZone: null,
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  ...initialState,

  setSelectedAOI: (aoi) => set({ selectedAOI: aoi }),

  setDrawnGeoJSON: (geojson) => set({ drawnGeoJSON: geojson }),

  startAnalysis: (runId) =>
    set({
      activeRunId: runId,
      isAnalyzing: true,
      themeResults: {},
      riskScore: null,
      error: null,
    }),

  setThemeResult: (theme, result) =>
    set((state) => ({
      themeResults: { ...state.themeResults, [theme]: result },
      mapLayerVisible: {
        ...state.mapLayerVisible,
        [theme]: state.mapLayerVisible[theme] ?? !result.error_message,
      },
    })),

  setRiskScore: (score) => set({ riskScore: score }),

  completeAnalysis: () => set({ isAnalyzing: false }),

  setError: (message) => set({ error: message, isAnalyzing: false }),

  selectTheme: (theme) => set({ selectedTheme: theme }),

  toggleLayerVisibility: (theme) =>
    set((state) => ({
      mapLayerVisible: {
        ...state.mapLayerVisible,
        [theme]: !state.mapLayerVisible[theme],
      },
    })),

  setIsDrawing: (val) => set({ isDrawing: val }),

  setInteractionMode: (mode) =>
    set({
      interactionMode: mode,
      isDrawing: mode === 'rectangle'
    }),

  setSelectedPresetId: (id) => set({ selectedPresetId: id }),

  setSelectedPreset: (preset) =>
    set({
      selectedPresetId: preset?.id ?? null,
      selectedPresetZone: preset,
    }),

  reset: () => set(initialState),
}))
