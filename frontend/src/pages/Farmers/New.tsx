import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, UserPlus } from 'lucide-react'

import { ApiError } from '@/lib/api'
import { useCreateFarmer } from '@/hooks/useFarmers'
import { Button, ButtonLink } from '@/components/common/Button'
import { Card, CardBody, CardFooter } from '@/components/common/Card'
import {
  Field,
  FieldGroup,
  FormError,
  TextArea,
  TextInput,
} from '@/components/common/Form'
import { PageHeader } from '@/components/common/PageHeader'

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
    <div>
      <PageHeader
        title="Register farmer"
        back={{ to: '/farmers', label: 'Farmers' }}
        description="Phone numbers are normalized to international format (E.164) before saving."
      />

      <form onSubmit={onSubmit} className="max-w-2xl">
        <Card>
          <CardBody className="space-y-6 p-5 sm:p-6">
            <FieldGroup
              title="Identity"
              description="The name the farmer is known by at the collection point."
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="First name" htmlFor="first_name" required>
                  <TextInput
                    id="first_name"
                    required
                    autoComplete="given-name"
                    value={form.first_name}
                    onChange={(e) => set('first_name', e.target.value)}
                  />
                </Field>
                <Field label="Last name" htmlFor="last_name" required>
                  <TextInput
                    id="last_name"
                    required
                    autoComplete="family-name"
                    value={form.last_name}
                    onChange={(e) => set('last_name', e.target.value)}
                  />
                </Field>
              </div>

              <Field
                label="Phone"
                htmlFor="phone"
                required
                hint="Kenyan local format accepted; stored as +254…"
              >
                <TextInput
                  id="phone"
                  required
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="0712345678 or +254712345678"
                  value={form.phone}
                  onChange={(e) => set('phone', e.target.value)}
                />
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="National ID" htmlFor="national_id" hint="Optional">
                  <TextInput
                    id="national_id"
                    value={form.national_id}
                    onChange={(e) => set('national_id', e.target.value)}
                  />
                </Field>
                <Field label="Date of birth" htmlFor="dob" hint="Optional">
                  <TextInput
                    id="dob"
                    type="date"
                    value={form.date_of_birth}
                    onChange={(e) => set('date_of_birth', e.target.value)}
                  />
                </Field>
              </div>
            </FieldGroup>

            <div className="border-t border-border/60 pt-6">
              <FieldGroup
                title="Context"
                description="Helps clerks find the right person and keeps notes out of the ledger."
              >
                <Field
                  label="Location"
                  htmlFor="location"
                  hint="Free text — a note for clerks, not used in reporting"
                >
                  <TextInput
                    id="location"
                    placeholder="Kisumu Central"
                    value={form.location}
                    onChange={(e) => set('location', e.target.value)}
                  />
                </Field>

                <Field label="Notes" htmlFor="notes">
                  <TextArea
                    id="notes"
                    rows={3}
                    value={form.notes}
                    onChange={(e) => set('notes', e.target.value)}
                    placeholder="Anything the next clerk should know."
                  />
                </Field>
              </FieldGroup>
            </div>

            {error && <FormError>{error}</FormError>}
          </CardBody>

          <CardFooter className="justify-end">
            <Link
              to="/farmers"
              className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              Cancel
            </Link>
            <Button type="submit" variant="primary" disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <UserPlus className="h-4 w-4" />
              )}
              {create.isPending ? 'Registering…' : 'Register farmer'}
            </Button>
          </CardFooter>
        </Card>

        <p className="mt-4 text-xs text-muted-foreground">
          Need the ledger now?{' '}
          <ButtonLink
            to="/farmers"
            variant="ghost"
            size="sm"
            className="h-auto px-1 py-0 text-xs text-primary-ink hover:bg-transparent hover:underline"
          >
            Return to the list
          </ButtonLink>
        </p>
      </form>
    </div>
  )
}
