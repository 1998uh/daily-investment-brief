'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { WatchlistPanel } from '@/components/WatchlistPanel';
import { useSession } from '@/hooks/useSession';
import { useMemory } from '@/hooks/useMemory';
import { user } from '@/lib/api';

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const currentId = pathname?.split('/chat/')[1];
  const [authChecked, setAuthChecked] = useState(false);

  // 鉴权守卫：未登录跳转 login
  useEffect(() => {
    user.me()
      .then(() => setAuthChecked(true))
      .catch(() => router.replace('/login'));
  }, [router]);

  const { sessionList, renameSession, deleteSession, refresh: refreshSessions } = useSession();
  const { watchlist, trades, addWatch, removeWatch } = useMemory();

  // 路由变化时刷新会话列表（新对话创建后触发）
  useEffect(() => {
    if (authChecked) {
      refreshSessions();
    }
  }, [pathname, authChecked, refreshSessions]);

  const handleNewChat = useCallback(async () => {
    router.push('/chat/new');
  }, [router]);

  const handleSymbolClick = useCallback((symbol: string) => {
    router.push(`/chat/new?q=${encodeURIComponent(`${symbol} 最近怎么看？`)}`);
  }, [router]);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg-primary">
        <p className="text-text-muted text-sm">验证登录中...</p>
      </div>
    );
  }

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
