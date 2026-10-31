import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  DeliveryCreateRequest,
  DeliveryReverseRequest,
} from '@/types/api'

export const deliveryKeys = {
  all: ['deliveries'] as const,
  list: (params: object) => ['deliveries', 'list', params] as const,
  detail: (id: string) => ['deliveries', 'detail', id] as const,
}

export interface DeliveryListParams {
  farmer_id?: string
  produce_line_id?: string
  recorded_by_id?: string
  delivered_from?: string
  delivered_to?: string
  include_reversals?: boolean
  unvalued_only?: boolean
  limit?: number
  offset?: number
}

export function useDeliveries(params: DeliveryListParams = {}) {
  return useQuery({
    queryKey: deliveryKeys.list(params),
    queryFn: () => api.deliveries.list(params),
  })
}

export function useDelivery(id: string | undefined) {
  return useQuery({
    queryKey: id ? deliveryKeys.detail(id) : ['deliveries', 'detail', 'none'],
    queryFn: () => api.deliveries.get(id!),
    enabled: !!id,
  })
}

export function useCreateDelivery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: DeliveryCreateRequest) => api.deliveries.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: deliveryKeys.all })
      // Farmers' balances changed too.
      qc.invalidateQueries({ queryKey: ['farmers', 'balance'] })
    },
  })
}

export function useValueDelivery(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.deliveries.value(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: deliveryKeys.detail(id) })
      qc.invalidateQueries({ queryKey: deliveryKeys.all })
      qc.invalidateQueries({ queryKey: ['farmers', 'balance'] })
    },
  })
}

export function useReverseDelivery(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: DeliveryReverseRequest) => api.deliveries.reverse(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: deliveryKeys.detail(id) })
      qc.invalidateQueries({ queryKey: deliveryKeys.all })
      qc.invalidateQueries({ queryKey: ['farmers', 'balance'] })
    },
  })
}