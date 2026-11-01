/**
 * Farmer statement.
 *
 * The chronological story of a farmer's position: every delivery, payment and
 * reversal, with the running debt/credit pair after each event. This is the
 * screen a dispute is settled on, so the closing pair is shown as prominently
 * as the entries — and it must match the balance on the farmer's page.
 *
 * The two links on the farmer detail page pointed at this route before it
 * existed, and silently fell through to the dashboard. It exists now.
 */
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Printer } from 'lucide-react'

import { Button } from '@/components/common/Button'
import { Card, CardBody, CardHeader } from '@/components/common/Card'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useFarmer, useFarmerStatement } from '@/hooks/useFarmers'
import { formatMoney } from '@/lib/auth'
import { formatDate, toIsoDate } from '@/lib/datetime'
import type { StatementEntry, StatementEntryType } from '@/types/api'

const TYPE_META: Record<
  StatementEntryType,
  { label: string; tone: 'success' | 'danger' | 'info' | 'neutral' }
> = {
  delivery: { label: 'Delivery', tone: 'success' },
  delivery_reversal: { label: 'Delivery reversal', tone: 'danger' },
  payment: { label: 'Payment', tone: 'info' },
  payment_reversal: { label: 'Payment reversal', tone: 'danger' },
}

// Default window: the last year. A co-op's cycle is seasonal, so a calendar
// year hides the start of the current season.
//
// `toIsoDate` is used rather than toISOString().slice(0, 10): the latter is UTC,
// so a clerk opening this at 01:00 in Nairobi would get yesterday as "to".
const TODAY = new Date()
const ONE_YEAR_AGO = new Date(TODAY.getTime() - 365 * 24 * 60 * 60 * 1000)

export default function FarmerStatement() {
  const { id } = useParams<{ id: string }>()
  const [start, setStart] = useState(toIsoDate(ONE_YEAR_AGO))
  const [end, setEnd] = useState(toIsoDate(TODAY))

  const farmer = useFarmer(id)
  const statement = useFarmerStatement(id, { start, end })

  if (farmer.isLoading) return <Loading />
  if (farmer.error) {
    return (
      <div className="py-6">
        <ErrorState
          message={(farmer.error as Error).message}
          onRetry={() => farmer.refetch()}
        />
      </div>
    )
  }
  if (!farmer.data) return null

  const f = farmer.data
  const data = statement.data
  const currency = data?.currency ?? 'KES'

  const columns: DataColumn<StatementEntry>[] = [
    {
      key: 'date',
      header: 'Date',
      hideBelow: 'sm',
      render: (entry) => (
        <span className="text-stone-600 tabular-nums">
          {formatDate(entry.date)}
        </span>
      ),
    },
    {
      key: 'description',
      header: 'Movement',
      render: (entry) => (
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge
              tone={TYPE_META[entry.type]?.tone ?? 'neutral'}
              dot={false}
            >
              {TYPE_META[entry.type]?.label ?? entry.type}
            </StatusBadge>
            <span className="text-xs text-muted-foreground sm:hidden">
              {formatDate(entry.date)}
            </span>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {entry.description}
          </div>
        </div>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      render: (entry) => {
        // A delivery recorded with no rate in force is unvalued, and the API
        // represents that as an amount of zero. Rendering "Ksh 0.00" would
        // claim the co-op valued the produce at nothing, which is a different
        // fact from "not priced yet".
        const unvalued = entry.type === 'delivery' && Number(entry.amount) === 0
        if (unvalued) {
          return (
            <span
              className="text-stone-400"
              title="Rate pending — this delivery has not been valued yet"
            >
              —
            </span>
          )
        }
        return (
          <span
            className={
              Number(entry.amount) < 0
                ? 'font-medium text-danger-ink'
                : 'font-medium text-foreground'
            }
          >
            {formatMoney(entry.amount, currency)}
          </span>
        )
      },
    },
    {
      key: 'debt',
      header: 'Debt after',
      align: 'right',
      hideBelow: 'md',
      render: (entry) => (
        <span className="text-stone-600">{formatMoney(entry.debt_after, currency)}</span>
      ),
    },
    {
      key: 'credit',
      header: 'Credit after',
      align: 'right',
      hideBelow: 'lg',
      render: (entry) => (
        <span className="text-stone-600">
          {formatMoney(entry.credit_after, currency)}
        </span>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        back={{ to: `/farmers/${f.id}`, label: `${f.first_name} ${f.last_name}` }}
        title="Statement"
        description="Every movement in date order, with the running position."
        action={
          <Button onClick={() => window.print()} className="print:hidden">
            <Printer className="h-4 w-4" />
            Print
          </Button>
        }
      />

      {/* Range */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label
            htmlFor="statement-start"
            className="mb-1 block text-[11px] font-semibold tracking-wider text-stone-500 uppercase"
          >
            From
          </label>
          <input
            id="statement-start"
            type="date"
            value={start}
            max={end}
            onChange={(event) => setStart(event.target.value)}
            className="h-9 rounded-lg border border-input bg-card px-3 text-sm shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
          />
        </div>
        <div>
          <label
            htmlFor="statement-end"
            className="mb-1 block text-[11px] font-semibold tracking-wider text-stone-500 uppercase"
          >
            To
          </label>
          <input
            id="statement-end"
            type="date"
            value={end}
            min={start}
            onChange={(event) => setEnd(event.target.value)}
            className="h-9 rounded-lg border border-input bg-card px-3 text-sm shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
          />
        </div>
      </div>

      {statement.isLoading && <Loading label="Building statement…" />}
      {statement.error && (
        <ErrorState
          message={(statement.error as Error).message}
          onRetry={() => statement.refetch()}
        />
      )}

      {data && (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader
                title="Opening position"
                // `start` is a period boundary, not an instant: slice the date
                // part so a west-of-UTC viewer does not see the previous day.
                description={`Before ${formatDate(data.start.slice(0, 10))}`}
              />
              <CardBody className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
                    Debt
                  </div>
                  <div className="mt-1 text-xl font-semibold text-foreground tabular-nums">
                    {formatMoney(data.opening.outstanding_debt, currency)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
                    Credit
                  </div>
                  <div className="mt-1 text-xl font-semibold text-foreground tabular-nums">
                    {formatMoney(data.opening.available_credit, currency)}
                  </div>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Closing position"
                description={`${data.entries.length} movement${data.entries.length === 1 ? '' : 's'} in this period`}
              />
              <CardBody className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[11px] font-semibold tracking-wider text-danger-ink/80 uppercase">
                    Debt
                  </div>
                  <div className="mt-1 text-xl font-semibold text-danger-ink tabular-nums">
                    {formatMoney(data.closing.outstanding_debt, currency)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] font-semibold tracking-wider text-success-ink/80 uppercase">
                    Credit
                  </div>
                  <div className="mt-1 text-xl font-semibold text-success-ink tabular-nums">
                    {formatMoney(data.closing.available_credit, currency)}
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>

          <DataTable
            ariaLabel="Statement entries"
            columns={columns}
            rows={data.entries}
            rowKey={(entry) =>
              entry.delivery_id ?? entry.payment_id ?? `${entry.date}-${entry.type}`
            }
            empty={{
              title: 'Nothing in this period',
              description: 'Widen the date range to see earlier movements.',
            }}
          />

          <p className="mt-3 text-xs text-muted-foreground">
            Money is derived from deliveries and payments — there is no stored
            balance. Closing figures match the balance shown on the farmer's page
            when the period ends today.
          </p>
        </>
      )}
    </div>
  )
}
