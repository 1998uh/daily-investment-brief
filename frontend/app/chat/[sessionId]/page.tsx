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
