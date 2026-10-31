import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  Paginated,
  ProduceLine,
  ProduceLineCreateRequest,
  Rate,
  RateCreateRequest,
} from '@/types/api'

export const produceLineKeys = {
  all: ['produce-lines'] as const,
  list: (params: object) => ['produce-lines', 'list', params] as const,
  detail: (id: string) => ['produce-lines', 'detail', id] as const,
  rates: (id: string) => ['produce-lines', 'rates', id] as const,
  currentRate: (id: string) => ['produce-lines', 'current-rate', id] as const,
}

export function useProduceLines(
  params: { include_inactive?: boolean; limit?: number; offset?: number } = {},
) {
  return useQuery({
    queryKey: produceLineKeys.list(params),
    queryFn: () => api.produceLines.list(params),
  })
}

export function useProduceLine(id: string | undefined) {
  return useQuery({
    queryKey: id ? produceLineKeys.detail(id) : ['produce-lines', 'detail', 'none'],
    queryFn: () => api.produceLines.get(id!),
    enabled: !!id,
  })
}

export function useRates(id: string | undefined) {
  return useQuery({
    queryKey: id ? produceLineKeys.rates(id) : ['produce-lines', 'rates', 'none'],
    queryFn: () => api.produceLines.rates(id!),
    enabled: !!id,
  })
}

export function useCurrentRate(id: string | undefined) {
  return useQuery({
    queryKey: id
      ? produceLineKeys.currentRate(id)
      : ['produce-lines', 'current-rate', 'none'],
    queryFn: () => api.produceLines.currentRate(id!),
    enabled: !!id,
  })
}

export function useCreateProduceLine() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ProduceLineCreateRequest) => api.produceLines.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: produceLineKeys.all })
    },
  })
}

export function useDeactivateProduceLine(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.produceLines.deactivate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: produceLineKeys.all })
      qc.invalidateQueries({ queryKey: produceLineKeys.detail(id) })
    },
  })
}

export function useCreateRate(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RateCreateRequest) => api.produceLines.createRate(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: produceLineKeys.rates(id) })
      qc.invalidateQueries({ queryKey: produceLineKeys.currentRate(id) })
      qc.invalidateQueries({ queryKey: produceLineKeys.all })
    },
  })
}

export type { ProduceLine, Rate, Paginated }