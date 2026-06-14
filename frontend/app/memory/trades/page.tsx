'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useMemory } from '@/hooks/useMemory';

export default function TradesPage() {
  const { trades, addTrade, deleteTrade } = useMemory();
  const [form, setForm] = useState({ symbol: '', action: 'buy', price: '', quantity: '', date: '', note: '' });
  const [showForm, setShowForm] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await addTrade({
      symbol: form.symbol.toUpperCase(),
      action: form.action,
      price: form.price ? parseFloat(form.price) : undefined,
      quantity: form.quantity ? parseFloat(form.quantity) : undefined,
      trade_date: form.date || undefined,
      note: form.note || undefined,
    });
    setForm({ symbol: '', action: 'buy', price: '', quantity: '', date: '', note: '' });
    setShowForm(false);
  };

  return (
    <div className="min-h-screen bg-bg-primary p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/chat/new" className="text-text-muted hover:text-text-primary text-sm">← 返回</Link>
          <h1 className="text-lg font-bold text-text-primary">交易记录</h1>
          <button
            onClick={() => setShowForm(s => !s)}
            className="ml-auto px-3 py-1.5 bg-accent-blue text-white text-sm rounded hover:opacity-90"
          >
            + 新增
          </button>
        </div>

        {showForm && (
          <form onSubmit={handleSubmit} className="mb-6 p-4 bg-bg-secondary border border-border-primary rounded-lg grid grid-cols-3 gap-3">
            {[
              { label: '标的', key: 'symbol', type: 'text', required: true },
              { label: '方向', key: 'action', type: 'select' },
              { label: '价格', key: 'price', type: 'number' },
              { label: '数量', key: 'quantity', type: 'number' },
              { label: '日期', key: 'date', type: 'date' },
              { label: '备注', key: 'note', type: 'text' },
            ].map(f => (
              <div key={f.key}>
                <label className="block text-xs text-text-muted mb-1">{f.label}</label>
                {f.type === 'select' ? (
                  <select
                    value={form.action}
                    onChange={e => setForm(p => ({ ...p, action: e.target.value }))}
                    className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none"
                  >
                    <option value="buy">买入</option>
                    <option value="sell">卖出</option>
                    <option value="add">加仓</option>
                    <option value="reduce">减仓</option>
                  </select>
                ) : (
                  <input
                    type={f.type}
                    required={f.required}
                    value={form[f.key as keyof typeof form]}
                    onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    className="w-full bg-bg-tertiary border border-border-primary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-text-accent"
                  />
                )}
              </div>
            ))}
            <div className="col-span-3 flex gap-2 justify-end">
              <button type="button" onClick={() => setShowForm(false)} className="px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary">取消</button>
              <button type="submit" className="px-4 py-1.5 bg-accent-blue text-white text-sm rounded hover:opacity-90">保存</button>
            </div>
          </form>
        )}

        <div className="bg-bg-secondary border border-border-primary rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-primary">
                {['日期', '标的', '操作', '价格', '数量', '备注', ''].map(h => (
                  <th key={h} className="px-4 py-2 text-left text-xs text-text-muted uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map(t => (
                <tr key={t.id} className="border-b border-border-primary hover:bg-bg-hover">
                  <td className="px-4 py-2 text-text-muted text-xs">{t.trade_date ?? '-'}</td>
                  <td className="px-4 py-2 font-mono text-text-primary">{t.symbol}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      t.action === 'buy' || t.action === '买入' ? 'bg-green-900/30 text-accent-green' : 'bg-red-900/30 text-accent-red'
                    }`}>{t.action}</span>
                  </td>
                  <td className="px-4 py-2 text-text-secondary">{t.price ?? '-'}</td>
                  <td className="px-4 py-2 text-text-secondary">{t.quantity ?? '-'}</td>
                  <td className="px-4 py-2 text-text-muted text-xs max-w-xs truncate">{t.note ?? '-'}</td>
                  <td className="px-4 py-2">
                    <button onClick={() => deleteTrade(t.id)} className="text-text-muted hover:text-accent-red text-xs">删除</button>
                  </td>
                </tr>
              ))}
              {trades.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-text-muted text-sm">暂无交易记录</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
