/**
 * Account screen: the signed-in user's identity plus a password change.
 *
 * Changing a password bumps the user's token_version server-side, which
 * invalidates every token issued before the change — including the one making
 * the request. So a successful change is also a sign-out, and we say so on the
 * login screen rather than silently dropping the session.
 */
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { KeyRound, Loader2, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/common/Button'
import { Card, CardBody, CardHeader } from '@/components/common/Card'
import { Field, FormError, TextInput } from '@/components/common/Form'
import { PageHeader } from '@/components/common/PageHeader'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api'
import { initials } from '@/lib/utils'

const MIN_PASSWORD_LENGTH = 10

export default function Account() {
  const { user, changePassword } = useAuth()
  const navigate = useNavigate()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(`New password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }
    if (newPassword !== confirmPassword) {
      setError('The new passwords do not match.')
      return
    }

    setBusy(true)
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      navigate('/login?changed=1', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Current password is incorrect.')
      } else if (err instanceof ApiError && err.status === 422) {
        setError(
          `New password must be at least ${MIN_PASSWORD_LENGTH} characters and differ from the current one.`,
        )
      } else {
        setError('Could not change the password. Try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  const nameParts = (user?.full_name ?? '?').split(' ')

  return (
    <div>
      <PageHeader
        title="Account"
        description="Your identity on this device and the password guarding it."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Profile" />
          <CardBody>
            <div className="flex items-center gap-3.5 border-b border-border/60 pb-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary-ink ring-1 ring-primary-100">
                {initials(nameParts[0] ?? '?', nameParts[1] ?? '')}
              </span>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-foreground">
                  {user?.full_name}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {user?.email}
                </div>
              </div>
            </div>

            <dl className="space-y-3 pt-4">
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-muted-foreground">Role</dt>
                <dd className="inline-flex items-center gap-1.5 rounded-full border border-border bg-stone-50 px-2 py-0.5 text-xs font-medium text-stone-700 capitalize">
                  <ShieldCheck className="h-3 w-3 text-primary-ink" />
                  {user?.role}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-muted-foreground">Status</dt>
                <dd className="text-sm text-foreground">
                  {user?.is_active ? 'Active' : 'Inactive'}
                </dd>
              </div>
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Change password"
            description="Every device signed in as you is signed out, including this one."
          />
          <CardBody>
            <form onSubmit={onSubmit} className="space-y-4">
              <Field label="Current password" htmlFor="current-password" required>
                <TextInput
                  id="current-password"
                  type="password"
                  required
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </Field>

              <Field
                label="New password"
                htmlFor="new-password"
                required
                hint={`At least ${MIN_PASSWORD_LENGTH} characters. Longer is better than complicated.`}
              >
                <TextInput
                  id="new-password"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </Field>

              <Field label="Confirm new password" htmlFor="confirm-password" required>
                <TextInput
                  id="confirm-password"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
              </Field>

              {error && <FormError>{error}</FormError>}

              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <KeyRound className="h-4 w-4" />
                )}
                {busy ? 'Changing…' : 'Change password'}
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>

    </div>
  )
}
