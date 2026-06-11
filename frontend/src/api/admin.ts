import { api } from './client';
import type { Job, JobListResponse } from './jobs';

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  role: string;
  status: string;
  created_at: string;
}

export const adminApi = {
  listUsers: () => api.get<AdminUser[]>('/admin/users'),

  updateUser: (id: string, updates: { role?: string; status?: string }) =>
    api.patch<AdminUser>(`/admin/users/${id}`, updates),

  deleteUser: (id: string) => api.delete(`/admin/users/${id}`),

  listJobs: (page = 1, pageSize = 50) =>
    api.get<JobListResponse>('/admin/jobs', { params: { page, page_size: pageSize } }),

  updateJob: (id: string, updates: { priority?: number; status?: string }) =>
    api.patch<Job>(`/admin/jobs/${id}`, updates),
};
