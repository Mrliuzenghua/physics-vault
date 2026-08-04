import type { LucideIcon } from 'lucide-react';
import {
  Bot,
  BookOpenText,
  CheckSquare,
  ClipboardList,
  FileStack,
  FolderTree,
  History,
  Images,
  LayoutDashboard,
  LayoutTemplate,
  LibraryBig,
  ListTodo,
  MonitorPlay,
  Presentation,
  Settings,
  Upload,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

interface NavItem {
  path: string;
  icon: LucideIcon;
  label: string;
}

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: '工作台',
    items: [{ path: '/dashboard', icon: LayoutDashboard, label: '工作概览' }],
  },
  {
    title: '内容治理',
    items: [
      { path: '/browse', icon: LibraryBig, label: '题库' },
      { path: '/import', icon: Upload, label: '导入识别' },
      { path: '/review', icon: CheckSquare, label: '校对中心' },
      { path: '/collections', icon: FolderTree, label: '目录与合集' },
      { path: '/assets-manager', icon: Images, label: '素材管理' },
    ],
  },
  {
    title: '教学制作',
    items: [
      { path: '/compose', icon: FileStack, label: '组卷工作台' },
      { path: '/handout', icon: BookOpenText, label: '讲义排版' },
      { path: '/slides', icon: Presentation, label: '课件制作' },
      { path: '/classroom', icon: MonitorPlay, label: '课堂授课' },
      { path: '/templates', icon: LayoutTemplate, label: '模板' },
    ],
  },
  {
    title: '运行管理',
    items: [
      { path: '/tasks', icon: ListTodo, label: '任务中心' },
      { path: '/audit', icon: History, label: '审计与回滚' },
      { path: '/settings', icon: Settings, label: '系统设置' },
      { path: '/settings/mcp', icon: Bot, label: 'AI 与 MCP' },
    ],
  },
];

export default function SideNav({ collapsed = false }: { collapsed?: boolean }) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <aside className={`hidden shrink-0 flex-col overflow-hidden border-r border-[#dce3ec] bg-white transition-[width] duration-200 md:flex ${collapsed ? 'w-14' : 'w-52'}`}>
      <nav className={`min-h-0 flex-1 overflow-y-auto py-3 ${collapsed ? 'px-1.5' : 'px-2.5'}`} aria-label="主导航">
        {NAV_GROUPS.map((group, groupIndex) => (
          <section key={group.title} className={groupIndex === 0 ? '' : 'mt-4'}>
            {!collapsed && <div className="px-2 pb-1.5 text-[10px] font-bold text-[#98a5b5]">{group.title}</div>}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = location.pathname === item.path || (item.path === '/dashboard' && location.pathname === '/');
                const Icon = item.icon;
                return (
                  <button
                    key={item.path}
                    type="button"
                    onClick={() => navigate(item.path)}
                    title={item.label}
                    aria-current={active ? 'page' : undefined}
                    className={`group flex h-9 w-full items-center rounded-md text-left text-[13px] transition-colors ${collapsed ? 'justify-center' : 'gap-2.5 px-2.5'} ${
                      active
                        ? 'bg-[#eaf3ff] font-semibold text-[#1768c5]'
                        : 'text-[#52657a] hover:bg-[#f3f6f9] hover:text-[#1d3148]'
                    }`}
                  >
                    <Icon size={17} strokeWidth={active ? 2.2 : 1.8} className="shrink-0" />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </nav>

      {!collapsed && (
        <div className="border-t border-[#e4e9ef] px-4 py-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-[#52657a]">
            <ClipboardList size={14} />
            导入 → 校对 → 题库 → 组卷
          </div>
        </div>
      )}
    </aside>
  );
}
