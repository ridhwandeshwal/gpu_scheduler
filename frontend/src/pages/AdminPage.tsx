import React from 'react';
import {
  Stack, Title, Text, Table, Paper, Select, ActionIcon,
  Tooltip, Skeleton, Group, Slider, Badge, Tabs,
} from '@mantine/core';
import { Trash2, XCircle } from 'lucide-react';
import { modals } from '@mantine/modals';
import {
  useAdminUsers, useAdminJobs, useUpdateUser, useDeleteUser, useUpdateAdminJob,
} from '../hooks/useAdmin';
import { useCancelJob } from '../hooks/useJobs';
import { StatusBadge } from '../components/StatusBadge';
import { fmtDate, shortId } from '../lib/format';
import type { StoredUser } from '../lib/auth';

interface Props {
  currentUser: StoredUser | null;
}

const ACTIVE = new Set(['queued', 'scheduled', 'running']);

export function AdminPage({ currentUser }: Props) {
  const { data: users = [], isLoading: usersLoading } = useAdminUsers();
  const { data: jobs = [], isLoading: jobsLoading } = useAdminJobs();
  const updateUser = useUpdateUser();
  const deleteUser = useDeleteUser();
  const updateJob = useUpdateAdminJob();
  const cancelJob = useCancelJob();

  function confirmDeleteUser(id: string, username: string) {
    modals.openConfirmModal({
      title: 'Delete user',
      children: <Text size="sm">Permanently delete <strong>{username}</strong>? This cannot be undone.</Text>,
      labels: { confirm: 'Delete', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteUser.mutate(id),
    });
  }

  return (
    <Stack gap="lg">
      <div>
        <Title order={3}>Admin Panel</Title>
        <Text size="sm" c="dimmed" mt={2}>Cluster-wide job control and user management.</Text>
      </div>

      <Tabs defaultValue="jobs">
        <Tabs.List mb="md">
          <Tabs.Tab value="jobs">
            Cluster Queue{' '}
            <Badge size="xs" variant="light" ml={4}>{jobs.length}</Badge>
          </Tabs.Tab>
          <Tabs.Tab value="users">
            Users{' '}
            <Badge size="xs" variant="light" ml={4}>{users.length}</Badge>
          </Tabs.Tab>
        </Tabs.List>

        {/* ── Jobs tab ── */}
        <Tabs.Panel value="jobs">
          <Paper radius="md" withBorder style={{ overflow: 'hidden' }}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Job</Table.Th>
                  <Table.Th>Owner</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Priority</Table.Th>
                  <Table.Th>Override Status</Table.Th>
                  <Table.Th>Submitted</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {jobsLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <Table.Tr key={i}>
                      {Array.from({ length: 7 }).map((_, j) => (
                        <Table.Td key={j}><Skeleton h={16} radius="sm" /></Table.Td>
                      ))}
                    </Table.Tr>
                  ))
                ) : jobs.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={7}>
                      <Text ta="center" c="dimmed" py="xl" size="sm">No jobs in the cluster.</Text>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  jobs.map((job) => (
                    <Table.Tr key={job.id}>
                      <Table.Td>
                        <Text size="sm" fw={600}>{job.title ?? `Job ${shortId(job.id)}`}</Text>
                        <Text size="xs" c="dimmed" ff="monospace">{shortId(job.id)}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed" ff="monospace">{shortId(job.user_id)}</Text>
                      </Table.Td>
                      <Table.Td><StatusBadge status={job.status} /></Table.Td>
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap" style={{ minWidth: 140 }}>
                          <Slider
                            style={{ flex: 1 }}
                            min={1} max={10} step={1}
                            value={job.priority}
                            onChange={(v) => updateJob.mutate({ id: job.id, updates: { priority: v } })}
                            size="xs"
                            color="violet"
                          />
                          <Text size="xs" ff="monospace" c="violet" w={16}>{job.priority}</Text>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Select
                          size="xs"
                          value={job.status}
                          onChange={(v) => v && updateJob.mutate({ id: job.id, updates: { status: v } })}
                          data={['queued', 'scheduled', 'running', 'completed', 'failed', 'cancelled']}
                          styles={{ input: { minWidth: 120 } }}
                        />
                      </Table.Td>
                      <Table.Td><Text size="sm">{fmtDate(job.submitted_at)}</Text></Table.Td>
                      <Table.Td>
                        {ACTIVE.has(job.status) && (
                          <Tooltip label="Terminate">
                            <ActionIcon
                              color="red" variant="subtle" size="sm"
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
        </Tabs.Panel>

        {/* ── Users tab ── */}
        <Tabs.Panel value="users">
          <Paper radius="md" withBorder style={{ overflow: 'hidden' }}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>User</Table.Th>
                  <Table.Th>Email</Table.Th>
                  <Table.Th>Role</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Joined</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {usersLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <Table.Tr key={i}>
                      {Array.from({ length: 6 }).map((_, j) => (
                        <Table.Td key={j}><Skeleton h={16} radius="sm" /></Table.Td>
                      ))}
                    </Table.Tr>
                  ))
                ) : (
                  users.map((u) => {
                    const isSelf = u.id === currentUser?.id;
                    return (
                      <Table.Tr key={u.id}>
                        <Table.Td>
                          <Text size="sm" fw={600}>{u.username}</Text>
                          {isSelf && <Badge size="xs" variant="outline" ml={4}>you</Badge>}
                        </Table.Td>
                        <Table.Td><Text size="sm">{u.email}</Text></Table.Td>
                        <Table.Td>
                          <Select
                            size="xs"
                            value={u.role}
                            disabled={isSelf}
                            onChange={(v) => v && updateUser.mutate({ id: u.id, updates: { role: v } })}
                            data={['user', 'admin']}
                            styles={{ input: { minWidth: 90 } }}
                          />
                        </Table.Td>
                        <Table.Td>
                          <Select
                            size="xs"
                            value={u.status}
                            disabled={isSelf}
                            onChange={(v) => v && updateUser.mutate({ id: u.id, updates: { status: v } })}
                            data={['active', 'suspended']}
                            styles={{ input: { minWidth: 110 } }}
                          />
                        </Table.Td>
                        <Table.Td><Text size="sm">{fmtDate(u.created_at)}</Text></Table.Td>
                        <Table.Td>
                          <Tooltip label="Delete user">
                            <ActionIcon
                              color="red" variant="subtle" size="sm"
                              disabled={isSelf}
                              onClick={() => confirmDeleteUser(u.id, u.username)}
                            >
                              <Trash2 size={14} />
                            </ActionIcon>
                          </Tooltip>
                        </Table.Td>
                      </Table.Tr>
                    );
                  })
                )}
              </Table.Tbody>
            </Table>
          </Paper>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
