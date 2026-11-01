import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Archive,
  Banknote,
  CheckCircle2,
  FileText,
  Package,
  TriangleAlert,
} from 'lucide-react'

import { Button, ButtonLink } from '@/components/common/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailRow,
} from '@/components/common/Card'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { FarmerStatusBadge } from '@/components/common/StatusBadge'
import { Avatar } from '@/components/common/Avatar'
import {
  useArchiveFarmer,
  useFarmer,
  useFarmerBalance,
  useVerifyFarmer,
} from '@/hooks/useFarmers'
import { useAuth } from '@/hooks/useAuth'
import { formatMoney } from '@/lib/auth'
import { formatDate, formatDateTime } from '@/lib/datetime'

export default function FarmerDetail() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const farmer = useFarmer(id)
  const balance = useFarmerBalance(id)
  const verify = useVerifyFarmer(id!)
  const archive = useArchiveFarmer(id!)
  const [actionError, setActionError] = useState<string | null>(null)

  if (farmer.isLoading) return <Loading />
  if (farmer.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(farmer.error as Error).message}
          onRetry={() => farmer.refetch()}
        />
      </div>
    )
  if (!farmer.data) return null

  const f = farmer.data
  const canVerify = f.status === 'pending_verification'
  const canArchive = f.status === 'active' || f.status === 'suspended'

  const doVerify = async () => {
    setActionError(null)
    try {
      await verify.mutateAsync()
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  const doArchive = async () => {
    setActionError(null)
    if (!confirm('Archive this farmer? Historical records are preserved.')) return
    try {
      await archive.mutateAsync()
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  return (
    <div>
      <PageHeader
        back={{ to: '/farmers', label: 'Farmers' }}
        title={`${f.first_name} ${f.last_name}`}
        badge={<FarmerStatusBadge status={f.status} />}
        description={f.phone}
        action={
          <>
            <ButtonLink
              to={`/farmers/${f.id}/statement`}
              icon={<FileText className="h-4 w-4" />}
            >
              Statement
            </ButtonLink>
            {isAdmin && canVerify && (
              <Button
                variant="primary"
                onClick={doVerify}
                disabled={verify.isPending}
              >
                <CheckCircle2 className="h-4 w-4" />
                {verify.isPending ? 'Verifying…' : 'Verify'}
              </Button>
            )}
            {isAdmin && canArchive && (
              <Button
                variant="danger"
                onClick={doArchive}
                disabled={archive.isPending}
              >
                <Archive className="h-4 w-4" />
                {archive.isPending ? 'Archiving…' : 'Archive'}
              </Button>
            )}
          </>
        }
      />

      {actionError && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Balance — the number that matters most on this screen */}
        <Card className="lg:col-span-3">
          <CardHeader
            title="Financial position"
            description="Derived from deliveries and payments — there is no stored balance to drift."
          />
          <CardBody>
            {balance.isLoading && <Loading label="Loading balance…" />}
            {balance.error && (
              <ErrorState message={(balance.error as Error).message} />
            )}
            {balance.data && (
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-danger/15 bg-danger-soft/60 p-4">
                  <div className="text-[11px] font-semibold tracking-wider text-danger-ink/80 uppercase">
                    Outstanding debt
                  </div>
                  <div className="mt-1.5 text-[26px] leading-none font-semibold text-danger-ink tabular-nums">
                    {formatMoney(
                      balance.data.outstanding_debt,
                      balance.data.currency,
                    )}
                  </div>
                  <div className="mt-1.5 text-xs text-danger-ink/75">
                    Still owed for deliveries
                  </div>
                </div>

                <div className="rounded-xl border border-success/20 bg-success-soft/70 p-4">
                  <div className="text-[11px] font-semibold tracking-wider text-success-ink/80 uppercase">
                    Available credit
                  </div>
                  <div className="mt-1.5 text-[26px] leading-none font-semibold text-success-ink tabular-nums">
                    {formatMoney(
                      balance.data.available_credit,
                      balance.data.currency,
                    )}
                  </div>
                  <div className="mt-1.5 text-xs text-success-ink/75">
                    Held on the farmer's behalf
                  </div>
                </div>

                <div className="rounded-xl border border-border bg-stone-50 p-4">
                  <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
                    Allocated to deliveries
                  </div>
                  <div className="mt-1.5 text-[26px] leading-none font-semibold text-foreground tabular-nums">
                    {formatMoney(
                      balance.data.allocated_to_deliveries,
                      balance.data.currency,
                    )}
                  </div>
                  <div className="mt-1.5 text-xs text-muted-foreground">
                    Already counted in debt
                  </div>
                </div>
              </div>
            )}

            {balance.data && balance.data.pending_valuation_deliveries > 0 && (
              <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2.5">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning-ink" />
                <p className="text-xs text-warning-ink">
                  {balance.data.pending_valuation_deliveries} delivery
                  {balance.data.pending_valuation_deliveries === 1 ? '' : 'ies'}{' '}
                  awaiting valuation — not included in the figures above.
                </p>
              </div>
            )}
          </CardBody>
        </Card>

        {/* Profile */}
        <Card className="lg:col-span-2">
          <CardHeader title="Profile" />
          <CardBody>
            <div className="mb-4 flex items-center gap-3 border-b border-border/60 pb-4">
              <Avatar
                first={f.first_name}
                last={f.last_name}
                className="h-11 w-11 text-sm"
              />
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">
                  {f.first_name} {f.last_name}
                </div>
                <div className="truncate text-xs text-muted-foreground tabular-nums">
                  {f.phone}
                </div>
              </div>
            </div>

            <dl className="space-y-3">
              <DetailRow label="National ID" value={f.national_id ?? '—'} />
              <DetailRow label="Date of birth" value={formatDate(f.date_of_birth)} />
              <DetailRow label="Location" value={f.location ?? '—'} />
              <DetailRow
                label="Verified"
                value={
                  f.verified_at ? formatDateTime(f.verified_at) : 'Not verified'
                }
              />
              <DetailRow
                label="Registered"
                value={formatDateTime(f.created_at)}
              />
            </dl>

            {f.notes && (
              <div className="mt-4 rounded-lg bg-stone-50 p-3">
                <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
                  Notes
                </div>
                <p className="mt-1 text-sm whitespace-pre-wrap text-stone-700">
                  {f.notes}
                </p>
              </div>
            )}
          </CardBody>
        </Card>

        {/* Quick actions */}
        <Card>
          <CardHeader title="Next actions" />
          <CardBody className="space-y-2.5">
            <Link
              to={`/deliveries/new?farmer_id=${f.id}`}
              className="group flex items-center gap-3 rounded-lg border border-border/80 p-3 transition-colors hover:border-primary-300 hover:bg-primary-soft/40"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-soft text-primary-ink">
                <Package className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">
                  Record delivery
                </span>
                <span className="block text-xs text-muted-foreground">
                  Value is snapshotted at today's rate
                </span>
              </span>
            </Link>

            <Link
              to={`/payments/new?farmer_id=${f.id}`}
              className="group flex items-center gap-3 rounded-lg border border-border/80 p-3 transition-colors hover:border-primary-300 hover:bg-primary-soft/40"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-success-soft text-success-ink">
                <Banknote className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">
                  Record payment
                </span>
                <span className="block text-xs text-muted-foreground">
                  Allocated to oldest debt first
                </span>
              </span>
            </Link>

            <Link
              to={`/farmers/${f.id}/statement`}
              className="group flex items-center gap-3 rounded-lg border border-border/80 p-3 transition-colors hover:border-primary-300 hover:bg-primary-soft/40"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-stone-100 text-stone-600">
                <FileText className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">
                  Open statement
                </span>
                <span className="block text-xs text-muted-foreground">
                  Every movement, in date order
                </span>
              </span>
            </Link>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
