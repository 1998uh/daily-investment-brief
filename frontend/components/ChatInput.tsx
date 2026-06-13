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
