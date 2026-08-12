import type { LucideIcon } from 'lucide-react';
import {
  ArrowRight,
  Bot,
  CheckSquare,
  CircleAlert,
  FileStack,
  LibraryBig,
  ListTodo,
  ShieldCheck,
  TriangleAlert,
  Upload,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { archiveTeachingProject, duplicateTeachingProject, fetchProcessingRuns, listTeachingProjects } from '../services/api';
import { fetchMcpStatus } from '../services/aiApi';
import { fetchCatalogHealth, fetchDatabaseStatus, type CatalogHealthReport } from '../services/catalogApi';
import { fetchMistakeCount } from '../services/favoritesApi';
import { fetchReviewTasks } from '../services/reviewApi';
import { buildClassroomFollowUpTasks, hydrateAllClassroomReflections, listClassroomReflections, setClassroomFollowUpTaskCompleted, type ClassroomFollowUpTask } from '../services/classroomReflection';
import type { TaskLog } from '../types';

interface DashboardStats {
  questionCount: number;
  mistakeCount: number;
  runningTasks: number;
  reviewCount: number;
  aiOnline: boolean;
}

interface TeachingProjectSummary {
  id: string;
  title: string;
  status?: string;
  contentRevision?: number;
  handoutStatus?: string;
  slidesStatus?: string;
  updatedAt?: string;
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
  const [followUpTasks, setFollowUpTasks] = useState<ClassroomFollowUpTask[]>([]);
  const [recentProjects, setRecentProjects] = useState<TeachingProjectSummary[]>([]);
  const [catalogHealth, setCatalogHealth] = useState<CatalogHealthReport | null>(null);

  const refreshFollowUpTasks = () => setFollowUpTasks(buildClassroomFollowUpTasks(listClassroomReflections()));

  const completeFollowUpTask = (taskId: string) => {
    setClassroomFollowUpTaskCompleted(taskId, true);
    refreshFollowUpTasks();
  };

  const refreshProjects = async () => {
    const projects = await listTeachingProjects(8);
    setRecentProjects(projects.map((item) => ({
      id: String(item.id || ''),
      title: String(item.title || '未命名教学项目'),
      status: typeof item.status === 'string' ? item.status : undefined,
      contentRevision: typeof item.contentRevision === 'number' ? item.contentRevision : undefined,
      handoutStatus: typeof item.handoutStatus === 'string' ? item.handoutStatus : undefined,
      slidesStatus: typeof item.slidesStatus === 'string' ? item.slidesStatus : undefined,
      updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : undefined,
    })).filter((item) => item.id));
  };

  const duplicateProject = async (project: TeachingProjectSummary) => {
    const title = window.prompt('请输入副本名称', `${project.title}（副本）`);
    if (!title?.trim()) return;
    await duplicateTeachingProject(project.id, title.trim());
    await refreshProjects();
  };

  const archiveProject = async (project: TeachingProjectSummary) => {
    if (!window.confirm(`确定归档“${project.title}”吗？`)) return;
    await archiveTeachingProject(project.id);
    await refreshProjects();
  };

  useEffect(() => {
    refreshFollowUpTasks();
    let cancelled = false;
    void hydrateAllClassroomReflections().then((reflections) => {
      if (!cancelled) setFollowUpTasks(buildClassroomFollowUpTasks(reflections));
    });
    async function loadStats() {
      setLoading(true);
      try {
        const [database, mistakes, runs, reviews, mcp, projects, health] = await Promise.allSettled([
          fetchDatabaseStatus(),
          fetchMistakeCount(),
          fetchProcessingRuns(),
          fetchReviewTasks(80),
          fetchMcpStatus(),
          listTeachingProjects(8),
          fetchCatalogHealth(),
        ]);
        if (cancelled) return;
        setStats({
          questionCount: database.status === 'fulfilled'
            ? database.value.browsable_questions_count ?? database.value.questions_count
            : 0,
          mistakeCount: mistakes.status === 'fulfilled' ? mistakes.value.count : 0,
          runningTasks: runs.status === 'fulfilled'
            ? (runs.value as TaskLog[]).filter((run) => run.status === 'running' || run.status === 'pending').length
            : 0,
          reviewCount: reviews.status === 'fulfilled' ? reviews.value.items.length : 0,
          aiOnline: mcp.status === 'fulfilled' ? mcp.value.vl_available || mcp.value.llm_available : false,
        });
        if (projects.status === 'fulfilled') {
          setRecentProjects(projects.value.map((item) => ({
            id: String(item.id || ''),
            title: String(item.title || '未命名教学项目'),
            status: typeof item.status === 'string' ? item.status : undefined,
            contentRevision: typeof item.contentRevision === 'number' ? item.contentRevision : undefined,
            handoutStatus: typeof item.handoutStatus === 'string' ? item.handoutStatus : undefined,
            slidesStatus: typeof item.slidesStatus === 'string' ? item.slidesStatus : undefined,
            updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : undefined,
          })).filter((item) => item.id));
        }
        if (health.status === 'fulfilled') setCatalogHealth(health.value);
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

        <CatalogHealthPanel report={catalogHealth} loading={loading} />

        {followUpTasks.length > 0 && <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-[#263b52]">课后跟进</h2>
              <p className="mt-1 text-xs text-[#8290a0]">根据最近授课复盘自动整理，完成后可回到课堂继续处理。</p>
            </div>
            <Link to="/classroom" className="text-xs font-semibold text-[#1768c5]">进入课堂</Link>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {followUpTasks.slice(0, 6).map((task) => (
              <div key={task.id} className="rounded-md border border-[#e1e7ee] px-3 py-3 hover:border-[#8eb8e5] hover:bg-[#f5f9ff]">
                <div className="flex items-center justify-between gap-2">
                  <label className="flex min-w-0 items-center gap-2 text-sm font-semibold text-[#2b4057]">
                    <input type="checkbox" aria-label={`完成${task.title}`} onChange={() => completeFollowUpTask(task.id)} className="h-4 w-4 accent-[#1768c5]" />
                    <span className="truncate">{task.title}</span>
                  </label>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${task.priority === 'high' ? 'bg-[#fff0f0] text-[#b33a3a]' : task.priority === 'medium' ? 'bg-[#fff7e8] text-[#b45f06]' : 'bg-[#eef9f2] text-[#28764b]'}`}>{task.priority === 'high' ? '优先' : task.priority === 'medium' ? '建议' : '可选'}</span>
                </div>
                <Link to="/classroom" className="mt-1 block text-[11px] text-[#8290a0] hover:text-[#1768c5]">{task.projectTitle} · {task.detail}</Link>
              </div>
            ))}
          </div>
        </section>}

        {recentProjects.length > 0 && <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-[#263b52]">最近教学项目</h2>
              <p className="mt-1 text-xs text-[#8290a0]">查看内容修订和讲义、课件产物状态，避免拿旧版本继续授课。</p>
            </div>
            <Link to="/compose" className="text-xs font-semibold text-[#1768c5]">进入组卷</Link>
          </div>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {recentProjects.map((project) => (
              <div key={project.id} className="rounded-md border border-[#e1e7ee] px-3 py-3 hover:border-[#8eb8e5] hover:bg-[#f5f9ff]">
                <div className="truncate text-sm font-semibold text-[#2b4057]">{project.title}</div>
                <div className="mt-1 text-[11px] text-[#8290a0]">内容修订 {project.contentRevision ?? 0} · {project.status === 'archived' ? '已归档' : '编辑中'}</div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                  <Link to="/handout" className="rounded hover:ring-1 hover:ring-[#8eb8e5]"><ArtifactStatus label="讲义" status={project.handoutStatus} /></Link>
                  <Link to="/slides" className="rounded hover:ring-1 hover:ring-[#8eb8e5]"><ArtifactStatus label="课件" status={project.slidesStatus} /></Link>
                </div>
                <div className="mt-2 flex items-center gap-3">
                  <Link to="/compose" className="text-[11px] font-semibold text-[#1768c5]">打开内容工作台 →</Link>
                  <button type="button" onClick={() => void duplicateProject(project)} className="text-[11px] text-[#56738f] hover:text-[#1768c5]">复制</button>
                  {project.status !== 'archived' && <button type="button" onClick={() => void archiveProject(project)} className="text-[11px] text-[#9a6870] hover:text-[#b33a3a]">归档</button>}
                </div>
              </div>
            ))}
          </div>
        </section>}

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

function CatalogHealthPanel({ report, loading }: { report: CatalogHealthReport | null; loading: boolean }) {
  const scoreTone = !report || report.score >= 95
    ? 'text-[#28764b] bg-[#eef9f2]'
    : report.score >= 80
      ? 'text-[#a35b0a] bg-[#fff7e8]'
      : 'text-[#b33a3a] bg-[#fff0f0]';

  return (
    <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm" aria-labelledby="catalog-health-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck size={17} className="text-[#52779c]" />
            <h2 id="catalog-health-title" className="text-sm font-bold text-[#263b52]">题库健康</h2>
          </div>
          <p className="mt-1 text-xs text-[#8290a0]">统一检查正式题库的答案、解析、知识点、标签和重复内容。</p>
        </div>
        <div className={`rounded-md px-3 py-2 text-right ${scoreTone}`}>
          <div className="text-xl font-black tabular-nums">{loading || !report ? '-' : report.score}<span className="ml-0.5 text-xs">分</span></div>
          <div className="text-[10px] font-semibold">{report ? `${report.questions_needing_attention} 题待处理` : '正在检查'}</div>
        </div>
      </div>

      {report ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {report.issues.map((issue) => {
            const sample = issue.sample_questions[0];
            return (
              <div key={issue.code} className={`rounded-md border px-3 py-3 ${issue.count > 0 ? 'border-[#ead8bd] bg-[#fffdf8]' : 'border-[#e3e8ee] bg-[#fafbfc]'}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5 text-sm font-semibold text-[#344a61]">
                    {issue.count > 0 ? <TriangleAlert size={14} className={issue.severity === 'danger' ? 'text-[#b33a3a]' : 'text-[#b56a14]'} /> : <ShieldCheck size={14} className="text-[#4a8a66]" />}
                    <span className="truncate">{issue.label}</span>
                  </div>
                  <span className={`rounded px-1.5 py-0.5 text-xs font-bold tabular-nums ${issue.count > 0 ? 'bg-white text-[#9a5c18]' : 'bg-[#eef9f2] text-[#28764b]'}`}>{issue.count}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-[#7b8998]">{issue.description}</p>
                {sample && (
                  <Link
                    to={issue.code === 'missing_knowledge' ? '/catalog-maintenance' : `/browse?query=${encodeURIComponent(sample.question_id)}&search_mode=strict`}
                    title={sample.title}
                    className="mt-2 inline-flex max-w-full items-center gap-1 text-[11px] font-semibold text-[#1768c5] hover:text-[#1159aa]"
                  >
                    <span className="truncate">查看样例 {sample.question_id}</span><ArrowRight size={12} className="shrink-0" />
                  </Link>
                )}
              </div>
            );
          })}
        </div>
      ) : !loading ? (
        <div className="mt-4 rounded-md bg-[#f6f8fa] px-3 py-3 text-xs text-[#718196]">暂时无法读取题库健康数据，其他工作区功能不受影响。</div>
      ) : null}

      {report && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#e7ebf0] pt-3 text-[11px] text-[#8290a0]">
          <span>{report.healthy_questions.toLocaleString()} / {report.total_questions.toLocaleString()} 道正式题目当前无已知结构问题</span>
          <span>{report.archived_duplicate_count} 道历史重复题已隔离，不计入题库总量</span>
        </div>
      )}
    </section>
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

function ArtifactStatus({ label, status }: { label: string; status?: string }) {
  const text = status === 'published'
    ? '已发布'
    : status === 'changed_after_publish'
      ? '内容已变更'
      : status === 'ready'
        ? '待发布'
        : status === 'stale'
          ? '需重新生成'
          : '草稿';
  const tone = status === 'published'
    ? 'bg-[#eef9f2] text-[#28764b]'
    : status === 'changed_after_publish' || status === 'stale'
      ? 'bg-[#fff0f0] text-[#b33a3a]'
      : 'bg-[#fff7e8] text-[#b45f06]';
  return <span className={`rounded px-1.5 py-0.5 ${tone}`}>{label}：{text}</span>;
}
