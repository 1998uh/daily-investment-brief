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
