import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'

import { cn } from '@/lib/utils'

export function EmptyState({
  title,
  description,
  action,
  bordered = true,
  icon,
}: {
  title: string
  description?: string
  action?: ReactNode
  /** Set false when rendered inside a table body, which already has a border. */
  bordered?: boolean
  icon?: ReactNode
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center px-6 py-14 text-center',
        bordered &&
          'rounded-card border border-dashed border-stone-300 bg-card/60',
      )}
    >
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-stone-100 text-stone-400">
        {icon ?? <Inbox className="h-5 w-5" />}
      </div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-balance-pretty text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
