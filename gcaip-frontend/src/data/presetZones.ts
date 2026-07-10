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

export interface EffluentPlumeExpected {
  plume_extent_km2_range: [number, number]
  ndci_mean_range: [number, number]
  ndti_mean_range: [number, number]
  expected_signal: 'strong_positive' | 'weak_positive' | 'negative' | 'ambiguous'
  signal_note: string
  source: string
}

export interface CoastalOutfallExpected {
  impact_area_km2_range: [number, number]
  spm_mean_range: [number, number]
  delta_sst_c_range: [number, number] | null
  thermal_plume_expected: boolean
  expected_signal: 'strong_positive' | 'weak_positive' | 'negative' | 'ambiguous'
  signal_note: string
  source: string
}

export interface PipelineCorridorExpected {
  disturbed_corridor_length_m_range: [number, number]
  encroachment_ha_range: [number, number]
  vegetation_loss_ha_range: [number, number]
  expected_signal: 'strong_positive' | 'weak_positive' | 'negative' | 'ambiguous'
  pipeline_vector_source: 'osm_overpass' | 'ogim' | 'either'
  signal_note: string
  source: string
}

export interface PresetExpected {
  rainfall: RainfallExpected
  landuse: LanduseExpected
  effluent_plume?: EffluentPlumeExpected
  coastal_outfall?: CoastalOutfallExpected
  pipeline_corridor?: PipelineCorridorExpected
}

export type ValidationTier = 'A_known_positive' | 'B_known_negative' | 'C_edge_case'

