import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'

export const notificationKeys = {
  all: ['notifications'] as const,
  list: (params: object) => ['notifications', 'list', params] as const,
  detail: (id: string) => ['notifications', 'detail', id] as const,
}

export interface NotificationListParams {
  farmer_id?: string
  limit?: number
  offset?: number
}

export function useNotifications(params: NotificationListParams = {}) {
  return useQuery({
    queryKey: notificationKeys.list(params),
    queryFn: () => api.notifications.list(params),
  })
}

export function useNotification(id: string | undefined) {
  return useQuery({
    queryKey: id
      ? notificationKeys.detail(id)
      : ['notifications', 'detail', 'none'],
    queryFn: () => api.notifications.get(id!),
    enabled: !!id,
  })
}

export function useRetryNotification(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.notifications.retry(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: notificationKeys.detail(id) })
      qc.invalidateQueries({ queryKey: notificationKeys.all })
    },
  })
}