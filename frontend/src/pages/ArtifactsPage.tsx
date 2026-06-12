import {
  Stack, Title, Text, Paper, Group, ActionIcon,
  Skeleton, Collapse, ThemeIcon, Tooltip,
  Divider,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { FolderOpen, Folder, Download, ChevronRight, ChevronDown, FileText } from 'lucide-react';
import { useJobs, useJobArtifacts } from '../hooks/useJobs';
import { fmtBytes, fmtDate, shortId } from '../lib/format';
import { StatusBadge } from '../components/StatusBadge';
import type { Job, JobArtifact } from '../api/jobs';

function ArtifactRow({ artifact }: { artifact: JobArtifact }) {
  return (
    <Group justify="space-between" px="sm" py={6} style={{ borderRadius: 4 }}
      styles={{ root: { '&:hover': { background: 'var(--mantine-color-dark-6)' } } }}
    >
      <Group gap="xs">
        <FileText size={14} color="var(--mantine-color-dimmed)" />
        <Text size="sm" ff="monospace">{artifact.file_name}</Text>
        <Text size="xs" c="dimmed">{fmtBytes(artifact.file_size_bytes)}</Text>
      </Group>
      <Tooltip label={artifact.download_url ? 'Download' : 'URL unavailable'} withArrow>
        <ActionIcon
          variant="subtle"
          size="sm"
          component="a"
          href={artifact.download_url ?? '#'}
          target="_blank"
          rel="noopener noreferrer"
          disabled={!artifact.download_url}
        >
          <Download size={14} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

function JobFolder({ job }: { job: Job }) {
  const [opened, { toggle }] = useDisclosure(false);
  const { data: artifacts = [], isLoading } = useJobArtifacts(opened ? job.id : null);

  const hasArtifacts = job.status === 'completed' || job.status === 'failed';

  return (
    <Paper radius="sm" withBorder>
      <Group
        justify="space-between"
        p="sm"
        style={{ cursor: hasArtifacts ? 'pointer' : 'default' }}
        onClick={hasArtifacts ? toggle : undefined}
      >
        <Group gap="sm">
          <ThemeIcon variant="subtle" size="sm" color={opened ? 'cyan' : 'gray'}>
            {opened ? <FolderOpen size={15} /> : <Folder size={15} />}
          </ThemeIcon>
          <div>
            <Text size="sm" fw={600}>{job.title ?? `Job ${shortId(job.id)}`}</Text>
            <Text size="xs" c="dimmed" ff="monospace">{shortId(job.id)} · {fmtDate(job.finished_at ?? job.submitted_at)}</Text>
          </div>
        </Group>
        <Group gap="sm">
          <StatusBadge status={job.status} />
          {hasArtifacts && (
            <ActionIcon variant="subtle" size="sm">
              {opened ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </ActionIcon>
          )}
        </Group>
      </Group>

      <Collapse expanded={opened}>
        <Divider />
        {isLoading ? (
          <Stack gap={4} p="sm">
            {[1, 2, 3].map((i) => <Skeleton key={i} h={28} radius="sm" />)}
          </Stack>
        ) : artifacts.length === 0 ? (
          <Text size="sm" c="dimmed" p="sm">No artifacts - script may not have written to /outputs.</Text>
        ) : (
          <Stack gap={0} py={4}>
            {artifacts.map((a) => (
              <ArtifactRow key={a.id} artifact={a} />
            ))}
          </Stack>
        )}
      </Collapse>
    </Paper>
  );
}

export function ArtifactsPage() {
  const { data: jobs = [], isLoading } = useJobs();

  const completedJobs = jobs.filter((j) => j.status === 'completed' || j.status === 'failed');
  const activeJobs = jobs.filter((j) => !['completed', 'failed', 'cancelled'].includes(j.status));

  return (
    <Stack gap="lg">
      <div>
        <Title order={3}>Artifacts</Title>
        <Text size="sm" c="dimmed" mt={2}>
          Output files from completed runs; click a job to browse its files
        </Text>
      </div>

      {isLoading ? (
        <Stack gap="sm">
          {[1, 2, 3].map((i) => <Skeleton key={i} h={56} radius="sm" />)}
        </Stack>
      ) : completedJobs.length === 0 ? (
        <Paper p="xl" radius="md" withBorder>
          <Text ta="center" c="dimmed" size="sm">
            No completed jobs yet. Artifacts appear here once a job finishes.
          </Text>
        </Paper>
      ) : (
        <Stack gap="sm">
          {completedJobs.map((job) => (
            <JobFolder key={job.id} job={job} />
          ))}
        </Stack>
      )}

      {activeJobs.length > 0 && (
        <>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>In progress</Text>
          <Stack gap="sm">
            {activeJobs.map((job) => (
              <Paper key={job.id} radius="sm" withBorder p="sm">
                <Group justify="space-between">
                  <Group gap="sm">
                    <ThemeIcon variant="subtle" size="sm" color="gray">
                      <Folder size={15} />
                    </ThemeIcon>
                    <div>
                      <Text size="sm" fw={600}>{job.title ?? `Job ${shortId(job.id)}`}</Text>
                      <Text size="xs" c="dimmed" ff="monospace">{shortId(job.id)}</Text>
                    </div>
                  </Group>
                  <StatusBadge status={job.status} />
                </Group>
              </Paper>
            ))}
          </Stack>
        </>
      )}
    </Stack>
  );
}
