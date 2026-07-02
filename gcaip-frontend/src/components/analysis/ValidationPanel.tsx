import type { ThemeResult } from '@/types/theme'
import type { PresetZone } from '@/data/presetZones'

interface Props {
  preset: PresetZone
  themeResults: Partial<Record<string, ThemeResult>>
}

type ValidationStatus = 'MATCH' | 'PARTIAL' | 'MISMATCH'

interface RowData {
  metric: string
  expectedText: string
  gotText: string
  status: ValidationStatus | 'INFO'
}

export default function ValidationPanel({ preset, themeResults }: Props) {
  const rainfallResult = themeResults['rainfall']
  const landuseResult = themeResults['landuse']

  // Helper validation functions
  const validateRange = (val: number | null | undefined, [min, max]: [number, number]): ValidationStatus => {
    if (val == null || isNaN(val)) return 'MISMATCH'
    if (val >= min && val <= max) return 'MATCH'
    const width = max - min || Math.abs(min) || 1.0
    if (val >= min - width * 0.3 && val <= max + width * 0.3) return 'PARTIAL'
    return 'MISMATCH'
  }

  const validateMin = (val: number | null | undefined, min: number): ValidationStatus => {
    if (val == null || isNaN(val)) return 'MISMATCH'
    if (val >= min) return 'MATCH'
    if (val >= min * 0.7) return 'PARTIAL'
    return 'MISMATCH'
  }

  // Gather Rainfall Rows
  const rainfallRows: RowData[] = []
  const expectedRain = preset.expected.rainfall

  if (rainfallResult) {
    const stats = rainfallResult.stats || {}
    const spi7 = stats.spi_7 as number | undefined
    const anomaly7d = stats.anomaly_7d_pct as number | undefined
    const confidenceVal = rainfallResult.confidence as number | undefined
    const spiLabel = stats.spi_label as string | undefined

    // 1. SPI-7
    const spiStatus = validateRange(spi7, expectedRain.spi_7_range)
    rainfallRows.push({
      metric: 'SPI-7',
      expectedText: `${expectedRain.spi_7_range[0]} to ${expectedRain.spi_7_range[1]}`,
      gotText: spi7 != null ? spi7.toFixed(2) : '—',
      status: spiStatus,
    })

    // 2. 7-day Anomaly %
    const anomalyStatus = validateRange(anomaly7d, expectedRain.anomaly_7d_pct_range)
    rainfallRows.push({
      metric: '7-day Anomaly %',
      expectedText: `${expectedRain.anomaly_7d_pct_range[0]}% to ${expectedRain.anomaly_7d_pct_range[1]}%`,
      gotText: anomaly7d != null ? `${anomaly7d > 0 ? '+' : ''}${anomaly7d.toFixed(1)}%` : '—',
      status: anomalyStatus,
    })

    // 3. Confidence
    const confStatus = validateMin(confidenceVal != null ? confidenceVal * 100 : null, expectedRain.confidence_min * 100)
    rainfallRows.push({
      metric: 'Confidence',
      expectedText: `> ${Math.round(expectedRain.confidence_min * 100)}%`,
      gotText: confidenceVal != null ? `${Math.round(confidenceVal * 100)}%` : '—',
      status: confStatus,
    })

    // 4. SPI Label (Info only)
    rainfallRows.push({
      metric: 'SPI Label',
      expectedText: expectedRain.spi_7_label,
      gotText: spiLabel || '—',
      status: 'INFO',
    })
  }

  // Gather Land Use Rows
  const landuseRows: RowData[] = []
  const expectedLand = preset.expected.landuse

  if (landuseResult) {
    const stats = landuseResult.stats || {}
    const changedArea = stats.changed_area_ha as number | undefined
    const deforestation = stats.deforestation_ha as number | undefined
    
    // Check tree_to_built_ha in transitions first, fallback to urban_expansion_ha
    const transitions = (stats.transitions || {}) as Record<string, any>
    const urbanExpansion = (transitions.tree_to_built_ha ?? stats.urban_expansion_ha) as number | undefined
    const runoffIncrease = stats.runoff_increase_pct as number | undefined

    // 1. Changed Area
    const changedStatus = validateMin(changedArea, expectedLand.changed_area_ha_min)
    landuseRows.push({
      metric: 'Changed Area (ha)',
      expectedText: `> ${expectedLand.changed_area_ha_min} ha`,
      gotText: changedArea != null ? `${changedArea.toLocaleString()} ha` : '—',
      status: changedStatus,
    })

    // 2. Deforestation
    const defStatus = validateMin(deforestation, expectedLand.deforestation_ha_min)
    landuseRows.push({
      metric: 'Deforestation (ha)',
      expectedText: `> ${expectedLand.deforestation_ha_min} ha`,
      gotText: deforestation != null ? `${deforestation.toLocaleString()} ha` : '—',
      status: defStatus,
    })

    // 3. Urban Expansion
    const urbanStatus = validateRange(urbanExpansion, expectedLand.urban_expansion_ha_range)
    landuseRows.push({
      metric: 'Urban Expansion (ha)',
      expectedText: `${expectedLand.urban_expansion_ha_range[0]} to ${expectedLand.urban_expansion_ha_range[1]} ha`,
      gotText: urbanExpansion != null ? `${urbanExpansion.toLocaleString()} ha` : '—',
      status: urbanStatus,
    })

    // 4. Runoff Increase %
    const runoffStatus = validateRange(runoffIncrease, expectedLand.runoff_increase_pct_range)
    landuseRows.push({
      metric: 'Runoff Increase %',
      expectedText: `${expectedLand.runoff_increase_pct_range[0]}% to ${expectedLand.runoff_increase_pct_range[1]}%`,
      gotText: runoffIncrease != null ? `${runoffIncrease.toFixed(1)}%` : '—',
      status: runoffStatus,
    })
  }

  // Calculate Matches
  const allCheckedRows = [...rainfallRows, ...landuseRows].filter((r) => r.status !== 'INFO')
  const totalChecked = allCheckedRows.length
  const matchCount = allCheckedRows.filter((r) => r.status === 'MATCH').length
  const matchPct = totalChecked > 0 ? Math.round((matchCount / totalChecked) * 100) : 0

  // Signal validity details
  let validityText = 'Low confidence — GEE may not have data for this period'
  let validityColor = 'text-signal-critical'
  let progressColor = 'bg-signal-critical'

  if (matchPct >= 80) {
    validityText = 'Data appears GENUINE'
    validityColor = 'text-signal-low' // Green/low risk
    progressColor = 'bg-signal-low'
  } else if (matchPct >= 50) {
    validityText = 'Partial signal — verify date range'
    validityColor = 'text-signal-watch' // Yellow/watch
    progressColor = 'bg-signal-watch'
  }

  const renderStatusIcon = (status: RowData['status']) => {
    switch (status) {
      case 'MATCH':
        return <span className="text-signal-low font-bold">✅</span>
      case 'PARTIAL':
        return <span className="text-signal-watch font-bold">⚠️</span>
      case 'MISMATCH':
        return <span className="text-signal-critical font-bold">❌</span>
      default:
        return <span className="text-muted text-[10px]">—</span>
    }
  }

  return (
    <div className="mt-6 rounded-xl border border-white/5 bg-panel-light p-4.5 space-y-5">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <h4 className="text-xs font-bold uppercase tracking-wider text-cyan-400">
          Validation — Expected vs Got
        </h4>
        <span className="text-[10px] text-muted font-mono">{preset.name}</span>
      </div>

      {/* Rainfall validation */}
      {rainfallResult && rainfallRows.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[11px] font-semibold text-ink">
            <span>🌧️ RAINFALL VALIDATION</span>
            <span className="text-[9px] text-muted font-normal max-w-[200px] truncate" title={expectedRain.source}>
              Source: {expectedRain.source}
            </span>
          </div>
          <table className="w-full text-left text-xs text-muted border-collapse">
            <thead>
              <tr className="border-b border-white/5 text-[10px] text-muted font-mono">
                <th className="py-1">Metric</th>
                <th className="py-1">Expected</th>
                <th className="py-1">Got</th>
                <th className="py-1 text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {rainfallRows.map((row, idx) => (
                <tr key={idx} className="border-b border-white/[0.02]">
                  <td className="py-1.5 font-medium text-ink/90">{row.metric}</td>
                  <td className="py-1.5 font-mono">{row.expectedText}</td>
                  <td className="py-1.5 font-mono text-ink">{row.gotText}</td>
                  <td className="py-1.5 text-center">{renderStatusIcon(row.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-muted italic leading-normal">
            📝 Note: {expectedRain.anomaly_note}
          </p>
        </div>
      )}

      {/* Land Use validation */}
      {landuseResult && landuseRows.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-white/5">
          <div className="flex items-center justify-between text-[11px] font-semibold text-ink">
            <span>🌳 LAND USE VALIDATION</span>
            <span className="text-[9px] text-muted font-normal max-w-[200px] truncate" title={expectedLand.source}>
              Source: {expectedLand.source}
            </span>
          </div>
          <table className="w-full text-left text-xs text-muted border-collapse">
            <thead>
              <tr className="border-b border-white/5 text-[10px] text-muted font-mono">
                <th className="py-1">Metric</th>
                <th className="py-1">Expected</th>
                <th className="py-1">Got</th>
                <th className="py-1 text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {landuseRows.map((row, idx) => (
                <tr key={idx} className="border-b border-white/[0.02]">
                  <td className="py-1.5 font-medium text-ink/90">{row.metric}</td>
                  <td className="py-1.5 font-mono">{row.expectedText}</td>
                  <td className="py-1.5 font-mono text-ink">{row.gotText}</td>
                  <td className="py-1.5 text-center">{renderStatusIcon(row.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[10px] text-muted italic leading-normal">
            📝 Note: {expectedLand.changed_area_note}
          </p>
        </div>
      )}

      {/* Overall validity score */}
      <div className="pt-3 border-t border-white/5 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted">Overall Signal Validity:</span>
          <span className="font-semibold text-ink">
            {matchCount}/{totalChecked} metrics matched
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${progressColor}`}
            style={{ width: `${matchPct}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-[11px]">
          <span className={`font-semibold ${validityColor}`}>
            {matchPct}% — {validityText}
          </span>
        </div>

        <p className="text-[10px] text-muted leading-normal leading-relaxed pt-1 border-t border-white/[0.02]">
          💡 Note: Expected ranges are based on annual averages. Seasonal timing affects results — Amazon dry season (Jun-Sept) will show lower rainfall than annual expected range.
        </p>
      </div>
    </div>
  )
}
