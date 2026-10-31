import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, FileText, Archive } from 'lucide-react'
import { useState } from 'react'

import { ErrorState, Loading } from '@/components/common/Loading'
import { FarmerStatusBadge } from '@/components/common/StatusBadge'
import {
  useArchiveFarmer,
  useFarmer,
  useFarmerBalance,
  useVerifyFarmer,
} from '@/hooks/useFarmers'
import { useAuth } from '@/hooks/useAuth'
import { formatMoney } from '@/lib/auth'

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
      <div className="p-6">
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
    <div className="p-4 md:p-6">
      <Link
        to="/farmers"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to farmers
      </Link>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-gray-900">
              {f.first_name} {f.last_name}
            </h1>
            <FarmerStatusBadge status={f.status} />
          </div>
          <p className="mt-1 text-sm text-gray-600">{f.phone}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            to={`/farmers/${f.id}/statement`}
            className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <FileText className="h-4 w-4" />
            Statement
          </Link>
          {isAdmin && canVerify && (
            <button
              onClick={doVerify}
              disabled={verify.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
            >
              <CheckCircle2 className="h-4 w-4" />
              {verify.isPending ? 'Verifying…' : 'Verify'}
            </button>
          )}
          {isAdmin && canArchive && (
            <button
              onClick={doArchive}
              disabled={archive.isPending}
              className="inline-flex items-center gap-2 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
            >
              <Archive className="h-4 w-4" />
              {archive.isPending ? 'Archiving…' : 'Archive'}
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {/* Profile card */}
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Profile
          </h2>
          <dl className="space-y-3 text-sm">
            <Row label="National ID" value={f.national_id ?? '—'} />
            <Row label="Date of birth" value={f.date_of_birth ?? '—'} />
            <Row label="Location" value={f.location ?? '—'} />
            <Row
              label="Verified"
              value={f.verified_at ? new Date(f.verified_at).toLocaleString() : 'No'}
            />
            <Row label="Registered" value={new Date(f.created_at).toLocaleString()} />
            {f.notes && (
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-gray-500">
                  Notes
                </dt>
                <dd className="mt-1 whitespace-pre-wrap text-gray-800">
                  {f.notes}
                </dd>
              </div>
            )}
          </dl>
        </section>

        {/* Balance card */}
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Financial position
          </h2>
          {balance.isLoading && <Loading label="Loading balance…" />}
          {balance.error && (
            <ErrorState message={(balance.error as Error).message} />
          )}
          {balance.data && (
            <dl className="space-y-3 text-sm">
              <div className="flex items-baseline justify-between">
                <dt className="text-gray-600">Outstanding debt</dt>
                <dd className="text-lg font-semibold text-gray-900">
                  {formatMoney(balance.data.outstanding_debt, balance.data.currency)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between">
                <dt className="text-gray-600">Available credit</dt>
                <dd className="text-lg font-semibold text-green-700">
                  {formatMoney(balance.data.available_credit, balance.data.currency)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between">
                <dt className="text-gray-600">Allocated to deliveries</dt>
                <dd className="text-gray-900">
                  {formatMoney(
                    balance.data.allocated_to_deliveries,
                    balance.data.currency,
                  )}
                </dd>
              </div>
              {balance.data.pending_valuation_deliveries > 0 && (
                <div className="rounded-md bg-amber-50 p-2 text-xs text-amber-800">
                  {balance.data.pending_valuation_deliveries} delivery
                  {balance.data.pending_valuation_deliveries === 1 ? '' : 'ies'} awaiting
                  valuation
                </div>
              )}
            </dl>
          )}
        </section>
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          to={`/deliveries/new?farmer_id=${f.id}`}
          className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          Record delivery
        </Link>
        <Link
          to={`/payments/new?farmer_id=${f.id}`}
          className="rounded-md border border-primary-300 bg-white px-4 py-2 text-sm font-medium text-primary-700 hover:bg-primary-50"
        >
          Record payment
        </Link>
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