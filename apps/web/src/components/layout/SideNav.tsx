import { useLocation, useNavigate } from 'react-router-dom';

interface NavItem {
  path: string;
  icon: string;
  label: string;
}

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: '总览',
    items: [{ path: '/dashboard', icon: 'Ov', label: '平台总览' }],
  },
  {
    title: '题库',
    items: [
      { path: '/browse', icon: 'Bk', label: '题库浏览' },
      { path: '/ai-chat', icon: 'AI', label: 'AI 题库助手' },
    ],
  },
  {
    title: '备课',
    items: [
      { path: '/compose', icon: 'Cp', label: '组卷工作台' },
      { path: '/handout', icon: 'A4', label: '讲义预览' },
      { path: '/slides', icon: 'Sl', label: '课件预览' },
      { path: '/templates', icon: 'Tp', label: '模板管理' },
    ],
  },
  {
    title: '授课',
    items: [{ path: '/classroom', icon: 'Cl', label: '课堂授课' }],
  },
  {
    title: '录入',
    items: [
      { path: '/import', icon: 'Im', label: '导入识别' },
      { path: '/review', icon: 'Rv', label: '校对中心' },
    ],
  },
  {
    title: '管理',
    items: [
      { path: '/assets-manager', icon: 'As', label: '素材管理' },
      { path: '/collections', icon: 'Ct', label: '目录管理' },
      { path: '/task-logs', icon: 'Lg', label: '任务日志' },
    ],
  },
  {
    title: '系统',
    items: [
      { path: '/settings', icon: 'St', label: '系统设置' },
      { path: '/settings/mcp', icon: 'Mc', label: 'MCP 配置' },
    ],
  },
];

export default function SideNav() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside className="flex w-44 flex-shrink-0 flex-col overflow-hidden border-r border-[var(--color-border)] bg-[var(--color-bg-sidebar)]">
      <nav className="flex-1 space-y-3 overflow-y-auto px-2 py-3">
        {NAV_GROUPS.map((group) => (
          <section key={group.title}>
            <div className="px-2 pb-1 text-[10px] font-semibold text-[var(--color-text-muted)]">
              {group.title}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active =
                  location.pathname === item.path ||
                  (item.path === '/dashboard' && location.pathname === '/');
                return (
                  <button
                    key={item.path}
                    type="button"
                    onClick={() => navigate(item.path)}
                    title={item.label}
                    className={`flex h-8 w-full cursor-pointer items-center gap-2 rounded-md px-2 text-left text-[13px] transition ${
                      active
                        ? 'bg-[var(--color-accent-light)] font-semibold text-[var(--color-accent)]'
                        : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text)]'
                    }`}
                  >
                    <span
                      className={`flex h-5 w-6 shrink-0 items-center justify-center rounded text-[10px] font-bold ${
                        active
                          ? 'bg-white/70 text-[var(--color-accent)]'
                          : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'
                      }`}
                    >
                      {item.icon}
                    </span>
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </nav>
    </aside>
  );
}
