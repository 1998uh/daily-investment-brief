'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { auth } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (mode === 'register') {
        await auth.register(username, password);
      }
      await auth.login(username, password);
      router.push('/chat/new');
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-text-accent font-mono tracking-wider">
            INVESTMENT AGENT
          </h1>
          <p className="text-text-muted text-sm mt-1">智能投资助手系统</p>
        </div>

        {/* Card */}
        <div className="bg-bg-secondary border border-border-primary rounded-lg p-8">
          {/* Mode Tabs */}
          <div className="flex mb-6 border border-border-primary rounded">
            {(['login', 'register'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 py-2 text-sm font-medium transition-colors ${
                  mode === m
                    ? 'bg-accent-orange text-black'
                    : 'text-text-secondary hover:text-text-primary'
                }`}
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-text-muted mb-1 uppercase tracking-wider">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded px-3 py-2
                           text-text-primary focus:outline-none focus:border-accent-orange
                           text-sm"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1 uppercase tracking-wider">
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded px-3 py-2
                           text-text-primary focus:outline-none focus:border-accent-orange
                           text-sm"
                required
              />
            </div>

            {error && (
              <div className="text-accent-red text-xs p-2 bg-red-950/20 border border-red-900/30 rounded">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 bg-accent-orange text-black font-medium rounded
                         hover:bg-yellow-400 disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors text-sm"
            >
              {loading ? '处理中...' : mode === 'login' ? '登录' : '注册并登录'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
