import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi } from '../api/admin';
import { notifications } from '@mantine/notifications';

export const ADMIN_KEYS = {
  users: ['admin', 'users'] as const,
  jobs: ['admin', 'jobs'] as const,
};

export function useAdminUsers() {
  return useQuery({
    queryKey: ADMIN_KEYS.users,
    queryFn: () => adminApi.listUsers().then((r) => r.data),
  });
}

export function useAdminJobs() {
  return useQuery({
    queryKey: ADMIN_KEYS.jobs,
    queryFn: () => adminApi.listJobs().then((r) => r.data.jobs),
    refetchInterval: 5000,
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: { role?: string; status?: string } }) =>
      adminApi.updateUser(id, updates),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ADMIN_KEYS.users });
      notifications.show({ color: 'teal', message: 'User updated.' });
    },
    onError: (e: any) => {
      notifications.show({ color: 'red', message: e.response?.data?.detail ?? 'Update failed.' });
    },
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => adminApi.deleteUser(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ADMIN_KEYS.users });
      notifications.show({ color: 'teal', message: 'User deleted.' });
    },
    onError: (e: any) => {
      notifications.show({ color: 'red', message: e.response?.data?.detail ?? 'Delete failed.' });
    },
  });
}

export function useUpdateAdminJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: { priority?: number; status?: string } }) =>
      adminApi.updateJob(id, updates),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ADMIN_KEYS.jobs });
      notifications.show({ color: 'teal', message: 'Job updated.' });
    },
    onError: (e: any) => {
      notifications.show({ color: 'red', message: e.response?.data?.detail ?? 'Update failed.' });
    },
  });
}
