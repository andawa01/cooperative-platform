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

import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api'

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

  return (
    <div className="p-4 md:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Account</h1>

      <div className="mt-6 max-w-xl rounded-lg border border-gray-200 bg-white p-6">
        <dl className="grid grid-cols-[7rem_1fr] gap-y-2 text-sm">
          <dt className="text-gray-500">Name</dt>
          <dd className="text-gray-900">{user?.full_name}</dd>
          <dt className="text-gray-500">Email</dt>
          <dd className="text-gray-900">{user?.email}</dd>
          <dt className="text-gray-500">Role</dt>
          <dd className="capitalize text-gray-900">{user?.role}</dd>
        </dl>
      </div>

      <form
        onSubmit={onSubmit}
        className="mt-6 max-w-xl space-y-4 rounded-lg border border-gray-200 bg-white p-6"
      >
        <div>
          <h2 className="text-lg font-medium text-gray-900">Change password</h2>
          <p className="mt-1 text-sm text-gray-600">
            Every device signed in as you is signed out, including this one.
          </p>
        </div>

        <PasswordField
          id="current-password"
          label="Current password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={setCurrentPassword}
        />
        <PasswordField
          id="new-password"
          label="New password"
          autoComplete="new-password"
          value={newPassword}
          onChange={setNewPassword}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters. Longer is better than complicated.`}
        />
        <PasswordField
          id="confirm-password"
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={setConfirmPassword}
        />

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
        >
          {busy ? 'Changing…' : 'Change password'}
        </button>
      </form>
    </div>
  )
}

function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  hint,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  autoComplete: string
  hint?: string
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700">
        {label}
      </label>
      <input
        id={id}
        type="password"
        required
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
      />
      {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    </div>
  )
}
