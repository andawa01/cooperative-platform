import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { ApiError } from '@/lib/api'
import { useCreateFarmer } from '@/hooks/useFarmers'

export default function NewFarmer() {
  const navigate = useNavigate()
  const create = useCreateFarmer()

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    national_id: '',
    location: '',
    date_of_birth: '',
    notes: '',
  })
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof typeof form>(k: K, v: string) =>
    setForm((f) => ({ ...f, [k]: v }))

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      const farmer = await create.mutateAsync({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim(),
        national_id: form.national_id.trim() || null,
        location: form.location.trim() || null,
        date_of_birth: form.date_of_birth || null,
        notes: form.notes.trim() || null,
      })
      navigate(`/farmers/${farmer.id}`, { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setError('That phone or national ID is already registered.')
        } else if (err.status === 422) {
          setError(
            'Please check the form — one or more fields are invalid ' +
              '(phone must be a valid format).',
          )
        } else {
          setError(err.message)
        }
      } else {
        setError('Something went wrong.')
      }
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

      <h1 className="text-2xl font-semibold text-gray-900">Register farmer</h1>
      <p className="mt-1 text-sm text-gray-600">
        Phone will be normalized to international format (E.164).
      </p>

      <form
        onSubmit={onSubmit}
        className="mt-6 max-w-xl space-y-4 rounded-lg border border-gray-200 bg-white p-6"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="First name"
            required
            value={form.first_name}
            onChange={(v) => set('first_name', v)}
            autoComplete="given-name"
          />
          <Field
            label="Last name"
            required
            value={form.last_name}
            onChange={(v) => set('last_name', v)}
            autoComplete="family-name"
          />
        </div>

        <Field
          label="Phone"
          required
          value={form.phone}
          onChange={(v) => set('phone', v)}
          placeholder="0712345678 or +254712345678"
          inputMode="tel"
          autoComplete="tel"
          hint="Kenyan local format accepted; stored as +254…"
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="National ID"
            value={form.national_id}
            onChange={(v) => set('national_id', v)}
            hint="Optional"
          />
          <Field
            label="Date of birth"
            type="date"
            value={form.date_of_birth}
            onChange={(v) => set('date_of_birth', v)}
            hint="Optional"
          />
        </div>

        <Field
          label="Location"
          value={form.location}
          onChange={(v) => set('location', v)}
          placeholder="Kisumu Central"
          hint="Free text — a note for clerks, not used in reporting"
        />

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Notes
          </label>
          <textarea
            value={form.notes}
            onChange={(e) => set('notes', e.target.value)}
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
            className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-700 disabled:opacity-60"
          >
            {create.isPending ? 'Registering…' : 'Register farmer'}
          </button>
          <Link
            to="/farmers"
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}

// Local form field component, kept inside the file because it's only used here.
function Field({
  label,
  value,
  onChange,
  type = 'text',
  required,
  placeholder,
  hint,
  inputMode,
  autoComplete,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  required?: boolean
  placeholder?: string
  hint?: string
  inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode']
  autoComplete?: string
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        inputMode={inputMode}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
      />
      {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    </div>
  )
}