/**
 * Farmer avatar medallion.
 *
 * Lives outside the picker because list rows, detail headers and the account
 * screen all show the same initials-in-a-circle, and a component file should
 * only export components (fast refresh).
 */
import { cn, initials } from '@/lib/utils'

export function Avatar({
  first,
  last,
  className,
}: {
  first: string
  last: string
  className?: string
}) {
  return (
    <span
      className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary-ink ring-1 ring-primary-100',
        className,
      )}
      aria-hidden="true"
    >
      {initials(first, last)}
    </span>
  )
}