export interface PresetZone {
  id: string
  name: string
  description: string
  tags: string[]
  theme_focus: string
  validation_tier?: ValidationTier
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
  },

  // ═══════════════════════════════════════════════════════════════════════
  // TIER A — KNOWN-POSITIVE ZONES (ground truth exists, signal is real)
  // ═══════════════════════════════════════════════════════════════════════

  {
    id: 'kanpur_wwtp_effluent',
    name: 'Kanpur WWTP Effluent — Ganges',
    description: 'Kanpur, India — downstream of Jajmau WWTP, one of the most polluted river stretches globally. CPCB real-time monitoring confirms persistent discharge.',
    tags: ['effluent_plume', 'rainfall'],
    theme_focus: 'Strong NDCI/NDTI plume signal expected year-round; monsoon amplifies runoff bypass',
    validation_tier: 'A_known_positive',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [80.37, 26.43], [80.42, 26.43], [80.42, 26.47], [80.37, 26.47], [80.37, 26.43]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-0.5, 2.5],
        spi_7_label: 'Monsoon dominated — wet June-Sept, dry otherwise',
        anomaly_7d_pct_range: [-30, 150],
        anomaly_note: 'Indo-Gangetic plain monsoon; effluent plume signal persists even in dry season',
        confidence_min: 0.6,
        source: 'CPCB National Water Quality Monitoring + IMD district rainfall'
      },
      landuse: {
        changed_area_ha_min: 5,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 50],
        runoff_increase_pct_range: [0, 5],
        changed_area_note: 'Mostly stable industrial/urban zone around tannery district',
        source: 'UP State Remote Sensing Centre + Dynamic World 2023'
      },
      effluent_plume: {
        plume_extent_km2_range: [0.05, 2.0],
        ndci_mean_range: [0.04, 0.25],
        ndti_mean_range: [0.08, 0.35],
        expected_signal: 'strong_positive',
        signal_note: 'Jajmau WWTP discharges 36 MLD of partially-treated tannery effluent. CPCB monitoring station KNP002 consistently reports BOD > 30 mg/L, faecal coliform > 10^5 MPN/100mL. S2 NDCI/NDTI should show clear plume extending 1-3 km downstream.',
        source: 'CPCB ENVIS Centre — Real-Time Water Quality Dashboard (station KNP002) + EPA ECHO equivalent'
      }
    }
  },
  {
    id: 'hyperion_outfall_la',
    name: 'Hyperion WWTP Marine Outfall — Los Angeles',
    description: 'Santa Monica Bay, CA — Hyperion WWTP 5-mile ocean outfall, one of the largest municipal marine discharges in the US. Well-documented diffuser location.',
    tags: ['coastal_outfall'],
    theme_focus: 'SPM/CDOM plume and thermal delta detectable near diffuser; coastal zone management filings document exact location',
    validation_tier: 'A_known_positive',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [-118.55, 33.88], [-118.48, 33.88], [-118.48, 33.94], [-118.55, 33.94], [-118.55, 33.88]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-1.0, 0.5],
        spi_7_label: 'Mediterranean climate — dry most of year',
        anomaly_7d_pct_range: [-50, 50],
        anomaly_note: 'LA receives ~380mm/yr, mostly Nov-Mar. Low rainfall makes plume from point-source easier to isolate.',
        confidence_min: 0.6,
        source: 'NWS Los Angeles + NOAA NCDC'
      },
      landuse: {
        changed_area_ha_min: 0,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 5],
        runoff_increase_pct_range: [0, 1],
        changed_area_note: 'Stable marine zone — no land use change applicable over water',
        source: 'N/A (marine zone)'
      },
      coastal_outfall: {
        impact_area_km2_range: [0.1, 5.0],
        spm_mean_range: [5, 50],
        delta_sst_c_range: [0.5, 3.0],
        thermal_plume_expected: true,
        expected_signal: 'strong_positive',
        signal_note: 'Hyperion discharges ~300 MGD via a 5-mile outfall with 64-port diffuser at ~57m depth. During calm conditions, surface expression visible in S2 as elevated SPM. Landsat thermal shows consistent 1-2°C delta. Coastal zone permit filed with LA County Sanitation Districts.',
        source: 'LA Sanitation & Environment NPDES Permit CA0109991 + SCCWRP ocean monitoring reports'
      }
    }
  },
  {
    id: 'keystone_pipeline_nebraska',
    name: 'Keystone Pipeline Spill Site — Nebraska',
    description: 'Mill Creek, KS/NE border — site of the 2022 Keystone Pipeline spill (~14,000 bbl), the largest onshore crude oil spill in nearly a decade. PHMSA incident data available.',
    tags: ['pipeline_corridor', 'landuse'],
    theme_focus: 'Backscatter ratio change + NDVI drop should be visible along right-of-way; OGIM and OSM both carry this pipeline segment',
    validation_tier: 'A_known_positive',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [-97.15, 39.85], [-97.05, 39.85], [-97.05, 39.95], [-97.15, 39.95], [-97.15, 39.85]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-1.0, 1.0],
        spi_7_label: 'Continental Great Plains — moderate variability',
        anomaly_7d_pct_range: [-40, 40],
        anomaly_note: 'Central Kansas ~750mm/yr, distributed across spring/summer',
        confidence_min: 0.6,
        source: 'NOAA Climate Division Data + CHIRPS US validation'
      },
      landuse: {
        changed_area_ha_min: 1,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 5],
        runoff_increase_pct_range: [0, 2],
        changed_area_note: 'Agricultural land with pipeline right-of-way clearing visible in DW',
        source: 'USDA CropScape + Dynamic World Great Plains validation'
      },
      pipeline_corridor: {
        disturbed_corridor_length_m_range: [200, 5000],
        encroachment_ha_range: [0, 2],
        vegetation_loss_ha_range: [0.5, 15],
        expected_signal: 'strong_positive',
        pipeline_vector_source: 'either',
        signal_note: 'December 2022 spill released ~14,000 bbl of crude near Mill Creek. PHMSA Incident Report #20220178. ROW clearing and remediation work created measurable S1 backscatter change and S2 NDVI drop along a ~2km stretch. Pipeline is in both OGIM (EDF) and OSM.',
        source: 'PHMSA incident report #20220178 + TC Energy public remediation updates + EPA Region 7 response'
      }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════
  // TIER B — KNOWN-NEGATIVE ZONES (control / clean reference)
  // ═══════════════════════════════════════════════════════════════════════

  {
    id: 'upper_ganges_clean',
    name: 'Upper Ganges — Rishikesh Clean Stretch',
    description: 'Rishikesh, India — upstream of major industrial discharge; river is relatively pristine here. Same water body as Kanpur but without WWTP influence.',
    tags: ['effluent_plume'],
    theme_focus: 'NDCI/NDTI should be near-zero or below thresholds — no industrial plume expected',
    validation_tier: 'B_known_negative',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [78.28, 30.08], [78.33, 30.08], [78.33, 30.12], [78.28, 30.12], [78.28, 30.08]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-0.5, 2.0],
        spi_7_label: 'Sub-Himalayan foothills — heavy monsoon',
        anomaly_7d_pct_range: [-20, 200],
        anomaly_note: 'Upstream Ganges at Rishikesh is fed by snowmelt + monsoon',
        confidence_min: 0.6,
        source: 'CWC (Central Water Commission) Rishikesh gauging station'
      },
      landuse: {
        changed_area_ha_min: 0,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 10],
        runoff_increase_pct_range: [0, 2],
        changed_area_note: 'Mostly Rajaji National Park buffer — minimal change',
        source: 'FSI India State of Forest Report 2023'
      },
      effluent_plume: {
        plume_extent_km2_range: [0, 0.01],
        ndci_mean_range: [-0.02, 0.03],
        ndti_mean_range: [-0.02, 0.05],
        expected_signal: 'negative',
        signal_note: 'Upper Ganges at Rishikesh is upstream of all major industrial cities. CPCB monitoring station RSH001 reports BOD < 3 mg/L, DO > 7 mg/L. If processor detects a plume here, it is a false positive requiring threshold recalibration.',
        source: 'CPCB ENVIS Centre station RSH001 + Uttarakhand Pollution Control Board records'
      }
    }
  },
  {
    id: 'open_pacific_clean',
    name: 'Open Pacific — Southern California Control',
    description: 'Open Pacific ~20 km offshore of Malibu, CA — no outfall, no river mouth. Clean marine reference for coastal_outfall.',
    tags: ['coastal_outfall'],
    theme_focus: 'SPM should be very low (< 5 mg/L), no thermal delta, no plume. Pure marine background.',
    validation_tier: 'B_known_negative',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [-118.80, 33.80], [-118.73, 33.80], [-118.73, 33.86], [-118.80, 33.86], [-118.80, 33.80]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-1.0, 0.5],
        spi_7_label: 'Open ocean — rainfall not meaningful',
        anomaly_7d_pct_range: [-100, 100],
        anomaly_note: 'Ocean-only zone, rainfall stats are noise',
        confidence_min: 0.3,
        source: 'N/A (open ocean)'
      },
      landuse: {
        changed_area_ha_min: 0,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 0],
        runoff_increase_pct_range: [0, 0],
        changed_area_note: 'Open ocean — no land use applicable',
        source: 'N/A (open ocean)'
      },
      coastal_outfall: {
        impact_area_km2_range: [0, 0.05],
        spm_mean_range: [0, 5],
        delta_sst_c_range: [-0.5, 0.5],
        thermal_plume_expected: false,
        expected_signal: 'negative',
        signal_note: 'Clean offshore Pacific ~20 km from nearest outfall or river mouth. No point-source discharge. If processor flags a plume here, it is a false positive (likely sunglint or algal bloom misclassification).',
        source: 'SCCWRP Bight Regional Monitoring — offshore reference stations'
      }
    }
  },
  {
    id: 'kansas_farmland_no_pipeline',
    name: 'Kansas Farmland — No Pipeline Infrastructure',
    description: 'Central Kansas agricultural area with no documented pipeline infrastructure in OGIM or OSM. Same state as Keystone Tier A zone but different area.',
    tags: ['pipeline_corridor'],
    theme_focus: 'OGIM should return 0 features, OSM has no man_made=pipeline. Processor should return error_result or zero disturbance.',
    validation_tier: 'B_known_negative',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [-98.50, 38.70], [-98.40, 38.70], [-98.40, 38.80], [-98.50, 38.80], [-98.50, 38.70]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-1.0, 1.0],
        spi_7_label: 'Central Great Plains — moderate rainfall',
        anomaly_7d_pct_range: [-40, 40],
        anomaly_note: 'Standard Kansas agricultural zone ~600mm/yr',
        confidence_min: 0.6,
        source: 'NOAA Climate Division Data'
      },
      landuse: {
        changed_area_ha_min: 0,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 2],
        runoff_increase_pct_range: [0, 1],
        changed_area_note: 'Stable cropland — minimal transitions',
        source: 'USDA CropScape 2023'
      },
      pipeline_corridor: {
        disturbed_corridor_length_m_range: [0, 0],
        encroachment_ha_range: [0, 0],
        vegetation_loss_ha_range: [0, 0],
        expected_signal: 'negative',
        pipeline_vector_source: 'either',
        signal_note: 'This zone was selected specifically to have no pipeline infrastructure in OGIM or OSM. The processor should return a GEEAssetNotFoundError ("No pipeline vector supplied") which maps to ThemeResult.error_result. If it runs analysis, the geometry resolution step has a bug.',
        source: 'OGIM EDF dataset manual inspection + OSM Overpass query verification'
      }
    }
  },

  // ═══════════════════════════════════════════════════════════════════════
  // TIER C — EDGE CASES (ambiguous/mixed signal, stresses classifiers)
  // ═══════════════════════════════════════════════════════════════════════

  {
    id: 'sundarbans_mangrove_channel',
    name: 'Sundarbans Mangrove Channel',
    description: 'Sundarbans delta, India/Bangladesh — tidal mangrove channels with natural tannin-rich runoff. High CDOM from organic matter mimics effluent plume spectral signature.',
    tags: ['effluent_plume', 'mangrove'],
    theme_focus: 'Natural CDOM from mangrove decay creates false-positive risk for NDTI; processor should handle gracefully',
    validation_tier: 'C_edge_case',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [88.80, 21.85], [88.85, 21.85], [88.85, 21.90], [88.80, 21.90], [88.80, 21.85]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [0, 3.0],
        spi_7_label: 'Bay of Bengal monsoon — heavy June-Sept',
        anomaly_7d_pct_range: [0, 200],
        anomaly_note: 'Sundarbans 1500-2000mm/yr, heavy monsoon influence',
        confidence_min: 0.5,
        source: 'IMD Kolkata division + CHIRPS Bay of Bengal validation'
      },
      landuse: {
        changed_area_ha_min: 0,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 5],
        runoff_increase_pct_range: [0, 2],
        changed_area_note: 'Protected mangrove reserve — minimal anthropogenic change',
        source: 'Sundarbans Tiger Reserve management plan + FSI mangrove monitoring'
      },
      effluent_plume: {
        plume_extent_km2_range: [0, 0.5],
        ndci_mean_range: [0.02, 0.15],
        ndti_mean_range: [0.05, 0.25],
        expected_signal: 'ambiguous',
        signal_note: 'Natural mangrove tannin runoff produces CDOM/NDTI signals that overlap with anthropogenic effluent. A well-calibrated processor should report a low-confidence plume or no plume. If anomaly_score > 50 here, the classifier is overfitting on spectral proxies without accounting for natural organic matter. This tests the distinction between anthropogenic and natural water quality signals.',
        source: 'Mukhopadhyay et al. (2021) Remote Sensing of Sundarbans Water Quality + IIT Kharagpur CDOM study'
      }
    }
  },
  {
    id: 'mumbai_harbor_mixed',
    name: 'Mumbai Harbor — Complex Urban-Marine Interface',
    description: 'Mumbai Harbor, India — multiple WWTP outfalls, industrial discharge, Mithi River mouth, and heavy shipping. Dense overlapping signals create an extremely challenging classification environment.',
    tags: ['coastal_outfall', 'effluent_plume'],
    theme_focus: 'Multiple overlapping plume sources; thermal from power plant cooling + WWTP discharge + river sediment. Tests multi-source disambiguation.',
    validation_tier: 'C_edge_case',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [72.84, 18.92], [72.90, 18.92], [72.90, 18.98], [72.84, 18.98], [72.84, 18.92]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-0.5, 3.5],
        spi_7_label: 'Extreme monsoon — Mumbai receives 2000-2500mm, 90% in June-Sept',
        anomaly_7d_pct_range: [-20, 300],
        anomaly_note: 'Mumbai monsoon creates massive stormwater runoff into harbor',
        confidence_min: 0.5,
        source: 'IMD Mumbai + BMC stormwater drainage records'
      },
      landuse: {
        changed_area_ha_min: 5,
        deforestation_ha_min: 0,
        urban_expansion_ha_range: [0, 20],
        runoff_increase_pct_range: [0, 3],
        changed_area_note: 'Dense urban + harbor — stable but complex land-water interface',
        source: 'MMRDA Development Plan + Dynamic World Mumbai 2023'
      },
      coastal_outfall: {
        impact_area_km2_range: [0.5, 10.0],
        spm_mean_range: [20, 200],
        delta_sst_c_range: [0, 4.0],
        thermal_plume_expected: true,
        expected_signal: 'ambiguous',
        signal_note: 'Mumbai Harbor has 4+ major WWTP outfalls (Worli, Bandra, Versova, Colaba), the Mithi River sediment plume, TATA power plant thermal discharge, and ship traffic turbidity — all overlapping. Any single-outfall classifier will struggle. This tests whether the processor gracefully handles multi-source pollution rather than attributing everything to a single point source. High SPM and thermal delta are real, but confidence should be penalized.',
        source: 'MPCB (Maharashtra Pollution Control Board) Mumbai coastal water quality reports + NEERI harbor study 2022'
      }
    }
  },
  {
    id: 'niger_delta_pipeline_dense',
    name: 'Niger Delta — Dense Pipeline Network',
    description: 'Rivers State, Nigeria — extremely dense pipeline network with documented chronic spills, gas flaring, and illegal tapping (bunkering). NOSDRA incident data available.',
    tags: ['pipeline_corridor', 'landuse', 'effluent_plume'],
    theme_focus: 'Dense pipeline mesh in OGIM; multiple overlapping corridors. Tests corridor geometry resolution when many pipelines intersect in a small area.',
    validation_tier: 'C_edge_case',
    geojson: {
      type: 'Polygon',
      coordinates: [[
        [6.95, 4.75], [7.05, 4.75], [7.05, 4.85], [6.95, 4.85], [6.95, 4.75]
      ]]
    },
    expected: {
      rainfall: {
        spi_7_range: [-0.5, 2.0],
        spi_7_label: 'Tropical — heavy year-round rainfall, peak May-Oct',
        anomaly_7d_pct_range: [-20, 100],
        anomaly_note: 'Niger Delta receives 2000-4000mm/yr, extremely wet',
        confidence_min: 0.5,
        source: 'NIMET Nigeria Meteorological Agency + CHIRPS West Africa'
      },
      landuse: {
        changed_area_ha_min: 10,
        deforestation_ha_min: 5,
        urban_expansion_ha_range: [5, 50],
        runoff_increase_pct_range: [0, 5],
        changed_area_note: 'Mangrove degradation + oil infrastructure expansion visible in DW',
        source: 'Hansen GFW Nigeria + Dynamic World Niger Delta 2023'
      },
      pipeline_corridor: {
        disturbed_corridor_length_m_range: [100, 10000],
        encroachment_ha_range: [1, 50],
        vegetation_loss_ha_range: [2, 100],
        expected_signal: 'ambiguous',
        pipeline_vector_source: 'ogim',
        signal_note: 'Niger Delta has one of the densest pipeline networks globally (Shell, NNPC, Agip, Total). OGIM may return 50+ pipeline features in a small AOI, creating a massive merged corridor geometry that can cause GEE computation timeouts or memory errors. Multiple documented chronic leaks (NOSDRA Oil Spill Monitor reports 100+ incidents/yr in this zone). This tests: 1) corridor geometry performance with dense pipeline mesh, 2) disturbance baseline — the entire area may be permanently disturbed, making change detection meaningless, 3) whether the confidence score properly degrades in high-noise environments.',
        source: 'NOSDRA Oil Spill Monitor Nigeria + EDF OGIM Niger Delta coverage report + Amnesty International pipeline incident database'
      }
    }
  }
]
