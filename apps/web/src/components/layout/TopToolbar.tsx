import type React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

interface Props {
  aiEnabled: boolean;
  onToggleAi: () => void;
  onToggleTheme: () => void;
  basketCount: number;
  taskCount: number;
}

const TABS = [
  { path: '/dashboard', label: '总览' },
  { path: '/browse', label: '题库' },
  { path: '/compose', label: '组卷' },
  { path: '/handout', label: '讲义' },
  { path: '/slides', label: '课件' },
  { path: '/classroom', label: '授课' },
];

export default function TopToolbar({
  aiEnabled,
  onToggleAi,
  onToggleTheme,
  basketCount,
  taskCount,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();

  const handleSearch = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    const query = (event.target as HTMLInputElement).value.trim();
    if (query) {
      navigate(`/browse?query=${encodeURIComponent(query)}`);
    }
  };

  return (
    <header className="app-header z-50 flex h-11 flex-shrink-0 items-center gap-3 px-3">
      <button
        type="button"
        onClick={() => navigate('/dashboard')}
        className="flex shrink-0 cursor-pointer items-center gap-2 border-0 bg-transparent"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-white/12 ring-1 ring-white/15">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 19.5V5a2 2 0 0 1 2-2h11a3 3 0 0 1 3 3v13.5" />
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M8 7h7" />
            <path d="M8 11h8" />
          </svg>
        </span>
        <span className="hidden text-[13px] font-semibold text-white sm:inline">
          Physics Vault
        </span>
      </button>

      <nav className="flex h-8 items-center rounded-md bg-black/15 p-0.5 ring-1 ring-white/10">
        {TABS.map((tab) => {
          const active =
            location.pathname === tab.path ||
            (tab.path === '/dashboard' && location.pathname === '/');

          return (
            <button
              key={tab.path}
              type="button"
              onClick={() => navigate(tab.path)}
              className={`h-7 cursor-pointer rounded-[5px] border-0 px-3 text-xs font-medium transition ${
                active ? 'bg-white text-[#183657] shadow-sm' : 'text-white/68 hover:bg-white/10 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </nav>

      <div className="flex-1" />

      <div className="relative hidden md:block">
        <svg
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/45"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
        <input
          type="text"
          placeholder="搜索题目、考点或来源"
          onKeyDown={handleSearch}
          className="h-8 w-64 rounded-md bg-black/15 pl-8 pr-3 text-xs text-white outline-none ring-1 ring-white/10 transition placeholder:text-white/40 hover:bg-black/20 focus:bg-black/25 focus:ring-2 focus:ring-white/30"
        />
      </div>

      <button
        type="button"
        onClick={() => navigate('/compose')}
        className="relative flex h-8 cursor-pointer items-center gap-1.5 rounded-md bg-white/5 px-3 text-xs font-medium text-white ring-1 ring-white/15 transition hover:bg-white/12 hover:ring-white/25"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
          <path d="M3 6h18" />
          <path d="M16 10a4 4 0 0 1-8 0" />
        </svg>
        选题篮
        {basketCount > 0 && (
          <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-white px-1 text-[10px] font-bold leading-none text-[#183657]">
            {basketCount}
          </span>
        )}
      </button>

      <button
        type="button"
        onClick={onToggleAi}
        className="flex h-8 cursor-pointer items-center gap-1.5 rounded-md bg-white/5 px-2.5 text-xs font-medium text-white ring-1 ring-white/15 transition hover:bg-white/12 hover:ring-white/25"
        title={aiEnabled ? 'AI 已开启' : 'AI 已关闭'}
      >
        <span className={`h-2 w-2 rounded-full ${aiEnabled ? 'bg-[#4ade80]' : 'bg-[#f87171]'}`} />
        AI
      </button>

      {taskCount > 0 && (
        <span className="flex h-7 items-center rounded-full bg-[var(--color-orange)]/90 px-2.5 text-[11px] font-semibold text-white shadow-sm">
          {taskCount} 个任务
        </span>
      )}

      <button
        type="button"
        onClick={onToggleTheme}
        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-white/72 transition hover:bg-white/12 hover:text-white"
        title="切换主题"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2" />
          <path d="M12 20v2" />
          <path d="m4.93 4.93 1.41 1.41" />
          <path d="m17.66 17.66 1.41 1.41" />
          <path d="M2 12h2" />
          <path d="M20 12h2" />
          <path d="m6.34 17.66-1.41 1.41" />
          <path d="m19.07 4.93-1.41 1.41" />
        </svg>
      </button>
    </header>
  );
}
