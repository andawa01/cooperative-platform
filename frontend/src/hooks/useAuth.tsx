/**
 * Auth context.
 *
 * Wraps: current user, login, logout. On mount, tries to hydrate the user
 * from localStorage (previously stored after login). If the token is
 * expired, clears it and the user is treated as logged out.
 *
 * We do NOT re-verify the token against /auth/me on every mount — that's
 * wasteful and can cause flashes. Instead we trust the stored user until
 * the first API call that requires auth, which will 401 if the token is
 * no longer valid, and the API client clears it.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

import { api } from '@/lib/api'
import {
  clearToken,
  getStoredUser,
  getToken,
  isTokenExpired,
  setStoredUser,
  setToken,
} from '@/lib/auth'
import type { LoginRequest, PasswordChangeRequest, User } from '@/types/api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (body: LoginRequest) => Promise<void>
  logout: () => Promise<void>
  /** Resolves after the password is changed; the caller is then signed out. */
  changePassword: (body: PasswordChangeRequest) => Promise<void>
  isAdmin: boolean
  isClerk: boolean
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // Hydrate on mount.
  useEffect(() => {
    const token = getToken()
    const stored = getStoredUser()
    if (!token || isTokenExpired(token) || !stored) {
      clearToken()
      setUser(null)
    } else {
      setUser(stored)
    }
    setLoading(false)
  }, [])

  const login = useCallback(async (body: LoginRequest) => {
    const { access_token } = await api.auth.login(body)
    setToken(access_token)
    // Fetch the canonical user object for the token we just received.
    const me = await api.auth.me()
    setStoredUser(me)
    setUser(me)
  }, [])

  const logout = useCallback(async () => {
    // Revoking server-side is what makes a copied token useless, but the
    // local sign-out must happen even if the call fails — otherwise a flaky
    // network leaves the user stuck inside a shell they asked to leave.
    try {
      await api.auth.logout()
    } catch {
      // Nothing to do: the token is cleared below either way.
    }
    clearToken()
    setUser(null)
  }, [])

  const changePassword = useCallback(async (body: PasswordChangeRequest) => {
    await api.auth.changePassword(body)
    // The server bumped token_version, so every token we hold is dead —
    // including this one. Drop it rather than waiting for a 401.
    clearToken()
    setUser(null)
  }, [])

  const value: AuthContextValue = {
    user,
    loading,
    login,
    logout,
    changePassword,
    isAdmin: user?.role === 'admin',
    isClerk: user?.role === 'clerk',
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}