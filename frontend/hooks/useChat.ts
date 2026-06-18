'use client';

import { useState, useCallback, useRef } from 'react';
import { sessions as sessionsApi } from '@/lib/api';
import { streamChat } from '@/lib/sse';
import type { Message, ThinkingStep, Source, ChatState, Attachment } from '@/lib/types';

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

  const sendMessage = useCallback(async (content: string, attachments?: Attachment[]) => {
    if (state.isStreaming) return;

    abortRef.current = new AbortController();

    const userMsg: Message = {
      id: Date.now(),
      session_id: state.sessionId ?? '',
      role: 'user',
      content,
      attachments,
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

      for await (const event of streamChat(content, sessionId, abortRef.current.signal, attachments)) {
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
