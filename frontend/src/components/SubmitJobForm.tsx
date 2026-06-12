import React, { useState } from 'react';
import {
  Stack, Tabs, TextInput, Textarea, Select,
  Group, Button, ActionIcon, Switch, Divider, Slider, Badge,
  FileInput, Text,
} from '@mantine/core';
import { Plus, Trash2, Play } from 'lucide-react';
import { useSubmitFileJob, useSubmitGithubJob } from '../hooks/useJobs';
import type { EnvVar } from '../api/jobs';
import type { StoredUser } from '../lib/auth';

interface Props {
  currentUser: StoredUser | null;
  onSuccess?: () => void;
}

interface EnvVarRow { key: string; value: string; isSecret: boolean }

export function SubmitJobForm({ currentUser, onSuccess }: Props) {
  const submitFile = useSubmitFileJob();
  const submitGithub = useSubmitGithubJob();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [gpuCount, setGpuCount] = useState<number>(1);
  const [priority, setPriority] = useState(5);
  const [envVars, setEnvVars] = useState<EnvVarRow[]>([]);

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [setupScript, setSetupScript] = useState<File | null>(null);
  const [requirementsFile, setRequirementsFile] = useState<File | null>(null);

  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('main');
  const [commitHash, setCommitHash] = useState('');
  const [repoSubdir, setRepoSubdir] = useState('');
  const [entrypoint, setEntrypoint] = useState('');
  const [repoRequirementsPath, setRepoRequirementsPath] = useState('');
  const [runAsModule, setRunAsModule] = useState(false);

  const isAdmin = currentUser?.role === 'admin';
  const isPending = submitFile.isPending || submitGithub.isPending;

  function buildPayload() {
    const builtEnvVars: EnvVar[] = envVars
      .filter((e) => e.key.trim())
      .map((e) => ({ var_name: e.key.trim(), var_value: e.value.trim(), is_secret: e.isSecret }));
    return {
      title: title || undefined,
      description: description || undefined,
      requested_gpu_count: gpuCount,
      priority: isAdmin ? priority : 5,
      queue_name: 'default',
      env_vars: builtEnvVars,
    };
  }

  function resetForm() {
    setTitle(''); setDescription(''); setGpuCount(1); setPriority(5);
    setEnvVars([]); setUploadFile(null); setSetupScript(null); setRequirementsFile(null); setRepoUrl(''); setRepoBranch('main');
    setCommitHash(''); setRepoSubdir(''); setEntrypoint(''); setRepoRequirementsPath(''); setRunAsModule(false);
  }

  async function handleFileSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadFile) return;
    await submitFile.mutateAsync({ ...buildPayload(), file: uploadFile, setup_script: setupScript ?? undefined, requirements_file: requirementsFile ?? undefined });
    resetForm();
    onSuccess?.();
  }

  async function handleGithubSubmit(e: React.FormEvent) {
    e.preventDefault();
    await submitGithub.mutateAsync({
      ...buildPayload(),
      repo_url: repoUrl,
      repo_branch: repoBranch || 'main',
      repo_commit_hash: commitHash || undefined,
      repo_subdir: repoSubdir || undefined,
      entrypoint,
      run_as_module: runAsModule,
      requirements_file_path: repoRequirementsPath || undefined,
    });
    resetForm();
    onSuccess?.();
  }

  function addEnvVar() {
    setEnvVars((prev) => [...prev, { key: '', value: '', isSecret: false }]);
  }

  function updateEnvVar(i: number, field: keyof EnvVarRow, value: string | boolean) {
    setEnvVars((prev) => prev.map((row, idx) => idx === i ? { ...row, [field]: value } : row));
  }

  function removeEnvVar(i: number) {
    setEnvVars((prev) => prev.filter((_, idx) => idx !== i));
  }

  function ResourceFields() {
    return (
      <Stack gap="sm">
        <Select
          label="GPUs"
          value={String(gpuCount)}
          onChange={(v) => setGpuCount(Number(v ?? 1))}
          data={[
            { value: '0', label: '0 — CPU only' },
            { value: '1', label: '1 GPU (RTX Titan)' },
          ]}
        />
        {isAdmin && (
          <div>
            <Text size="xs" c="dimmed" fw={600} mb={6}>
              Priority override{' '}
              <Badge size="xs" color="violet" variant="light">admin</Badge>
            </Text>
            <Group gap="md">
              <Slider
                flex={1}
                min={1} max={10} step={1}
                value={priority}
                onChange={setPriority}
                marks={[{ value: 1, label: '1' }, { value: 5, label: '5' }, { value: 10, label: '10' }]}
                color="violet"
              />
              <Text ff="monospace" fw={700} c="violet" w={20} ta="center">{priority}</Text>
            </Group>
          </div>
        )}
      </Stack>
    );
  }

  function EnvVarsSection() {
    return (
      <Stack gap="xs">
        <Group justify="space-between">
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Environment Variables</Text>
          <ActionIcon variant="subtle" size="sm" onClick={addEnvVar}>
            <Plus size={14} />
          </ActionIcon>
        </Group>
        {envVars.map((ev, i) => (
          <Group key={i} gap="xs" align="flex-end">
            <TextInput
              placeholder="VAR_NAME"
              value={ev.key}
              onChange={(e) => updateEnvVar(i, 'key', e.currentTarget.value)}
              style={{ flex: 1 }}
            />
            <TextInput
              placeholder="value"
              value={ev.value}
              type={ev.isSecret ? 'password' : 'text'}
              onChange={(e) => updateEnvVar(i, 'value', e.currentTarget.value)}
              style={{ flex: 1 }}
            />
            <Switch
              size="xs"
              label="Secret"
              checked={ev.isSecret}
              onChange={(e) => updateEnvVar(i, 'isSecret', e.currentTarget.checked)}
            />
            <ActionIcon color="red" variant="subtle" size="sm" onClick={() => removeEnvVar(i)}>
              <Trash2 size={14} />
            </ActionIcon>
          </Group>
        ))}
      </Stack>
    );
  }

  return (
    <Tabs defaultValue="file">
      <Tabs.List mb="md">
        <Tabs.Tab value="file">Python / Shell Script</Tabs.Tab>
        <Tabs.Tab value="github">GitHub Repository</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="file">
        <form onSubmit={handleFileSubmit}>
          <Stack gap="sm">
            <TextInput label="Job Title" placeholder="e.g. MNIST Smoke Test" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
            <Textarea label="Description" placeholder="Optional notes..." value={description} onChange={(e) => setDescription(e.currentTarget.value)} autosize minRows={2} />
            <FileInput
              label="Python Script (.py)"
              placeholder="Click to select"
              accept=".py"
              value={uploadFile}
              onChange={setUploadFile}
              required
            />
            <Group grow gap="sm">
              <FileInput
                label="Setup Script (.sh, optional)"
                description="Runs before the Python script — use for env setup, data prep, etc."
                placeholder="Click to select"
                accept=".sh"
                value={setupScript}
                onChange={setSetupScript}
                clearable
              />
              <FileInput
                label="requirements.txt (optional)"
                placeholder="Click to select"
                accept=".txt"
                value={requirementsFile}
                onChange={setRequirementsFile}
                clearable
              />
            </Group>
            <Divider />
            <ResourceFields />
            <Divider />
            <EnvVarsSection />
            <Button type="submit" leftSection={<Play size={16} />} loading={isPending} mt="xs">
              Submit Job
            </Button>
          </Stack>
        </form>
      </Tabs.Panel>

      <Tabs.Panel value="github">
        <form onSubmit={handleGithubSubmit}>
          <Stack gap="sm">
            <TextInput label="Job Title" placeholder="e.g. CIFAR-10 ResNet18" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
            <Textarea label="Description" autosize minRows={2} value={description} onChange={(e) => setDescription(e.currentTarget.value)} />
            <TextInput
              label="GitHub Repo URL"
              placeholder="https://github.com/org/repo.git"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.currentTarget.value)}
              required
            />
            <Group grow>
              <TextInput label="Branch" placeholder="main" value={repoBranch} onChange={(e) => setRepoBranch(e.currentTarget.value)} />
              <TextInput
                label="Entrypoint"
                placeholder={runAsModule ? 'package.train' : 'scripts/train.py'}
                description={runAsModule ? 'Module path (dots) or file path — both accepted' : undefined}
                value={entrypoint}
                onChange={(e) => setEntrypoint(e.currentTarget.value)}
                required
              />
            </Group>
            <Switch
              label="Run as module (python -m)"
              description="Use when your code has relative imports (from .utils import …)"
              checked={runAsModule}
              onChange={(e) => setRunAsModule(e.currentTarget.checked)}
            />
            <Group grow>
              <TextInput label="Subdirectory (optional)" placeholder="src" value={repoSubdir} onChange={(e) => setRepoSubdir(e.currentTarget.value)} />
              <TextInput label="Commit Hash (optional)" placeholder="Latest if blank" value={commitHash} onChange={(e) => setCommitHash(e.currentTarget.value)} />
            </Group>
            <TextInput
              label="Requirements file path (optional)"
              placeholder="requirements.txt"
              description="Relative path to requirements.txt inside the repo"
              value={repoRequirementsPath}
              onChange={(e) => setRepoRequirementsPath(e.currentTarget.value)}
            />
            <Divider />
            <ResourceFields />
            <Divider />
            <EnvVarsSection />
            <Button type="submit" leftSection={<Play size={16} />} loading={isPending} mt="xs">
              Submit Job
            </Button>
          </Stack>
        </form>
      </Tabs.Panel>
    </Tabs>
  );
}
