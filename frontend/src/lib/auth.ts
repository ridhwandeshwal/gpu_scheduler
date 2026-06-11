export interface StoredUser {
  id: string;
  username: string;
  email: string;
  role: string;
}

export function getStoredUser(): StoredUser | null {
  try {
    const raw = localStorage.getItem('user_info');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveSession(token: string, user: StoredUser) {
  localStorage.setItem('session_token', token);
  localStorage.setItem('user_info', JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem('session_token');
  localStorage.removeItem('user_info');
}
