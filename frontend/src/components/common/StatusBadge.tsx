/**
 * Status pills. One file so the same word always renders in the same colour —
 * a clerk should be able to scan a list and read status by shape and colour
 * before reading the label.
 */
import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

const TONE_CLASSES: Record<Tone, { pill: string; dot: string }> = {
  neutral: {
    pill: 'border-stone-200 bg-stone-100/80 text-stone-700',
    dot: 'bg-stone-400',
  },
  success: {
    pill: 'border-success/25 bg-success-soft text-success-ink',
    dot: 'bg-success',
  },
  warning: {
    pill: 'border-warning/30 bg-warning-soft text-warning-ink',
    dot: 'bg-warning',
  },
  danger: {
    pill: 'border-danger/25 bg-danger-soft text-danger-ink',
    dot: 'bg-danger',
  },
  info: {
    pill: 'border-info/25 bg-info-soft text-info-ink',
    dot: 'bg-info',
  },
}

export function StatusBadge({
  tone = 'neutral',
  children,
  className,
  dot = true,
}: {
  tone?: Tone
  children: React.ReactNode
  className?: string
  /** A leading dot makes status scannable at a glance. */
  dot?: boolean
}) {
  const classes = TONE_CLASSES[tone]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        classes.pill,
        className,
      )}
    >
      {dot && (
        <span
          className={cn('h-1.5 w-1.5 shrink-0 rounded-full', classes.dot)}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  )
}

// Farmer-specific colour mapping, kept here so any screen renders the
// same word with the same colour.
export function FarmerStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; tone: Tone }> = {
    pending_verification: { label: 'Pending', tone: 'warning' },
    active: { label: 'Active', tone: 'success' },
    suspended: { label: 'Suspended', tone: 'danger' },
    archived: { label: 'Archived', tone: 'neutral' },
    merged: { label: 'Merged', tone: 'info' },
  }
  const entry = map[status] ?? { label: status, tone: 'neutral' as Tone }
  return <StatusBadge tone={entry.tone}>{entry.label}</StatusBadge>
}

export function NotificationStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; tone: Tone }> = {
    queued: { label: 'Queued', tone: 'info' },
    sending: { label: 'Sending', tone: 'info' },
    sent: { label: 'Sent', tone: 'success' },
    failed: { label: 'Failed', tone: 'danger' },
    queued_redis_unreachable: { label: 'Queued (offline)', tone: 'warning' },
    unknown: { label: 'Unknown', tone: 'neutral' },
  }
  const entry = map[status] ?? { label: status, tone: 'neutral' as Tone }
  return <StatusBadge tone={entry.tone}>{entry.label}</StatusBadge>
}

/** Small neutral chip, e.g. a produce code or a page count. */
export function Chip({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border border-border/70 bg-stone-50 px-1.5 py-0.5 font-mono text-[11px] text-stone-600',
        className,
      )}
    >
      {children}
    </span>
  )
}
