/**
 * Thin typed fetch wrapper.
 *
 * Responsibilities:
 * - Prepends the API base URL.
 * - Adds the bearer token from storage (if present).
 * - Parses JSON responses.
 * - Translates non-2xx responses into a typed ApiError.
 * - On 401, clears the token so the app falls back to the login screen.
 *
 * This is NOT a data-fetching library. Query hooks (react-query) wrap
 * these functions.
 */
import type { DashboardSummary } from '../types/api'
import { clearToken, getToken } from './auth'
import type {
  AllocationInput,
  AuditEntry,
  Balance,
  Deduction,
  DeductionCreateRequest,
  DeductionReverseRequest,
  Delivery,
  DeliveryCreateRequest,
  DeliveryReverseRequest,
  Farmer,
  FarmerCreateRequest,
  FarmerUpdateRequest,
  LoginRequest,
  Notification,
  Paginated,
  Payment,
  PaymentCreateRequest,
  PasswordChangeRequest,
  PaymentReverseRequest,
  ProduceLine,
  ProduceLineCreateRequest,
  Rate,
  RateCreateRequest,
  RateCreateResponse,
  Statement,
  TokenResponse,
  User,
  UserCreateRequest,
  UserUpdateRequest,
} from '@/types/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  detail: unknown
  /** Seconds from a 429's `Retry-After`, when the server sent one. */
  retryAfter: number | null

  constructor(status: number, detail: unknown, retryAfter: number | null = null) {
    super(
      typeof detail === 'string'
        ? detail
        : (detail as { detail?: string })?.detail || `HTTP ${status}`,
    )
    this.status = status
    this.detail = detail
    this.retryAfter = retryAfter
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (opts.query) {
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, String(v))
      }
    }
  }

  const headers: Record<string, string> = {
    Accept: 'application/json',
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(url.toString(), {
    method: opts.method ?? 'GET',
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  })

  // 401 handling: clear token so the app can route to login.
  if (res.status === 401) {
    clearToken()
  }

  if (res.status === 204) {
    return undefined as T
  }

  const text = await res.text()
  const data = text ? JSON.parse(text) : undefined

  if (!res.ok) {
    const retryAfter = Number(res.headers.get('retry-after'))
    throw new ApiError(
      res.status,
      data,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    )
  }
  return data as T
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const api = {
  auth: {
    login: (body: LoginRequest) =>
      request<TokenResponse>('/auth/login', { method: 'POST', body }),
    me: () => request<User>('/auth/me'),
    /** Revokes this token server-side, not just locally. */
    logout: () => request<void>('/auth/logout', { method: 'POST' }),
    changePassword: (body: PasswordChangeRequest) =>
      request<void>('/auth/password', { method: 'POST', body }),
    /** Admin-only once any user exists (open only for the first bootstrap). */
    register: (body: UserCreateRequest) =>
      request<User>('/auth/register', { method: 'POST', body }),
  },

  users: {
    list: (params: {
      search?: string
      role?: string
      limit?: number
      offset?: number
    } = {}) => request<Paginated<User>>('/users', { query: params }),
    update: (id: string, body: UserUpdateRequest) =>
      request<User>(`/users/${id}`, { method: 'PATCH', body }),
  },

  audit: {
    list: (params: {
      action?: string
      entity_type?: string
      entity_id?: string
      actor_id?: string
      limit?: number
      offset?: number
    } = {}) => request<Paginated<AuditEntry>>('/audit', { query: params }),
  },

  farmers: {
    list: (params: {
      status?: string
      search?: string
      include_merged?: boolean
      limit?: number
      offset?: number
    } = {}) =>
      request<Paginated<Farmer>>('/farmers', { query: params }),
    get: (id: string) => request<Farmer>(`/farmers/${id}`),
    create: (body: FarmerCreateRequest) =>
      request<Farmer>('/farmers', { method: 'POST', body }),
    update: (id: string, body: FarmerUpdateRequest) =>
      request<Farmer>(`/farmers/${id}`, { method: 'PATCH', body }),
    verify: (id: string) =>
      request<Farmer>(`/farmers/${id}/verify`, { method: 'POST' }),
    archive: (id: string) =>
      request<Farmer>(`/farmers/${id}/archive`, { method: 'POST' }),
    balance: (id: string) => request<Balance>(`/farmers/${id}/balance`),
    statement: (id: string, params: { start?: string; end?: string } = {}) =>
      request<Statement>(`/farmers/${id}/statement`, { query: params }),
  },

  produceLines: {
    list: (params: { include_inactive?: boolean; limit?: number; offset?: number } = {}) =>
      request<Paginated<ProduceLine>>('/produce-lines', { query: params }),
    get: (id: string) => request<ProduceLine>(`/produce-lines/${id}`),
    create: (body: ProduceLineCreateRequest) =>
      request<ProduceLine>('/produce-lines', { method: 'POST', body }),
    deactivate: (id: string) =>
      request<ProduceLine>(`/produce-lines/${id}/deactivate`, { method: 'POST' }),
    rates: (id: string) => request<Rate[]>(`/produce-lines/${id}/rates`),
    currentRate: (id: string) =>
      request<{ rate: Rate | null }>(`/produce-lines/${id}/rates/current`),
    createRate: (id: string, body: RateCreateRequest) =>
      request<RateCreateResponse>(`/produce-lines/${id}/rates`, {
        method: 'POST',
        body,
      }),
  },

  deliveries: {
    list: (params: {
      farmer_id?: string
      produce_line_id?: string
      recorded_by_id?: string
      delivered_from?: string
      delivered_to?: string
      include_reversals?: boolean
      unvalued_only?: boolean
      limit?: number
      offset?: number
    } = {}) => request<Paginated<Delivery>>('/deliveries', { query: params }),
    get: (id: string) => request<Delivery>(`/deliveries/${id}`),
    create: (body: DeliveryCreateRequest) =>
      request<Delivery>('/deliveries', { method: 'POST', body }),
    value: (id: string) =>
      request<Delivery>(`/deliveries/${id}/value`, { method: 'POST' }),
    reverse: (id: string, body: DeliveryReverseRequest) =>
      request<Delivery>(`/deliveries/${id}/reverse`, { method: 'POST', body }),
  },

  payments: {
    list: (params: {
      farmer_id?: string
      include_reversals?: boolean
      limit?: number
      offset?: number
    } = {}) => request<Paginated<Payment>>('/payments', { query: params }),
    get: (id: string) => request<Payment>(`/payments/${id}`),
    create: (body: PaymentCreateRequest) =>
      request<Payment>('/payments', { method: 'POST', body }),
    reverse: (id: string, body: PaymentReverseRequest) =>
      request<Payment>(`/payments/${id}/reverse`, { method: 'POST', body }),
  },

  deductions: {
    list: (params: {
      farmer_id?: string
      reason_code?: string
      include_reversals?: boolean
      limit?: number
      offset?: number
    } = {}) => request<Paginated<Deduction>>('/deductions', { query: params }),
    get: (id: string) => request<Deduction>(`/deductions/${id}`),
    create: (body: DeductionCreateRequest) =>
      request<Deduction>('/deductions', { method: 'POST', body }),
    reverse: (id: string, body: DeductionReverseRequest) =>
      request<Deduction>(`/deductions/${id}/reverse`, { method: 'POST', body }),
  },

  notifications: {
    list: (params: { farmer_id?: string; limit?: number; offset?: number } = {}) =>
      request<Paginated<Notification>>('/notifications', { query: params }),
    get: (id: string) => request<Notification>(`/notifications/${id}`),
    retry: (id: string) =>
      request<Notification>(`/notifications/${id}/retry`, { method: 'POST' }),
  },

    dashboard: {
    summary: (params: { days?: number } = {}) =>
      request<DashboardSummary>('/dashboard/summary', { query: params }),
  },
}

// Re-export AllocationInput so components importing from api.ts can build
// payment payloads without reaching into types directly.
export type { AllocationInput }