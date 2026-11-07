import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  CollectionPoint,
  CollectionPointCreateRequest,
  CollectionPointUpdateRequest,
  Paginated,
  ProductionByPoint,
} from '@/types/api'

export const collectionPointKeys = {
  all: ['collection-points'] as const,
  list: (params: object) => ['collection-points', 'list', params] as const,
  production: (params: object) =>
    ['collection-points', 'production', params] as const,
}

export function useCollectionPoints(
  params: { active_only?: boolean; search?: string } = {},
) {
  return useQuery({
    queryKey: collectionPointKeys.list(params),
    queryFn: () => api.collectionPoints.list(params),
  })
}

export function useProductionByPoint(
  params: { delivered_from?: string; delivered_to?: string } = {},
) {
  return useQuery<ProductionByPoint>({
    queryKey: collectionPointKeys.production(params),
    queryFn: () => api.reports.productionByPoint(params),
  })
}

export function useCreateCollectionPoint() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CollectionPointCreateRequest) =>
      api.collectionPoints.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: collectionPointKeys.all })
    },
  })
}

export function useUpdateCollectionPoint() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string
      body: CollectionPointUpdateRequest
    }) => api.collectionPoints.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: collectionPointKeys.all })
    },
  })
}

export type { CollectionPoint, Paginated }
