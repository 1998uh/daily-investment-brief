'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useMemory } from '@/hooks/useMemory';

export default function EventsPage() {
  const { events, addEvent, deleteEvent } = useMemory();
  const [form, setForm] = useState({ title: '', content: '', date: '', tags: '' });
  const [showForm, setShowForm] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await addEvent({
      title: form.title,
      content: form.content || undefined,
      event_date: form.date || undefined,
      tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
    });
    setForm({ title: '', content: '', date: '', tags: '' });
    setShowForm(false);
  };

  return (
    <div className="min-h-screen bg-bg-primary p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/chat/new" className="text-text-muted hover:text-text-primary text-sm">← 返回</Link>
          <h1 className="text-lg font-bold text-text-primary">事件记录</h1>
          <button
            onClick={() => setShowForm(s => !s)}
            className="ml-auto px-3 py-1.5 bg-accent-orange text-black text-sm rounded hover:bg-yellow-400"
          >
            + 新增
          </button>
        </div>

        {showForm && (
          <form onSubmit={handleSubmit} className="mb-6 p-4 bg-bg-secondary border border-border-primary rounded-lg grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text-muted mb-1">标题</label>
              <input
                type="text"
                required
                value={form.title}
                onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
                className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent-orange"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">日期</label>
              <input
                type="date"
                value={form.date}
                onChange={e => setForm(p => ({ ...p, date: e.target.value }))}
                className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent-orange"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-text-muted mb-1">内容</label>
              <textarea
                rows={3}
                value={form.content}
                onChange={e => setForm(p => ({ ...p, content: e.target.value }))}
                className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent-orange resize-none"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-text-muted mb-1">标签（逗号分隔）</label>
              <input
                type="text"
                value={form.tags}
                onChange={e => setForm(p => ({ ...p, tags: e.target.value }))}
                placeholder="macro, earnings, policy"
                className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent-orange"
              />
            </div>
            <div className="col-span-2 flex gap-2 justify-end">
              <button type="button" onClick={() => setShowForm(false)} className="px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary">取消</button>
              <button type="submit" className="px-4 py-1.5 bg-accent-orange text-black text-sm rounded hover:bg-yellow-400">保存</button>
            </div>
          </form>
        )}

        <div className="space-y-3">
          {events.map(ev => (
            <div key={ev.id} className="bg-bg-secondary border border-border-primary rounded-lg p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-text-primary font-medium text-sm">{ev.title}</span>
                    {ev.event_date && (
                      <span className="text-text-muted text-xs">{ev.event_date}</span>
                    )}
                  </div>
                  {ev.content && (
                    <p className="text-text-secondary text-xs mt-1 line-clamp-2">{ev.content}</p>
                  )}
                  {ev.tags && ev.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {ev.tags.map(tag => (
                        <span key={tag} className="text-xs bg-bg-tertiary border border-border-primary rounded px-1.5 py-0.5 text-text-muted">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => deleteEvent(ev.id)}
                  className="text-text-muted hover:text-accent-red text-xs shrink-0"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
          {events.length === 0 && (
            <div className="text-center text-text-muted text-sm py-12">暂无事件记录</div>
          )}
        </div>
      </div>
    </div>
  );
}
