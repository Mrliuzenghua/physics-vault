import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { fetchMcpStatus, fetchMistakeCount, fetchProcessingRuns, searchQuestions } from '../services/api';
import type { TaskLog } from '../types';

interface DashboardStats {
  questionCount: number;
  mistakeCount: number;
  runningTasks: number;
  aiOnline: boolean;
}

const MODULES = [
  {
    index: '01',
    title: '服务形态与部署',
    desc: '从个人轻量使用到团队协作，保留本地题库、素材目录、导入批次和缓存目录的配置入口，为后续私有化部署打基础。',
    path: '/settings',
    action: '配置系统',
  },
  {
    index: '02',
    title: '深度自定义题库',
    desc: '围绕学科、目录、知识点、标签、题型、难度和来源进行组合筛选，让题库真正成为可维护、可检索的知识资产。',
    path: '/browse',
    action: '管理题库',
  },
  {
    index: '03',
    title: 'AI 录题与治理',
    desc: '将文档、图片与批量识别流程接入校对中心，先规范化再入库，减少重复录入和脏数据沉积。',
    path: '/import',
    action: '批量导入',
  },
  {
    index: '04',
    title: '智能组卷与输出',
    desc: '从选题篮进入组卷工作台，继续生成讲义、课件与课堂材料，把题库内容转化为可直接教学的资源。',
    path: '/compose',
    action: '去组卷',
  },
  {
    index: '05',
    title: '错题整理与反馈',
    desc: '把错题标记、收藏分组、相似题和批注沉淀下来，后续可扩展为学生个性化练习与测评分析。',
    path: '/browse?is_mistake=true',
    action: '查看错题',
  },
];

const WORKFLOW = [
  { label: '建库', detail: '目录、分类、知识点' },
  { label: '录入', detail: '手动新建、批量导入' },
  { label: '治理', detail: '校对、去重、标签' },
  { label: '组卷', detail: '选题篮、模板、导出' },
  { label: '反馈', detail: '错题、批注、复练' },
];

