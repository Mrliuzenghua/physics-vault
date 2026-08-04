import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  Ban,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Search,
} from 'lucide-react';
import { cancelTask, downloadTaskResult, fetchTasks, retryTask } from '../services/api';
import type { ImportTaskStatus, TaskCenterItem, TaskCenterListResponse } from '../types';

const ACTIVE_STATUSES = new Set<ImportTaskStatus>(['pending', 'running', 'retrying', 'cancel_requested']);

const STATUS_META: Record<ImportTaskStatus, { label: string; className: string }> = {
  pending: { label: '等待中', className: 'bg-slate-100 text-slate-700' },
  running: { label: '运行中', className: 'bg-blue-50 text-blue-700' },
  retrying: { label: '重试中', className: 'bg-amber-50 text-amber-700' },
  cancel_requested: { label: '取消中', className: 'bg-orange-50 text-orange-700' },
  cancelled: { label: '已取消', className: 'bg-slate-100 text-slate-500' },
  completed: { label: '已完成', className: 'bg-emerald-50 text-emerald-700' },
  failed: { label: '失败', className: 'bg-red-50 text-red-700' },
};

const TYPE_OPTIONS = [
  ['background_recognize', '导入识别'],
  ['background_pandoc', '文档转换'],
  ['background_ai_clean', 'AI 清洗'],
  ['background_ai_structure', 'AI 结构化'],
  ['ai_parse_document', 'AI 文档识别'],
  ['ai_generated_review', 'AI 生成送审'],
  ['import_confirmed', '导入校对'],
  ['word_export', 'Word 导出'],
  ['pptx_export', 'PPT 导出'],
];

const EMPTY_RESPONSE: TaskCenterListResponse = { items: [], total: 0, page: 1, page_size: 20, pages: 1 };

