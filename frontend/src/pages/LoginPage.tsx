import React, { useState } from 'react';
import {
  Box, Paper, Stack, TextInput, PasswordInput, Button, Text,
  Title, Anchor, Alert,
} from '@mantine/core';
import { AlertCircle } from 'lucide-react';
import { authApi } from '../api/auth';
import { saveSession } from '../lib/auth';
import type { StoredUser } from '../lib/auth';

interface Props {
  onAuth: (user: StoredUser) => void;
}

export function LoginPage({ onAuth }: Props) {
  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Login fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  // Register fields
  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regFullName, setRegFullName] = useState('');
  const [regPassword, setRegPassword] = useState('');

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data } = await authApi.login(username, password);
      const user: StoredUser = { id: data.user_id, username: data.username, email: data.email, role: data.role };
      saveSession(data.session_token, user);
      onAuth(user);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Login failed.');
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data } = await authApi.register(regUsername, regEmail, regPassword, regFullName || undefined);
      const user: StoredUser = { id: data.user_id, username: data.username, email: data.email, role: data.role };
      saveSession(data.session_token, user);
      onAuth(user);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Registration failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--mantine-color-dark-8)',
      }}
    >
      <Paper w={420} p="xl" radius="md" withBorder>
        <Stack gap="xs" mb="lg">
          <Title order={3}>GPU Job Scheduler</Title>
          <Text size="sm" c="dimmed">
            {tab === 'login' ? 'Sign in to manage cluster runs.' : 'Create an account to get started.'}
          </Text>
        </Stack>

        {error && (
          <Alert icon={<AlertCircle size={16} />} color="red" mb="md" radius="sm">
            {error}
          </Alert>
        )}

        {tab === 'login' ? (
          <form onSubmit={handleLogin}>
            <Stack gap="sm">
              <TextInput label="Username" value={username} onChange={(e) => setUsername(e.currentTarget.value)} required />
              <PasswordInput label="Password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} required />
              <Button type="submit" loading={loading} fullWidth mt="xs">Sign In</Button>
            </Stack>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <Stack gap="sm">
              <TextInput label="Username" value={regUsername} onChange={(e) => setRegUsername(e.currentTarget.value)} required minLength={3} />
              <TextInput label="Email" type="email" value={regEmail} onChange={(e) => setRegEmail(e.currentTarget.value)} required />
              <TextInput label="Full Name (optional)" value={regFullName} onChange={(e) => setRegFullName(e.currentTarget.value)} />
              <PasswordInput label="Password" value={regPassword} onChange={(e) => setRegPassword(e.currentTarget.value)} required minLength={8} />
              <Button type="submit" loading={loading} fullWidth mt="xs">Create Account</Button>
            </Stack>
          </form>
        )}

        <Text ta="center" size="sm" mt="md" c="dimmed">
          {tab === 'login' ? (
            <>No account?{' '}<Anchor onClick={() => { setTab('register'); setError(null); }}>Register here</Anchor></>
          ) : (
            <>Already registered?{' '}<Anchor onClick={() => { setTab('login'); setError(null); }}>Sign in</Anchor></>
          )}
        </Text>
      </Paper>
    </Box>
  );
}
