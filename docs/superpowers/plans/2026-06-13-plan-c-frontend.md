# Plan C: Next.js 14 前端

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建完整的 Next.js 14 App Router 前端，实现 Bloomberg 暗色风格的投资智能对话界面，包括三列布局、SSE 流式推理链展示、会话管理、记忆面板。

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind CSS v3, react-markdown@9, remark-gfm, eventsource-parser, shadcn/ui（仅颜色变量/不引入全套组件）

**Auth Flow:** 登录后 JWT 存 httpOnly cookie（后端设置）；前端通过 `/api/auth/me` 验证登录状态；未登录跳转 `/login`。

---

## 文件地图

```
frontend/
├── app/
│   ├── layout.tsx              全局布局 + Provider
│   ├── page.tsx                重定向到 /chat/new
│   ├── login/page.tsx          登录/注册页
│   ├── chat/
│   │   ├── layout.tsx          三列布局骨架
│   │   ├── new/page.tsx        新会话
│   │   └── [sessionId]/page.tsx 具体会话
│   └── memory/
│       ├── trades/page.tsx     交易记录
│       └── events/page.tsx     事件记录
├── components/
│   ├── Sidebar.tsx             左侧会话列表
│   ├── ThinkingBubble.tsx      推理链折叠展示
│   ├── ChatWindow.tsx          对话主区
│   ├── MessageBubble.tsx       单条消息（含 markdown）
│   ├── SourceCards.tsx         来源文章卡片
│   ├── WatchlistPanel.tsx      右侧关注标的
│   ├── TradePanel.tsx          右侧最近交易
│   ├── ChatInput.tsx           输入框组件
│   └── ConfirmDialog.tsx       操作确认弹窗
├── lib/
│   ├── api.ts                  fetch 封装
│   ├── types.ts                TypeScript 类型
│   └── sse.ts                  SSE 流式解析
├── hooks/
│   ├── useChat.ts              对话状态管理
│   ├── useSession.ts           会话列表管理
│   └── useMemory.ts            watchlist/trades/events
├── next.config.js
├── tailwind.config.js
├── tsconfig.json
└── package.json
```

---

## Task 1: 初始化 Next.js 14 项目

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/tsconfig.json`
- Create: `frontend/postcss.config.js`
- Create: `frontend/app/globals.css`

- [ ] **Step 1: 初始化项目**

```bash
cd D:/ai-project/daily-investment-brief
npx create-next-app@14 frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

