import React from 'react';
import {
  Drawer, Stack, Group, Text, Badge, Divider, Tabs,
  ScrollArea, Code, Button, SimpleGrid, Paper, Loader,
} from '@mantine/core';
import { XCircle } from 'lucide-react';
import { useJobEvents, useJobLogs, useCancelJob } from '../hooks/useJobs';
import { StatusBadge } from './StatusBadge';
import { fmtDate, shortId } from '../lib/format';
import type { Job } from '../api/jobs';

interface Props {
  job: Job | null;
  opened: boolean;
  onClose: () => void;
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

export function JobDetailDrawer({ job, opened, onClose }: Props) {
  const isFinished = job ? !ACTIVE.has(job.status) : true;
  const { data: events = [], isLoading: eventsLoading } = useJobEvents(job?.id ?? null);
  const cancelJob = useCancelJob();

  const [drawerWidth, setDrawerWidth] = React.useState(500);

  const handleMouseDown = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = drawerWidth;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const newWidth = startWidth + (startX - moveEvent.clientX);
      // Min 500px (current lg), Max 75vw
      const clamped = Math.max(500, Math.min(newWidth, window.innerWidth * 0.75));
      setDrawerWidth(clamped);
    };

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, [drawerWidth]);

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size={drawerWidth}
      title={
        <Group gap="sm" ml="sm">
          <Text fw={700} size="md">{job?.title ?? `Job ${shortId(job?.id ?? '')}`}</Text>
          {job && <StatusBadge status={job.status} />}
        </Group>
      }
      styles={{ body: { padding: 0 } }}
    >
      <div
        onMouseDown={handleMouseDown}
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 0,
          width: '6px',
          cursor: 'col-resize',
          zIndex: 1000,
          transition: 'background-color 0.15s ease',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--mantine-color-dark-4)')}
        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
      />
      {!job ? null : (
        <Stack gap={0} h="100%">
          <ScrollArea flex={1} p="md">
            <Stack gap="md">
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

              <Tabs defaultValue="events">
                <Tabs.List>
                  <Tabs.Tab value="events">Events</Tabs.Tab>
                  <Tabs.Tab value="logs">Logs</Tabs.Tab>
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
              </Tabs>
            </Stack>
          </ScrollArea>

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
