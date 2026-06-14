'use client';

import { useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ChatInput } from '@/components/ChatInput';
import { useChat } from '@/hooks/useChat';

function NewChatContent() {
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
                           text-text-secondary hover:text-text-primary hover:border-text-accent
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

export default function NewChatPage() {
  return (
    <Suspense fallback={<div className="flex-1 flex items-center justify-center text-text-muted">加载中...</div>}>
      <NewChatContent />
    </Suspense>
  );
}
