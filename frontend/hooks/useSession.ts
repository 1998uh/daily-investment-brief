'use client';

import { useState, useCallback, useEffect } from 'react';
import { sessions as sessionsApi } from '@/lib/api';
import type { Session } from '@/lib/types';

export function useSession() {
  const [sessionList, setSessionList] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await sessionsApi.list();
      setSessionList(data);
    } catch {
      // ignore auth errors at this level
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const createSession = useCallback(async (title?: string) => {
    const s = await sessionsApi.create(title);
    setSessionList(prev => [s, ...prev]);
    return s;
  }, []);

  const renameSession = useCallback(async (id: string, title: string) => {
    await sessionsApi.rename(id, title);
    setSessionList(prev => prev.map(s => s.id === id ? { ...s, title } : s));
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    await sessionsApi.delete(id);
    setSessionList(prev => prev.filter(s => s.id !== id));
  }, []);

  return { sessionList, loading, refresh, createSession, renameSession, deleteSession };
}
