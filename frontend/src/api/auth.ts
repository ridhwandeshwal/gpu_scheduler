import { api } from './client';

export interface AuthResponse {
  user_id: string;
  username: string;
  email: string;
  role: string;
  session_token: string;
}

export const authApi = {
  login: (username: string, password: string) =>
    api.post<AuthResponse>('/auth/login', { username, password }),

  register: (username: string, email: string, password: string, full_name?: string) =>
    api.post<AuthResponse>('/auth/register', { username, email, password, full_name }),

  logout: () => api.post('/auth/logout'),
};
