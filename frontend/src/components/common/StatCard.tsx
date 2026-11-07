/**
 * KPI tile used by the dashboard and detail summaries.
 *
 * Colour carries meaning, not decoration. A tinted surface plus a coloured
 * figure lets a row of six numbers read as "owed / withheld / paid" before a
 * single label is read, which is the whole point of a dashboard.
 *
 * Two rules keep it from turning into a paint chart:
 *
 * - `neutral` stays a plain white (or dark) card. A screen where everything is
 *   coloured has no hierarchy left, so the calm tile is part of the design.
 * - Only the `-soft`/`-ink` token pairs are used. They invert in dark mode
 *   (pale green wash in light, deep green wash with light text in dark), so a
 *   tone never has to be defined twice.
 */
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'brand' | 'success' | 'danger' | 'info' | 'warning'

const ICON_TONE: Record<Tone, string> = {
  neutral: 'bg-stone-100 text-stone-600',
  brand: 'bg-primary-soft text-primary-ink',
  success: 'bg-success-soft text-success-ink',
  danger: 'bg-danger-soft text-danger-ink',
  info: 'bg-info-soft text-info-ink',
  warning: 'bg-warning-soft text-warning-ink',
}

/**
 * Surface for each tone: a diagonal wash from the tone's tint into the card,
 * so the colour reads as depth rather than a second block of colour.
 */
const CARD_TONE: Record<Tone, string> = {
  neutral: 'border-border/80 bg-card',
  brand:
    'border-primary/25 bg-gradient-to-br from-primary-soft via-primary-soft/45 to-card',
  success:
    'border-success/25 bg-gradient-to-br from-success-soft via-success-soft/45 to-card',
  danger:
    'border-danger/25 bg-gradient-to-br from-danger-soft via-danger-soft/45 to-card',
  info: 'border-info/25 bg-gradient-to-br from-info-soft via-info-soft/45 to-card',
  warning:
    'border-warning/30 bg-gradient-to-br from-warning-soft via-warning-soft/45 to-card',
}

/** The blurred corner bloom. Same hue, low alpha — depth, not a second colour. */
const GLOW_TONE: Record<Tone, string> = {
  neutral: '',
  brand: 'bg-primary/25',
  success: 'bg-success/25',
  danger: 'bg-danger/25',
  info: 'bg-info/25',
  warning: 'bg-warning/30',
}

const LABEL_TONE: Record<Tone, string> = {
  neutral: 'text-muted-foreground',
  brand: 'text-primary-ink/80',
  success: 'text-success-ink/80',
  danger: 'text-danger-ink/85',
  info: 'text-info-ink/80',
  warning: 'text-warning-ink/85',
}

const VALUE_TONE: Record<Tone, string> = {
  neutral: 'text-foreground',
  brand: 'text-primary-ink',
  success: 'text-success-ink',
  danger: 'text-danger-ink',
  info: 'text-info-ink',
  warning: 'text-warning-ink',
}

const SUB_TONE: Record<Tone, string> = {
  neutral: 'text-muted-foreground',
  brand: 'text-primary-ink/70',
  success: 'text-success-ink/70',
  danger: 'text-danger-ink/70',
  info: 'text-info-ink/70',
  warning: 'text-warning-ink/70',
}

export function StatCard({
  icon,
  label,
  value,
  sub,
  tone = 'neutral',
  className,
}: {
  icon: ReactNode
  label: string
  value: string
  sub?: ReactNode
  tone?: Tone
  className?: string
}) {
  const tinted = tone !== 'neutral'

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-card border p-4 shadow-card transition-shadow duration-200 hover:shadow-lift sm:p-5',
        CARD_TONE[tone],
        className,
      )}
    >
      {tinted && (
        <span
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute -top-12 -right-10 h-28 w-28 rounded-full blur-2xl',
            GLOW_TONE[tone],
          )}
        />
      )}

      <div className="relative flex items-center gap-2.5">
        <span
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-lg [&_svg]:h-4 [&_svg]:w-4',
            // On a tinted card the icon sits on its own colour, so give it the
            // card surface as a chip and keep the tone only for the glyph.
            tinted ? 'bg-card/80 shadow-xs' : '',
            ICON_TONE[tone],
          )}
        >
          {icon}
        </span>
        <span
          className={cn(
            'text-[11px] font-semibold tracking-wider uppercase',
            LABEL_TONE[tone],
          )}
        >
          {label}
        </span>
      </div>

      <div
        className={cn(
          'relative mt-3 text-[22px] leading-none font-semibold tracking-tight tabular-nums',
          VALUE_TONE[tone],
        )}
      >
        {value}
      </div>

      {sub && (
        <div className={cn('relative mt-1.5 text-xs', SUB_TONE[tone])}>
          {sub}
        </div>
      )}
    </div>
  )
}
