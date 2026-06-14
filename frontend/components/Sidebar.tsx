'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { Session } from '@/lib/types';

interface Props {
  sessions: Session[];
  currentId?: string;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onNewChat: () => void;
}

function groupByDate(sessions: Session[]): Record<string, Session[]> {
  const groups: Record<string, Session[]> = {};
  for (const s of sessions) {
    const d = s.updated_at?.slice(0, 10) ?? s.created_at?.slice(0, 10) ?? 'unknown';
    const today = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const key = d === today ? '今天' : d === yesterday ? '昨天' : d;
    (groups[key] ??= []).push(s);
  }
  return groups;
}

export function Sidebar({ sessions, currentId, onRename, onDelete, onNewChat }: Props) {
  const router = useRouter();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [search, setSearch] = useState('');
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setUsername(data.username))
      .catch(() => {});
  }, []);

  const filtered = sessions.filter(s =>
    !search || (s.title ?? '').toLowerCase().includes(search.toLowerCase())
  );
  const groups = groupByDate(filtered);

  const handleRenameSubmit = (id: string) => {
    if (editValue.trim()) onRename(id, editValue.trim());
    setEditingId(null);
  };

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    if (confirm('删除此会话？')) {
      onDelete(id);
      if (id === currentId) router.push('/chat/new');
    }
  };

  return (
    <aside className="w-[260px] bg-bg-secondary border-r border-border-primary flex flex-col h-full shrink-0">
      {/* Header */}
      <div className="p-4 border-b border-border-primary flex items-center justify-between gap-2">
        <div className="text-xs text-text-accent font-mono tracking-widest">
          INVESTMENT AGENT
        </div>
        <button
          onClick={onNewChat}
          className="px-3 py-1.5 text-xs bg-accent-blue text-white rounded font-medium
                     hover:opacity-90 transition-opacity shrink-0"
        >
          + 新对话
        </button>
      </div>

      {/* Search */}
      <div className="px-4 py-2">
        <input
          type="text"
          placeholder="搜索会话..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full bg-bg-tertiary border border-border-primary rounded px-3 py-1.5
                     text-xs text-text-primary placeholder-text-muted focus:outline-none
                     focus:border-text-accent"
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {Object.entries(groups).map(([date, group]) => (
          <div key={date} className="mb-3">
            <div className="text-xs text-text-muted px-2 py-1 uppercase tracking-wider">
              {date}
            </div>
            {group.map(s => (
              <div key={s.id} className="group relative">
                {editingId === s.id ? (
                  <input
                    autoFocus
                    value={editValue}
                    onChange={e => setEditValue(e.target.value)}
                    onBlur={() => handleRenameSubmit(s.id)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleRenameSubmit(s.id);
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    className="w-full bg-bg-elevated border border-text-accent rounded px-2 py-1
                               text-xs text-text-primary focus:outline-none"
                  />
                ) : (
                  <Link
                    href={`/chat/${s.id}`}
                    className={`block px-2 py-1.5 rounded text-xs truncate transition-colors ${
                      s.id === currentId
                        ? 'bg-bg-tertiary border-l-2 border-text-accent text-text-primary pl-[6px]'
                        : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
                    }`}
                  >
                    {s.title ?? '新对话'}
                  </Link>
                )}
                {editingId !== s.id && (
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-1">
                    <button
                      onClick={() => { setEditingId(s.id); setEditValue(s.title ?? ''); }}
                      className="text-text-muted hover:text-text-primary p-0.5 text-xs"
                      title="重命名"
                    >
                      ✏
                    </button>
                    <button
                      onClick={e => handleDelete(e, s.id)}
                      className="text-text-muted hover:text-accent-red p-0.5 text-xs"
                      title="删除"
                    >
                      ✕
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="text-text-muted text-xs text-center py-8">
            {search ? '无匹配会话' : '暂无会话记录'}
          </div>
        )}
      </div>

      {/* Bottom links */}
      <div className="border-t border-border-primary p-2 space-y-1">
        <Link href="/memory/trades" className="block px-2 py-1.5 text-xs text-text-secondary hover:text-text-primary rounded hover:bg-bg-hover">
          📊 交易记录
        </Link>
        <Link href="/memory/events" className="block px-2 py-1.5 text-xs text-text-secondary hover:text-text-primary rounded hover:bg-bg-hover">
          📝 事件记录
        </Link>
      </div>

      {/* User avatar */}
      <Link
        href="/profile"
        className="flex items-center gap-2 px-3 py-3 border-t border-border-primary
                   hover:bg-bg-hover transition-colors"
      >
        <div className="w-7 h-7 rounded-full bg-bg-elevated border border-border-secondary
                        flex items-center justify-center shrink-0">
          <span className="text-text-muted text-xs">
            {username ? username[0].toUpperCase() : '?'}
          </span>
        </div>
        <span className="text-xs text-text-secondary truncate">
          {username ?? '加载中...'}
        </span>
      </Link>
    </aside>
  );
}
