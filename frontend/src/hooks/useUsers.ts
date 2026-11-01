import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { UserCreateRequest, UserUpdateRequest } from '@/types/api'

export const userKeys = {
  all: ['users'] as const,
  list: (params: object) => ['users', 'list', params] as const,
}

export interface UserListParams {
  search?: string
  role?: string
  limit?: number
  offset?: number
}

export function useUsers(params: UserListParams = {}) {
  return useQuery({
    queryKey: userKeys.list(params),
    queryFn: () => api.users.list(params),
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UserUpdateRequest }) =>
      api.users.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.all })
    },
  })
}

export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: UserCreateRequest) => api.auth.register(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.all })
    },
  })
}
