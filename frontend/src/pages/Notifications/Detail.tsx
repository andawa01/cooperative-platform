import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, MessageSquare, RefreshCw } from 'lucide-react'

import { Button } from '@/components/common/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailRow,
} from '@/components/common/Card'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
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
      <div className="py-6">
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
    <div>
      <PageHeader
        back={{ to: '/notifications', label: 'Notifications' }}
        title={n.recipient}
        badge={<NotificationStatusBadge status={n.status} />}
        description={new Date(n.created_at).toLocaleString()}
        action={
          isAdmin &&
          (n.status === 'failed' ||
            n.status === 'queued_redis_unreachable') && (
            <Button
              variant="primary"
              onClick={doRetry}
              disabled={retry.isPending}
            >
              <RefreshCw className="h-4 w-4" />
              {retry.isPending ? 'Retrying…' : 'Retry send'}
            </Button>
          )
        }
      />

      {actionError && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Message" />
          <CardBody>
            <div className="flex items-start gap-3 rounded-xl bg-stone-50 p-4">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-card text-stone-400 ring-1 ring-border">
                <MessageSquare className="h-4 w-4" />
              </span>
              <p className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
                {n.content}
              </p>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Dispatch" />
          <CardBody>
            <dl className="space-y-3">
            <DetailRow label="Channel" value={n.channel.toUpperCase()} />
            <DetailRow label="Template" value={n.template.replace('_', ' ')} />
            <DetailRow label="Attempts" value={String(n.attempts)} />
            <DetailRow
              label="Sent at"
              value={n.sent_at ? new Date(n.sent_at).toLocaleString() : '—'}
            />
            {n.last_error && (
              <DetailRow label="Last error" value={n.last_error} />
            )}
            </dl>

            <div className="mt-3 space-y-2 border-t border-border/60 pt-3">
              {farmer.data && (
                <Link
                  to={`/farmers/${farmer.data.id}`}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm font-medium text-primary-ink transition-colors hover:bg-primary-soft/50 hover:text-primary-ink"
                >
                  {farmer.data.first_name} {farmer.data.last_name}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              )}
              {n.related_entity_type === 'delivery' &&
                n.related_entity_id && (
                  <Link
                    to={`/deliveries/${n.related_entity_id}`}
                    className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm font-medium text-primary-ink transition-colors hover:bg-primary-soft/50 hover:text-primary-ink"
                  >
                    View delivery
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                )}
              {n.related_entity_type === 'payment' && n.related_entity_id && (
                <Link
                  to={`/payments/${n.related_entity_id}`}
                  className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm font-medium text-primary-ink transition-colors hover:bg-primary-soft/50 hover:text-primary-ink"
                >
                  View payment
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
