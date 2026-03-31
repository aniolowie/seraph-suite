import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

const TITLE_MAP: Record<string, string> = {
  '/': 'Dashboard',
  '/benchmarks': 'Benchmarks',
  '/knowledge': 'Knowledge Base',
  '/learning': 'Learning Loop',
  '/machines': 'Machines',
  '/writeups/submit': 'Submit Writeup',
};

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { pathname } = useLocation();
  const title = TITLE_MAP[pathname] ?? 'Seraph Suite';

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0d0d1a', color: '#e0e0e0' }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Header title={title} />
        <main
          style={{ flex: 1, overflow: 'auto', padding: 24 }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
