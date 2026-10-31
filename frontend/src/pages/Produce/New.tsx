import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Sprout } from 'lucide-react'

import { ApiError } from '@/lib/api'
import { useCreateProduceLine } from '@/hooks/useProduceLines'
import { Button } from '@/components/common/Button'
import { Card, CardBody, CardFooter } from '@/components/common/Card'
import {
  Field,
  FormError,
  TextArea,
  TextInput,
} from '@/components/common/Form'
import { PageHeader } from '@/components/common/PageHeader'

export default function NewProduceLine() {
  const navigate = useNavigate()
  const create = useCreateProduceLine()
  const [form, setForm] = useState({
    code: '',
    name: '',
    unit: 'kg',
    description: '',
  })
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      const line = await create.mutateAsync({
        code: form.code.trim().toLowerCase(),
        name: form.name.trim(),
        unit: form.unit.trim(),
        description: form.description.trim() || null,
      })
      navigate(`/produce/${line.id}`, { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) setError('That produce code is already in use.')
        else if (err.status === 422)
          setError(
            'Please check the fields — code must be lowercase letters, digits, underscores.',
          )
        else setError(err.message)
      } else {
        setError('Something went wrong.')
      }
    }
  }

  return (
    <div>
      <PageHeader
        title="Add produce line"
        back={{ to: '/produce', label: 'Produce & Rates' }}
        description="The unit is permanent once set — deliveries snapshot their rate against it."
      />

      <form onSubmit={onSubmit} className="max-w-xl">
        <Card>
          <CardBody className="space-y-4 p-5 sm:p-6">
            <Field
              label="Code"
              htmlFor="code"
              required
              hint="Short lowercase identifier — used in reports and API calls"
            >
              <TextInput
                id="code"
                required
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                placeholder="coffee, dairy, banana"
                className="font-mono"
              />
            </Field>

            <Field label="Name" htmlFor="name" required>
              <TextInput
                id="name"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Coffee"
              />
            </Field>

            <Field
              label="Unit"
              htmlFor="unit"
              required
              hint="Immutable after creation — kg, liter, piece"
            >
              <TextInput
                id="unit"
                required
                value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })}
                placeholder="kg, liter, piece"
              />
            </Field>

            <Field label="Description" htmlFor="description">
              <TextArea
                id="description"
                rows={3}
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </Field>

            {error && <FormError>{error}</FormError>}
          </CardBody>

          <CardFooter className="justify-end">
            <Link
              to="/produce"
              className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              Cancel
            </Link>
            <Button type="submit" variant="primary" disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sprout className="h-4 w-4" />
              )}
              {create.isPending ? 'Creating…' : 'Create produce line'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  )
}