如果 create-next-app 交互，选择：
- TypeScript: Yes
- ESLint: Yes
- Tailwind CSS: Yes
- src/ directory: No
- App Router: Yes
- import alias: @/*

- [ ] **Step 2: 安装额外依赖**

```bash
cd frontend
npm install react-markdown@9 remark-gfm eventsource-parser
npm install -D @types/node
```

- [ ] **Step 3: 配置 Tailwind Bloomberg 暗色主题 `tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    './hooks/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0a',
          secondary: '#111111',
          tertiary: '#1a1a1a',
          elevated: '#222222',
          hover: '#2a2a2a',
        },
        border: {
          primary: '#2a2a2a',
          secondary: '#333333',
        },
        text: {
          primary: '#e8e8e8',
          secondary: '#999999',
          muted: '#666666',
          accent: '#f0a500',
        },
        accent: {
          orange: '#f0a500',
          green: '#22c55e',
          red: '#ef4444',
          blue: '#3b82f6',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 4: 配置 globals.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
}

body {
  background-color: #0a0a0a;
  color: #e8e8e8;
  font-family: system-ui, -apple-system, sans-serif;
}

/* 滚动条样式 */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #111111; }
::-webkit-scrollbar-thumb { background: #333333; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #444444; }

/* markdown 代码块 */
.prose pre { background: #1a1a1a !important; border: 1px solid #2a2a2a; }
.prose code { color: #f0a500; font-size: 0.875em; }
.prose a { color: #3b82f6; }
.prose table { border-collapse: collapse; }
.prose th, .prose td { border: 1px solid #2a2a2a; padding: 0.5rem 0.75rem; }
.prose th { background: #1a1a1a; }
```

- [ ] **Step 5: 配置 `next.config.js`**

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8080/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
```

> 注：开发时代理到后端 8080，生产用 Docker 网络。

- [ ] **Step 6: 验证启动**

```bash
cd frontend && npm run dev
```

Expected: `http://localhost:3000` 可访问（Next.js 初始页面）。

---

## Task 2: 类型定义 + API 客户端

**Files:**
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/sse.ts`

- [ ] **Step 1: 创建 `frontend/lib/types.ts`**

```typescript
export interface User {
  id: string;
  username: string;
  email?: string;
}

export interface Session {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  agent?: string;
  sources?: Source[];
  thinking_steps?: ThinkingStep[];
  created_at: string;
}

export interface Source {
  title: string;
  author: string;
  date: string;
  url?: string;
  source?: string;
}

export interface ThinkingStep {
  agent: string;
  text: string;
}

export interface SSEEvent {
  type: 'thinking' | 'token' | 'done' | 'session_id' | 'error';
  agent?: string;
  text?: string;
  sources?: Source[];
  session_id?: string;
  message?: string;
}

export interface WatchItem {
  symbol: string;
  note?: string;
  added_at: string;
}

export interface Trade {
  id: number;
  symbol: string;
  action: string;
  price?: number;
  quantity?: number;
  trade_date?: string;
  note?: string;
  created_at: string;
}

export interface Event {
  id: number;
  title: string;
  content?: string;
  event_date?: string;
  tags?: string[];
  created_at: string;
}

export interface ChatState {
  sessionId: string | null;
  messages: Message[];
  isStreaming: boolean;
  thinkingSteps: ThinkingStep[];
  currentTokens: string;
  error: string | null;
}
```

- [ ] **Step 2: 创建 `frontend/lib/api.ts`**

```typescript
const BASE = '';  // next.config.js rewrites /api/* → backend

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
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

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
import type { Session, Message } from './types';

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
import type { WatchItem, Trade, Event } from './types';

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
```

- [ ] **Step 3: 创建 `frontend/lib/sse.ts`**

```typescript
import type { SSEEvent } from './types';

export async function* streamChat(
  message: string,
  sessionId?: string | null,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6)) as SSEEvent;
        } catch {
          // skip malformed lines
        }
      }
    }
  }
}
```

---

## Task 3: 核心 Hooks

**Files:**
- Create: `frontend/hooks/useSession.ts`
- Create: `frontend/hooks/useChat.ts`
- Create: `frontend/hooks/useMemory.ts`

- [ ] **Step 1: 创建 `frontend/hooks/useSession.ts`**

```typescript
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
```

- [ ] **Step 2: 创建 `frontend/hooks/useChat.ts`**

```typescript
'use client';

import { useState, useCallback, useRef } from 'react';
import { sessions as sessionsApi } from '@/lib/api';
import { streamChat } from '@/lib/sse';
import type { Message, ThinkingStep, Source, ChatState } from '@/lib/types';

const INITIAL_STATE: ChatState = {
  sessionId: null,
  messages: [],
  isStreaming: false,
  thinkingSteps: [],
  currentTokens: '',
  error: null,
};

