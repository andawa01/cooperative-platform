import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  Approval,
  ApprovalCreateRequest,
  ApprovalStatus,
  Paginated,
} from '@/types/api'

export const approvalKeys = {
  all: ['approvals'] as const,
  list: (params: object) => ['approvals', 'list', params] as const,
}

export function useApprovals(
  params: { status?: ApprovalStatus; limit?: number; offset?: number } = {},
) {
  return useQuery({
    queryKey: approvalKeys.list(params),
    queryFn: () => api.approvals.list(params),
  })
}

export function useCreateApproval() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ApprovalCreateRequest) => api.approvals.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: approvalKeys.all })
    },
  })
}

/**
 * Approving executes the underlying money move, so every screen that shows
 * money has to be refreshed — the same rule as the direct reverse/dispatch
 * path, or a stale balance survives the one action that changed it.
 */
function useInvalidateAfterDecision() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: approvalKeys.all })
    qc.invalidateQueries({ queryKey: ['payments'] })
    qc.invalidateQueries({ queryKey: ['deductions'] })
    qc.invalidateQueries({ queryKey: ['payout-runs'] })
    qc.invalidateQueries({ queryKey: ['farmers'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    qc.invalidateQueries({ queryKey: ['notifications'] })
  }
}

export function useDecideApproval() {
  const invalidate = useInvalidateAfterDecision()
  return useMutation({
    mutationFn: ({
      id,
      approve,
      note,
    }: {
      id: string
      approve: boolean
      note?: string | null
    }) =>
      approve
        ? api.approvals.approve(id, { note })
        : api.approvals.reject(id, { note }),
    onSuccess: invalidate,
  })
}

export type { Approval, Paginated }
