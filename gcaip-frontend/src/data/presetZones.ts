/**
 * Predefined extreme climate zones for validation testing.
 * Each zone has known satellite signals that make GEE output verifiable.
 *
 * IMPORTANT: All polygons must stay under 500 km² (backend GEE_AOI_MAX_KM2_ANON).
 * Original bounding boxes were 4,000–220,000 km² — shrunk to ~0.2°×0.2° focal
 * areas centered on the highest-signal location within each zone.
 *
 * Expected ranges are SEASON-AWARE: each zone defines a base (annual) range
 * plus optional per-quarter overrides. The ValidationPanel selects the
 * appropriate quarter based on the current month.
 */

export interface RainfallExpected {
  spi_7_range: [number, number]
  spi_7_label: string
  anomaly_7d_pct_range: [number, number]
  anomaly_note: string
  confidence_min: number
  source: string
  /** Per-quarter overrides — Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec */
  seasonal?: {
    [quarter: string]: {
      spi_7_range?: [number, number]
      spi_7_label?: string
      anomaly_7d_pct_range?: [number, number]
    }
  }
}

export interface LanduseExpected {
  changed_area_ha_min: number
  deforestation_ha_min: number
  urban_expansion_ha_range: [number, number]
  runoff_increase_pct_range: [number, number]
  changed_area_note: string
  source: string
}

export interface PresetExpected {
  rainfall: RainfallExpected
  landuse: LanduseExpected
}

export interface PresetZone {
  id: string
  name: string
  description: string
  tags: string[]
  theme_focus: string
  geojson: GeoJSON.Polygon
  expected: PresetExpected
}

/** Get the current quarter key: 'Q1' | 'Q2' | 'Q3' | 'Q4' */
export function getCurrentQuarter(): string {
  const month = new Date().getMonth() // 0-indexed
  if (month < 3) return 'Q1'
  if (month < 6) return 'Q2'
  if (month < 9) return 'Q3'
  return 'Q4'
}

/** Resolve season-aware rainfall expected values for the current quarter */
export function getSeasonalRainfall(expected: RainfallExpected): RainfallExpected {
  const q = getCurrentQuarter()
  const override = expected.seasonal?.[q]
  if (!override) return expected
  return {
    ...expected,
    spi_7_range: override.spi_7_range ?? expected.spi_7_range,
    spi_7_label: override.spi_7_label ?? expected.spi_7_label,
    anomaly_7d_pct_range: override.anomaly_7d_pct_range ?? expected.anomaly_7d_pct_range,
  }
}

