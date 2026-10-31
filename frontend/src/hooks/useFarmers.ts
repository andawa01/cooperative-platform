/**
 * React Query hooks for the farmers resource.
 *
 * Convention (repeated for every resource):
 * - One hook per query, keyed by a tuple with resource name + params.
 * - One hook per mutation. Mutations invalidate the relevant query keys,
 *   not the whole cache.
 * - Backend errors propagate as ApiError; UI reads .status and .message.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  Farmer,
  FarmerCreateRequest,
  FarmerUpdateRequest,
  Paginated,
} from '@/types/api'

// ---------------------------------------------------------------------------
// Keys
// ---------------------------------------------------------------------------

export const farmerKeys = {
  all: ['farmers'] as const,
  list: (params: object) => ['farmers', 'list', params] as const,
  detail: (id: string) => ['farmers', 'detail', id] as const,
  balance: (id: string) => ['farmers', 'balance', id] as const,
  statement: (id: string, params: object) =>
    ['farmers', 'statement', id, params] as const,
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export interface FarmerListParams {
  status?: string
  search?: string
  include_merged?: boolean
  limit?: number
  offset?: number
}

export function useFarmers(
  params: FarmerListParams = {},
  options?: Omit<UseQueryOptions<Paginated<Farmer>>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: farmerKeys.list(params),
    queryFn: () => api.farmers.list(params),
    ...options,
  })
}

export function useFarmer(id: string | undefined) {
  return useQuery({
    queryKey: id ? farmerKeys.detail(id) : ['farmers', 'detail', 'none'],
    queryFn: () => api.farmers.get(id!),
    enabled: !!id,
  })
}

export function useFarmerBalance(id: string | undefined) {
  return useQuery({
    queryKey: id ? farmerKeys.balance(id) : ['farmers', 'balance', 'none'],
    queryFn: () => api.farmers.balance(id!),
    enabled: !!id,
  })
}

export function useFarmerStatement(
  id: string | undefined,
  params: { start?: string; end?: string } = {},
) {
  return useQuery({
    queryKey: id
      ? farmerKeys.statement(id, params)
      : ['farmers', 'statement', 'none', params],
    queryFn: () => api.farmers.statement(id!, params),
    enabled: !!id,
  })
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function useCreateFarmer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FarmerCreateRequest) => api.farmers.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: farmerKeys.all })
    },
  })
}

export function useUpdateFarmer(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FarmerUpdateRequest) => api.farmers.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: farmerKeys.detail(id) })
      qc.invalidateQueries({ queryKey: farmerKeys.all })
    },
  })
}

export function useVerifyFarmer(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.farmers.verify(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: farmerKeys.detail(id) })
      qc.invalidateQueries({ queryKey: farmerKeys.all })
    },
  })
}

export function useArchiveFarmer(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.farmers.archive(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: farmerKeys.detail(id) })
      qc.invalidateQueries({ queryKey: farmerKeys.all })
    },
  })
}