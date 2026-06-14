import type { Session, Message, WatchItem, Trade, Event } from './types';

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// User
export const user = {
  me: () => request<{ id: string; username: string; email: string | null; created_at: string }>('/api/auth/me'),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
};

// Auth
export const auth = {
  register: (username: string, password: string, email?: string) =>
    request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, email }),
    }),
  login: (username: string, password: string) =>
    request<{ access_token: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  refresh: () => request('/api/auth/refresh', { method: 'POST' }),
};

// Sessions
export const sessions = {
  list: () => request<Session[]>('/api/sessions'),
  create: (title?: string) =>
    request<Session>('/api/sessions', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  rename: (id: string, title: string) =>
    request(`/api/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  delete: (id: string) =>
    request(`/api/sessions/${id}`, { method: 'DELETE' }),
  getMessages: (id: string) =>
    request<Message[]>(`/api/sessions/${id}/messages`),
};

// Memory
export const memory = {
  getWatchlist: () => request<WatchItem[]>('/api/memory/watchlist'),
  addWatch: (symbol: string, note?: string) =>
    request('/api/memory/watchlist', {
      method: 'POST',
      body: JSON.stringify({ symbol, note }),
    }),
  removeWatch: (symbol: string) =>
    request(`/api/memory/watchlist/${symbol}`, { method: 'DELETE' }),

  getTrades: (params?: { symbol?: string; from_date?: string; to_date?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Trade[]>(`/api/memory/trades${qs ? '?' + qs : ''}`);
  },
  addTrade: (data: Omit<Trade, 'id' | 'created_at'>) =>
    request<Trade>('/api/memory/trades', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteTrade: (id: number) =>
    request(`/api/memory/trades/${id}`, { method: 'DELETE' }),

  getEvents: (params?: { from_date?: string; to_date?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Event[]>(`/api/memory/events${qs ? '?' + qs : ''}`);
  },
  addEvent: (data: Omit<Event, 'id' | 'created_at'>) =>
    request<Event>('/api/memory/events', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteEvent: (id: number) =>
    request(`/api/memory/events/${id}`, { method: 'DELETE' }),
};
