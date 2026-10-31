import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, RotateCcw } from 'lucide-react'

import { Button } from '@/components/common/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailRow,
} from '@/components/common/Card'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import { usePayment, useReversePayment } from '@/hooks/usePayments'
import { useFarmer } from '@/hooks/useFarmers'
import { formatMoney } from '@/lib/auth'

export default function PaymentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const payment = usePayment(id)
  const farmer = useFarmer(payment.data?.farmer_id)
  const reverse = useReversePayment(id!)
  const [actionError, setActionError] = useState<string | null>(null)

  if (payment.isLoading) return <Loading />
  if (payment.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(payment.error as Error).message}
          onRetry={() => payment.refetch()}
        />
      </div>
    )
  if (!payment.data) return null

  const p = payment.data
  const isReversal = p.reversal_of_id !== null
  const unallocated = Number(p.unallocated_amount)

  const doReverse = async () => {
    setActionError(null)
    const reason = prompt(
      'Reason for reversing this payment (this action is auditable):',
    )
    if (!reason || reason.trim().length === 0) return
    try {
      await reverse.mutateAsync({ reason: reason.trim() })
      navigate('/payments')
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  return (
    <div>
      <PageHeader
        back={{ to: '/payments', label: 'Payments' }}
        title={formatMoney(p.amount, p.currency)}
        badge={
          <>
            {isReversal && (
              <StatusBadge tone="danger">
                <RotateCcw className="mr-0.5 h-3 w-3" />
                Reversal
              </StatusBadge>
            )}
            {unallocated > 0 && !isReversal && (
              <StatusBadge tone="info">
                {formatMoney(unallocated, p.currency)} unallocated
              </StatusBadge>
            )}
            {unallocated <= 0 && !isReversal && (
              <StatusBadge tone="success">Fully allocated</StatusBadge>
            )}
          </>
        }
        description={
          <>
            {farmer.data
              ? `${farmer.data.first_name} ${farmer.data.last_name}`
              : 'Loading…'}{' '}
            · {new Date(p.paid_at).toLocaleString()}
          </>
        }
        action={
          isAdmin &&
          !isReversal && (
            <Button
              variant="danger"
              onClick={doReverse}
              disabled={reverse.isPending}
            >
              <RotateCcw className="h-4 w-4" />
              {reverse.isPending ? 'Reversing…' : 'Reverse'}
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
          <CardHeader title="Payment" />
          <CardBody>
            <dl className="space-y-3">
            <DetailRow label="Amount" value={formatMoney(p.amount, p.currency)} />
            <DetailRow label="Method" value={p.method.replace('_', ' ')} />
            {p.reference && <DetailRow label="Reference" value={p.reference} />}
            <DetailRow
              label="Paid at"
              value={new Date(p.paid_at).toLocaleString()}
            />
            <DetailRow
              label="Recorded at"
              value={new Date(p.recorded_at).toLocaleString()}
            />
            <DetailRow
              label="Unallocated"
              value={formatMoney(p.unallocated_amount, p.currency)}
            />
            {p.notes && <DetailRow label="Notes" value={p.notes} />}
            {p.reversal_of_id && (
              <DetailRow label="Reverses" value={p.reversal_of_id} mono />
            )}
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title={`Allocations (${p.allocations.length})`}
            description="Which deliveries this money settled."
          />
          <CardBody>
            {p.allocations.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No deliveries were allocated against this payment. The full
                amount is credit on account.
              </p>
            ) : (
              <ul className="divide-y divide-border/60">
                {p.allocations.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center justify-between gap-3 py-2.5 text-sm"
                  >
                    <Link
                      to={`/deliveries/${a.delivery_id}`}
                      className="group inline-flex items-center gap-1.5 font-mono text-xs text-primary-ink hover:text-primary-ink"
                    >
                      Delivery {a.delivery_id.slice(0, 8)}…
                      <ArrowRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
                    </Link>
                    <span
                      className={
                        Number(a.amount) < 0
                          ? 'font-medium text-danger-ink tabular-nums'
                          : 'font-medium text-foreground tabular-nums'
                      }
                    >
                      {formatMoney(a.amount, p.currency)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      {farmer.data && (
        <Link
          to={`/farmers/${farmer.data.id}`}
          className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-primary-ink hover:text-primary-ink"
        >
          View farmer profile
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      )}
    </div>
  )
}
