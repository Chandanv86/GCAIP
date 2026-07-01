import {
  Droplets,
  CloudRain,
  Waves,
  Trees,
  Mountain,
  Leaf,
  Map as MapIcon,
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
}

export function themeIcon(theme: ThemeId): LucideIcon {
  return ICONS[theme]
}
