/**
 * KPI tile used by the dashboard and detail summaries.
 *
 * Deliberately restrained: a tinted icon tile, the number, and one line of
 * context. Colour is used to distinguish meaning (debt vs. paid), never as
 * decoration.
 */
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'brand' | 'success' | 'danger' | 'info'

const ICON_TONE: Record<Tone, string> = {
  neutral: 'bg-stone-100 text-stone-600',
  brand: 'bg-primary-soft text-primary-ink',
  success: 'bg-success-soft text-success-ink',
  danger: 'bg-danger-soft text-danger-ink',
  info: 'bg-info-soft text-info-ink',
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
  return (
    <div
      className={cn(
        'group rounded-card border border-border/80 bg-card p-4 shadow-card transition-shadow duration-200 hover:shadow-lift sm:p-5',
        className,
      )}
    >
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-lg [&_svg]:h-4 [&_svg]:w-4',
            ICON_TONE[tone],
          )}
        >
          {icon}
        </span>
        <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
          {label}
        </span>
      </div>
      <div className="mt-3 text-[22px] leading-none font-semibold tracking-tight text-foreground tabular-nums">
        {value}
      </div>
      {sub && (
        <div className="mt-1.5 text-xs text-muted-foreground">{sub}</div>
      )}
    </div>
  )
}