export const PRESET_ZONES: PresetZone[] = [
  {
    id: 'brahmaputra_flood',
    name: 'Brahmaputra Floodplain',
    description: 'Assam, India — annual extreme flooding, June-Sept peak',
    tags: ['rainfall', 'landuse'],
    theme_focus: 'Strong IMERG signal — monsoon anomaly typically +80 to +200%',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [91.3, 26.3], [91.5, 26.3], [91.5, 26.5], [91.3, 26.5], [91.3, 26.3]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-1.5, 3.0],
        spi_7_label: 'Variable — depends on season (monsoon vs dry)',
        anomaly_7d_pct_range: [-100, 300],
        anomaly_note: 'Brahmaputra basin receives 1500-3000mm annually, 80% in June-Sept monsoon',
        confidence_min: 0.55,
        source: 'IMD records + CHIRPS South Asia validation study (2020)',
        seasonal: {
          Q1: { spi_7_range: [-2.0, 0.5], spi_7_label: 'Dry season (Jan-Mar)', anomaly_7d_pct_range: [-100, 50] },
          Q2: { spi_7_range: [-0.5, 2.0], spi_7_label: 'Pre-monsoon (Apr-Jun)', anomaly_7d_pct_range: [-50, 150] },
          Q3: { spi_7_range: [0.0, 3.0], spi_7_label: 'Peak monsoon (Jul-Sep)', anomaly_7d_pct_range: [20, 300] },
          Q4: { spi_7_range: [-1.5, 1.0], spi_7_label: 'Post-monsoon (Oct-Dec)', anomaly_7d_pct_range: [-80, 80] },
        }
      },
      landuse: {
        changed_area_ha_min: 5,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 200],
        runoff_increase_pct_range: [0, 25],
        changed_area_note: 'Active floodplain — high seasonal bare/water transitions. Values scaled for ~500km² AOI.',
        source: 'Hansen GFW NE India + Dynamic World Assam validation (2022)'
      }
    }
  },
  {
    id: 'mekong_delta',
    name: 'Mekong Delta',
    description: 'Vietnam — seasonal inundation + rapid land use change',
    tags: ['rainfall', 'landuse'],
    theme_focus: 'High Dynamic World flux — paddy to aquaculture conversion visible',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [105.8, 9.8], [106.0, 9.8], [106.0, 10.0], [105.8, 10.0], [105.8, 9.8]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-1.5, 2.5],
        spi_7_label: 'Variable — wet season May-Nov, dry Dec-Apr',
        anomaly_7d_pct_range: [-100, 200],
        anomaly_note: 'Bimodal rainfall, strong El Nino/La Nina variance',
        confidence_min: 0.55,
        source: 'MRC (Mekong River Commission) Hydrology Report 2023',
        seasonal: {
          Q1: { spi_7_range: [-2.0, 0.5], spi_7_label: 'Dry season (Jan-Mar)', anomaly_7d_pct_range: [-100, 30] },
          Q2: { spi_7_range: [-0.5, 2.0], spi_7_label: 'Early wet season (Apr-Jun)', anomaly_7d_pct_range: [-40, 150] },
          Q3: { spi_7_range: [0.0, 2.5], spi_7_label: 'Peak wet season (Jul-Sep)', anomaly_7d_pct_range: [0, 200] },
          Q4: { spi_7_range: [-0.5, 2.0], spi_7_label: 'Late wet season (Oct-Dec)', anomaly_7d_pct_range: [-30, 150] },
        }
      },
      landuse: {
        changed_area_ha_min: 5,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 500],
        runoff_increase_pct_range: [0, 30],
        changed_area_note: 'One of fastest land use change zones in SE Asia. Values scaled for ~500km² AOI.',
        source: 'ESA WorldCover vs Dynamic World Mekong validation (2023)'
      }
    }
  },
  {
    id: 'sahel_rainfall',
    name: 'Sahel Rainfall Anomaly Zone',
    description: 'Mali/Niger border — extreme interannual rainfall variability',
    tags: ['rainfall'],
    theme_focus: 'CHIRPS baseline shows high SPI variance, clear anomaly signal',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [2.3, 14.5], [2.5, 14.5], [2.5, 14.7], [2.3, 14.7], [2.3, 14.5]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-2.5, 2.5],
        spi_7_label: 'High variance — can swing Extremely Dry to Wet year to year',
        anomaly_7d_pct_range: [-100, 300],
        anomaly_note: 'Sahel receives 200-600mm/yr — any reading outside ±50% is notable',
        confidence_min: 0.50,
        source: 'FEWS NET West Africa rainfall monitoring, CHIRPS Sahel study (2021)',
        seasonal: {
          Q1: { spi_7_range: [-2.5, 0.0], spi_7_label: 'Deep dry season (Jan-Mar)', anomaly_7d_pct_range: [-100, 0] },
          Q2: { spi_7_range: [-1.5, 1.5], spi_7_label: 'Pre-rainy season (Apr-Jun)', anomaly_7d_pct_range: [-100, 150] },
          Q3: { spi_7_range: [-0.5, 2.5], spi_7_label: 'Rainy season (Jul-Sep)', anomaly_7d_pct_range: [-50, 300] },
          Q4: { spi_7_range: [-2.0, 0.5], spi_7_label: 'Post-rainy season (Oct-Dec)', anomaly_7d_pct_range: [-100, 50] },
        }
      },
      landuse: {
        changed_area_ha_min: 2,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 100],
        runoff_increase_pct_range: [0, 15],
        changed_area_note: 'Sahel greening documented in satellite records post-2000. Values scaled for ~500km² AOI.',
        source: 'Brandt et al. 2017 — Satellite-based mapping of Sahel woody cover'
      }
    }
  },
  {
    id: 'amazon_deforestation',
    name: 'Amazon Arc of Deforestation',
    description: 'Para/Mato Grosso, Brazil — highest deforestation rate globally',
    tags: ['landuse'],
    theme_focus: 'Dynamic World tree→crops/bare transitions must be clearly visible',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [-52.4, -9.9], [-52.2, -9.9], [-52.2, -9.7], [-52.4, -9.7], [-52.4, -9.9]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-2.0, 2.0],
        spi_7_label: 'Amazon — highly seasonal (dry Jun-Sep, wet Oct-May)',
        anomaly_7d_pct_range: [-100, 150],
        anomaly_note: 'Deforestation itself reducing local rainfall 5-10% per decade',
        confidence_min: 0.50,
        source: 'INPE PRODES + Amazon deforestation-rainfall feedback study (2022)',
        seasonal: {
          Q1: { spi_7_range: [-0.5, 2.0], spi_7_label: 'Wet season (Jan-Mar)', anomaly_7d_pct_range: [-30, 150] },
          Q2: { spi_7_range: [-1.5, 1.0], spi_7_label: 'Transition (Apr-Jun)', anomaly_7d_pct_range: [-80, 80] },
          Q3: { spi_7_range: [-2.0, 0.5], spi_7_label: 'Dry season (Jul-Sep)', anomaly_7d_pct_range: [-100, 30] },
          Q4: { spi_7_range: [-0.5, 2.0], spi_7_label: 'Wet season onset (Oct-Dec)', anomaly_7d_pct_range: [-50, 150] },
        }
      },
      landuse: {
        changed_area_ha_min: 5,
        deforestation_ha_min: 10,
        urban_expansion_ha_range: [0, 500],
        runoff_increase_pct_range: [0, 60],
        changed_area_note: 'PRODES reports 10,000-15,000 km²/yr deforestation across full arc. Values scaled for ~500km² AOI.',
        source: 'Hansen GFW 2023 + MapBiomas Brazil Collection 8'
      }
    }
  },
  {
    id: 'ganges_plain',
    name: 'Ganges-Yamuna Doab',
    description: 'UP, India — intensive agriculture, groundwater stress, seasonal flood',
    tags: ['rainfall', 'landuse'],
    theme_focus: 'Cropland dominance in DW, monsoon SPI spikes clearly measurable',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [79.8, 27.2], [80.0, 27.2], [80.0, 27.4], [79.8, 27.4], [79.8, 27.2]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-2.0, 3.0],
        spi_7_label: 'Highly seasonal — near 0 outside monsoon, wet during June-Sept',
        anomaly_7d_pct_range: [-100, 250],
        anomaly_note: 'Indo-Gangetic plain 600-900mm/yr, 80% in June-Sept',
        confidence_min: 0.55,
        source: 'IMD district rainfall records + CHIRPS South Asia 2023',
        seasonal: {
          Q1: { spi_7_range: [-2.0, 0.5], spi_7_label: 'Dry/cool season (Jan-Mar)', anomaly_7d_pct_range: [-100, 50] },
          Q2: { spi_7_range: [-1.0, 2.0], spi_7_label: 'Pre-monsoon heat (Apr-Jun)', anomaly_7d_pct_range: [-80, 150] },
          Q3: { spi_7_range: [0.0, 3.0], spi_7_label: 'Peak monsoon (Jul-Sep)', anomaly_7d_pct_range: [0, 250] },
          Q4: { spi_7_range: [-1.5, 0.5], spi_7_label: 'Post-monsoon (Oct-Dec)', anomaly_7d_pct_range: [-100, 50] },
        }
      },
      landuse: {
        changed_area_ha_min: 2,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 300],
        runoff_increase_pct_range: [0, 15],
        changed_area_note: 'Mostly cropland-to-built transitions, stable forest cover. Values scaled for ~500km² AOI.',
        source: 'LISS-IV National Remote Sensing Centre India + Dynamic World (2023)'
      }
    }
  },
  {
    id: 'jakarta_landuse',
    name: 'Greater Jakarta Expansion',
    description: 'Java, Indonesia — fastest urban expansion in SE Asia',
    tags: ['landuse'],
    theme_focus: 'Tree/wetland→built transition must show high urban expansion ha',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [106.8, -6.3], [107.0, -6.3], [107.0, -6.1], [106.8, -6.1], [106.8, -6.3]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-2.0, 2.0],
        spi_7_label: 'Near Normal — Jakarta bimodal, wet Nov-Mar',
        anomaly_7d_pct_range: [-100, 150],
        anomaly_note: 'Jakarta 1800mm/yr, increasingly impacted by urban heat island',
        confidence_min: 0.50,
        source: 'BMKG Indonesia rainfall records + CHIRPS 2022',
        seasonal: {
          Q1: { spi_7_range: [-0.5, 2.0], spi_7_label: 'Wet season (Jan-Mar)', anomaly_7d_pct_range: [-30, 150] },
          Q2: { spi_7_range: [-1.5, 1.0], spi_7_label: 'Transition (Apr-Jun)', anomaly_7d_pct_range: [-80, 80] },
          Q3: { spi_7_range: [-2.0, 0.5], spi_7_label: 'Dry season (Jul-Sep)', anomaly_7d_pct_range: [-100, 30] },
          Q4: { spi_7_range: [-0.5, 2.0], spi_7_label: 'Wet season onset (Oct-Dec)', anomaly_7d_pct_range: [-50, 150] },
        }
      },
      landuse: {
        changed_area_ha_min: 5,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 1000],
        runoff_increase_pct_range: [0, 70],
        changed_area_note: 'Jabodetabek grew 4% annually — one of world\'s fastest expansions. Values scaled for ~500km² AOI.',
        source: 'World Bank Jakarta Urban Study 2022 + BPS Indonesia Land Use Census'
      }
    }
  }
]
