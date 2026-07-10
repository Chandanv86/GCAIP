# React Frontend Store & SSE Hooks

The frontend is a React application built with TypeScript, TailwindCSS, Vite, MapLibre GL for map visualizations, Recharts for charts, and Zustand for state management. This section details the store and data flow.

---

## 1. State Management Store

### `src/store/analysisStore.ts`
*   **One-line purpose**: Stores selection boundaries, running status, layer visibility, and SSE results.
*   **Type**: Zustand Store.
*   **State Fields**:
    *   `selectedAOI`: Active geocoded AOI boundary (`AOI | null`).
    *   `drawnGeoJSON`: Active drawn shape coordinates (`GeoJSON.Feature | null`).
    *   `activeRunId`: Running analysis job ID (`string | null`).
    *   `isAnalyzing`: Compute status indicator.
    *   `themeResults`: Dictionary mapping theme IDs to results (`ThemeResult`).
    *   `riskScore`: Composite risk scores (`RiskScore | null`).
    *   `selectedTheme`: Active theme selection.
    *   `mapLayerVisible`: Map layer visibility toggle states.
    *   `error`: Active error message details.
    *   `isDrawing`: Boundary drawing mode state.
    *   `interactionMode`: Map interaction mode (`navigate`\|`point`\|`rectangle`).
    *   `selectedPresetId` / `selectedPresetZone`: Reference boundaries.
*   **Key Mutator Actions**:
    *   `startAnalysis(runId)`: Sets the running state, clears previous results, and resets errors.
    *   `setThemeResult(theme, result)`: Appends completed theme results and updates default layer visibility.
    *   `setRiskScore(score)`: Stores composite scores.
    *   `completeAnalysis()`: Resets compute status indicator.
    *   `toggleLayerVisibility(theme)`: Toggles map layer display.
    *   `reset()`: Resets state back to initial values.

---

## 2. Server-Sent Events Consumer Hook

### `src/hooks/useSSEStream.ts`
*   **One-line purpose**: Subscribes to the backend SSE endpoint and commits updates to the Zustand store.
*   **Type**: React Hook.
*   **Logic Flow**:
    1.  Listens for active `runId` states.
    2.  Creates a native `EventSource` connection pointing to `${API_BASE}/analyze/${runId}/stream`.
    3.  Attaches an `onmessage` handler to parse incoming JSON payloads.
    4.  Processes events:
        *   `connected`: Confirms connection.
        *   `theme_complete` / `theme_error`: Calls `setThemeResult` with the updated status.
        *   `risk_score`: Calls `setRiskScore`.
        *   `analysis_complete`: Calls `completeAnalysis` and closes the stream.
        *   `error`: Calls `setError` and closes the stream.
    5.  Implements auto-reconnect behavior in `onerror`. If the connection is fully terminated (`CLOSED`), sets a fatal error.
    6.  Cleans up and closes the connection when the component unmounts or the `runId` changes.

---

## 3. Frontend Types Reference

### `src/types/theme.ts`
*   **One-line purpose**: TypeScript type interfaces for GCAIP entities.
*   **Key Interfaces**:
    *   `ThemeId`: Literal union (`'flood' | 'rainfall' | 'reservoir' | 'mangrove' | 'erosion' | 'vegetation' | 'landuse' | 'effluent_plume' | 'coastal_outfall' | 'pipeline_corridor'`).
    *   `ThemeResult`: Maps directly to the backend's `ThemeResult` JSON representation (metric value, unit, label, stats, confidence, etc.).
    *   `EnrichedContext`: Defines the geocoded population and infrastructure count fields.
    *   `RiskScore`: Defines the overall score and the list of cross-theme insights.
    *   `Alert`: Defines alert event fields.

---

## 4. Key Component Structure

### `GlobeView.tsx`
*   **Purpose**: Main MapLibre GL map viewport.
*   **Key Logic**:
    *   Renders the map context.
    *   Displays drawn shapes and selected boundaries.
    *   Loads GEE map tile layers (`ThemeLayerManager`) based on visibility configurations.

### `DrawControl.tsx`
*   **Purpose**: Drawing tools interface.
*   **Key Logic**:
    *   Provides rectangle and point drawing tools.
    *   Integrates with Mapbox Draw to capture coordinate boundaries.

### `ThemeCard.tsx`
*   **Purpose**: Displays the status and metrics for individual analysis themes.
*   **Key Logic**:
    *   Shows loading skeletons while analysis is running.
    *   Renders metrics, units, and data sources on completion.
    *   Displays error states (with classification details).

### `ValidationPanel.tsx`
*   **Purpose**: Sidebar UI for managing analysis runs and displaying results.
*   **Key Logic**:
    *   Triggers new analyses and monitors progress.
    *   Displays the overall risk score, geocoded population metrics, and active alerts.
    *   Renders cross-theme insights and recommended actions.
