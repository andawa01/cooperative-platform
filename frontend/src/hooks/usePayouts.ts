import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  PayoutBatch,
  PayoutCreateRequest,
  PayoutDispatchResult,
  Paginated,
} from '@/types/api'

export const payoutKeys = {
  all: ['payout-runs'] as const,
  list: (params: object) => ['payout-runs', 'list', params] as const,
  detail: (id: string) => ['payout-runs', 'detail', id] as const,
}

export function usePayoutRuns(params: { limit?: number; offset?: number } = {}) {
  return useQuery({
    queryKey: payoutKeys.list(params),
    queryFn: () => api.payoutRuns.list(params),
  })
}

export function usePayoutRun(id: string | undefined) {
  return useQuery({
    queryKey: id ? payoutKeys.detail(id) : ['payout-runs', 'detail', 'none'],
    queryFn: () => api.payoutRuns.get(id!),
    enabled: !!id,
  })
}

/**
 * A run moves real money, so every mutation invalidates the views that show
 * money. A stale balance after a payout is the worst kind of stale — someone
 * gets paid twice because a screen still said they were owed.
 */
function useInvalidateMoneyViews() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: payoutKeys.all })
    qc.invalidateQueries({ queryKey: ['farmers', 'balance'] })
    qc.invalidateQueries({ queryKey: ['farmers', 'statement'] })
    qc.invalidateQueries({ queryKey: ['payments'] })
    qc.invalidateQueries({ queryKey: ['notifications'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
}

export function useCreatePayoutRun() {
  const invalidate = useInvalidateMoneyViews()
  return useMutation({
    mutationFn: (body: PayoutCreateRequest) => api.payoutRuns.create(body),
    onSuccess: invalidate,
  })
}

export function useApprovePayoutRun(id: string) {
  const qc = useQueryClient()
  const invalidate = useInvalidateMoneyViews()
  return useMutation({
    mutationFn: () => api.payoutRuns.approve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: payoutKeys.detail(id) })
      invalidate()
    },
  })
}

export function useDispatchPayoutRun(id: string) {
  const qc = useQueryClient()
  const invalidate = useInvalidateMoneyViews()
  return useMutation<PayoutDispatchResult>({
    mutationFn: () => api.payoutRuns.dispatch(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: payoutKeys.detail(id) })
      invalidate()
    },
  })
}

export function useCancelPayoutRun(id: string) {
  const qc = useQueryClient()
  const invalidate = useInvalidateMoneyViews()
  return useMutation({
    mutationFn: () => api.payoutRuns.cancel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: payoutKeys.detail(id) })
      invalidate()
    },
  })
}

export type { PayoutBatch, Paginated }
