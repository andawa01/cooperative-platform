import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  Deduction,
  DeductionCreateRequest,
  DeductionReverseRequest,
  Paginated,
} from '@/types/api'

export const deductionKeys = {
  all: ['deductions'] as const,
  list: (params: object) => ['deductions', 'list', params] as const,
  detail: (id: string) => ['deductions', 'detail', id] as const,
}

export interface DeductionListParams {
  farmer_id?: string
  reason_code?: string
  include_reversals?: boolean
  limit?: number
  offset?: number
}

export function useDeductions(params: DeductionListParams = {}) {
  return useQuery({
    queryKey: deductionKeys.list(params),
    queryFn: () => api.deductions.list(params),
  })
}

export function useDeduction(id: string | undefined) {
  return useQuery({
    queryKey: id ? deductionKeys.detail(id) : ['deductions', 'detail', 'none'],
    queryFn: () => api.deductions.get(id!),
    enabled: !!id,
  })
}

/**
 * Recording or reversing a deduction moves the member's net payable, so the
 * balance, statement and dashboard caches are invalidated too. Forgetting one
 * of those leaves a screen confidently showing a stale number, which is how a
 * clerk ends up paying the wrong amount.
 */
function useInvalidateMoneyViews() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: deductionKeys.all })
    qc.invalidateQueries({ queryKey: ['farmers', 'balance'] })
    qc.invalidateQueries({ queryKey: ['farmers', 'statement'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
}

export function useCreateDeduction() {
  const invalidate = useInvalidateMoneyViews()
  return useMutation({
    mutationFn: (body: DeductionCreateRequest) => api.deductions.create(body),
    onSuccess: invalidate,
  })
}

export function useReverseDeduction(id: string) {
  const invalidate = useInvalidateMoneyViews()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: DeductionReverseRequest) => api.deductions.reverse(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: deductionKeys.detail(id) })
      invalidate()
    },
  })
}

export type { Deduction, Paginated }
