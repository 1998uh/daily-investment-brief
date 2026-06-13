'use client';

import { useState, useCallback, useEffect } from 'react';
import { memory as memoryApi } from '@/lib/api';
import type { WatchItem, Trade, Event } from '@/lib/types';

export function useMemory() {
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [events, setEvents] = useState<Event[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [w, t, e] = await Promise.all([
        memoryApi.getWatchlist(),
        memoryApi.getTrades(),
        memoryApi.getEvents(),
      ]);
      setWatchlist(w);
      setTrades(t);
      setEvents(e);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const addWatch = useCallback(async (symbol: string, note?: string) => {
    await memoryApi.addWatch(symbol, note);
    await refresh();
  }, [refresh]);

  const removeWatch = useCallback(async (symbol: string) => {
    await memoryApi.removeWatch(symbol);
    setWatchlist(prev => prev.filter(w => w.symbol !== symbol));
  }, []);

  const addTrade = useCallback(async (data: Omit<Trade, 'id' | 'created_at'>) => {
    const t = await memoryApi.addTrade(data);
    setTrades(prev => [t, ...prev]);
  }, []);

  const deleteTrade = useCallback(async (id: number) => {
    await memoryApi.deleteTrade(id);
    setTrades(prev => prev.filter(t => t.id !== id));
  }, []);

  const addEvent = useCallback(async (data: Omit<Event, 'id' | 'created_at'>) => {
    const e = await memoryApi.addEvent(data);
    setEvents(prev => [e, ...prev]);
  }, []);

  const deleteEvent = useCallback(async (id: number) => {
    await memoryApi.deleteEvent(id);
    setEvents(prev => prev.filter(e => e.id !== id));
  }, []);

  return {
    watchlist, trades, events,
    addWatch, removeWatch,
    addTrade, deleteTrade,
    addEvent, deleteEvent,
    refresh,
  };
}
