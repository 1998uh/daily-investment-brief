# Frontend UI 重设计 + 个人中心实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将前端全部页面从 Bloomberg 橙色主题改为 GitHub 深蓝灰风格，修复 chat 页 Bug，新增个人中心页，保留右侧自选股面板。

**Architecture:** 先改全局色彩 token（tailwind + globals.css），再逐页更新组件颜色，最后新增后端 `/api/auth/me` + `/api/auth/logout` 接口和前端 `/profile` 页。所有改动都是纯样式或小功能追加，不改业务逻辑。

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, FastAPI (Python), aiosqlite

**Prerequisite:** 后端已运行（`python -m agent --port 8080`），前端开发服务器已运行（`cd frontend && npm run dev`）。

---

## 文件地图

| 文件 | 操作 | 职责 |
|------|------|------|
| `frontend/tailwind.config.js` | 修改 | 全局色彩 token |
| `frontend/app/globals.css` | 修改 | body 背景色、滚动条色 |
| `frontend/app/login/page.tsx` | 修改 | 登录/注册页主题色 |
| `frontend/components/Sidebar.tsx` | 修改 | 侧边栏主题色 + 底部用户入口 |
| `frontend/components/WatchlistPanel.tsx` | 修改 | 右侧面板主题色 |
| `frontend/app/chat/layout.tsx` | 修改 | 布局层加用户名状态（传给 Sidebar） |
| `frontend/app/chat/[sessionId]/page.tsx` | 修改 | 修复 params Bug + 消息样式 |
| `frontend/app/chat/new/page.tsx` | 修改 | 欢迎页主题色 |
| `frontend/app/memory/trades/page.tsx` | 修改 | 主题色同步 |
| `frontend/app/memory/events/page.tsx` | 修改 | 主题色同步 |
| `frontend/app/profile/page.tsx` | 新建 | 个人中心页 |
| `frontend/lib/api.ts` | 修改 | 新增 `user.me()` + `user.logout()` |
| `agent/routers/auth.py` | 修改 | 新增 `GET /api/auth/me` + `POST /api/auth/logout` |

---

## Task 1: 全局色彩 token 更新

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: 更新 `frontend/tailwind.config.js`**

将 `theme.extend.colors` 完整替换为：

```js
colors: {
  bg: {
    primary:   '#0d1117',
    secondary: '#161b22',
    tertiary:  '#21262d',
    elevated:  '#2d333b',
    hover:     '#30363d',
  },
  border: {
    primary:   '#30363d',
    secondary: '#3d444d',
  },
  text: {
    primary:   '#f0f6fc',
    secondary: '#c9d1d9',
    muted:     '#8b949e',
    accent:    '#58a6ff',
  },
  accent: {
    blue:   '#58a6ff',
    green:  '#3fb950',
    red:    '#f85149',
    orange: '#e3b341',
  },
},
```

- [ ] **Step 2: 更新 `frontend/app/globals.css`**

将文件内容替换为：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
}

