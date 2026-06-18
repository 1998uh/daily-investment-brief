'use client';

import { useState, useRef, useCallback } from 'react';
import type { Attachment } from '@/lib/types';

interface Props {
  onSend: (message: string, attachments?: Attachment[]) => void;
  disabled?: boolean;
  onStop?: () => void;
  placeholder?: string;
  onUpload?: (files: File[]) => Promise<Attachment[]>;
}

export function ChatInput({ onSend, disabled, onStop, placeholder, onUpload }: Props) {
  const [value, setValue] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = useCallback(() => {
    const msg = value.trim();
    if ((!msg && attachments.length === 0) || disabled) return;
    onSend(msg || '(附件)', attachments.length > 0 ? attachments : undefined);
    setValue('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, disabled, onSend, attachments]);

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

  const handleFileSelect = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0 || !onUpload) return;
    const fileArray = Array.from(files).slice(0, 5); // max 5 files
    setUploading(true);
    try {
      const uploaded = await onUpload(fileArray);
      setAttachments(prev => [...prev, ...uploaded]);
    } catch (err) {
      console.error('Upload failed:', err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [onUpload]);

  const removeAttachment = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  return (
    <div className="border-t border-border-primary bg-bg-secondary p-4">
      {/* Attachment preview bar */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachments.map(att => (
            <div
              key={att.id}
              className="flex items-center gap-1 bg-bg-tertiary border border-border-primary rounded px-2 py-1 text-xs"
            >
              <span className="text-text-muted">
                {att.kind === 'image' ? '🖼' : '📄'}
              </span>
              <span className="text-text-primary truncate max-w-[120px]">
                {att.filename}
              </span>
              <button
                onClick={() => removeAttachment(att.id)}
                className="text-text-muted hover:text-accent-red ml-1"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-3 items-end">
        {/* File upload button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading}
          className="px-3 py-3 text-text-muted hover:text-accent-orange transition-colors disabled:opacity-30 shrink-0"
          title="上传文件"
        >
          {uploading ? (
            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" opacity="0.3" />
              <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          ) : (
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
          )}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".txt,.md,.csv,.pdf,.png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={e => handleFileSelect(e.target.files)}
        />

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
            disabled={!value.trim() && attachments.length === 0}
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
