/**
 * Small coloured pill for statuses across resources.
 * One file so the visual language stays consistent.
 */
import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-gray-100 text-gray-700 border-gray-200',
  success: 'bg-green-50 text-green-700 border-green-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  danger: 'bg-red-50 text-red-700 border-red-200',
  info: 'bg-blue-50 text-blue-700 border-blue-200',
}

export function StatusBadge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: Tone
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        TONE_CLASSES[tone],
        className,
      )}
    >
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