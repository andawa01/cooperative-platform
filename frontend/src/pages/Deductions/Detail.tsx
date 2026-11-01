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
import { useDeduction, useReverseDeduction } from '@/hooks/useDeductions'
import { formatMoney } from '@/lib/auth'
import { formatDate, formatDateTime } from '@/lib/datetime'
import { reasonLabel } from '@/lib/deductions'

export default function DeductionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const deduction = useDeduction(id)
  const reverse = useReverseDeduction(id!)
  const [actionError, setActionError] = useState<string | null>(null)

  if (deduction.isLoading) return <Loading />
  if (deduction.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(deduction.error as Error).message}
          onRetry={() => deduction.refetch()}
        />
      </div>
    )
  if (!deduction.data) return null

  const d = deduction.data
  const isReversal = d.reversal_of_id !== null

  const doReverse = async () => {
    setActionError(null)
    const reason = prompt(
      'Reason for reversing this deduction (this action is auditable):',
    )
    if (!reason || reason.trim().length === 0) return
    try {
      await reverse.mutateAsync({ reason: reason.trim() })
      navigate('/deductions')
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  return (
    <div>
      <PageHeader
        back={{ to: '/deductions', label: 'Deductions' }}
        title={formatMoney(d.amount, d.currency)}
        badge={
          isReversal ? (
            <StatusBadge tone="danger">
              <RotateCcw className="mr-0.5 h-3 w-3" />
              Reversal
            </StatusBadge>
          ) : (
            <StatusBadge tone="warning">Withheld</StatusBadge>
          )
        }
        description={
          <>
            {d.farmer_name} · {reasonLabel(d.reason_code)} · {formatDate(d.applied_at)}
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
          <CardHeader title="Deduction" />
          <CardBody>
            <dl className="space-y-3">
              <DetailRow
                label="Amount"
                value={
                  <span
                    className={
                      isReversal ? 'text-success-ink' : 'text-foreground'
                    }
                  >
                    {formatMoney(d.amount, d.currency)}
                  </span>
                }
              />
              <DetailRow label="Reason" value={reasonLabel(d.reason_code)} />
              {d.reference && (
                <DetailRow label="Reference" value={d.reference} mono />
              )}
              <DetailRow label="Applied on" value={formatDate(d.applied_at)} />
              <DetailRow label="Recorded at" value={formatDateTime(d.recorded_at)} />
              {d.notes && <DetailRow label="Notes" value={d.notes} />}
              {d.reversal_of_id && (
                <DetailRow label="Reverses" value={d.reversal_of_id} mono />
              )}
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="How this affects the member"
            description="A deduction withholds from what the cooperative hands over. It does not change what the member earned."
          />
          <CardBody>
            <p className="text-sm text-stone-600">
              The amount reduces{' '}
              <span className="font-medium text-foreground">net payable</span> on
              the member's balance and appears as its own line on their
              statement, tagged with the reason above — so a dispute can be
              settled by reading one document.
            </p>
            <Link
              to={`/farmers/${d.farmer_id}`}
              className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary-ink hover:text-primary-ink"
            >
              View farmer profile
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
