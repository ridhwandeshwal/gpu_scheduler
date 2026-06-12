import { useState } from 'react';
import {
  Stack, Group, Title, Button, Text, Table, Skeleton,
  Paper, ActionIcon, Tooltip,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Plus, Minus, RefreshCw, XCircle } from 'lucide-react';
import { useJobs, useCancelJob } from '../hooks/useJobs';
import { StatusBadge } from '../components/StatusBadge';
import { JobDetailDrawer } from '../components/JobDetailDrawer';
import { SubmitJobForm } from '../components/SubmitJobForm';
import { fmtDate, shortId } from '../lib/format';
import type { Job } from '../api/jobs';
import type { StoredUser } from '../lib/auth';

interface Props {
  currentUser: StoredUser | null;
}

const ACTIVE = new Set(['queued', 'scheduled', 'running']);

export function JobsPage({ currentUser }: Props) {
  const { data: jobs = [], isLoading, refetch } = useJobs();
  const cancelJob = useCancelJob();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const selectedJob = jobs.find((j) => j.id === selectedJobId) ?? null;
  const [drawerOpened, { open: openDrawer, close: closeDrawer }] = useDisclosure(false);
  const [formOpened, { toggle: toggleForm }] = useDisclosure(false);

  function openJob(job: Job) {
    setSelectedJobId(job.id);
    openDrawer();
  }

  const activeCount = jobs.filter((j) => ACTIVE.has(j.status)).length;

  return (
    <Stack gap="lg">
      {/* Header */}
      <Group justify="space-between">
        <div>
          <Title order={3}>My Jobs</Title>
          <Text size="sm" c="dimmed" mt={2}>
            {jobs.length} total · {activeCount} active
          </Text>
        </div>
        <Group gap="xs">
          <Tooltip label="Refresh">
            <ActionIcon variant="subtle" onClick={() => refetch()}>
              <RefreshCw size={16} />
            </ActionIcon>
          </Tooltip>
          <Button leftSection={formOpened ? <Minus size={16} /> : <Plus size={16} />} onClick={toggleForm} variant={formOpened ? 'filled' : 'light'}>
            {formOpened ? 'Close' : 'New Job'}
          </Button>
        </Group>
      </Group>

      {/* Submit form */}
      {formOpened && (
        <Paper p="lg" radius="md" withBorder>
          <Title order={5} mb="md">Submit New Job</Title>
          <SubmitJobForm currentUser={currentUser} onSuccess={() => toggleForm()} />
        </Paper>
      )}

      {/* Jobs table */}
      <Paper radius="md" withBorder style={{ overflow: 'hidden' }}>
        <Table highlightOnHover striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Job</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>GPUs</Table.Th>
              <Table.Th>Queue</Table.Th>
              <Table.Th>Priority</Table.Th>
              <Table.Th>Submitted</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Table.Tr key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <Table.Td key={j}><Skeleton h={16} radius="sm" /></Table.Td>
                  ))}
                </Table.Tr>
              ))
            ) : jobs.length === 0 ? (
              <Table.Tr>
                <Table.Td colSpan={7}>
                  <Text ta="center" c="dimmed" py="xl" size="sm">
                    No jobs yet. Submit one above.
                  </Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              jobs.map((job) => (
                <Table.Tr
                  key={job.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => openJob(job)}
                >
                  <Table.Td>
                    <Text size="sm" fw={600}>{job.title ?? `Job ${shortId(job.id)}`}</Text>
                    <Text size="xs" c="dimmed" ff="monospace">{shortId(job.id)}</Text>
                  </Table.Td>
                  <Table.Td><StatusBadge status={job.status} /></Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">{job.requested_gpu_count}</Text>
                  </Table.Td>
                  <Table.Td><Text size="sm">{job.queue_name}</Text></Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">{job.priority}</Text>
                  </Table.Td>
                  <Table.Td><Text size="sm">{fmtDate(job.submitted_at)}</Text></Table.Td>
                  <Table.Td onClick={(e) => e.stopPropagation()}>
                    {ACTIVE.has(job.status) && (
                      <Tooltip label="Cancel">
                        <ActionIcon
                          color="red"
                          variant="subtle"
                          size="sm"
                          loading={cancelJob.isPending}
                          onClick={() => cancelJob.mutate(job.id)}
                        >
                          <XCircle size={15} />
                        </ActionIcon>
                      </Tooltip>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      <JobDetailDrawer
        job={selectedJob}
        opened={drawerOpened}
        onClose={closeDrawer}
      />
    </Stack>
  );
}
