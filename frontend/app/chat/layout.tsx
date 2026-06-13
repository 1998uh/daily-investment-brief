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

  const { sessionList, renameSession, deleteSession } = useSession();
  const { watchlist, trades, addWatch, removeWatch } = useMemory();

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
