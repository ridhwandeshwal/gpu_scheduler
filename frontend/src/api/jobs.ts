import { api } from './client';

export interface EnvVar {
  var_name: string;
  var_value: string;
  is_secret: boolean;
}

export interface Job {
  id: string;
  user_id: string;
  title: string | null;
  description: string | null;
  source_type: string;
  status: 'queued' | 'scheduled' | 'running' | 'completed' | 'failed' | 'cancelled';
  priority: number;
  queue_name: string;
  requested_gpu_count: number;
  requested_cpu_cores: number | null;
  requested_memory_mb: number | null;
  max_runtime_seconds: number | null;
  submitted_at: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  latest_run_id: string | null;
  failure_reason: string | null;
  created_at: string;
}

export interface JobEvent {
  id: string;
  job_id: string;
  job_run_id: string | null;
  event_type: string;
  event_message: string | null;
  created_at: string;
}

export interface JobArtifact {
  id: string;
  job_run_id: string;
  artifact_type: string;
  file_name: string;
  object_key: string;
  file_size_bytes: number | null;
  checksum_sha256: string | null;
  created_at: string;
  download_url: string | null;
}

export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  page_size: number;
}

export interface SubmitFileJobPayload {
  file: File;
  setup_script?: File;
  requirements_file?: File;
  title?: string;
  description?: string;
  requested_gpu_count: number;
  requested_cpu_cores?: number;
  requested_memory_mb?: number;
  max_runtime_seconds?: number;
  priority: number;
  queue_name: string;
  env_vars: EnvVar[];
}

export interface SubmitGithubJobPayload {
  repo_url: string;
  repo_branch: string;
  repo_commit_hash?: string;
  repo_subdir?: string;
  entrypoint: string;
  run_as_module?: boolean;
  requirements_file_path?: string;
  title?: string;
  description?: string;
  requested_gpu_count: number;
  requested_cpu_cores?: number;
  requested_memory_mb?: number;
  max_runtime_seconds?: number;
  priority: number;
  queue_name: string;
  env_vars: EnvVar[];
}

export const jobsApi = {
  list: (page = 1, pageSize = 50) =>
    api.get<JobListResponse>('/jobs', { params: { page, page_size: pageSize } }),

  get: (id: string) => api.get<Job>(`/jobs/${id}`),

  events: (id: string) => api.get<JobEvent[]>(`/jobs/${id}/events`),

  artifacts: (id: string) => api.get<JobArtifact[]>(`/jobs/${id}/artifacts`),

  logs: (id: string, type: 'stdout' | 'stderr' | 'combined') =>
    api.get<string>(`/jobs/${id}/logs/${type}`),

  cancel: (id: string) => api.post(`/jobs/${id}/cancel`),

  submitFile: (payload: SubmitFileJobPayload) => {
    const metadata = {
      title: payload.title || null,
      description: payload.description || null,
      requested_gpu_count: payload.requested_gpu_count,
      requested_cpu_cores: payload.requested_cpu_cores || null,
      requested_memory_mb: payload.requested_memory_mb || null,
      max_runtime_seconds: payload.max_runtime_seconds || null,
      priority: payload.priority,
      queue_name: payload.queue_name,
      env_vars: payload.env_vars,
    };
    const form = new FormData();
    form.append('file', payload.file);
    if (payload.setup_script) {
      form.append('setup_script', payload.setup_script);
    }
    if (payload.requirements_file) {
      form.append('requirements_file', payload.requirements_file);
    }
    form.append('metadata', JSON.stringify(metadata));
    return api.post<Job>('/jobs/python-file', form);
  },

  submitGithub: (payload: SubmitGithubJobPayload) =>
    api.post<Job>('/jobs/github', {
      repo_url: payload.repo_url,
      repo_branch: payload.repo_branch,
      repo_commit_hash: payload.repo_commit_hash || null,
      repo_subdir: payload.repo_subdir || null,
      entrypoint: payload.entrypoint,
      run_as_module: payload.run_as_module ?? false,
      requirements_file_path: payload.requirements_file_path || null,
      title: payload.title || null,
      description: payload.description || null,
      requested_gpu_count: payload.requested_gpu_count,
      requested_cpu_cores: payload.requested_cpu_cores || null,
      requested_memory_mb: payload.requested_memory_mb || null,
      max_runtime_seconds: payload.max_runtime_seconds || null,
      priority: payload.priority,
      queue_name: payload.queue_name,
      env_vars: payload.env_vars,
    }),

  artifactDownloadUrl: (jobId: string, artifactId: string) =>
    `/api/jobs/${jobId}/artifacts/${artifactId}/download`,
};
