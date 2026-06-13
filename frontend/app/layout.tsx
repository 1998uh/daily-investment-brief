import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Investment Agent',
  description: '智能投资助手',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="bg-bg-primary text-text-primary antialiased">{children}</body>
    </html>
  );
}
