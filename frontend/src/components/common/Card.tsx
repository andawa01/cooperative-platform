/**
 * Surface primitives.
 *
 * Every panel in the app is a card: one border, one radius, one shadow. Having
 * a single component means a new screen cannot invent a slightly different
 * grey border, and a design change is one file.
 */
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function Card({
  className,
  children,
  ...props
}: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'overflow-hidden rounded-card border border-border/80 bg-card shadow-card',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeader({
  title,
  description,
  action,
  className,
  divider = false,
}: {
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
  /** Draw a rule between the header and the body. */
  divider?: boolean
}) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-3 px-5 py-4',
        divider && 'border-b border-border/70',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
          {title}
        </h2>
        {description && (
          <p className="mt-1 text-sm text-balance-pretty text-stone-600">
            {description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function CardBody({
  className,
  children,
  ...props
}: React.ComponentProps<'div'>) {
  return (
    <div className={cn('px-5 py-4', className)} {...props}>
      {children}
    </div>
  )
}

export function CardFooter({
  className,
  children,
  ...props
}: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 border-t border-border/70 bg-stone-50/60 px-5 py-3',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

/**
 * Label/value row used by every detail screen. Values default to right-aligned
 * with tabular numerals so money lines up down the column.
 */
export function DetailRow({
  label,
  value,
  mono = false,
  className,
}: {
  label: string
  value: ReactNode
  mono?: boolean
  className?: string
}) {
  return (
    <div className={cn('flex items-baseline justify-between gap-6', className)}>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          'text-right text-sm text-foreground',
          mono && 'font-mono text-xs break-all',
          !mono && 'tabular-nums',
        )}
      >
        {value}
      </dd>
    </div>
  )
}
