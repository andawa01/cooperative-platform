import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  LockKeyhole,
  Sprout,
} from 'lucide-react'

import { Button } from '@/components/common/Button'
import { Field, TextInput } from '@/components/common/Form'
import { useAuth } from '@/hooks/useAuth'
import { ApiError } from '@/lib/api'

const HIGHLIGHTS = [
  'Every delivery recorded, valued and traceable',
  'Payments allocated to the oldest debt first',
  'Farmers get an SMS confirming each transaction',
]

export default function Login() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation() as { state?: { from?: string } }
  // A flag in the URL rather than router state: the account screen may be
  // unmounted by the auth guard in the same tick it redirects here.
  const [params] = useSearchParams()
  const changedPassword = params.get('changed') === '1'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // If already logged in, redirect. This must not run during render:
  // calling navigate() there updates BrowserRouter while Login is still
  // rendering, which React reports as a cross-component setState.
  useEffect(() => {
    if (user) navigate(location.state?.from ?? '/', { replace: true })
  }, [user, location.state, navigate])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login({ email, password })
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Invalid email or password.')
      } else if (err instanceof ApiError && err.status === 429) {
        // The account is locked after too many failures. Say how long, so
        // the clerk stops retrying instead of assuming the app is broken.
        setError(`Too many failed attempts. ${waitFor(err.retryAfter)}`)
      } else {
        setError('Unable to sign in. Check your connection and try again.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-primary-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          className="pointer-events-none absolute -top-32 -left-24 h-96 w-96 rounded-full bg-primary-500/25 blur-3xl"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute -right-24 bottom-0 h-80 w-80 rounded-full bg-emerald-400/15 blur-3xl"
          aria-hidden="true"
        />

        <div className="relative flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-card/10 ring-1 ring-white/20 backdrop-blur">
            <Sprout className="h-5 w-5" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">
            ShambaTrack
          </span>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-[40px] leading-[1.08] font-semibold tracking-[-0.03em] text-balance-pretty">
            The ledger a cooperative can defend.
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-primary-100/85">
            Deliveries, rates, payments and farmer balances — recorded once,
            never silently edited, and answerable at the end of the season.
          </p>

          <ul className="mt-8 space-y-3">
            {HIGHLIGHTS.map((item) => (
              <li key={item} className="flex items-start gap-2.5">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                <span className="text-sm text-primary-100/90">{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex items-center gap-2 text-xs text-primary-200/70">
          <LockKeyhole className="h-3.5 w-3.5" />
          Every action is written to an append-only audit trail.
        </div>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center px-5 py-12 sm:px-8">
        <div className="w-full max-w-[400px]">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600 text-white">
              <Sprout className="h-5 w-5" />
            </span>
            <span className="text-[15px] font-semibold tracking-tight text-foreground">
              ShambaTrack
            </span>
          </div>

          <h2 className="text-[26px] leading-tight font-semibold tracking-[-0.02em] text-foreground">
            Sign in
          </h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Use the account your cooperative administrator created for you.
          </p>

          {changedPassword && (
            <div className="mt-5 flex items-start gap-2.5 rounded-lg border border-success/25 bg-success-soft px-3 py-2.5 text-sm text-success-ink">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              Password changed. Sign in again with your new password.
            </div>
          )}

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <Field label="Email" htmlFor="email" required>
              <TextInput
                id="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@cooperative.io"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>

            <Field label="Password" htmlFor="password" required>
              <TextInput
                id="password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>

            {error && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={busy}
              className="w-full"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>

          <div className="mt-8 rounded-lg border border-dashed border-stone-300 bg-card/60 px-4 py-3">
            <p className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
              Demo credentials
            </p>
            <div className="mt-1.5 space-y-1 text-xs text-stone-600">
              <p className="tabular-nums">
                <span className="font-medium text-stone-800">Admin</span>{' '}
                admin@shambatrack.io / demo-admin-123
              </p>
              <p className="tabular-nums">
                <span className="font-medium text-stone-800">Clerk</span>{' '}
                clerk1@shambatrack.io / demo-clerk-123
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Turn a Retry-After (seconds) into something a person can act on. */
function waitFor(seconds: number | null): string {
  if (!seconds || seconds <= 0) return 'Try again later.'
  if (seconds < 90) return `Try again in ${Math.ceil(seconds)} seconds.`
  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) return `Try again in about ${minutes} minutes.`
  return 'Try again later, or ask an admin to reset your password.'
}
