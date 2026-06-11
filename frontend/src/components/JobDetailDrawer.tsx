import {
  Drawer, Stack, Group, Text, Badge, Divider, Tabs,
  ScrollArea, Code, Button, Loader, SimpleGrid, Paper, ActionIcon,
} from '@mantine/core';
import { Download, XCircle } from 'lucide-react';
import { useJobEvents, useJobArtifacts, useJobLogs, useCancelJob } from '../hooks/useJobs';
import { StatusBadge } from './StatusBadge';
import { fmtDate, fmtDuration, fmtBytes, shortId } from '../lib/format';
import { jobsApi, type Job } from '../api/jobs';
import type { StoredUser } from '../lib/auth';

interface Props {
  job: Job | null;
  opened: boolean;
  onClose: () => void;
  currentUser: StoredUser | null;
}

const ACTIVE = new Set(['queued', 'scheduled', 'running']);

function StatCell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Paper p="sm" radius="sm" withBorder>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} mb={4}>{label}</Text>
      <Text size="sm" fw={500}>{value}</Text>
    </Paper>
  );
}

export function JobDetailDrawer({ job, opened, onClose, currentUser }: Props) {
  const isFinished = job ? !ACTIVE.has(job.status) : true;
  const { data: events = [], isLoading: eventsLoading } = useJobEvents(job?.id ?? null);
  const { data: artifacts = [] } = useJobArtifacts(job?.id ?? null);
  const cancelJob = useCancelJob();

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="lg"
      title={
        <Group gap="sm">
          <Text fw={700} size="md">{job?.title ?? `Job ${shortId(job?.id ?? '')}`}</Text>
          {job && <StatusBadge status={job.status} />}
        </Group>
      }
      styles={{ body: { padding: 0 } }}
    >
      {!job ? null : (
        <Stack gap={0} h="100%">
          <ScrollArea flex={1} p="md">
            <Stack gap="md">
              {/* Stat grid */}
              <SimpleGrid cols={3} spacing="sm">
                <StatCell label="GPUs" value={`${job.requested_gpu_count} GPU${job.requested_gpu_count !== 1 ? 's' : ''}`} />
                <StatCell label="Priority" value={job.priority} />
                <StatCell label="Queue" value={job.queue_name} />
                <StatCell label="Submitted" value={fmtDate(job.submitted_at)} />
                <StatCell label="Started" value={fmtDate(job.started_at)} />
                <StatCell label="Finished" value={fmtDate(job.finished_at)} />
              </SimpleGrid>

              {job.failure_reason && (
                <Paper p="sm" radius="sm" bg="red.9" style={{ borderColor: 'var(--mantine-color-red-7)' }} withBorder>
                  <Text size="xs" c="red.3" fw={600} mb={4}>FAILURE REASON</Text>
                  <Text size="xs" c="red.2" ff="monospace">{job.failure_reason}</Text>
                </Paper>
              )}

              <Divider />

              {/* Tabs */}
              <Tabs defaultValue="events">
                <Tabs.List>
                  <Tabs.Tab value="events">Events</Tabs.Tab>
                  <Tabs.Tab value="logs">Logs</Tabs.Tab>
                  <Tabs.Tab value="artifacts">Artifacts {artifacts.length > 0 && `(${artifacts.length})`}</Tabs.Tab>
                </Tabs.List>

                <Tabs.Panel value="events" pt="sm">
                  {eventsLoading ? (
                    <Loader size="sm" />
                  ) : events.length === 0 ? (
                    <Text size="sm" c="dimmed">No events yet.</Text>
                  ) : (
                    <Stack gap={4}>
                      {events.map((evt) => (
                        <Group key={evt.id} justify="space-between" wrap="nowrap">
                          <Text size="xs" c="teal.4">• {evt.event_message ?? evt.event_type}</Text>
                          <Text size="xs" c="dimmed" ff="monospace" style={{ whiteSpace: 'nowrap' }}>
                            {fmtDate(evt.created_at)}
                          </Text>
                        </Group>
                      ))}
                    </Stack>
                  )}
                </Tabs.Panel>

                <Tabs.Panel value="logs" pt="sm">
                  <LogsPanel jobId={job.id} isFinished={isFinished} />
                </Tabs.Panel>

                <Tabs.Panel value="artifacts" pt="sm">
                  {artifacts.length === 0 ? (
                    <Text size="sm" c="dimmed">No artifacts yet. Scripts should write outputs to <Code>/outputs</Code>.</Text>
                  ) : (
                    <Stack gap="xs">
                      {artifacts.map((art) => (
                        <Paper key={art.id} p="sm" radius="sm" withBorder>
                          <Group justify="space-between">
                            <div>
                              <Text size="sm" fw={600}>{art.file_name}</Text>
                              <Text size="xs" c="dimmed">{fmtBytes(art.file_size_bytes)} · {art.artifact_type}</Text>
                            </div>
                            <ActionIcon
                              variant="subtle"
                              component="a"
                              href={`/api/jobs/${job.id}/artifacts/${art.id}/download`}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <Download size={16} />
                            </ActionIcon>
                          </Group>
                        </Paper>
                      ))}
                    </Stack>
                  )}
                </Tabs.Panel>
              </Tabs>
            </Stack>
          </ScrollArea>

          {/* Footer actions */}
          {ACTIVE.has(job.status) && (
            <>
              <Divider />
              <Group p="md" justify="flex-end">
                <Button
                  leftSection={<XCircle size={16} />}
                  color="red"
                  variant="light"
                  loading={cancelJob.isPending}
                  onClick={() => cancelJob.mutate(job.id)}
                >
                  Cancel Job
                </Button>
              </Group>
            </>
          )}
        </Stack>
      )}
    </Drawer>
  );
}

function LogsPanel({ jobId, isFinished }: { jobId: string; isFinished: boolean }) {
  const [logType, setLogType] = React.useState<'stdout' | 'stderr' | 'combined'>('stdout');
  const { data: logs, isLoading, isError } = useJobLogs(jobId, logType, isFinished);

  return (
    <Stack gap="sm">
      <Group gap="xs">
        {(['stdout', 'stderr', 'combined'] as const).map((t) => (
          <Badge
            key={t}
            variant={logType === t ? 'filled' : 'outline'}
            color="gray"
            style={{ cursor: 'pointer' }}
            onClick={() => setLogType(t)}
          >
            {t}
          </Badge>
        ))}
      </Group>
      <ScrollArea h={320}>
        <Code block style={{ fontSize: 11, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: '#0a0b0d', color: '#a7f3d0' }}>
          {isLoading
            ? 'Loading...'
            : isError
            ? 'Logs not available yet.'
            : logs ?? '(empty)'}
        </Code>
      </ScrollArea>
    </Stack>
  );
}

import React from 'react';
