/**
 * TypeScript mirrors of the backend's API schemas.
 *
 * Hand-written for MVP (see D-025). If these drift from the backend, API
 * calls will fail loudly, which is the right failure mode.
 *
 * Money note: FastAPI/Pydantic serialises Decimal as a *string* in JSON,
 * not a number. That is deliberate on the backend (money is never float).
 * The frontend treats money as strings and converts for arithmetic via
 * `parseMoney()`. Never do `a + b` on money strings directly.
 */

// ---------------------------------------------------------------------------
// Auth / users
// ---------------------------------------------------------------------------

export type UserRole = 'admin' | 'clerk'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface PasswordChangeRequest {
  current_password: string
  /** The API enforces a floor of 10 characters (mirrored in the form). */
  new_password: string
}

export interface UserCreateRequest {
  email: string
  full_name: string
  password: string
  role?: UserRole
}

export interface UserUpdateRequest {
  full_name?: string
  role?: UserRole
  is_active?: boolean
}

// ---------------------------------------------------------------------------
// Farmers
// ---------------------------------------------------------------------------

export type FarmerStatus =
  | 'pending_verification'
  | 'active'
  | 'suspended'
  | 'archived'
  | 'merged'

export interface Farmer {
  id: string
  first_name: string
  last_name: string
  phone: string
  date_of_birth: string | null
  national_id: string | null
  location: string | null
  notes: string | null
  status: FarmerStatus
  verified_at: string | null
  merged_into_id: string | null
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface FarmerCreateRequest {
  first_name: string
  last_name: string
  phone: string
  date_of_birth?: string | null
  national_id?: string | null
  location?: string | null
  notes?: string | null
}

export interface FarmerUpdateRequest {
  first_name?: string
  last_name?: string
  date_of_birth?: string | null
  national_id?: string | null
  location?: string | null
  notes?: string | null
}

// ---------------------------------------------------------------------------
// Produce lines and rates
// ---------------------------------------------------------------------------

export interface ProduceLine {
  id: string
  code: string
  name: string
  unit: string
  description: string | null
  is_active: boolean
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface ProduceLineCreateRequest {
  code: string
  name: string
  unit: string
  description?: string | null
}

export interface Rate {
  id: string
  produce_line_id: string
  rate_per_unit: string
  currency: string
  effective_from: string
  effective_to: string | null
  created_by_id: string
  created_at: string
  updated_at: string
}

export interface RateCreateRequest {
  rate_per_unit: string
  currency: string
  effective_from: string
}

export interface RateCreateResponse {
  new_rate: Rate
  previous_rate: Rate | null
  affected_deliveries: number
}

export interface CurrentRateResponse {
  rate: Rate | null
}

// ---------------------------------------------------------------------------
// Deliveries
// ---------------------------------------------------------------------------

export interface Delivery {
  id: string
  farmer_id: string
  produce_line_id: string
  /** Resolved server-side so list screens do not need a second lookup. */
  farmer_name: string
  produce_line_name: string
  quantity: string
  delivered_at: string
  recorded_at: string
  recorded_by_id: string
  rate_snapshot: string | null
  currency_snapshot: string
  amount: string | null
  reversal_of_id: string | null
  location: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface DeliveryCreateRequest {
  farmer_id: string
  produce_line_id: string
  quantity: string
  delivered_at: string
  location?: string | null
  notes?: string | null
}

export interface DeliveryReverseRequest {
  reason: string
}

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------

export type PaymentMethod = 'cash' | 'mobile_money' | 'bank_transfer'
export type PaymentStatus = 'confirmed' | 'reversed'

export interface Allocation {
  id: string
  delivery_id: string
  amount: string
  reversal_of_id: string | null
}

export interface Payment {
  id: string
  farmer_id: string
  farmer_name: string
  amount: string
  currency: string
  method: PaymentMethod
  reference: string | null
  paid_at: string
  recorded_at: string
  recorded_by_id: string
  status: PaymentStatus
  reversal_of_id: string | null
  notes: string | null
  allocations: Allocation[]
  unallocated_amount: string
  created_at: string
  updated_at: string
}

export interface AllocationInput {
  delivery_id: string
  amount: string
}

export interface PaymentCreateRequest {
  farmer_id: string
  amount: string
  currency: string
  method: PaymentMethod
  reference?: string | null
  paid_at: string
  idempotency_key: string
  allocations?: AllocationInput[] | null
  notes?: string | null
}

export interface PaymentReverseRequest {
  reason: string
}

// ---------------------------------------------------------------------------
// Balance and statement
// ---------------------------------------------------------------------------

export interface Balance {
  farmer_id: string
  currency: string
  outstanding_debt: string
  allocated_to_deliveries: string
  available_credit: string
  pending_valuation_deliveries: number
}

export type StatementEntryType =
  | 'delivery'
  | 'delivery_reversal'
  | 'payment'
  | 'payment_reversal'

export interface StatementEntry {
  date: string
  type: StatementEntryType
  amount: string
  description: string
  delivery_id: string | null
  payment_id: string | null
  reversal_of_id: string | null
  debt_after: string
  credit_after: string
}

export interface Statement {
  farmer_id: string
  start: string
  end: string
  currency: string
  opening: {
    outstanding_debt: string
    available_credit: string
  }
  entries: StatementEntry[]
  closing: {
    outstanding_debt: string
    available_credit: string
  }
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export type DispatchStatus =
  | 'queued'
  | 'sending'
  | 'sent'
  | 'failed'
  | 'queued_redis_unreachable'
  | 'unknown'

export interface Notification {
  id: string
  farmer_id: string
  channel: 'sms'
  template: 'delivery_recorded' | 'payment_recorded'
  recipient: string
  content: string
  related_entity_type: 'delivery' | 'payment' | null
  related_entity_id: string | null
  created_at: string
  status: DispatchStatus
  attempts: number
  last_error: string | null
  sent_at: string | null
}

// ---------------------------------------------------------------------------
// Audit trail
// ---------------------------------------------------------------------------

/**
 * `before`/`after` are the fields that changed, not full rows, and the set
 * differs per action (amount and rate for a payment, status and notes for a
 * farmer). Hence `unknown` values rather than a discriminated union.
 */
export interface AuditEntry {
  id: string
  action: string
  entity_type: string
  entity_id: string
  actor_id: string | null
  actor_name: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  request_id: string | null
  created_at: string
}

// ---------------------------------------------------------------------------
// Paginated envelope
// ---------------------------------------------------------------------------

export interface Paginated<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export interface FarmersByStatus {
  pending_verification: number
  active: number
  suspended: number
  archived: number
  merged: number
}

export interface DeliveriesByLine {
  produce_line_id: string
  produce_line_name: string
  unit: string
  count: number
  quantity: string
  value: string
}

export interface DeliveriesDaily {
  date: string  // YYYY-MM-DD
  count: number
  value: string
}

export interface ActivityItem {
  type: 'delivery' | 'delivery_reversal' | 'payment' | 'payment_reversal'
  id: string
  at: string
  description: string
  amount: string | null
  currency: string | null
  farmer_id: string
  farmer_name: string
}

export interface DashboardSummary {
  generated_at: string
  period_days: number
  currency: string
  farmers_total: number
  farmers_by_status: FarmersByStatus
  deliveries_in_period: number
  deliveries_value_in_period: string
  payments_in_period: number
  payments_value_in_period: string
  outstanding_debt_total: string
  available_credit_total: string
  pending_valuation_count: number
  deliveries_by_line: DeliveriesByLine[]
  deliveries_daily: DeliveriesDaily[]
  recent_activity: ActivityItem[]
}
