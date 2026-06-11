import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { jobsApi } from '../api/jobs';
import { notifications } from '@mantine/notifications';

export const JOB_KEYS = {
  list: ['jobs'] as const,
  detail: (id: string) => ['jobs', id] as const,
  events: (id: string) => ['jobs', id, 'events'] as const,
  artifacts: (id: string) => ['jobs', id, 'artifacts'] as const,
  logs: (id: string, type: string) => ['jobs', id, 'logs', type] as const,
};

export function useJobs() {
  return useQuery({
    queryKey: JOB_KEYS.list,
    queryFn: () => jobsApi.list().then((r) => r.data.jobs),
    refetchInterval: 5000,
  });
}

export function useJobEvents(jobId: string | null) {
  return useQuery({
    queryKey: JOB_KEYS.events(jobId ?? ''),
    queryFn: () => jobsApi.events(jobId!).then((r) => r.data),
    enabled: !!jobId,
    refetchInterval: 3000,
  });
}

export function useJobArtifacts(jobId: string | null) {
  return useQuery({
    queryKey: JOB_KEYS.artifacts(jobId ?? ''),
    queryFn: () => jobsApi.artifacts(jobId!).then((r) => r.data),
    enabled: !!jobId,
  });
}

export function useJobLogs(jobId: string | null, type: 'stdout' | 'stderr' | 'combined', isFinished: boolean) {
  return useQuery({
    queryKey: JOB_KEYS.logs(jobId ?? '', type),
    queryFn: () => jobsApi.logs(jobId!, type).then((r) => r.data),
    enabled: !!jobId,
    refetchInterval: isFinished ? false : 3000,
    retry: false,
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => jobsApi.cancel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOB_KEYS.list });
      notifications.show({ color: 'orange', message: 'Job cancellation initiated.' });
    },
    onError: (e: any) => {
      notifications.show({ color: 'red', message: e.response?.data?.detail ?? 'Failed to cancel job.' });
    },
  });
}

export function useSubmitFileJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: jobsApi.submitFile,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOB_KEYS.list });
      notifications.show({ color: 'teal', message: 'Job submitted to queue.' });
    },
    onError: (e: any) => {
      notifications.show({ color: 'red', message: e.response?.data?.detail ?? 'Submission failed.' });
    },
  });
}

export function useSubmitGithubJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: jobsApi.submitGithub,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOB_KEYS.list });
      notifications.show({ color: 'teal', message: 'Job submitted to queue.' });
    },
    onError: (e: any) => {
      notifications.show({ color: 'red', message: e.response?.data?.detail ?? 'Submission failed.' });
    },
  });
}