export function useChat(onNewSession?: (sessionId: string) => void) {
  const [state, setState] = useState<ChatState>(INITIAL_STATE);
  const abortRef = useRef<AbortController | null>(null);

  const loadSession = useCallback(async (sessionId: string) => {
    const messages = await sessionsApi.getMessages(sessionId);
    setState(prev => ({
      ...prev,
      sessionId,
      messages,
      thinkingSteps: [],
      currentTokens: '',
      error: null,
    }));
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (state.isStreaming) return;

    abortRef.current = new AbortController();

    // Optimistically add user message
    const userMsg: Message = {
      id: Date.now(),
      session_id: state.sessionId ?? '',
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    setState(prev => ({
      ...prev,
      messages: [...prev.messages, userMsg],
      isStreaming: true,
      thinkingSteps: [],
      currentTokens: '',
      error: null,
    }));

    try {
      let sessionId = state.sessionId;
      let tokens = '';
      const thinking: ThinkingStep[] = [];
      let sources: Source[] = [];

      for await (const event of streamChat(content, sessionId, abortRef.current.signal)) {
        if (event.type === 'thinking') {
          thinking.push({ agent: event.agent ?? 'orchestrator', text: event.text ?? '' });
          setState(prev => ({ ...prev, thinkingSteps: [...thinking] }));
        } else if (event.type === 'token') {
          tokens += event.text ?? '';
          setState(prev => ({ ...prev, currentTokens: tokens }));
        } else if (event.type === 'done') {
          sources = event.sources ?? [];
        } else if (event.type === 'session_id') {
          sessionId = event.session_id ?? sessionId;
          if (sessionId && !state.sessionId) {
            onNewSession?.(sessionId);
          }
        }
      }

      const assistantMsg: Message = {
        id: Date.now() + 1,
        session_id: sessionId ?? '',
        role: 'assistant',
        content: tokens,
        agent: 'orchestrator',
        sources,
        thinking_steps: thinking,
        created_at: new Date().toISOString(),
      };

      setState(prev => ({
        ...prev,
        sessionId,
        messages: [...prev.messages, assistantMsg],
        isStreaming: false,
        currentTokens: '',
        thinkingSteps: [],
      }));
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setState(prev => ({
          ...prev,
          isStreaming: false,
          error: (err as Error).message,
        }));
      }
    }
  }, [state.sessionId, state.isStreaming, onNewSession]);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setState(prev => ({ ...prev, isStreaming: false }));
  }, []);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  return { state, loadSession, sendMessage, stopStreaming, reset };
}
```

- [ ] **Step 3: 创建 `frontend/hooks/useMemory.ts`**

```typescript
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
```

---

## Task 4: 登录页面

**Files:**
- Create: `frontend/app/login/page.tsx`

- [ ] **Step 1: 创建 `frontend/app/login/page.tsx`**

```tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { auth } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (mode === 'register') {
        await auth.register(username, password);
      }
      await auth.login(username, password);
      router.push('/chat/new');
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-text-accent font-mono tracking-wider">
            INVESTMENT AGENT
          </h1>
          <p className="text-text-muted text-sm mt-1">智能投资助手系统</p>
        </div>

        {/* Card */}
        <div className="bg-bg-secondary border border-border-primary rounded-lg p-8">
          {/* Mode Tabs */}
          <div className="flex mb-6 border border-border-primary rounded">
            {(['login', 'register'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  mode === m
                    ? 'bg-accent-orange text-black'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-text-muted mb-1 uppercase tracking-wider">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded px-3 py-2
                           text-text-primary focus:outline-none focus:border-accent-orange
                           text-sm"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1 uppercase tracking-wider">
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded px-3 py-2
                           text-text-primary focus:outline-none focus:border-accent-orange
                           text-sm"
                required
              />
            </div>

            {error && (
              <div className="text-accent-red text-xs p-2 bg-red-950/20 border border-red-900/30 rounded">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 bg-accent-orange text-black font-medium rounded
                         hover:bg-yellow-400 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors text-sm"
            >
              {loading ? '处理中...' : mode === 'login' ? '登录' : '注册并登录'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
```

---

## Task 5: 核心 UI 组件

**Files:**
- Create: `frontend/components/ThinkingBubble.tsx`
- Create: `frontend/components/MessageBubble.tsx`
- Create: `frontend/components/SourceCards.tsx`
- Create: `frontend/components/ChatInput.tsx`
- Create: `frontend/components/Sidebar.tsx`
- Create: `frontend/components/WatchlistPanel.tsx`

- [ ] **Step 1: 创建 `frontend/components/ThinkingBubble.tsx`**

```tsx
'use client';

import { useState } from 'react';
import type { ThinkingStep } from '@/lib/types';

const AGENT_COLORS: Record<string, string> = {
  orchestrator: 'text-accent-orange',
  research: 'text-accent-blue',
  memory: 'text-accent-green',
  action: 'text-yellow-400',
};

interface Props {
  steps: ThinkingStep[];
  isStreaming?: boolean;
}

export function ThinkingBubble({ steps, isStreaming }: Props) {
  const [expanded, setExpanded] = useState(true);

  if (steps.length === 0) return null;

  return (
    <div className="mb-3 border border-border-secondary rounded bg-bg-elevated">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-text-muted hover:text-text-secondary"
      >
        <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▶</span>
        <span>
          {isStreaming ? '🤔 Agent 推理中...' : `推理链 (${steps.length} 步)`}
        </span>
      </button>
      {expanded && (
        <div className="border-t border-border-primary px-3 py-2 space-y-1">
          {steps.map((step, i) => (
            <div key={i} className="flex gap-2 text-xs">
              <span className={`shrink-0 font-mono ${AGENT_COLORS[step.agent] ?? 'text-text-muted'}`}>
                [{step.agent}]
              </span>
              <span className="text-text-secondary">{step.text}</span>
            </div>
          ))}
          {isStreaming && (
            <div className="flex gap-2 text-xs">
              <span className="text-text-muted animate-pulse">▌</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 创建 `frontend/components/MessageBubble.tsx`**

```tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ThinkingBubble } from './ThinkingBubble';
import { SourceCards } from './SourceCards';
import type { Message } from '@/lib/types';

interface Props {
  message: Message;
  streamingTokens?: string;
  streamingThinking?: { agent: string; text: string }[];
  isCurrentStreaming?: boolean;
}

export function MessageBubble({ message, streamingTokens, streamingThinking, isCurrentStreaming }: Props) {
  const isUser = message.role === 'user';
  const content = isCurrentStreaming ? streamingTokens ?? '' : message.content;
  const thinking = isCurrentStreaming ? streamingThinking : message.thinking_steps;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[80%] ${isUser ? 'order-2' : 'order-1'}`}>
        {/* Agent thinking */}
        {!isUser && thinking && thinking.length > 0 && (
          <ThinkingBubble steps={thinking} isStreaming={isCurrentStreaming} />
        )}

        {/* Message content */}
        <div
          className={`rounded-lg px-4 py-3 ${
            isUser
              ? 'bg-bg-elevated border border-border-secondary text-text-primary'
              : 'bg-bg-secondary border border-border-primary text-text-primary'
          }`}
        >
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap">{content}</p>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content || (isCurrentStreaming ? '▌' : '')}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <SourceCards sources={message.sources} />
        )}

        {/* Timestamp */}
        <div className={`text-xs text-text-muted mt-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {new Date(message.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 创建 `frontend/components/SourceCards.tsx`**

```tsx
import type { Source } from '@/lib/types';

interface Props {
  sources: Source[];
}

export function SourceCards({ sources }: Props) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-2 space-y-1">
      <p className="text-xs text-text-muted uppercase tracking-wider">来源文章</p>
      <div className="flex flex-wrap gap-2">
        {sources.map((s, i) => (
          <div
            key={i}
            className="text-xs bg-bg-tertiary border border-border-primary rounded px-2 py-1 max-w-xs"
          >
            <div className="text-text-primary truncate">{s.title || '无标题'}</div>
            <div className="text-text-muted">
              {s.author && <span>{s.author}</span>}
              {s.date && <span className="ml-1 text-text-muted">· {s.date}</span>}
            </div>
            {s.url && (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent-blue hover:underline"
              >
                链接
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 创建 `frontend/components/ChatInput.tsx`**

```tsx
'use client';

import { useState, useRef, useCallback } from 'react';

interface Props {
  onSend: (message: string) => void;
  disabled?: boolean;
  onStop?: () => void;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, onStop, placeholder }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const msg = value.trim();
    if (!msg || disabled) return;
    onSend(msg);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, disabled, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
  };

  return (
    <div className="border-t border-border-primary bg-bg-secondary p-4">
      <div className="flex gap-3 items-end">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder ?? '输入消息... (Enter 发送，Shift+Enter 换行)'}
          rows={1}
          className="flex-1 bg-bg-tertiary border border-border-primary rounded-lg
                     px-4 py-3 text-text-primary text-sm resize-none
                     focus:outline-none focus:border-accent-orange
                     disabled:opacity-50 placeholder-text-muted
                     min-h-[48px] max-h-[200px]"
        />
        {disabled ? (
          <button
            onClick={onStop}
            className="px-4 py-3 bg-accent-red text-white rounded-lg text-sm hover:bg-red-600 transition-colors shrink-0"
          >
            停止
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!value.trim()}
            className="px-4 py-3 bg-accent-orange text-black rounded-lg text-sm
                       font-medium hover:bg-yellow-400 disabled:opacity-30
                       disabled:cursor-not-allowed transition-colors shrink-0"
          >
            发送
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: 创建 `frontend/components/Sidebar.tsx`**

```tsx
'use client';

import { useState } from 'react';
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
    <aside className="w-64 bg-bg-secondary border-r border-border-primary flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border-primary">
        <div className="text-xs text-text-accent font-mono tracking-widest mb-3">
          INVESTMENT AGENT
        </div>
        <button
          onClick={onNewChat}
          className="w-full py-2 text-sm bg-accent-orange text-black rounded font-medium
                     hover:bg-yellow-400 transition-colors"
        >
          + 新建对话
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
                     focus:border-accent-orange"
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
                    className="w-full bg-bg-elevated border border-accent-orange rounded px-2 py-1
                               text-xs text-text-primary focus:outline-none"
                  />
                ) : (
                  <Link
                    href={`/chat/${s.id}`}
                    className={`block px-2 py-1.5 rounded text-xs truncate transition-colors ${
                      s.id === currentId
                        ? 'bg-bg-elevated text-text-primary'
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
    </aside>
  );
}
```

- [ ] **Step 6: 创建 `frontend/components/WatchlistPanel.tsx`**

```tsx
'use client';

import { useState } from 'react';
import type { WatchItem, Trade } from '@/lib/types';

interface Props {
  watchlist: WatchItem[];
  trades: Trade[];
  onAddWatch: (symbol: string) => void;
  onRemoveWatch: (symbol: string) => void;
  onSymbolClick?: (symbol: string) => void;
}

export function WatchlistPanel({ watchlist, trades, onAddWatch, onRemoveWatch, onSymbolClick }: Props) {
  const [newSymbol, setNewSymbol] = useState('');
  const [collapsed, setCollapsed] = useState(false);

  const handleAdd = () => {
    const s = newSymbol.trim().toUpperCase();
    if (s) { onAddWatch(s); setNewSymbol(''); }
  };

  const recentTrades = trades.slice(0, 5);

  if (collapsed) {
    return (
      <div className="w-8 bg-bg-secondary border-l border-border-primary flex flex-col items-center py-4">
        <button onClick={() => setCollapsed(false)} className="text-text-muted hover:text-text-primary text-xs">
          ◀
        </button>
      </div>
    );
  }

  return (
    <aside className="w-72 bg-bg-secondary border-l border-border-primary flex flex-col h-full shrink-0">
      <div className="flex items-center justify-between p-3 border-b border-border-primary">
        <span className="text-xs text-text-accent font-mono tracking-wider uppercase">信息面板</span>
        <button onClick={() => setCollapsed(true)} className="text-text-muted hover:text-text-primary text-xs">
          ▶
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Watchlist */}
        <section>
          <div className="text-xs text-text-muted uppercase tracking-wider mb-2">关注标的</div>
          <div className="flex gap-1 mb-2">
            <input
              value={newSymbol}
              onChange={e => setNewSymbol(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
              placeholder="添加标的..."
              className="flex-1 bg-bg-tertiary border border-border-primary rounded px-2 py-1
                         text-xs text-text-primary focus:outline-none focus:border-accent-orange"
            />
            <button
              onClick={handleAdd}
              className="px-2 py-1 bg-accent-orange text-black text-xs rounded hover:bg-yellow-400"
            >
              +
            </button>
          </div>
          <div className="flex flex-wrap gap-1">
            {watchlist.map(w => (
              <div key={w.symbol} className="group flex items-center gap-1 bg-bg-elevated border border-border-primary rounded px-2 py-1">
                <button
                  onClick={() => onSymbolClick?.(w.symbol)}
                  className="text-xs text-text-primary font-mono hover:text-accent-orange"
                >
                  {w.symbol}
                </button>
                <button
                  onClick={() => onRemoveWatch(w.symbol)}
                  className="hidden group-hover:block text-text-muted hover:text-accent-red text-xs"
                >
                  ×
                </button>
              </div>
            ))}
            {watchlist.length === 0 && (
              <div className="text-text-muted text-xs">暂无关注</div>
            )}
          </div>
        </section>

        {/* Recent trades */}
        <section>
          <div className="text-xs text-text-muted uppercase tracking-wider mb-2">最近交易</div>
          {recentTrades.length === 0 ? (
            <div className="text-text-muted text-xs">暂无记录</div>
          ) : (
            <div className="space-y-1">
              {recentTrades.map(t => (
                <div key={t.id} className="flex items-center gap-2 text-xs bg-bg-tertiary rounded px-2 py-1.5">
                  <span className={t.action === 'buy' || t.action === '买入' ? 'text-accent-green' : 'text-accent-red'}>
                    {t.action === 'buy' ? '买↑' : t.action === 'sell' ? '卖↓' : t.action}
                  </span>
                  <span className="text-text-primary font-mono">{t.symbol}</span>
                  {t.quantity && <span className="text-text-secondary">{t.quantity}股</span>}
                  {t.price && <span className="text-text-muted">@{t.price}</span>}
                  {t.trade_date && (
                    <span className="text-text-muted ml-auto">{t.trade_date.slice(5)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}
```

---

## Task 6: 对话页面 + 布局

**Files:**
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/chat/layout.tsx`
- Create: `frontend/app/chat/new/page.tsx`
- Create: `frontend/app/chat/[sessionId]/page.tsx`

- [ ] **Step 1: 创建根布局 `frontend/app/layout.tsx`**

```tsx
import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Investment Agent',
  description: '智能投资助手',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="bg-bg-primary text-text-primary antialiased">{children}</body>
    </html>
  );
}
```

- [ ] **Step 2: 根页面重定向 `frontend/app/page.tsx`**

```tsx
import { redirect } from 'next/navigation';

export default function HomePage() {
  redirect('/chat/new');
}
```

- [ ] **Step 3: 对话布局 `frontend/app/chat/layout.tsx`**

```tsx
'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useCallback } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { WatchlistPanel } from '@/components/WatchlistPanel';
import { useSession } from '@/hooks/useSession';
import { useMemory } from '@/hooks/useMemory';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const currentId = pathname?.split('/chat/')[1];

  const { sessionList, createSession, renameSession, deleteSession } = useSession();
  const { watchlist, trades, addWatch, removeWatch } = useMemory();

  const handleNewChat = useCallback(async () => {
    router.push('/chat/new');
  }, [router]);

  const handleSymbolClick = useCallback((symbol: string) => {
    // 将 symbol 注入到当前输入框（通过 URL 查询参数）
    router.push(`/chat/new?q=${encodeURIComponent(`${symbol} 最近怎么看？`)}`);
  }, [router]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        sessions={sessionList}
        currentId={currentId}
        onRename={renameSession}
        onDelete={deleteSession}
        onNewChat={handleNewChat}
      />
      <main className="flex-1 flex flex-col overflow-hidden">
        {children}
      </main>
      <WatchlistPanel
        watchlist={watchlist}
        trades={trades}
        onAddWatch={addWatch}
        onRemoveWatch={removeWatch}
        onSymbolClick={handleSymbolClick}
      />
    </div>
  );
}
```

- [ ] **Step 4: 新会话页 `frontend/app/chat/new/page.tsx`**

```tsx
'use client';

import { useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChatInput } from '@/components/ChatInput';
import { useChat } from '@/hooks/useChat';

export default function NewChatPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';

  const handleNewSession = useCallback((sessionId: string) => {
    router.replace(`/chat/${sessionId}`);
  }, [router]);

  const { state, sendMessage, stopStreaming } = useChat(handleNewSession);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-text-accent font-mono">INVESTMENT AGENT</h2>
          <p className="text-text-secondary mt-2 text-sm">有什么可以帮您分析的？</p>
          <div className="mt-6 flex flex-wrap gap-2 justify-center max-w-lg">
            {['今天的简报是什么？', '帮我查一下陈达对美光的观点', '我最近的交易记录'].map(q => (
              <button
                key={q}
                onClick={() => sendMessage(q)}
                className="text-xs border border-border-primary rounded px-3 py-1.5
                           text-text-secondary hover:text-text-primary hover:border-accent-orange
                           transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      </div>
      <ChatInput
        onSend={sendMessage}
        disabled={state.isStreaming}
        onStop={stopStreaming}
        placeholder={initialQ || undefined}
      />
    </div>
  );
}
```

- [ ] **Step 5: 会话页 `frontend/app/chat/[sessionId]/page.tsx`**

```tsx
'use client';

import { use, useEffect, useRef, useCallback } from 'react';
import { MessageBubble } from '@/components/MessageBubble';
import { ChatInput } from '@/components/ChatInput';
import { useChat } from '@/hooks/useChat';

export default function SessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { state, loadSession, sendMessage, stopStreaming } = useChat();

  useEffect(() => {
    loadSession(sessionId);
  }, [sessionId, loadSession]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.messages.length, state.currentTokens]);

  const handleSend = useCallback((msg: string) => {
    sendMessage(msg);
  }, [sendMessage]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {state.messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Streaming assistant message */}
        {state.isStreaming && (
          <MessageBubble
            message={{
              id: -1,
              session_id: sessionId,
              role: 'assistant',
              content: '',
              created_at: new Date().toISOString(),
            }}
            streamingTokens={state.currentTokens}
            streamingThinking={state.thinkingSteps}
            isCurrentStreaming
          />
        )}

        {state.error && (
          <div className="text-accent-red text-sm p-3 bg-red-950/20 border border-red-900/30 rounded mb-4">
            错误：{state.error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <ChatInput
        onSend={handleSend}
        disabled={state.isStreaming}
        onStop={stopStreaming}
      />
    </div>
  );
}
```

---

## Task 7: 记忆详情页

**Files:**
- Create: `frontend/app/memory/trades/page.tsx`
- Create: `frontend/app/memory/events/page.tsx`

- [ ] **Step 1: 创建 `frontend/app/memory/trades/page.tsx`**

```tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useMemory } from '@/hooks/useMemory';

export default function TradesPage() {
  const { trades, addTrade, deleteTrade } = useMemory();
  const [form, setForm] = useState({ symbol: '', action: 'buy', price: '', quantity: '', date: '', note: '' });
  const [showForm, setShowForm] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await addTrade({
      symbol: form.symbol.toUpperCase(),
      action: form.action,
      price: form.price ? parseFloat(form.price) : undefined,
      quantity: form.quantity ? parseFloat(form.quantity) : undefined,
      trade_date: form.date || undefined,
      note: form.note || undefined,
    });
    setForm({ symbol: '', action: 'buy', price: '', quantity: '', date: '', note: '' });
    setShowForm(false);
  };

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center gap-4 mb-6">
        <Link href="/chat/new" className="text-text-muted hover:text-text-primary text-sm">← 返回</Link>
        <h1 className="text-lg font-bold text-text-primary">交易记录</h1>
        <button
          onClick={() => setShowForm(s => !s)}
          className="ml-auto px-3 py-1.5 bg-accent-orange text-black text-sm rounded hover:bg-yellow-400"
        >
          + 新增
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="mb-6 p-4 bg-bg-secondary border border-border-primary rounded-lg grid grid-cols-3 gap-3">
          {[
            { label: '标的', key: 'symbol', type: 'text', required: true },
            { label: '方向', key: 'action', type: 'select' },
            { label: '价格', key: 'price', type: 'number' },
            { label: '数量', key: 'quantity', type: 'number' },
            { label: '日期', key: 'date', type: 'date' },
            { label: '备注', key: 'note', type: 'text' },
          ].map(f => (
            <div key={f.key}>
              <label className="block text-xs text-text-muted mb-1">{f.label}</label>
              {f.type === 'select' ? (
                <select
                  value={form.action}
                  onChange={e => setForm(p => ({ ...p, action: e.target.value }))}
                  className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none"
                >
                  <option value="buy">买入</option>
                  <option value="sell">卖出</option>
                  <option value="add">加仓</option>
                  <option value="reduce">减仓</option>
                </select>
              ) : (
                <input
                  type={f.type}
                  required={f.required}
                  value={form[f.key as keyof typeof form]}
                  onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent-orange"
                />
              )}
            </div>
          ))}
          <div className="col-span-3 flex gap-2 justify-end">
            <button type="button" onClick={() => setShowForm(false)} className="px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary">取消</button>
            <button type="submit" className="px-4 py-1.5 bg-accent-orange text-black text-sm rounded hover:bg-yellow-400">保存</button>
          </div>
        </form>
      )}

      <div className="bg-bg-secondary border border-border-primary rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-primary">
              {['日期', '标的', '操作', '价格', '数量', '备注', ''].map(h => (
                <th key={h} className="px-4 py-2 text-left text-xs text-text-muted uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trades.map(t => (
              <tr key={t.id} className="border-b border-border-primary hover:bg-bg-hover">
                <td className="px-4 py-2 text-text-muted text-xs">{t.trade_date ?? '-'}</td>
                <td className="px-4 py-2 font-mono text-text-primary">{t.symbol}</td>
                <td className="px-4 py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    t.action === 'buy' || t.action === '买入' ? 'bg-green-900/30 text-accent-green' : 'bg-red-900/30 text-accent-red'
                  }`}>{t.action}</span>
                </td>
                <td className="px-4 py-2 text-text-secondary">{t.price ?? '-'}</td>
                <td className="px-4 py-2 text-text-secondary">{t.quantity ?? '-'}</td>
                <td className="px-4 py-2 text-text-muted text-xs max-w-xs truncate">{t.note ?? '-'}</td>
                <td className="px-4 py-2">
                  <button onClick={() => deleteTrade(t.id)} className="text-text-muted hover:text-accent-red text-xs">删除</button>
                </td>
              </tr>
            ))}
            {trades.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-text-muted text-sm">暂无交易记录</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 创建 `frontend/app/memory/events/page.tsx`** （结构类似，略）

参考 trades 页面实现，字段改为 title / content / date / tags。

---

## Task 8: 集成验证

- [ ] **Step 1: 启动后端**

```bash
python -m agent --port 8080
```

- [ ] **Step 2: 启动前端**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 手动测试黄金路径**

1. 访问 `http://localhost:3000` → 跳转 `/chat/new`
2. 注册账号 + 登录
3. 发送消息 → 看到 SSE 流式响应（推理链 + 打字机效果）
4. 添加关注标的 → 点击标的快速提问
5. 新建会话 → 切换会话 → 历史消息恢复
6. 重命名 + 删除会话

- [ ] **Step 4: TypeScript 类型检查**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Next.js 14 investment agent UI — chat, sessions, SSE, watchlist"
```
