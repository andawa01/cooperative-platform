import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'

export const auditKeys = {
  all: ['audit'] as const,
  list: (params: object) => ['audit', 'list', params] as const,
}

export interface AuditListParams {
  action?: string
  entity_type?: string
  entity_id?: string
  actor_id?: string
  limit?: number
  offset?: number
}

export function useAuditEntries(params: AuditListParams = {}) {
  return useQuery({
    queryKey: auditKeys.list(params),
    queryFn: () => api.audit.list(params),
    // The trail is append-only, so a cached page only ever goes stale by
    // growing. A short window keeps the screen live without hammering it.
    staleTime: 15_000,
  })
}