body {
  background-color: #0d1117;
  color: #f0f6fc;
  font-family: system-ui, -apple-system, sans-serif;
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #161b22; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #3d444d; }

.prose pre { background: #161b22 !important; border: 1px solid #30363d; }
.prose code { color: #58a6ff; font-size: 0.875em; }
.prose a { color: #58a6ff; }
.prose table { border-collapse: collapse; }
.prose th, .prose td { border: 1px solid #30363d; padding: 0.5rem 0.75rem; }
.prose th { background: #21262d; }

@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
.typing-dot {
  display: inline-block;
  width: 6px; height: 6px;
  background: #8b949e;
  border-radius: 50%;
  animation: blink 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
```

- [ ] **Step 3: 验证前端编译无报错**

检查 `npm run dev` 控制台——无 Tailwind 编译错误。打开 http://localhost:3000 确认背景已变为深蓝灰（`#0d1117`）。

- [ ] **Step 4: Commit**

```bash
git add frontend/tailwind.config.js frontend/app/globals.css
git commit -m "style: update color tokens to GitHub dark blue-gray theme"
```

---

## Task 2: 修复 chat/[sessionId] Bug

**Files:**
- Modify: `frontend/app/chat/[sessionId]/page.tsx`

- [ ] **Step 1: 修复 params 类型和解包方式**

将文件第 1-11 行替换为：

```tsx
'use client';

import { useEffect, useRef, useCallback } from 'react';
import { MessageBubble } from '@/components/MessageBubble';
import { ChatInput } from '@/components/ChatInput';
import { useChat } from '@/hooks/useChat';

export default function SessionPage({ params }: { params: { sessionId: string } }) {
  const { sessionId } = params;
  const bottomRef = useRef<HTMLDivElement>(null);
  const { state, loadSession, sendMessage, stopStreaming } = useChat();
```

注意：移除 `use` 的 import，参数类型从 `Promise<{sessionId: string}>` 改为 `{sessionId: string}`，直接解构不调用 `use()`。

- [ ] **Step 2: 验证修复**

在浏览器登录后点击任意会话或新建会话后输入消息——不再出现 "An unsupported type was passed to use()" 错误。

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/chat/[sessionId]/page.tsx"
git commit -m "fix: resolve use(params) runtime error in session page"
```

---

## Task 3: 登录页主题更新

**Files:**
- Modify: `frontend/app/login/page.tsx`

- [ ] **Step 1: 更新登录页颜色**

将 `frontend/app/login/page.tsx` 完整替换为：

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
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-text-accent tracking-wider">
            Investment Agent
          </h1>
          <p className="text-text-muted text-sm mt-1">智能投资助手</p>
        </div>

        <div className="bg-bg-secondary border border-border-primary rounded-lg p-8">
          <div className="flex mb-6 bg-bg-tertiary rounded-md p-1">
            {(['login', 'register'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 py-1.5 text-sm font-medium rounded transition-colors ${
                  mode === m
                    ? 'bg-bg-elevated text-text-primary shadow-sm'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-text-muted mb-1.5 uppercase tracking-wider">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded-md px-3 py-2
                           text-text-primary text-sm focus:outline-none focus:border-text-accent
                           focus:ring-1 focus:ring-text-accent/30"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1.5 uppercase tracking-wider">
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded-md px-3 py-2
                           text-text-primary text-sm focus:outline-none focus:border-text-accent
                           focus:ring-1 focus:ring-text-accent/30"
                required
              />
            </div>

            {error && (
              <div className="text-accent-red text-xs p-2.5 bg-red-950/20 border border-red-900/30 rounded-md">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 bg-text-accent text-bg-primary font-medium rounded-md
                         hover:bg-blue-400 disabled:opacity-50 disabled:cursor-not-allowed
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

- [ ] **Step 2: 验证**

打开 http://localhost:3000/login，确认：背景深蓝灰、按钮蓝色、Tab 切换样式正确。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/login/page.tsx
git commit -m "style: update login page to GitHub dark theme"
```

---

## Task 4: 后端新增 /api/auth/me 和 /api/auth/logout

**Files:**
- Modify: `agent/routers/auth.py`

- [ ] **Step 1: 在 `agent/routers/auth.py` 末尾追加两个路由**

在文件最后追加：

```python
@router.get("/me")
async def me(request: Request):
    user = await get_current_user(request)
    cfg = _settings(request)
    from agent.db import get_user_by_id
    full_user = await get_user_by_id(cfg.db_path, user["id"])
    return {
        "id": full_user["id"],
        "username": full_user["username"],
        "email": full_user["email"],
        "created_at": full_user["created_at"],
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"ok": True}
```

- [ ] **Step 2: 验证接口**

重启后端（`Ctrl+C` 后 `python -m agent --port 8080`），然后：

```bash
# 先登录拿 cookie
curl -s -c /tmp/cookies.txt -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}' | python -m json.tool

# 测试 /me
curl -s -b /tmp/cookies.txt http://localhost:8080/api/auth/me | python -m json.tool
```

Expected：`/me` 返回 `{"id": "...", "username": "test", "email": null, "created_at": "..."}`.

- [ ] **Step 3: Commit**

```bash
git add agent/routers/auth.py
git commit -m "feat(auth): add GET /api/auth/me and POST /api/auth/logout endpoints"
```

---

## Task 5: 前端 api.ts 新增 user 模块

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: 在 `frontend/lib/api.ts` 末尾追加 user 模块**

在文件最后追加：

```ts
// User / Auth
export const user = {
  me: () =>
    request<{ id: string; username: string; email: string | null; created_at: string }>(
      '/api/auth/me',
    ),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
};
```

- [ ] **Step 2: 验证编译**

检查前端控制台无 TypeScript 报错。

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api): add user.me() and user.logout() client helpers"
```

---

## Task 6: 个人中心页 /profile

**Files:**
- Create: `frontend/app/profile/page.tsx`

- [ ] **Step 1: 创建 `frontend/app/profile/page.tsx`**

```tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { user as userApi } from '@/lib/api';

interface UserInfo {
  id: string;
  username: string;
  email: string | null;
  created_at: string;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`;
}

export default function ProfilePage() {
  const router = useRouter();
  const [info, setInfo] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    userApi.me()
      .then(setInfo)
      .catch(() => router.replace('/login'))
      .finally(() => setLoading(false));
  }, [router]);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await userApi.logout();
    } finally {
      router.replace('/login');
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-primary">
        <div className="text-text-muted text-sm">加载中...</div>
      </div>
    );
  }

  if (!info) return null;

  return (
    <div className="flex-1 bg-bg-primary p-8">
      <div className="max-w-lg mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <Link href="/chat/new" className="text-text-muted hover:text-text-primary text-sm">
            ← 返回
          </Link>
          <h1 className="text-lg font-semibold text-text-primary">个人中心</h1>
        </div>

        <div className="bg-bg-secondary border border-border-primary rounded-lg overflow-hidden">
          {/* Avatar header */}
          <div className="bg-bg-tertiary px-6 py-8 flex items-center gap-4 border-b border-border-primary">
            <div className="w-14 h-14 rounded-full bg-bg-elevated border border-border-secondary
                            flex items-center justify-center text-text-secondary text-xl font-semibold">
              {info.username[0].toUpperCase()}
            </div>
            <div>
              <div className="text-text-primary font-semibold text-lg">{info.username}</div>
              <div className="text-text-muted text-sm">注册于 {formatDate(info.created_at)}</div>
            </div>
          </div>

          {/* Info rows */}
          <div className="divide-y divide-border-primary">
            <div className="px-6 py-4 flex items-center justify-between">
              <span className="text-text-muted text-sm">用户名</span>
              <span className="text-text-primary text-sm font-mono">{info.username}</span>
            </div>
            <div className="px-6 py-4 flex items-center justify-between">
              <span className="text-text-muted text-sm">邮箱</span>
              <span className="text-text-secondary text-sm">{info.email ?? '未设置'}</span>
            </div>
            <div className="px-6 py-4 flex items-center justify-between">
              <span className="text-text-muted text-sm">用户 ID</span>
              <span className="text-text-muted text-xs font-mono">{info.id}</span>
            </div>
            <div className="px-6 py-4 flex items-center justify-between">
              <span className="text-text-muted text-sm">注册时间</span>
              <span className="text-text-secondary text-sm">{formatDate(info.created_at)}</span>
            </div>
          </div>

          {/* Logout */}
          <div className="px-6 py-4 border-t border-border-primary">
            <button
              onClick={handleLogout}
              disabled={loggingOut}
              className="w-full py-2 text-sm text-accent-red border border-accent-red/40 rounded-md
                         hover:bg-accent-red/10 disabled:opacity-50 transition-colors"
            >
              {loggingOut ? '退出中...' : '退出登录'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 验证**

打开 http://localhost:3000/profile，确认显示用户名、注册时间，退出按钮可点击并跳转到登录页。

- [ ] **Step 3: Commit**

```bash
git add frontend/app/profile/page.tsx
git commit -m "feat(frontend): add /profile page with user info and logout"
```

---

## Task 7: 侧边栏 + layout 主题更新（含用户入口）

**Files:**
- Modify: `frontend/components/Sidebar.tsx`
- Modify: `frontend/app/chat/layout.tsx`

- [ ] **Step 1: 更新 `frontend/components/Sidebar.tsx`**

将文件完整替换为：

```tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { Session } from '@/lib/types';

interface Props {
  sessions: Session[];
  currentId?: string;
  username?: string;
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

export function Sidebar({ sessions, currentId, username, onRename, onDelete, onNewChat }: Props) {
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
      <div className="p-4 border-b border-border-primary flex items-center justify-between">
        <span className="text-sm font-semibold text-text-primary">Investment Agent</span>
        <button
          onClick={onNewChat}
          className="px-2.5 py-1 text-xs bg-text-accent text-bg-primary rounded-md font-medium
                     hover:bg-blue-400 transition-colors"
        >
          + 新对话
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <input
          type="text"
          placeholder="搜索会话..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full bg-bg-tertiary border border-border-primary rounded-md px-3 py-1.5
                     text-xs text-text-primary placeholder-text-muted focus:outline-none
                     focus:border-text-accent"
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        {Object.entries(groups).map(([date, group]) => (
          <div key={date} className="mb-3">
            <div className="text-xs text-text-muted px-2 py-1 uppercase tracking-wider">{date}</div>
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
                    className={`flex items-center px-2 py-1.5 rounded-md text-xs truncate transition-colors ${
                      s.id === currentId
                        ? 'bg-bg-tertiary text-text-primary border-l-2 border-text-accent pl-[6px]'
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
                    >✏</button>
                    <button
                      onClick={e => handleDelete(e, s.id)}
                      className="text-text-muted hover:text-accent-red p-0.5 text-xs"
                    >✕</button>
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

      {/* Bottom nav */}
      <div className="border-t border-border-primary p-2 space-y-0.5">
        <Link href="/memory/trades"
          className="flex items-center gap-2 px-2 py-1.5 text-xs text-text-muted hover:text-text-primary rounded-md hover:bg-bg-hover">
          <span>📊</span> 交易记录
        </Link>
        <Link href="/memory/events"
          className="flex items-center gap-2 px-2 py-1.5 text-xs text-text-muted hover:text-text-primary rounded-md hover:bg-bg-hover">
          <span>📝</span> 事件记录
        </Link>
      </div>

      {/* User entry */}
      <div className="border-t border-border-primary p-3">
        <Link
          href="/profile"
          className="flex items-center gap-2.5 px-2 py-2 rounded-md hover:bg-bg-hover transition-colors group"
        >
          <div className="w-7 h-7 rounded-full bg-bg-elevated border border-border-secondary
                          flex items-center justify-center text-text-secondary text-xs font-semibold shrink-0">
            {username ? username[0].toUpperCase() : '?'}
          </div>
          <span className="text-sm text-text-secondary group-hover:text-text-primary truncate">
            {username ?? '个人中心'}
          </span>
        </Link>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: 更新 `frontend/app/chat/layout.tsx` — 传 username 给 Sidebar**

将文件完整替换为：

```tsx
'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { WatchlistPanel } from '@/components/WatchlistPanel';
import { useSession } from '@/hooks/useSession';
import { useMemory } from '@/hooks/useMemory';
import { user as userApi } from '@/lib/api';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const currentId = pathname?.split('/chat/')[1];
  const [username, setUsername] = useState<string | undefined>();

  const { sessionList, renameSession, deleteSession } = useSession();
  const { watchlist, trades, addWatch, removeWatch } = useMemory();

  useEffect(() => {
    userApi.me().then(u => setUsername(u.username)).catch(() => {});
  }, []);

  const handleNewChat = useCallback(async () => {
    router.push('/chat/new');
  }, [router]);

  const handleSymbolClick = useCallback((symbol: string) => {
    router.push(`/chat/new?q=${encodeURIComponent(`${symbol} 最近怎么看？`)}`);
  }, [router]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        sessions={sessionList}
        currentId={currentId}
        username={username}
        onRename={renameSession}
        onDelete={deleteSession}
        onNewChat={handleNewChat}
      />
      <main className="flex-1 flex flex-col overflow-hidden min-w-0">
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

- [ ] **Step 3: 验证**

刷新 http://localhost:3000，确认：
- 侧边栏背景深蓝灰，当前会话有蓝色左边线高亮
- 底部显示用户名首字母头像，点击跳转 `/profile`
- 右侧自选股面板正常显示

- [ ] **Step 4: Commit**

```bash
git add frontend/components/Sidebar.tsx frontend/app/chat/layout.tsx
git commit -m "style(sidebar): GitHub dark theme + user avatar entry to profile"
```

---

## Task 8: WatchlistPanel 主题更新

**Files:**
- Modify: `frontend/components/WatchlistPanel.tsx`

- [ ] **Step 1: 更新 `frontend/components/WatchlistPanel.tsx`**

将文件完整替换为：

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
    <aside className="w-64 bg-bg-secondary border-l border-border-primary flex flex-col h-full shrink-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-primary">
        <span className="text-xs text-text-accent font-semibold tracking-wider uppercase">信息面板</span>
        <button onClick={() => setCollapsed(true)} className="text-text-muted hover:text-text-primary text-xs">
          ▶
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-5">
        {/* Watchlist */}
        <section>
          <div className="text-xs text-text-muted uppercase tracking-wider mb-2">关注标的</div>
          <div className="flex gap-1.5 mb-2">
            <input
              value={newSymbol}
              onChange={e => setNewSymbol(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
              placeholder="添加标的..."
              className="flex-1 bg-bg-tertiary border border-border-primary rounded-md px-2 py-1
                         text-xs text-text-primary focus:outline-none focus:border-text-accent"
            />
            <button
              onClick={handleAdd}
              className="px-2.5 py-1 bg-text-accent text-bg-primary text-xs rounded-md hover:bg-blue-400 transition-colors"
            >
              +
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {watchlist.map(w => (
              <div key={w.symbol}
                className="group flex items-center gap-1 bg-bg-tertiary border border-border-primary rounded-md px-2 py-1">
                <button
                  onClick={() => onSymbolClick?.(w.symbol)}
                  className="text-xs text-text-primary font-mono hover:text-text-accent"
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
                <div key={t.id}
                  className="flex items-center gap-2 text-xs bg-bg-tertiary rounded-md px-2 py-1.5">
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

- [ ] **Step 2: 验证**

确认右侧面板背景、边框、按钮颜色已更新为蓝色主题，折叠/展开功能正常。

- [ ] **Step 3: Commit**

```bash
git add frontend/components/WatchlistPanel.tsx
git commit -m "style(watchlist): update panel to GitHub dark theme"
```

---

## Task 9: 聊天页消息样式更新

**Files:**
- Modify: `frontend/app/chat/[sessionId]/page.tsx`（样式部分）
- Modify: `frontend/app/chat/new/page.tsx`

- [ ] **Step 1: 更新 `frontend/app/chat/[sessionId]/page.tsx` 错误提示颜色**

将错误提示 div 的 className 改为：

```tsx
className="text-accent-red text-sm p-3 bg-red-950/20 border border-red-900/30 rounded-md mb-4"
```

（已修复 Bug 的文件基础上更新此 className）

- [ ] **Step 2: 更新 `frontend/app/chat/new/page.tsx` 欢迎页颜色**

将文件中以下 className 做对应替换：

| 原 className 片段 | 新 className 片段 |
|---|---|
| `text-text-accent font-mono` | `text-text-primary font-semibold` |
| `hover:border-accent-orange` | `hover:border-text-accent hover:text-text-accent` |
| `border-border-primary` | `border-border-primary` （不变） |

完整替换欢迎区块：

```tsx
<div className="text-center max-w-md">
  <h2 className="text-2xl font-semibold text-text-primary mb-2">Investment Agent</h2>
  <p className="text-text-muted text-sm mb-6">有什么可以帮您分析的？</p>
  <div className="flex flex-wrap gap-2 justify-center">
    {['今天的简报是什么？', '帮我查一下陈达对美光的观点', '我最近的交易记录'].map(q => (
      <button
        key={q}
        onClick={() => sendMessage(q)}
        className="text-xs border border-border-primary rounded-md px-3 py-1.5
                   text-text-muted hover:text-text-accent hover:border-text-accent
                   transition-colors"
      >
        {q}
      </button>
    ))}
  </div>
</div>
```

- [ ] **Step 3: 验证**

新建对话页欢迎文字、快捷按钮 hover 效果已更新为蓝色。

- [ ] **Step 4: Commit**

```bash
git add "frontend/app/chat/[sessionId]/page.tsx" frontend/app/chat/new/page.tsx
git commit -m "style(chat): update message error color and welcome page theme"
```

---

## Task 10: Memory 页面主题同步

**Files:**
- Modify: `frontend/app/memory/trades/page.tsx`
- Modify: `frontend/app/memory/events/page.tsx`

- [ ] **Step 1: 替换 trades 页中的橙色引用**

在 `frontend/app/memory/trades/page.tsx` 中全局替换：

| 原字符串 | 替换为 |
|---|---|
| `bg-accent-orange` | `bg-text-accent` |
| `hover:bg-yellow-400` | `hover:bg-blue-400` |
| `focus:border-accent-orange` | `focus:border-text-accent` |
| `text-black` | `text-bg-primary` |

- [ ] **Step 2: 替换 events 页中的橙色引用**

在 `frontend/app/memory/events/page.tsx` 中做相同替换：

| 原字符串 | 替换为 |
|---|---|
| `bg-accent-orange` | `bg-text-accent` |
| `hover:bg-yellow-400` | `hover:bg-blue-400` |
| `focus:border-accent-orange` | `focus:border-text-accent` |
| `text-black` | `text-bg-primary` |

- [ ] **Step 3: 验证**

打开 http://localhost:3000/memory/trades 和 /memory/events，确认按钮为蓝色，表单 focus 边框为蓝色。

- [ ] **Step 4: Commit**

```bash
git add frontend/app/memory/trades/page.tsx frontend/app/memory/events/page.tsx
git commit -m "style(memory): replace orange accent with blue across trades and events pages"
```

---

## 自查

**Spec 覆盖检查：**
- ✅ Bug 修复（Task 2）
- ✅ 全局色彩 token（Task 1）
- ✅ 登录页（Task 3）
- ✅ 侧边栏 + 用户入口（Task 7）
- ✅ WatchlistPanel 保留且主题更新（Task 8）
- ✅ Chat 页样式（Task 9）
- ✅ Memory 页面（Task 10）
- ✅ 后端 /me + /logout（Task 4）
- ✅ 前端 api.ts（Task 5）
- ✅ 个人中心页（Task 6）

**类型一致性：** `user.me()` 在 Task 5 定义，Task 6 和 Task 7 使用，字段名一致（`username`, `email`, `created_at`）。`Sidebar` 新增 `username?: string` prop，Task 7 同步传入。
