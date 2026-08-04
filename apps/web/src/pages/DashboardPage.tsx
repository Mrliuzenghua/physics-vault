import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  Bot,
  CheckSquare,
  CircleAlert,
  FileStack,
  LibraryBig,
  ListTodo,
  Upload,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { fetchMcpStatus, fetchMistakeCount, fetchProcessingRuns, fetchReviewTasks, searchQuestions } from '../services/api';
import type { TaskLog } from '../types';

interface DashboardStats {
  questionCount: number;
  mistakeCount: number;
  runningTasks: number;
  reviewCount: number;
  aiOnline: boolean;
}

const WORKFLOW: Array<{ label: string; detail: string; path: string; icon: LucideIcon }> = [
  { label: '导入', detail: '文档与图片识别', path: '/import', icon: Upload },
  { label: '校对', detail: '确认题干与答案', path: '/review', icon: CheckSquare },
  { label: '题库', detail: '检索与内容治理', path: '/browse', icon: LibraryBig },
  { label: '组卷', detail: '选题与页面编排', path: '/compose', icon: FileStack },
  { label: '输出', detail: '讲义、课件与授课', path: '/handout', icon: ArrowRight },
];

const QUICK_ACTIONS = [
  { label: '导入新资料', detail: '上传 Word、PDF 或图片，后台识别后进入校对', path: '/import', icon: Upload },
  { label: '处理待校对内容', detail: '逐题确认文本、公式、图片、答案与解析', path: '/review', icon: CheckSquare },
  { label: '从题库选题', detail: '按考点、题型和难度筛选并加入选题篮', path: '/browse', icon: LibraryBig },
  { label: '继续组卷', detail: '编辑试卷结构、页面设置与教学输出', path: '/compose', icon: FileStack },
];

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({
    questionCount: 0,
    mistakeCount: 0,
    runningTasks: 0,
    reviewCount: 0,
    aiOnline: false,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function loadStats() {
      setLoading(true);
      try {
        const [questions, mistakes, runs, reviews, mcp] = await Promise.allSettled([
          searchQuestions({ limit: 1, offset: 0, search_mode: 'browse' }),
          fetchMistakeCount(),
          fetchProcessingRuns(),
          fetchReviewTasks(80),
          fetchMcpStatus(),
        ]);
        if (cancelled) return;
        setStats({
          questionCount: questions.status === 'fulfilled' ? questions.value.total : 0,
          mistakeCount: mistakes.status === 'fulfilled' ? mistakes.value.count : 0,
          runningTasks: runs.status === 'fulfilled'
            ? (runs.value as TaskLog[]).filter((run) => run.status === 'running' || run.status === 'pending').length
            : 0,
          reviewCount: reviews.status === 'fulfilled' ? reviews.value.items.length : 0,
          aiOnline: mcp.status === 'fulfilled' ? mcp.value.vl_available || mcp.value.llm_available : false,
        });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadStats();
    return () => { cancelled = true; };
  }, []);

  const statusItems = [
    { label: '待校对', value: stats.reviewCount, unit: '批', path: '/review', tone: 'text-[#b45f06] bg-[#fff7e8]' },
    { label: '运行任务', value: stats.runningTasks, unit: '个', path: '/tasks', tone: 'text-[#1768c5] bg-[#edf5ff]' },
    { label: '题库总量', value: stats.questionCount, unit: '题', path: '/browse', tone: 'text-[#28764b] bg-[#eef9f2]' },
    { label: '错题', value: stats.mistakeCount, unit: '题', path: '/browse?is_mistake=true', tone: 'text-[#b33a3a] bg-[#fff0f0]' },
  ];

  return (
    <div className="h-full overflow-y-auto bg-[#f3f6fa] p-3 sm:p-5">
      <div className="mx-auto max-w-[1280px] space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-[#1d3148]">工作概览</h1>
            <p className="mt-1 text-sm text-[#718196]">从待处理事项开始，沿教学流程完成内容生产。</p>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/import" className="flex h-9 items-center gap-1.5 rounded-md border border-[#cfd9e5] bg-white px-3 text-sm font-semibold text-[#43566b] hover:bg-[#f7f9fb]"><Upload size={15} />导入资料</Link>
            <Link to="/browse" className="flex h-9 items-center gap-1.5 rounded-md bg-[#1768c5] px-3 text-sm font-semibold text-white hover:bg-[#1159aa]"><LibraryBig size={15} />进入题库</Link>
          </div>
        </header>

        <section className="overflow-hidden rounded-lg border border-[#dce3ec] bg-white shadow-sm">
          <div className="grid divide-y divide-[#e5eaf0] sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4">
            {statusItems.map((item) => (
              <Link key={item.label} to={item.path} className="flex items-center justify-between gap-3 px-4 py-4 hover:bg-[#f8fafc]">
                <div>
                  <div className="text-xs font-semibold text-[#718196]">{item.label}</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums text-[#1d3148]">{loading ? '-' : item.value}<span className="ml-1 text-xs font-medium text-[#8b99a8]">{item.unit}</span></div>
                </div>
                <span className={`flex h-8 w-8 items-center justify-center rounded-md ${item.tone}`}><ArrowRight size={15} /></span>
              </Link>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-[#263b52]">教学内容流程</h2>
              <p className="mt-1 text-xs text-[#8290a0]">每一步都只处理一种业务对象，减少来回切换。</p>
            </div>
            <span className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold ${stats.aiOnline ? 'bg-[#eef9f2] text-[#28764b]' : 'bg-[#f1f3f5] text-[#748294]'}`}><Bot size={13} />AI {stats.aiOnline ? '在线' : '离线'}</span>
          </div>
          <div className="grid gap-2 md:grid-cols-5">
            {WORKFLOW.map((step, index) => {
              const Icon = step.icon;
              return (
                <Link key={step.label} to={step.path} className="group flex min-w-0 items-center gap-3 rounded-md border border-[#e1e7ee] px-3 py-3 hover:border-[#8eb8e5] hover:bg-[#f5f9ff]">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-[#edf3f9] text-[#3c6f9f] group-hover:bg-[#dceeff]"><Icon size={16} /></span>
                  <div className="min-w-0"><div className="flex items-center gap-1 text-sm font-semibold text-[#263b52]"><span className="text-[10px] text-[#9aa7b5]">{index + 1}</span>{step.label}</div><div className="truncate text-[11px] text-[#7f8e9f]">{step.detail}</div></div>
                </Link>
              );
            })}
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.6fr)]">
          <section className="overflow-hidden rounded-lg border border-[#dce3ec] bg-white shadow-sm">
            <div className="border-b border-[#e3e8ee] px-4 py-3"><h2 className="text-sm font-bold text-[#263b52]">快捷操作</h2></div>
            <div className="divide-y divide-[#e8edf2]">
              {QUICK_ACTIONS.map((action) => {
                const Icon = action.icon;
                return (
                  <Link key={action.path} to={action.path} className="flex items-center gap-3 px-4 py-3 hover:bg-[#f8fafc]">
                    <Icon size={17} className="shrink-0 text-[#52779c]" />
                    <div className="min-w-0 flex-1"><div className="text-sm font-semibold text-[#2b4057]">{action.label}</div><div className="mt-0.5 truncate text-xs text-[#7f8e9f]">{action.detail}</div></div>
                    <ArrowRight size={15} className="shrink-0 text-[#9aa7b5]" />
                  </Link>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
            <h2 className="text-sm font-bold text-[#263b52]">需要关注</h2>
            <div className="mt-3 space-y-2">
              <AttentionRow icon={CheckSquare} label="待校对批次" value={`${stats.reviewCount} 批`} path="/review" active={stats.reviewCount > 0} />
              <AttentionRow icon={ListTodo} label="后台运行任务" value={`${stats.runningTasks} 个`} path="/tasks" active={stats.runningTasks > 0} />
              <AttentionRow icon={CircleAlert} label="错题内容" value={`${stats.mistakeCount} 题`} path="/browse?is_mistake=true" active={stats.mistakeCount > 0} />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function AttentionRow({ icon: Icon, label, value, path, active }: { icon: LucideIcon; label: string; value: string; path: string; active: boolean }) {
  return (
    <Link to={path} className="flex items-center gap-3 rounded-md border border-[#e3e8ee] px-3 py-2.5 hover:bg-[#f8fafc]">
      <Icon size={16} className={active ? 'text-[#c26b16]' : 'text-[#8190a1]'} />
      <span className="min-w-0 flex-1 text-sm text-[#43566b]">{label}</span>
      <span className="text-xs font-semibold text-[#263b52]">{value}</span>
    </Link>
  );
}
