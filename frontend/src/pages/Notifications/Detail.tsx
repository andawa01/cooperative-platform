import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'

import { ErrorState, Loading } from '@/components/common/Loading'
import { NotificationStatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import { useNotification, useRetryNotification } from '@/hooks/useNotifications'
import { useFarmer } from '@/hooks/useFarmers'

export default function NotificationDetail() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const notif = useNotification(id)
  const farmer = useFarmer(notif.data?.farmer_id)
  const retry = useRetryNotification(id!)
  const [actionError, setActionError] = useState<string | null>(null)

  if (notif.isLoading) return <Loading />
  if (notif.error)
    return (
      <div className="p-6">
        <ErrorState
          message={(notif.error as Error).message}
          onRetry={() => notif.refetch()}
        />
      </div>
    )
  if (!notif.data) return null

  const n = notif.data

  const doRetry = async () => {
    setActionError(null)
    try {
      await retry.mutateAsync()
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  return (
    <div className="p-4 md:p-6">
      <Link
        to="/notifications"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to notifications
      </Link>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-gray-900">
              {n.recipient}
            </h1>
            <NotificationStatusBadge status={n.status} />
          </div>
          <p className="mt-1 text-sm text-gray-600">
            {new Date(n.created_at).toLocaleString()}
          </p>
        </div>

        {isAdmin &&
          (n.status === 'failed' || n.status === 'queued_redis_unreachable') && (
            <button
              onClick={doRetry}
              disabled={retry.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
            >
              <RefreshCw className="h-4 w-4" />
              {retry.isPending ? 'Retrying…' : 'Retry send'}
            </button>
          )}
      </div>

      {actionError && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Message
          </h2>
          <p className="whitespace-pre-wrap text-sm text-gray-900">
            {n.content}
          </p>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Dispatch
          </h2>
          <dl className="space-y-3 text-sm">
            <Row label="Channel" value={n.channel.toUpperCase()} />
            <Row label="Template" value={n.template.replace('_', ' ')} />
            <Row label="Attempts" value={String(n.attempts)} />
            <Row
              label="Sent at"
              value={n.sent_at ? new Date(n.sent_at).toLocaleString() : '—'}
            />
            {n.last_error && (
              <Row label="Last error" value={n.last_error} />
            )}
            {farmer.data && (
              <div className="pt-2">
                <Link
                  to={`/farmers/${farmer.data.id}`}
                  className="text-sm text-primary-700 hover:text-primary-800"
                >
                  View farmer: {farmer.data.first_name} {farmer.data.last_name} →
                </Link>
              </div>
            )}
            {n.related_entity_type === 'delivery' && n.related_entity_id && (
              <div>
                <Link
                  to={`/deliveries/${n.related_entity_id}`}
                  className="text-sm text-primary-700 hover:text-primary-800"
                >
                  View delivery →
                </Link>
              </div>
            )}
            {n.related_entity_type === 'payment' && n.related_entity_id && (
              <div>
                <Link
                  to={`/payments/${n.related_entity_id}`}
                  className="text-sm text-primary-700 hover:text-primary-800"
                >
                  View payment →
                </Link>
              </div>
            )}
          </dl>
        </section>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-gray-600">{label}</dt>
      <dd className="text-right text-gray-900">{value}</dd>
    </div>
  )
}