import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  Paginated,
  Payment,
  PaymentCreateRequest,
  PaymentReverseRequest,
} from '@/types/api'

export const paymentKeys = {
  all: ['payments'] as const,
  list: (params: object) => ['payments', 'list', params] as const,
  detail: (id: string) => ['payments', 'detail', id] as const,
}

export interface PaymentListParams {
  farmer_id?: string
  include_reversals?: boolean
  limit?: number
  offset?: number
}

export function usePayments(params: PaymentListParams = {}) {
  return useQuery({
    queryKey: paymentKeys.list(params),
    queryFn: () => api.payments.list(params),
  })
}

export function usePayment(id: string | undefined) {
  return useQuery({
    queryKey: id ? paymentKeys.detail(id) : ['payments', 'detail', 'none'],
    queryFn: () => api.payments.get(id!),
    enabled: !!id,
  })
}

export function useCreatePayment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: PaymentCreateRequest) => api.payments.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: paymentKeys.all })
      qc.invalidateQueries({ queryKey: ['farmers', 'balance'] })
      qc.invalidateQueries({ queryKey: ['deliveries'] })
    },
  })
}

export function useReversePayment(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: PaymentReverseRequest) => api.payments.reverse(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: paymentKeys.detail(id) })
      qc.invalidateQueries({ queryKey: paymentKeys.all })
      qc.invalidateQueries({ queryKey: ['farmers', 'balance'] })
      qc.invalidateQueries({ queryKey: ['deliveries'] })
    },
  })
}

export type { Payment, Paginated }