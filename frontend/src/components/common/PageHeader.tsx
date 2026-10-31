/**
 * Page title block shared by every screen.
 *
 * Keeping this in one place is what makes the heading, subtitle, back link and
 * primary action line up identically on every page.
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

export function PageHeader({
  title,
  description,
  action,
  back,
  badge,
}: {
  title: string
  description?: ReactNode
  action?: ReactNode
  /** Renders an inline back link above the title. */
  back?: { to: string; label: string }
  badge?: ReactNode
}) {
  return (
    <div className="mb-6">
      {back && (
        <Link
          to={back.to}
          className="mb-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {back.label}
        </Link>
      )}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] text-foreground">
              {title}
            </h1>
            {badge}
          </div>
          {description && (
            <p className="mt-1.5 max-w-2xl text-sm text-balance-pretty text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {action && (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {action}
          </div>
        )}
      </div>
    </div>
  )
}
