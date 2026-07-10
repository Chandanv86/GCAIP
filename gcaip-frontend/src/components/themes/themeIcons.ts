import {
  Droplets,
  CloudRain,
  Waves,
  Trees,
  Mountain,
  Leaf,
  Map as MapIcon,
  Pipette,
  Anchor,
  Activity,
  type LucideIcon,
} from 'lucide-react'
import type { ThemeId } from '@/types/theme'

const ICONS: Record<ThemeId, LucideIcon> = {
  flood: Droplets,
  rainfall: CloudRain,
  reservoir: Waves,
  mangrove: Trees,
  erosion: Mountain,
  vegetation: Leaf,
  landuse: MapIcon,
  effluent_plume: Pipette,
  coastal_outfall: Anchor,
  pipeline_corridor: Activity,
}

export function themeIcon(theme: ThemeId): LucideIcon {
  return ICONS[theme]
}
