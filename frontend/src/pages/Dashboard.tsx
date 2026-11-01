import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowUpRight,
  Banknote,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Card, CardBody, CardHeader } from '@/components/common/Card'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { StatCard } from '@/components/common/StatCard'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useDashboardSummary } from '@/hooks/useDashboard'
import { formatMoney, parseMoney } from '@/lib/auth'
import { formatDate, formatDayMonth, formatTime } from '@/lib/datetime'

const LINE_COLOURS = ['#15803d', '#0891b2', '#7c3aed', '#c2410c', '#be123c']

// Chart chrome is themed with CSS variables so the dashboard follows dark mode
// without Recharts needing to know about React state.
const TOOLTIP_STYLE = {
  fontSize: 12,
  background: 'var(--color-card)',
  color: 'var(--color-foreground)',
  border: '1px solid var(--color-border)',
  borderRadius: 10,
  boxShadow: '0 10px 30px -12px rgb(28 25 23 / 0.25)',
  padding: '8px 10px',
} as const

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useDashboardSummary(30)

  if (isLoading) return <Loading label="Loading dashboard…" />
  if (error)
    return (
      <div className="py-6">
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      </div>
    )
  if (!data) return null

  // Short labels for the daily chart so mobile isn't crowded.
  const dailyData = data.deliveries_daily.map((d) => ({
    date: formatDayMonth(d.date), // dd/mm
    count: d.count,
    value: parseMoney(d.value),
  }))

  const lineData = data.deliveries_by_line.map((l, i) => ({
    name: l.produce_line_name,
    value: parseMoney(l.value),
    count: l.count,
    colour: LINE_COLOURS[i % LINE_COLOURS.length],
  }))

  const status = data.farmers_by_status
  const maxStatus = Math.max(
    status.active,
    status.pending_verification,
    status.suspended,
    status.archived,
    status.merged,
    1,
  )

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description={
          <>
            Last {data.period_days} days · refreshed{' '}
            {formatTime(data.generated_at)}
          </>
        }
      />

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <StatCard
          icon={<Wallet />}
          tone="danger"
          label="Outstanding debt"
          value={formatMoney(data.outstanding_debt_total, data.currency)}
          sub="Owed to farmers for deliveries"
        />
        <StatCard
          icon={<Banknote />}
          tone="success"
          label={`Paid (${data.period_days}d)`}
          value={formatMoney(data.payments_value_in_period, data.currency)}
          sub={`${data.payments_in_period} payments`}
        />
        <StatCard
          icon={<TrendingUp />}
          tone="brand"
          label={`Delivered (${data.period_days}d)`}
          value={formatMoney(data.deliveries_value_in_period, data.currency)}
          sub={`${data.deliveries_in_period} deliveries`}
        />
        <StatCard
          icon={<Users />}
          tone="info"
          label="Active farmers"
          value={String(status.active)}
          sub={`of ${data.farmers_total} registered`}
        />
      </div>

      {/* Alerts */}
      {data.pending_valuation_count > 0 && (
        <div className="mt-4 flex items-start gap-3 rounded-card border border-warning/30 bg-warning-soft p-4">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-card/70 text-warning-ink">
            <AlertTriangle className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-warning-ink">
              {data.pending_valuation_count} deliver
              {data.pending_valuation_count === 1 ? 'y is' : 'ies are'} awaiting
              valuation
            </p>
            <p className="mt-0.5 text-xs text-warning-ink/80">
              These cannot be paid against until a rate is applied.
            </p>
          </div>
          <Link
            to="/deliveries?unvalued=1"
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-warning-ink underline-offset-2 hover:underline"
          >
            Review
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}

      {/* Charts */}
      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader title="Deliveries per day" />
          <CardBody className="pt-1">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dailyData} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    vertical={false}
                    stroke="var(--color-border)"
                  />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: 'var(--color-stone-500)' }}
                    axisLine={false}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: 'var(--color-stone-500)' }}
                    axisLine={false}
                    tickLine={false}
                    width={40}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={TOOLTIP_STYLE}
                    cursor={{ fill: 'rgba(21, 128, 61, 0.06)' }}
                    formatter={(value) => [`${value} deliveries`, '']}
                    labelFormatter={(label) => `Date: ${label}`}
                  />
                  <Bar
                    dataKey="count"
                    fill="var(--color-primary-600)"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={28}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="By produce line" />
          <CardBody className="pt-1">
            {lineData.length === 0 ? (
              <p className="py-12 text-center text-sm text-muted-foreground">
                No deliveries recorded in this period.
              </p>
            ) : (
              <>
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={lineData}
                      layout="vertical"
                      margin={{ left: 0, right: 8, top: 4, bottom: 0 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        horizontal={false}
                        stroke="var(--color-border)"
                      />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 11, fill: 'var(--color-stone-500)' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fontSize: 12, fill: 'var(--color-stone-700)' }}
                        axisLine={false}
                        tickLine={false}
                        width={72}
                      />
                      <Tooltip
                        contentStyle={TOOLTIP_STYLE}
                        cursor={{ fill: 'rgba(21, 128, 61, 0.06)' }}
                        formatter={(value) => {
                          // Recharts widens the value to ValueType; a bar series
                          // is always scalar here.
                          const v = Array.isArray(value) ? value[0] : value
                          return [formatMoney(v, data.currency), 'Value']
                        }}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={22}>
                        {lineData.map((entry) => (
                          <Cell key={entry.name} fill={entry.colour} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <ul className="mt-4 space-y-1.5 border-t border-border/60 pt-3 text-xs">
                  {data.deliveries_by_line.map((l, i) => (
                    <li key={l.produce_line_id} className="flex justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2 text-stone-600">
                        <span
                          className="inline-block h-2 w-2 shrink-0 rounded-full"
                          style={{
                            backgroundColor: LINE_COLOURS[i % LINE_COLOURS.length],
                          }}
                        />
                        <span className="truncate">{l.produce_line_name}</span>
                      </span>
                      <span className="shrink-0 text-muted-foreground tabular-nums">
                        {l.count} · {formatMoney(l.value, data.currency)}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Activity feed + status breakdown */}
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent activity"
            action={
              <Link
                to="/deliveries"
                className="text-xs font-medium text-primary-ink hover:text-primary-ink"
              >
                View all
              </Link>
            }
          />
          <CardBody className="pt-1">
            {data.recent_activity.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                Nothing to show yet.
              </p>
            ) : (
              <ul className="divide-y divide-border/60">
                {data.recent_activity.map((item) => (
                  <li key={`${item.type}-${item.id}`}>
                    <ActivityRow item={item} />
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Farmers by status" />
          <CardBody className="pt-1">
            <ul className="space-y-3 text-sm">
              <StatusRow
                label="Active"
                value={status.active}
                max={maxStatus}
                tone="success"
              />
              <StatusRow
                label="Pending verification"
                value={status.pending_verification}
                max={maxStatus}
                tone="warning"
              />
              <StatusRow
                label="Suspended"
                value={status.suspended}
                max={maxStatus}
                tone="danger"
              />
              <StatusRow
                label="Archived"
                value={status.archived}
                max={maxStatus}
                tone="neutral"
              />
              {status.merged > 0 && (
                <StatusRow
                  label="Merged"
                  value={status.merged}
                  max={maxStatus}
                  tone="info"
                />
              )}
            </ul>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const BAR_TONE: Record<string, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  neutral: 'bg-stone-300',
  info: 'bg-info',
}

function StatusRow({
  label,
  value,
  max,
  tone,
}: {
  label: string
  value: number
  max: number
  tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info'
}) {
  return (
    <li>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] text-stone-600">{label}</span>
        <span className="text-sm font-semibold text-foreground tabular-nums">
          {value}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-stone-100">
        <div
          className={`h-full rounded-full ${BAR_TONE[tone]}`}
          style={{ width: `${Math.max(value ? 4 : 0, (value / max) * 100)}%` }}
        />
      </div>
    </li>
  )
}

function ActivityRow({
  item,
}: {
  item: {
    type: string
    id: string
    at: string
    description: string
    amount: string | null
    currency: string | null
    farmer_id: string
    farmer_name: string
  }
}) {
  const isDelivery = item.type === 'delivery' || item.type === 'delivery_reversal'
  const isReversal =
    item.type === 'delivery_reversal' || item.type === 'payment_reversal'
  const to = isDelivery ? `/deliveries/${item.id}` : `/payments/${item.id}`

  return (
    <Link
      to={to}
      className="group -mx-2 flex items-start justify-between gap-3 rounded-lg px-2 py-3 transition-colors hover:bg-stone-50"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground group-hover:text-primary-ink">
            {item.farmer_name}
          </span>
          {isReversal && <StatusBadge tone="danger">Reversal</StatusBadge>}
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {item.description} · {formatDate(item.at)}
        </p>
      </div>
      {item.amount && (
        <span
          className={`shrink-0 text-sm font-medium tabular-nums ${
            Number(item.amount) < 0 ? 'text-danger-ink' : 'text-foreground'
          }`}
        >
          {formatMoney(item.amount, item.currency ?? 'KES')}
        </span>
      )}
    </Link>
  )
}
