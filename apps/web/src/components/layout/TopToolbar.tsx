import type React from 'react';
import { Bot, LibraryBig, ListTodo, Menu, Search, ShoppingBasket } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

interface Props {
  aiEnabled: boolean;
  onToggleAi: () => void;
  basketCount: number;
  taskCount: number;
  showSidebarToggle: boolean;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
}

const ROUTE_LABELS: Array<[string, string]> = [
  ['/settings/mcp', 'AI 与 MCP'],
  ['/assets-manager', '素材管理'],
  ['/collections', '目录与合集'],
  ['/dashboard', '工作概览'],
  ['/browse', '题库'],
  ['/import', '导入识别'],
  ['/review', '校对中心'],
  ['/compose', '组卷工作台'],
  ['/handout', '讲义排版'],
  ['/slides', '课件制作'],
  ['/classroom', '课堂授课'],
  ['/templates', '模板'],
  ['/tasks', '任务中心'],
  ['/audit', '审计与回滚'],
  ['/settings', '系统设置'],
];

export default function TopToolbar({
  aiEnabled,
  onToggleAi,
  basketCount,
  taskCount,
  showSidebarToggle,
  sidebarCollapsed,
  onToggleSidebar,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const pageLabel = ROUTE_LABELS.find(([path]) => location.pathname === path || location.pathname.startsWith(`${path}/`))?.[1] || '工作概览';

  const handleSearch = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    const query = (event.target as HTMLInputElement).value.trim();
    if (query) navigate(`/browse?query=${encodeURIComponent(query)}`);
  };

  return (
    <header className="app-header z-50 flex h-12 shrink-0 items-center gap-2 px-3">
      <button
        type="button"
        onClick={() => navigate('/dashboard')}
        className="flex h-9 shrink-0 items-center gap-2 rounded-md px-1.5 hover:bg-[#f3f6f9]"
        title="返回工作概览"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded bg-[#1768c5] text-white">
          <LibraryBig size={16} />
        </span>
        <span className="hidden text-[13px] font-bold text-[#18334f] sm:inline">Physics Vault</span>
      </button>

      {showSidebarToggle && (
        <button
          type="button"
          onClick={onToggleSidebar}
          title={sidebarCollapsed ? '展开导航' : '收起导航'}
          aria-label={sidebarCollapsed ? '展开导航' : '收起导航'}
          className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#66788d] hover:bg-[#f0f3f7] hover:text-[#1e3650] md:flex"
        >
          <Menu size={18} />
        </button>
      )}

      <div className="hidden h-5 w-px bg-[#dce3ec] sm:block" />
      <div className="hidden shrink-0 text-sm font-semibold text-[#354a61] sm:block">{pageLabel}</div>

      <div className="relative mx-auto hidden min-w-[220px] max-w-xl flex-1 md:block">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8998a9]" size={15} />
        <input
          type="search"
          placeholder="全局搜索题目、考点或来源"
          onKeyDown={handleSearch}
          className="h-8 w-full rounded-md border border-[#d8e0e9] bg-[#f8fafc] pl-9 pr-3 text-sm text-[#1d2d40] outline-none transition placeholder:text-[#9ba8b6] focus:border-[#5a9be0] focus:bg-white focus:ring-2 focus:ring-[#dbeafe]"
        />
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-1.5 md:ml-0">
        <button
          type="button"
          onClick={() => navigate('/compose')}
          className="relative flex h-8 items-center gap-1.5 rounded-md border border-[#d8e0e9] bg-white px-2.5 text-xs font-semibold text-[#43566b] hover:bg-[#f4f7fa]"
          title="打开选题篮"
        >
          <ShoppingBasket size={15} />
          <span className="hidden sm:inline">选题篮</span>
          {basketCount > 0 && <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-[#1768c5] px-1 text-[10px] text-white">{basketCount}</span>}
        </button>

        <button
          type="button"
          onClick={() => navigate('/tasks')}
          className="relative flex h-8 w-8 items-center justify-center rounded-md text-[#66788d] hover:bg-[#f0f3f7] hover:text-[#1e3650]"
          title="任务中心"
          aria-label="任务中心"
        >
          <ListTodo size={17} />
          {taskCount > 0 && <span className="absolute right-0 top-0 h-2 w-2 rounded-full bg-[#e27a18] ring-2 ring-white" />}
        </button>

        <button
          type="button"
          onClick={onToggleAi}
          className={`flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold ${
            aiEnabled ? 'border-[#b9dfca] bg-[#f0faf4] text-[#28764b]' : 'border-[#d8e0e9] bg-white text-[#66788d]'
          }`}
          title={aiEnabled ? 'AI 已开启，点击关闭' : 'AI 已关闭，点击开启'}
        >
          <Bot size={15} />
          <span className="hidden sm:inline">AI</span>
          <span className={`h-1.5 w-1.5 rounded-full ${aiEnabled ? 'bg-[#2bb673]' : 'bg-[#aab5c2]'}`} />
        </button>
      </div>
    </header>
  );
}
