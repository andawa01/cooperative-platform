import { Link } from 'react-router-dom'
import {
  AlertTriangle,
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

import { ErrorState, Loading } from '@/components/common/Loading'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useDashboardSummary } from '@/hooks/useDashboard'
import { formatMoney, parseMoney } from '@/lib/auth'

const LINE_COLOURS = ['#15803d', '#0891b2', '#7c3aed', '#c2410c', '#be123c']

export default function Dashboard() {
  const { data, isLoading, error, refetch } = useDashboardSummary(30)

  if (isLoading) return <Loading label="Loading dashboard…" />
  if (error)
    return (
      <div className="p-6">
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      </div>
    )
  if (!data) return null

  // Short labels for the daily chart so mobile isn't crowded.
  const dailyData = data.deliveries_daily.map((d) => ({
    date: d.date.slice(5), // MM-DD
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

  return (
    <div className="p-4 md:p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-600">
          Last {data.period_days} days · updated{' '}
          {new Date(data.generated_at).toLocaleTimeString()}
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiCard
          icon={<Wallet className="h-5 w-5 text-red-600" />}
          label="Outstanding debt"
          value={formatMoney(data.outstanding_debt_total, data.currency)}
          tone="danger"
        />
        <KpiCard
          icon={<Banknote className="h-5 w-5 text-green-600" />}
          label="Paid (30d)"
          value={formatMoney(data.payments_value_in_period, data.currency)}
          sub={`${data.payments_in_period} payments`}
          tone="success"
        />
        <KpiCard
          icon={<TrendingUp className="h-5 w-5 text-primary-600" />}
          label="Delivered (30d)"
          value={formatMoney(data.deliveries_value_in_period, data.currency)}
          sub={`${data.deliveries_in_period} deliveries`}
        />
        <KpiCard
          icon={<Users className="h-5 w-5 text-blue-600" />}
          label="Active farmers"
          value={String(status.active)}
          sub={`of ${data.farmers_total} registered`}
        />
      </div>

      {/* Alerts */}
      {data.pending_valuation_count > 0 && (
        <div className="mt-4 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-900">
              {data.pending_valuation_count} deliver
              {data.pending_valuation_count === 1 ? 'y is' : 'ies are'} awaiting
              valuation
            </p>
            <p className="mt-1 text-xs text-amber-800">
              These cannot be paid against until a rate is applied.
            </p>
          </div>
          <Link
            to="/deliveries?unvalued=1"
            className="text-xs font-medium text-amber-900 underline"
          >
            Review
          </Link>
        </div>
      )}

      {/* Charts */}
      <div className="mt-6 grid gap-4 lg:grid-cols-5">
        <section className="lg:col-span-3 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Deliveries per day
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  axisLine={false}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  axisLine={false}
                  tickLine={false}
                  width={28}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 12,
                    border: '1px solid #e5e7eb',
                    borderRadius: 6,
                  }}
                  formatter={(value) => [`${value} deliveries`, '']}
                  labelFormatter={(label) => `Date: ${label}`}
                />
                <Bar dataKey="count" fill="#15803d" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="lg:col-span-2 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            By produce line
          </h2>
          {lineData.length === 0 ? (
            <p className="text-sm text-gray-500">
              No deliveries recorded in this period.
            </p>
          ) : (
            <>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={lineData} layout="vertical" margin={{ left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
                    <XAxis
                      type="number"
                      tick={{ fontSize: 11, fill: '#6b7280' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      tick={{ fontSize: 12, fill: '#374151' }}
                      axisLine={false}
                      tickLine={false}
                      width={60}
                    />
                    <Tooltip
                      contentStyle={{
                        fontSize: 12,
                        border: '1px solid #e5e7eb',
                        borderRadius: 6,
                      }}
                      formatter={(value) => {
                        // Recharts widens the value to ValueType; a bar series
                        // is always scalar here.
                        const v = Array.isArray(value) ? value[0] : value
                        return [formatMoney(v, data.currency), 'Value']
                      }}
                    />
                    <Bar dataKey="value" radius={[0, 2, 2, 0]}>
                      {lineData.map((entry) => (
                        <Cell key={entry.name} fill={entry.colour} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-3 space-y-1 text-xs text-gray-600">
                {data.deliveries_by_line.map((l, i) => (
                  <li key={l.produce_line_id} className="flex justify-between">
                    <span className="flex items-center gap-2">
                      <span
                        className="inline-block h-2 w-2 rounded-full"
                        style={{
                          backgroundColor: LINE_COLOURS[i % LINE_COLOURS.length],
                        }}
                      />
                      {l.produce_line_name}
                    </span>
                    <span>
                      {l.count} · {formatMoney(l.value, data.currency)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>

      {/* Activity feed + status breakdown */}
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <section className="lg:col-span-2 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Recent activity
          </h2>
          {data.recent_activity.length === 0 ? (
            <p className="text-sm text-gray-500">Nothing to show yet.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {data.recent_activity.map((item) => (
                <li key={`${item.type}-${item.id}`} className="py-2.5">
                  <ActivityRow item={item} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Farmers by status
          </h2>
          <ul className="space-y-2 text-sm">
            <StatusRow label="Active" value={status.active} tone="success" />
            <StatusRow
              label="Pending verification"
              value={status.pending_verification}
              tone="warning"
            />
            <StatusRow label="Suspended" value={status.suspended} tone="danger" />
            <StatusRow label="Archived" value={status.archived} tone="neutral" />
            {status.merged > 0 && (
              <StatusRow label="Merged" value={status.merged} tone="info" />
            )}
          </ul>
        </section>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function KpiCard({
  icon,
  label,
  value,
  sub,
  tone = 'neutral',
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  tone?: 'neutral' | 'danger' | 'success'
}) {
  const border =
    tone === 'danger'
      ? 'border-l-4 border-l-red-400'
      : tone === 'success'
        ? 'border-l-4 border-l-green-400'
        : ''
  return (
    <div
      className={`rounded-lg border border-gray-200 bg-white p-4 ${border}`}
    >
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
          {label}
        </span>
      </div>
      <div className="mt-2 text-xl font-semibold text-gray-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-gray-500">{sub}</div>}
    </div>
  )
}

function StatusRow({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info'
}) {
  return (
    <li className="flex items-center justify-between">
      <StatusBadge tone={tone}>{label}</StatusBadge>
      <span className="font-medium text-gray-900">{value}</span>
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
    <Link to={to} className="flex items-start justify-between gap-3 group">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-gray-900 group-hover:text-primary-700">
            {item.farmer_name}
          </span>
          {isReversal && <StatusBadge tone="danger">Reversal</StatusBadge>}
        </div>
        <p className="truncate text-xs text-gray-600">
          {item.description}
          {new Date(item.at).toLocaleDateString()}
        </p>
      </div>
      {item.amount && (
        <span
          className={`shrink-0 text-sm font-medium ${
            Number(item.amount) < 0 ? 'text-red-700' : 'text-gray-900'
          }`}
        >
          {formatMoney(item.amount, item.currency ?? 'KES')}
        </span>
      )}
    </Link>
  )
}