import { useState } from 'react'
import { Loader2, MapPin, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/common/Button'
import { Card, CardBody, CardHeader } from '@/components/common/Card'
import { Field, TextInput } from '@/components/common/Form'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import {
  useCollectionPoints,
  useCreateCollectionPoint,
  useProductionByPoint,
  useUpdateCollectionPoint,
} from '@/hooks/useCollectionPoints'
import { formatMoney } from '@/lib/auth'

/**
 * Collection points: the reference data behind "where did this arrive?" and
 * the production-by-point report (D-039).
 *
 * Retiring a point is a PATCH, never a delete: history stays attached to it,
 * and the server refuses to assign new members or deliveries to a retired
 * point.
 */
export default function CollectionPointsList() {
  const points = useCollectionPoints()
  const production = useProductionByPoint()
  const create = useCreateCollectionPoint()
  const update = useUpdateCollectionPoint()

  const [form, setForm] = useState({
    name: '',
    code: '',
    county: '',
    ward: '',
    zone: '',
    scale_id: '',
  })
  const [error, setError] = useState<string | null>(null)

  if (points.isLoading) return <Loading />
  if (points.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(points.error as Error).message}
          onRetry={() => points.refetch()}
        />
      </div>
    )

  const items = points.data?.items ?? []

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!form.name.trim() || !form.code.trim()) {
      setError('Name and code are required.')
      return
    }
    try {
      await create.mutateAsync({
        name: form.name.trim(),
        code: form.code.trim(),
        county: form.county.trim() || null,
        ward: form.ward.trim() || null,
        zone: form.zone.trim() || null,
        scale_id: form.scale_id.trim() || null,
      })
      toast.success('Collection point added', {
        description: `${form.name.trim()} can now be assigned to members and deliveries.`,
      })
      setForm({ name: '', code: '', county: '', ward: '', zone: '', scale_id: '' })
    } catch (err) {
      const message = (err as Error).message
      setError(message)
      toast.error('Could not add the point', { description: message })
    }
  }

  const toggle = async (id: string, isActive: boolean) => {
    try {
      await update.mutateAsync({ id, body: { is_active: !isActive } })
      toast.success(isActive ? 'Point retired' : 'Point reactivated', {
        description: isActive
          ? 'History stays on it; new members and deliveries cannot use it.'
          : 'It can take new members and deliveries again.',
      })
    } catch (err) {
      toast.error('Could not update the point', {
        description: (err as Error).message,
      })
    }
  }

  const productionItems = production.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="Collection points"
        description="Where produce is handed over. Deliveries default to the member's point, and production is reported against it."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Production by point"
            description="Net intake, reversals included — what the co-op actually kept."
          />
          <CardBody>
            {productionItems.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No deliveries recorded yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-[11px] tracking-wider text-stone-500 uppercase">
                      <th className="py-2 pr-4 font-semibold">Point</th>
                      <th className="py-2 pr-4 font-semibold">Code</th>
                      <th className="py-2 pr-4 text-right font-semibold">Entries</th>
                      <th className="py-2 pr-4 text-right font-semibold">Quantity</th>
                      <th className="py-2 text-right font-semibold">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {productionItems.map((row) => (
                      <tr
                        key={row.collection_point_id ?? 'unassigned'}
                        className="border-b border-border/50 last:border-0"
                      >
                        <td className="py-2.5 pr-4 font-medium text-foreground">
                          {row.collection_point_name}
                        </td>
                        <td className="py-2.5 pr-4 font-mono text-xs text-stone-500">
                          {row.collection_point_code ?? '—'}
                        </td>
                        <td className="py-2.5 pr-4 text-right text-stone-600 tabular-nums">
                          {row.entries}
                        </td>
                        <td className="py-2.5 pr-4 text-right text-stone-700 tabular-nums">
                          {Number(row.quantity).toLocaleString()}
                        </td>
                        <td className="py-2.5 text-right font-medium text-foreground tabular-nums">
                          {formatMoney(row.value, row.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Add a point" />
          <CardBody>
            <form onSubmit={submit} className="space-y-3">
              <Field label="Name" htmlFor="point-name" required>
                <TextInput
                  id="point-name"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  placeholder="Kisumu Central"
                />
              </Field>
              <Field
                label="Code"
                htmlFor="point-code"
                required
                hint="Short, unique, printed on reports."
              >
                <TextInput
                  id="point-code"
                  value={form.code}
                  onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                  placeholder="KSM-CENTRAL"
                  className="font-mono uppercase"
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="County" htmlFor="point-county">
                  <TextInput
                    id="point-county"
                    value={form.county}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, county: e.target.value }))
                    }
                    placeholder="Kisumu"
                  />
                </Field>
                <Field label="Ward" htmlFor="point-ward">
                  <TextInput
                    id="point-ward"
                    value={form.ward}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, ward: e.target.value }))
                    }
                  />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Zone" htmlFor="point-zone">
                  <TextInput
                    id="point-zone"
                    value={form.zone}
                    onChange={(e) => setForm((f) => ({ ...f, zone: e.target.value }))}
                  />
                </Field>
                <Field label="Scale ID" htmlFor="point-scale">
                  <TextInput
                    id="point-scale"
                    value={form.scale_id}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, scale_id: e.target.value }))
                    }
                  />
                </Field>
              </div>

              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-danger/20 bg-danger-soft px-3 py-2 text-sm text-danger-ink"
                >
                  {error}
                </p>
              )}

              <Button type="submit" variant="primary" disabled={create.isPending}>
                {create.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                {create.isPending ? 'Adding…' : 'Add point'}
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>

      <div className="mt-4">
        <Card>
          <CardHeader
            title={`Points (${items.length})`}
            description="A retired point keeps its deliveries and members; it just stops taking new ones."
          />
          <CardBody>
            {items.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-10 text-center">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-stone-100 text-stone-500">
                  <MapPin className="h-5 w-5" />
                </span>
                <p className="text-sm font-medium text-foreground">
                  No collection points yet
                </p>
                <p className="max-w-sm text-sm text-stone-500">
                  Add the sheds and buying centres members deliver to; every
                  delivery and report can then be grouped by them.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-border/60">
                {items.map((point) => (
                  <li
                    key={point.id}
                    className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-foreground">
                          {point.name}
                        </span>
                        <span className="font-mono text-[11px] text-stone-500">
                          {point.code}
                        </span>
                        <StatusBadge tone={point.is_active ? 'success' : 'neutral'}>
                          {point.is_active ? 'Active' : 'Retired'}
                        </StatusBadge>
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {[point.ward, point.zone, point.county]
                          .filter(Boolean)
                          .join(' · ') || 'No geography recorded'}
                        {point.scale_id ? ` · scale ${point.scale_id}` : ''}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant={point.is_active ? 'danger' : 'secondary'}
                      onClick={() => toggle(point.id, point.is_active)}
                      disabled={update.isPending}
                    >
                      {point.is_active ? 'Retire' : 'Reactivate'}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
