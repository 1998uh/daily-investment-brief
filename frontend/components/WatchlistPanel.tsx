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
    <aside className="w-72 bg-bg-secondary border-l border-border-primary flex flex-col h-full shrink-0">
      <div className="flex items-center justify-between p-3 border-b border-border-primary">
        <span className="text-xs text-text-accent font-mono tracking-wider uppercase">信息面板</span>
        <button onClick={() => setCollapsed(true)} className="text-text-muted hover:text-text-primary text-xs">
          ▶
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Watchlist */}
        <section>
          <div className="text-xs text-text-muted uppercase tracking-wider mb-2">关注标的</div>
          <div className="flex gap-1 mb-2">
            <input
              value={newSymbol}
              onChange={e => setNewSymbol(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
              placeholder="添加标的..."
              className="flex-1 bg-bg-tertiary border border-border-primary rounded px-2 py-1
                         text-xs text-text-primary focus:outline-none focus:border-accent-orange"
            />
            <button
              onClick={handleAdd}
              className="px-2 py-1 bg-accent-orange text-black text-xs rounded hover:bg-yellow-400"
            >
              +
            </button>
          </div>
          <div className="flex flex-wrap gap-1">
            {watchlist.map(w => (
              <div key={w.symbol} className="group flex items-center gap-1 bg-bg-elevated border border-border-primary rounded px-2 py-1">
                <button
                  onClick={() => onSymbolClick?.(w.symbol)}
                  className="text-xs text-text-primary font-mono hover:text-accent-orange"
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
                <div key={t.id} className="flex items-center gap-2 text-xs bg-bg-tertiary rounded px-2 py-1.5">
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
