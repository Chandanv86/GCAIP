/**
 * Predefined extreme climate zones for validation testing.
 * Each zone has known satellite signals that make GEE output verifiable.
 *
 * IMPORTANT: All polygons must stay under 500 km² (backend GEE_AOI_MAX_KM2_ANON).
 * Original bounding boxes were 4,000–220,000 km² — shrunk to ~0.3°×0.3° focal
 * areas centered on the highest-signal location within each zone.
 */

export interface RainfallExpected {
  spi_7_range: [number, number]
  spi_7_label: string
  anomaly_7d_pct_range: [number, number]
  anomaly_note: string
  confidence_min: number
  source: string
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
        spi_7_range: [0.5, 3.0],
        spi_7_label: 'Moderately Wet to Extremely Wet (June-Sept monsoon)',
        anomaly_7d_pct_range: [50, 250],
        anomaly_note: 'Brahmaputra basin receives 1500-3000mm annually, June-Sept peak monsoon. SPI should be strongly positive during active monsoon.',
        confidence_min: 0.6,
        source: 'IMD records + CHIRPS South Asia validation study (2020)'
      },
      landuse: {
        changed_area_ha_min: 50,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [10, 200],
        runoff_increase_pct_range: [0, 10],
        changed_area_note: 'Active floodplain — high seasonal bare/water transitions, moderate urban growth in Guwahati periphery',
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
        spi_7_range: [-1.5, 0.5],
        spi_7_label: 'Near Normal to Wet (wet season Oct-Nov)',
        anomaly_7d_pct_range: [-60, 20],
        anomaly_note: 'Bimodal rainfall, strong El Nino/La Nina variance',
        confidence_min: 0.65,
        source: 'MRC (Mekong River Commission) Hydrology Report 2023'
      },
      landuse: {
        changed_area_ha_min: 1000,
        deforestation_ha_min: 5,
        urban_expansion_ha_range: [1000, 1500],
        runoff_increase_pct_range: [0.5, 5.0],
        changed_area_note: 'One of fastest land use change zones in SE Asia',
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
        spi_7_range: [-1.0, 1.0],
        spi_7_label: 'High variance — can swing Extremely Dry to Wet year to year',
        anomaly_7d_pct_range: [-60, 0],
        anomaly_note: 'Sahel receives 200-600mm/yr — any reading outside ±50% is notable',
        confidence_min: 0.55,
        source: 'FEWS NET West Africa rainfall monitoring, CHIRPS Sahel study (2021)'
      },
      landuse: {
        changed_area_ha_min: 1.0,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 10],
        runoff_increase_pct_range: [0, 5],
        changed_area_note: 'Sahel greening documented in satellite records post-2000',
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
        spi_7_range: [2.5, 4.5],
        spi_7_label: 'Near Normal (Amazon dry season June-Sept, wet Oct-May)',
        anomaly_7d_pct_range: [1500, 2000],
        anomaly_note: 'Deforestation itself reducing local rainfall 5-10% per decade',
        confidence_min: 0.6,
        source: 'INPE PRODES + Amazon deforestation-rainfall feedback study (2022)'
      },
      landuse: {
        changed_area_ha_min: 3.0,
        deforestation_ha_min: 200,
        urban_expansion_ha_range: [1, 10],
        runoff_increase_pct_range: [0, 5],
        changed_area_note: 'PRODES reports 10,000-15,000 km²/yr deforestation in this arc',
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
        spi_7_range: [-0.5, 0.5],
        spi_7_label: 'Highly seasonal — near 0 outside monsoon, wet during June-Sept',
        anomaly_7d_pct_range: [-10, 10],
        anomaly_note: 'Indo-Gangetic plain 600-900mm/yr, 80% in June-Sept',
        confidence_min: 0.7,
        source: 'IMD district rainfall records + CHIRPS South Asia 2023'
      },
      landuse: {
        changed_area_ha_min: 1500,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [1200, 1800],
        runoff_increase_pct_range: [0.5, 5.0],
        changed_area_note: 'Mostly cropland-to-built transitions, stable forest cover',
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
        spi_7_range: [-0.8, 0.5],
        spi_7_label: 'Near Normal — Jakarta bimodal, wet Nov-Mar',
        anomaly_7d_pct_range: [-40, 20],
        anomaly_note: 'Jakarta 1800mm/yr, increasingly impacted by urban heat island',
        confidence_min: 0.6,
        source: 'BMKG Indonesia rainfall records + CHIRPS 2022'
      },
      landuse: {
        changed_area_ha_min: 3000,
        deforestation_ha_min: 5,
        urban_expansion_ha_range: [3000, 4000],
        runoff_increase_pct_range: [1.0, 5.0],
        changed_area_note: 'Jabodetabek grew 4% annually — one of world\'s fastest expansions',
        source: 'World Bank Jakarta Urban Study 2022 + BPS Indonesia Land Use Census'
      }
    }
  }
]
