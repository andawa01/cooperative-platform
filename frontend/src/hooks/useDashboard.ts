import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'

export function useDashboardSummary(days = 30) {
  return useQuery({
    queryKey: ['dashboard', 'summary', days],
    queryFn: () => api.dashboard.summary({ days }),
    staleTime: 60_000, // dashboard numbers can be a minute stale
  })
}