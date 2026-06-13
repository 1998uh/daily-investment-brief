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
