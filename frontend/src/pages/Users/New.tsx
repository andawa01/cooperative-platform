/**
 * Create a user.
 *
 * This posts to `POST /auth/register`, which is open only for the very first
 * account (bootstrap) and admin-guarded after that. Reusing that endpoint
 * keeps the password rules in one place rather than duplicating them in a
 * second creation path.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/common/Button'
import { PageHeader } from '@/components/common/PageHeader'
import { useCreateUser } from '@/hooks/useUsers'
import type { UserRole } from '@/types/api'

const MIN_PASSWORD_LENGTH = 10

const FIELD =
  'h-10 w-full rounded-lg border border-input bg-card px-3 text-sm shadow-xs transition-[border-color,box-shadow] placeholder:text-stone-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none'
const LABEL =
  'mb-1.5 block text-[11px] font-semibold tracking-wider text-stone-500 uppercase'

export default function NewUser() {
  const navigate = useNavigate()
  const create = useCreateUser()

  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('clerk')
  const [error, setError] = useState<string | null>(null)

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const canSubmit =
    email.trim() !== '' &&
    fullName.trim() !== '' &&
    password.length >= MIN_PASSWORD_LENGTH &&
    !create.isPending

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await create.mutateAsync({
        email: email.trim(),
        full_name: fullName.trim(),
        password,
        role,
      })
      navigate('/users')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div>
      <PageHeader
        back={{ to: '/users', label: 'Users' }}
        title="New user"
        description="An account can record deliveries and payments, or also administer the co-op."
      />

      <form
        onSubmit={handleSubmit}
        className="max-w-lg overflow-hidden rounded-card border border-border/80 bg-card shadow-card"
      >
        <div className="space-y-4 px-5 py-5">
          <div>
            <label htmlFor="user-name" className={LABEL}>
              Full name
            </label>
            <input
              id="user-name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              autoComplete="name"
              required
              className={FIELD}
            />
          </div>

          <div>
            <label htmlFor="user-email" className={LABEL}>
              Email
            </label>
            <input
              id="user-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
              className={FIELD}
            />
          </div>

          <div>
            <label htmlFor="user-password" className={LABEL}>
              Temporary password
            </label>
            <input
              id="user-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              required
              className={FIELD}
            />
            <p
              className={
                passwordTooShort
                  ? 'mt-1.5 text-xs text-danger-ink'
                  : 'mt-1.5 text-xs text-muted-foreground'
              }
            >
              At least {MIN_PASSWORD_LENGTH} characters. They can change it
              after signing in.
            </p>
          </div>

          <div>
            <label htmlFor="user-role" className={LABEL}>
              Role
            </label>
            <select
              id="user-role"
              value={role}
              onChange={(event) => setRole(event.target.value as UserRole)}
              className="h-10 w-full cursor-pointer rounded-lg border border-input bg-card px-3 text-sm text-stone-700 shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
            >
              <option value="clerk">Clerk — records farmers, deliveries, payments</option>
              <option value="admin">Admin — also manages rates, reversals, accounts</option>
            </select>
          </div>

          {error && (
            <div
              role="alert"
              className="rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
            >
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border/70 bg-stone-50/60 px-5 py-3">
          <Button onClick={() => navigate('/users')} disabled={create.isPending}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={!canSubmit}
            formNoValidate={false}
          >
            {create.isPending ? 'Creating…' : 'Create user'}
          </Button>
        </div>
      </form>
    </div>
  )
}
