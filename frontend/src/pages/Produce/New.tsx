import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { ApiError } from '@/lib/api'
import { useCreateProduceLine } from '@/hooks/useProduceLines'

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
          setError('Please check the fields — code must be lowercase letters, digits, underscores.')
        else setError(err.message)
      } else {
        setError('Something went wrong.')
      }
    }
  }

  return (
    <div className="p-4 md:p-6">
      <Link
        to="/produce"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to produce
      </Link>

      <h1 className="text-2xl font-semibold text-gray-900">
        Add produce line
      </h1>

      <form
        onSubmit={onSubmit}
        className="mt-6 max-w-xl space-y-4 rounded-lg border border-gray-200 bg-white p-6"
      >
        <Field
          label="Code"
          required
          value={form.code}
          onChange={(v) => setForm({ ...form, code: v })}
          placeholder="coffee, dairy, banana"
          hint="Short lowercase identifier — used in reports and API calls"
        />
        <Field
          label="Name"
          required
          value={form.name}
          onChange={(v) => setForm({ ...form, name: v })}
          placeholder="Coffee"
        />
        <Field
          label="Unit"
          required
          value={form.unit}
          onChange={(v) => setForm({ ...form, unit: v })}
          placeholder="kg, liter, piece"
          hint="Immutable after creation"
        />
        <div>
          <label className="block text-sm font-medium text-gray-700">
            Description
          </label>
          <textarea
            value={form.description}
            onChange={(e) =>
              setForm({ ...form, description: e.target.value })
            }
            rows={3}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
          >
            {create.isPending ? 'Creating…' : 'Create produce line'}
          </button>
          <Link
            to="/produce"
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  hint,
  required,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  hint?: string
  required?: boolean
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      <input
        type="text"
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
      />
      {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    </div>
  )
}