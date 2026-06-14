'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Sidebar } from '@/components/Sidebar';
import { useSession } from '@/hooks/useSession';
import { user as userApi } from '@/lib/api';

interface UserInfo {
  id: string;
  username: string;
  email: string | null;
  created_at: string;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`;
}

export default function ProfilePage() {
  const router = useRouter();
  const { sessionList, renameSession, deleteSession } = useSession();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    userApi.me()
      .then(setUserInfo)
      .catch(() => router.push('/login'))
      .finally(() => setLoading(false));
  }, [router]);

  const handleLogout = useCallback(async () => {
    setLoggingOut(true);
    try {
      await userApi.logout();
    } finally {
      router.push('/login');
    }
  }, [router]);

  const handleNewChat = useCallback(() => {
    router.push('/chat/new');
  }, [router]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        sessions={sessionList}
        currentId={undefined}
        onRename={renameSession}
        onDelete={deleteSession}
        onNewChat={handleNewChat}
      />

      <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
        <div className="flex-1 flex items-center justify-center p-8">
          {loading ? (
            <div className="w-full max-w-md space-y-4 animate-pulse">
              <div className="h-8 bg-bg-elevated rounded w-1/2" />
              <div className="h-5 bg-bg-elevated rounded w-3/4" />
              <div className="h-5 bg-bg-elevated rounded w-1/3" />
            </div>
          ) : userInfo ? (
            <div className="w-full max-w-md">
              <div className="bg-bg-secondary border border-border-primary rounded-lg p-8">
                {/* Avatar */}
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-16 h-16 rounded-full bg-bg-elevated border border-border-secondary
                                  flex items-center justify-center shrink-0">
                    <span className="text-text-secondary text-2xl font-bold">
                      {userInfo.username[0].toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <h1 className="text-xl font-bold text-text-primary">{userInfo.username}</h1>
                    <p className="text-text-muted text-sm mt-0.5">个人中心</p>
                  </div>
                </div>

                {/* Info */}
                <div className="space-y-4 mb-8">
                  <div className="flex justify-between items-center py-3 border-b border-border-primary">
                    <span className="text-text-muted text-sm">用户名</span>
                    <span className="text-text-primary text-sm font-mono">{userInfo.username}</span>
                  </div>
                  <div className="flex justify-between items-center py-3 border-b border-border-primary">
                    <span className="text-text-muted text-sm">邮箱</span>
                    <span className="text-text-secondary text-sm">{userInfo.email ?? '未设置'}</span>
                  </div>
                  <div className="flex justify-between items-center py-3 border-b border-border-primary">
                    <span className="text-text-muted text-sm">注册时间</span>
                    <span className="text-text-secondary text-sm">{formatDate(userInfo.created_at)}</span>
                  </div>
                </div>

                {/* Logout */}
                <button
                  onClick={handleLogout}
                  disabled={loggingOut}
                  className="w-full py-2 bg-accent-red text-white text-sm font-medium rounded
                             hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
                             transition-opacity"
                >
                  {loggingOut ? '退出中...' : '退出登录'}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
