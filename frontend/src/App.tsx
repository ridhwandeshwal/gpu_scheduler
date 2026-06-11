import { useState } from 'react';
import {
  AppShell, NavLink, Group, Text, Avatar,
  ActionIcon, Divider, useMantineColorScheme, Tooltip,
} from '@mantine/core';
import { Terminal, ShieldAlert, LogOut, Sun, Moon, FolderOpen } from 'lucide-react';
import { LoginPage } from './pages/LoginPage';
import { JobsPage } from './pages/JobsPage';
import { AdminPage } from './pages/AdminPage';
import { ArtifactsPage } from './pages/ArtifactsPage';
import { SidebarLogo } from './components/SidebarLogo';
import { authApi } from './api/auth';
import { getStoredUser, clearSession } from './lib/auth';
import type { StoredUser } from './lib/auth';

type Page = 'jobs' | 'artifacts' | 'admin';

export default function App() {
  const [user, setUser] = useState<StoredUser | null>(() => getStoredUser());
  const [page, setPage] = useState<Page>('jobs');
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();

  async function handleLogout() {
    try { await authApi.logout(); } catch { /* best-effort */ }
    clearSession();
    setUser(null);
  }

  if (!user) {
    return <LoginPage onAuth={(u) => setUser(u)} />;
  }

  return (
    <AppShell
      navbar={{ width: 220, breakpoint: 'sm' }}
      padding="lg"
    >
      <AppShell.Navbar p="md">
        <AppShell.Section>
          <SidebarLogo />
        </AppShell.Section>

        <AppShell.Section grow>
          <NavLink
            label="My Jobs"
            leftSection={<Terminal size={16} />}
            active={page === 'jobs'}
            onClick={() => setPage('jobs')}
            mb={4}
          />
          <NavLink
            label="Artifacts"
            leftSection={<FolderOpen size={16} />}
            active={page === 'artifacts'}
            onClick={() => setPage('artifacts')}
            mb={4}
          />
          {user.role === 'admin' && (
            <NavLink
              label="Admin"
              leftSection={<ShieldAlert size={16} />}
              active={page === 'admin'}
              onClick={() => setPage('admin')}
            />
          )}
        </AppShell.Section>

        <AppShell.Section>
          <Divider mb="sm" />
          <Group justify="space-between" px={4}>
            <Group gap="xs">
              <Avatar size="sm" color="cyan" radius="xl">
                {user.username[0].toUpperCase()}
              </Avatar>
              <div>
                <Text size="xs" fw={600} lineClamp={1}>{user.username}</Text>
                <Text size="xs" c={user.role === 'admin' ? 'violet' : 'dimmed'} tt="uppercase" fw={700} style={{ letterSpacing: '0.05em', fontSize: 10 }}>
                  {user.role}
                </Text>
              </div>
            </Group>
            <Group gap={4}>
              <Tooltip label={colorScheme === 'dark' ? 'Light mode' : 'Dark mode'}>
                <ActionIcon variant="subtle" size="sm" onClick={toggleColorScheme}>
                  {colorScheme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
                </ActionIcon>
              </Tooltip>
              <Tooltip label="Sign out">
                <ActionIcon variant="subtle" size="sm" color="red" onClick={handleLogout}>
                  <LogOut size={14} />
                </ActionIcon>
              </Tooltip>
            </Group>
          </Group>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        {page === 'jobs' && <JobsPage currentUser={user} />}
        {page === 'artifacts' && <ArtifactsPage />}
        {page === 'admin' && user.role === 'admin' && <AdminPage currentUser={user} />}
      </AppShell.Main>
    </AppShell>
  );
}
