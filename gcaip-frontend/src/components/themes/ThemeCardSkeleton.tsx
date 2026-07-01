import { THEME_LABELS, type ThemeId } from '@/types/theme'
import { themeIcon } from './themeIcons'

interface Props {
  theme: ThemeId
}

export default function ThemeCardSkeleton({ theme }: Props) {
  const Icon = themeIcon(theme)
  return (
    <div className="rounded-xl bg-panel-light/50 p-4 ring-1 ring-white/5">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/5">
          <Icon size={15} className="text-muted" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-ink">{THEME_LABELS[theme]}</p>
          <div className="mt-1.5 h-2 w-24 animate-pulse rounded-full bg-white/10" />
        </div>
        <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-sentinel" />
      </div>
    </div>
  )
}
