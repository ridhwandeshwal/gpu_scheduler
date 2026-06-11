import { Badge } from '@mantine/core';
import type { Job } from '../api/jobs';

const STATUS_CONFIG: Record<Job['status'], { color: string; label: string }> = {
  queued:    { color: 'yellow', label: 'Queued' },
  scheduled: { color: 'orange', label: 'Scheduled' },
  running:   { color: 'blue',   label: 'Running' },
  completed: { color: 'teal',   label: 'Completed' },
  failed:    { color: 'red',    label: 'Failed' },
  cancelled: { color: 'gray',   label: 'Cancelled' },
};

export function StatusBadge({ status }: { status: Job['status'] }) {
  const cfg = STATUS_CONFIG[status] ?? { color: 'gray', label: status };
  return (
    <Badge color={cfg.color} variant="light" size="sm" radius="sm">
      {cfg.label}
    </Badge>
  );
}