export default function TaskCenterPage() {
  const [data, setData] = useState<TaskCenterListResponse>(EMPTY_RESPONSE);
  const [status, setStatus] = useState('');
  const [taskType, setTaskType] = useState('');
  const [createdFrom, setCreatedFrom] = useState('');
  const [createdTo, setCreatedTo] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionTaskId, setActionTaskId] = useState<string | null>(null);
  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set());

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const response = await fetchTasks({
        status: status || undefined,
        task_type: taskType || undefined,
        created_from: createdFrom ? new Date(`${createdFrom}T00:00:00`).toISOString() : undefined,
        created_to: createdTo ? new Date(`${createdTo}T23:59:59.999`).toISOString() : undefined,
        page,
        page_size: 20,
      });
      setData(response);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '任务列表加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [createdFrom, createdTo, page, status, taskType]);

  useEffect(() => {
    void load(false);
  }, [load]);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const schedule = () => {
      const hasActive = data.items.some((task) => ACTIVE_STATUSES.has(task.status));
      const delay = document.hidden ? 30_000 : hasActive ? 4_000 : 15_000;
      timer = window.setTimeout(async () => {
        if (stopped) return;
        await load(true);
        if (!stopped) schedule();
      }, delay);
    };
    schedule();
    const onVisibility = () => {
      if (timer) window.clearTimeout(timer);
      schedule();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [data.items, load]);

  const activeCount = useMemo(
    () => data.items.filter((task) => ACTIVE_STATUSES.has(task.status)).length,
    [data.items],
  );

  const resetPage = (setter: (value: string) => void, value: string) => {
    setter(value);
    setPage(1);
  };

  const handleRetry = async (task: TaskCenterItem) => {
    setActionTaskId(task.task_id);
    try {
      await retryTask(task.task_id);
      await load(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '重试失败');
    } finally {
      setActionTaskId(null);
    }
  };

  const handleCancel = async (task: TaskCenterItem) => {
    if (!window.confirm(`确定取消“${task.task_name}”吗？`)) return;
    setActionTaskId(task.task_id);
    try {
      await cancelTask(task.task_id);
      await load(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '取消失败');
    } finally {
      setActionTaskId(null);
    }
  };

  const handleDownload = async (task: TaskCenterItem) => {
    setActionTaskId(task.task_id);
    try {
      await downloadTaskResult(task.task_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '下载失败');
    } finally {
      setActionTaskId(null);
    }
  };

  const toggleError = (taskId: string) => {
    setExpandedErrors((current) => {
      const next = new Set(current);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  return (
    <div className="min-h-full bg-white text-slate-900">
      <header className="border-b border-slate-200 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-3">
          <div>
            <h1 className="text-lg font-bold tracking-tight">任务中心</h1>
            <p className="mt-0.5 text-xs text-slate-500">查看导入与 AI 处理进度，任务记录会在刷新后保留。</p>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
            {activeCount > 0 && <span>{activeCount} 个任务处理中</span>}
            <button
              type="button"
              onClick={() => void load(true)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 font-semibold text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
              刷新
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-4 py-4 sm:px-6">
        <section aria-label="任务筛选" className="mb-4 flex flex-wrap items-end gap-2 border-b border-slate-200 pb-4">
          <FilterSelect label="状态" value={status} onChange={(value) => resetPage(setStatus, value)}>
            <option value="">全部状态</option>
            {Object.entries(STATUS_META).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}
          </FilterSelect>
          <FilterSelect label="类型" value={taskType} onChange={(value) => resetPage(setTaskType, value)}>
            <option value="">全部类型</option>
            {TYPE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FilterSelect>
          <DateFilter label="开始日期" value={createdFrom} onChange={(value) => resetPage(setCreatedFrom, value)} />
          <DateFilter label="结束日期" value={createdTo} onChange={(value) => resetPage(setCreatedTo, value)} />
          {(status || taskType || createdFrom || createdTo) && (
            <button
              type="button"
              onClick={() => { setStatus(''); setTaskType(''); setCreatedFrom(''); setCreatedTo(''); setPage(1); }}
              className="h-8 px-2 text-xs font-semibold text-slate-500 hover:text-slate-900"
            >
              清除筛选
            </button>
          )}
          <span className="ml-auto pb-1 text-xs text-slate-500">共 {data.total} 项</span>
        </section>

        {error && (
          <div className="mb-3 flex items-start gap-2 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-800">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span className="min-w-0 flex-1 break-words">{error}</span>
            <button type="button" onClick={() => setError(null)} className="shrink-0 text-xs font-semibold">关闭</button>
          </div>
        )}

        <section className="overflow-hidden border border-slate-200" aria-label="任务列表">
          <div className="hidden grid-cols-[minmax(220px,1.5fr)_150px_minmax(170px,1fr)_150px_150px] gap-4 border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-bold uppercase tracking-wide text-slate-500 md:grid">
            <span>任务</span><span>状态</span><span>进度 / 步骤</span><span>创建 / 耗时</span><span className="text-right">操作</span>
          </div>

          {loading ? (
            <div className="flex h-52 items-center justify-center gap-2 text-sm text-slate-500"><LoaderCircle size={18} className="animate-spin" />正在加载任务</div>
          ) : data.items.length === 0 ? (
            <div className="flex h-52 flex-col items-center justify-center text-center text-slate-500">
              <Search size={24} strokeWidth={1.5} />
              <p className="mt-2 text-sm font-semibold text-slate-700">没有符合条件的任务</p>
              <p className="mt-1 text-xs">任务提交后会自动出现在这里。</p>
            </div>
          ) : data.items.map((task) => (
            <TaskRow
              key={task.task_id}
              task={task}
              busy={actionTaskId === task.task_id}
              errorExpanded={expandedErrors.has(task.task_id)}
              onToggleError={() => toggleError(task.task_id)}
              onRetry={() => void handleRetry(task)}
              onCancel={() => void handleCancel(task)}
              onDownload={() => void handleDownload(task)}
            />
          ))}
        </section>

        {data.pages > 1 && (
          <nav className="mt-4 flex items-center justify-end gap-2 text-xs" aria-label="任务分页">
            <button type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="inline-flex h-8 items-center gap-1 rounded border border-slate-300 px-2 disabled:opacity-40"><ChevronLeft size={14} />上一页</button>
            <span className="px-2 text-slate-600">第 {data.page} / {data.pages} 页</span>
            <button type="button" disabled={page >= data.pages} onClick={() => setPage((value) => value + 1)} className="inline-flex h-8 items-center gap-1 rounded border border-slate-300 px-2 disabled:opacity-40">下一页<ChevronRight size={14} /></button>
          </nav>
        )}
      </main>
    </div>
  );
}

function TaskRow({ task, busy, errorExpanded, onToggleError, onRetry, onCancel, onDownload }: {
  task: TaskCenterItem;
  busy: boolean;
  errorExpanded: boolean;
  onToggleError: () => void;
  onRetry: () => void;
  onCancel: () => void;
  onDownload: () => void;
}) {
  const meta = STATUS_META[task.status];
  const canCancel = ACTIVE_STATUSES.has(task.status) && task.status !== 'cancel_requested';
  const retrySupported = task.task_type.startsWith('background_') || task.task_type === 'word_export' || task.task_type === 'pptx_export';
  const canRetry = (task.status === 'failed' || task.status === 'cancelled') && retrySupported;
  return (
    <article className="border-b border-slate-200 px-4 py-3 last:border-b-0">
      <div className="grid gap-3 md:grid-cols-[minmax(220px,1.5fr)_150px_minmax(170px,1fr)_150px_150px] md:items-center md:gap-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" title={task.task_name}>{task.task_name}</div>
          <div className="mt-1 flex min-w-0 items-center gap-2 text-[11px] text-slate-500">
            <span className="truncate">{task.task_type}</span>
            <span aria-hidden="true">·</span>
            <span className="truncate font-mono" title={task.task_id}>{task.task_id.slice(0, 8)}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 md:block">
          <span className={`inline-flex rounded-full px-2 py-1 text-[11px] font-bold ${meta.className}`}>{meta.label}</span>
          <span className="text-[11px] text-slate-500 md:mt-1 md:block">第 {task.attempt}/{task.max_attempts} 次</span>
        </div>

        <div className="min-w-0">
          <div className="flex items-center justify-between gap-2 text-[11px] text-slate-600"><span className="truncate">{task.current_step || '—'}</span><span className="shrink-0 font-semibold">{task.progress}%</span></div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${task.status === 'failed' ? 'bg-red-500' : task.status === 'completed' ? 'bg-emerald-500' : 'bg-blue-600'}`} style={{ width: `${task.progress}%` }} /></div>
        </div>

        <div className="text-[11px] text-slate-500">
          <div>{formatDate(task.created_at)}</div>
          <div className="mt-1 flex items-center gap-1"><Clock3 size={12} />{formatDuration(task)}</div>
        </div>

        <div className="flex flex-wrap justify-start gap-1.5 md:justify-end">
          {task.error && <ActionButton icon={<ChevronDown size={13} className={errorExpanded ? 'rotate-180' : ''} />} label="错误" onClick={onToggleError} />}
          {canRetry && <ActionButton icon={<RotateCcw size={13} />} label="重试" onClick={onRetry} disabled={busy} />}
          {canCancel && <ActionButton icon={<Ban size={13} />} label="取消" onClick={onCancel} disabled={busy} />}
          {task.status === 'completed' && task.result_available && <ActionButton icon={<Download size={13} />} label="下载" onClick={onDownload} disabled={busy} />}
        </div>
      </div>

      {task.error && (
        <div className="mt-3 border-l-2 border-red-400 bg-red-50 px-3 py-2 text-xs text-red-900">
          <div className="font-semibold">{task.error.user_message}</div>
          {errorExpanded && task.error.technical_detail && (
            <div className="mt-2 border-t border-red-200 pt-2">
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-red-600">技术详情 · {task.error.error_type}</div>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-5 text-red-800">{task.error.technical_detail}</pre>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function ActionButton({ icon, label, onClick, disabled = false }: { icon: React.ReactNode; label: string; onClick: () => void; disabled?: boolean }) {
  return <button type="button" onClick={onClick} disabled={disabled} className="inline-flex h-7 items-center gap-1 rounded border border-slate-300 bg-white px-2 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">{icon}{label}</button>;
}

function FilterSelect({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: React.ReactNode }) {
  return <label className="grid gap-1 text-[11px] font-semibold text-slate-600"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} className="h-8 min-w-32 rounded border border-slate-300 bg-white px-2 text-xs font-normal text-slate-900 outline-none focus:border-blue-500">{children}</select></label>;
}

function DateFilter({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="grid gap-1 text-[11px] font-semibold text-slate-600"><span>{label}</span><input type="date" value={value} onChange={(event) => onChange(event.target.value)} className="h-8 rounded border border-slate-300 bg-white px-2 text-xs font-normal text-slate-900 outline-none focus:border-blue-500" /></label>;
}

function formatDate(raw: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(raw));
}

function formatDuration(task: TaskCenterItem) {
  const start = new Date(task.started_at || task.created_at).getTime();
  const end = task.finished_at ? new Date(task.finished_at).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`;
}