const QUICK_LINKS = [
  { label: '手动新建', path: '/question/new' },
  { label: '批量导入', path: '/import' },
  { label: '校对中心', path: '/review' },
  { label: '目录管理', path: '/collections' },
  { label: '素材管理', path: '/assets-manager' },
  { label: '模板管理', path: '/templates' },
];

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({
    questionCount: 0,
    mistakeCount: 0,
    runningTasks: 0,
    aiOnline: false,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadStats() {
      setLoading(true);
      try {
        const [questions, mistakes, runs, mcp] = await Promise.allSettled([
          searchQuestions({ limit: 1, offset: 0, search_mode: 'browse' }),
          fetchMistakeCount(),
          fetchProcessingRuns(),
          fetchMcpStatus(),
        ]);

        if (cancelled) return;

        const runningTasks =
          runs.status === 'fulfilled'
            ? (runs.value as TaskLog[]).filter((run) => run.status === 'running' || run.status === 'pending').length
            : 0;

        setStats({
          questionCount: questions.status === 'fulfilled' ? questions.value.total : 0,
          mistakeCount: mistakes.status === 'fulfilled' ? mistakes.value.count : 0,
          runningTasks,
          aiOnline: mcp.status === 'fulfilled' ? mcp.value.vl_available || mcp.value.llm_available : false,
        });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadStats();
    return () => {
      cancelled = true;
    };
  }, []);

  const statCards = useMemo(
    () => [
      { label: '题库题量', value: stats.questionCount, suffix: '题' },
      { label: '错题沉淀', value: stats.mistakeCount, suffix: '题' },
      { label: '运行任务', value: stats.runningTasks, suffix: '个' },
      { label: 'AI 状态', value: stats.aiOnline ? '在线' : '离线', suffix: '' },
    ],
    [stats],
  );

  return (
    <div className="min-h-full bg-[var(--color-bg)] px-6 py-5">
      <div className="mx-auto flex max-w-7xl flex-col gap-5">
        <section className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-sm">
          <div className="border-b border-[var(--color-border)] px-6 py-5">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3 py-1 text-xs font-medium text-[var(--color-text-secondary)]">
              <span className="h-2 w-2 rounded-full bg-[var(--color-teal)]" />
              AI 辅助 · 私有题库 · 教学资源管理
            </div>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-[var(--color-text-main)]">
                  一个自定义题库与教学资源管理平台
                </h1>
                <p className="mt-3 max-w-4xl text-[15px] leading-7 text-[var(--color-text-secondary)]">
                  面向教学研与命题场景，把建库、维护、录入、组卷、讲义、课件和错题反馈放在同一套工作流里，
                  让个人教师和教研团队都能沉淀自己的知识资产。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white shadow-sm" to="/import">
                  批量导入
                </Link>
                <Link className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-2 text-sm font-semibold text-[var(--color-text-secondary)]" to="/browse">
                  浏览题库
                </Link>
              </div>
            </div>
          </div>

          <div className="grid gap-px bg-[var(--color-border)] md:grid-cols-4">
            {statCards.map((item) => (
              <div key={item.label} className="bg-[var(--color-bg-card)] px-6 py-4">
                <div className="text-xs font-medium text-[var(--color-text-muted)]">{item.label}</div>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-2xl font-bold text-[var(--color-text-main)]">
                    {loading && item.label !== 'AI 状态' ? '-' : item.value}
                  </span>
                  {item.suffix && <span className="text-xs text-[var(--color-text-muted)]">{item.suffix}</span>}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[1fr_320px]">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-[var(--color-text-main)]">能力路线</h2>
                <p className="mt-1 text-sm text-[var(--color-text-muted)]">按目标拆成可持续迭代的产品模块。</p>
              </div>
              <Link className="text-sm font-semibold text-[var(--color-accent)]" to="/task-logs">
                查看任务日志
              </Link>
            </div>

            <div className="space-y-3">
              {MODULES.map((item) => (
                <article key={item.index} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 transition hover:border-[var(--color-accent)]">
                  <div className="flex flex-wrap items-start gap-4">
                    <span className="flex h-10 w-12 shrink-0 items-center justify-center rounded-md border border-[var(--color-teal)] bg-[var(--color-teal-light)] text-sm font-bold text-[var(--color-teal)]">
                      {item.index}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-base font-bold text-[var(--color-text-main)]">{item.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{item.desc}</p>
                    </div>
                    <Link className="rounded-md bg-[var(--color-bg-hover)] px-3 py-1.5 text-sm font-semibold text-[var(--color-text-secondary)] hover:text-[var(--color-accent)]" to={item.path}>
                      {item.action}
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <aside className="flex flex-col gap-5">
            <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 shadow-sm">
              <h2 className="text-lg font-bold text-[var(--color-text-main)]">闭环流程</h2>
              <div className="mt-4 space-y-3">
                {WORKFLOW.map((step, index) => (
                  <div key={step.label} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-accent-light)] text-xs font-bold text-[var(--color-accent)]">
                        {index + 1}
                      </span>
                      {index < WORKFLOW.length - 1 && <span className="h-8 w-px bg-[var(--color-border)]" />}
                    </div>
                    <div>
                      <div className="font-semibold text-[var(--color-text-main)]">{step.label}</div>
                      <div className="text-xs text-[var(--color-text-muted)]">{step.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 shadow-sm">
              <h2 className="text-lg font-bold text-[var(--color-text-main)]">常用入口</h2>
              <div className="mt-4 grid grid-cols-2 gap-2">
                {QUICK_LINKS.map((link) => (
                  <Link
                    key={link.path}
                    to={link.path}
                    className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-center text-sm font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-accent)]"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            </section>
          </aside>
        </section>
      </div>
    </div>
  );
}
