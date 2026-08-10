import { useMemo, useState } from 'react';
import { AlertTriangle, Check, ChevronDown, Clock3, Copy, RotateCcw, TriangleAlert } from 'lucide-react';

import type { TaskContextResponse, TaskStageEvent } from '../../types';

const INITIAL_EVENT_LIMIT = 12;

export function getVisibleStageEvents(events: TaskStageEvent[], expanded: boolean): TaskStageEvent[] {
  const ordered = [...events].sort((left, right) => left.started_at.localeCompare(right.started_at));
  return expanded ? ordered : ordered.slice(-INITIAL_EVENT_LIMIT);
}

export function formatStageDuration(event: Pick<TaskStageEvent, 'duration_ms' | 'started_at' | 'finished_at'>): string {
  if (typeof event.duration_ms === 'number') {
    if (event.duration_ms < 1_000) return `${event.duration_ms} ms`;
    return `${(event.duration_ms / 1_000).toFixed(event.duration_ms >= 10_000 ? 0 : 1)} 秒`;
  }
  if (!event.finished_at) return '进行中';
  const milliseconds = Math.max(0, new Date(event.finished_at).getTime() - new Date(event.started_at).getTime());
  return `${Math.round(milliseconds / 1_000)} 秒`;
}

function formatDate(raw: string): string {
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(date);
}

function eventTone(event: TaskStageEvent): string {
  if (event.error_code || event.event_type.toLowerCase().includes('fail')) return 'border-red-200 bg-red-50 text-red-800';
  if (event.warning || event.event_type.toLowerCase().includes('warn')) return 'border-amber-200 bg-amber-50 text-amber-800';
  if (event.retry_count > 0 || event.event_type.toLowerCase().includes('retry')) return 'border-blue-200 bg-blue-50 text-blue-800';
  return 'border-slate-200 bg-white text-slate-700';
}

function TraceId({ traceId }: { traceId?: string }) {
  const [copied, setCopied] = useState(false);
  if (!traceId) return null;
  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(traceId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_500);
    } catch {
      // Clipboard access is optional; the trace remains selectable in the UI.
    }
  };
  return (
    <div className="flex min-w-0 items-center gap-1.5 text-[11px] text-slate-500">
      <span>trace_id</span>
      <code className="min-w-0 truncate rounded bg-slate-100 px-1.5 py-0.5 text-slate-700" title={traceId}>{traceId}</code>
      <button type="button" onClick={() => void copy()} className="inline-flex shrink-0 items-center gap-1 rounded px-1 py-0.5 font-semibold text-slate-600 hover:bg-slate-100" title="复制 trace_id">
        {copied ? <Check size={12} /> : <Copy size={12} />}{copied ? '已复制' : '复制'}
      </button>
    </div>
  );
}

export default function TaskStageTimeline({
  events,
  traceId,
  loading,
  error,
  context,
  contextLoading,
  contextError,
}: {
  events: TaskStageEvent[];
  traceId?: string;
  loading: boolean;
  error: string | null;
  context: TaskContextResponse | null;
  contextLoading: boolean;
  contextError: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const visibleEvents = useMemo(() => getVisibleStageEvents(events, expanded), [events, expanded]);
  const hiddenCount = Math.max(0, events.length - INITIAL_EVENT_LIMIT);
  const resolvedTraceId = traceId || events.find((event) => event.trace_id)?.trace_id;

  const contextPanel = contextLoading ? <div className="border-t border-slate-200 px-4 py-3 text-xs text-slate-500">正在加载关联产物与操作审计…</div>
    : contextError ? <div className="border-t border-slate-200 px-4 py-3 text-xs text-amber-700">关联上下文加载失败：{contextError}</div>
      : context && <div className="border-t border-slate-200 px-4 py-3 text-xs text-slate-700"><div className="font-bold">安全重试</div><div className="mt-1">{context.retry_allowed ? '服务端允许重试' : '服务端不允许重试'}：{context.retry_reason || '未提供原因'}</div><div className="mt-3 font-bold">关联产物</div>{context.artifacts.length ? <ul className="mt-1 space-y-1">{context.artifacts.map((artifact) => <li key={`${artifact.type}-${artifact.download_url}`}><a className="text-blue-700 underline" href={artifact.download_url}>{artifact.display_name}</a><span className="ml-2 text-slate-500">{artifact.type}</span></li>)}</ul> : <div className="mt-1 text-slate-500">暂无关联产物</div>}<div className="mt-3 font-bold">操作审计</div>{context.audits.length ? <ul className="mt-1 space-y-1">{context.audits.map((audit) => <li key={audit.audit_id}>{audit.created_at} · {audit.action} · {audit.operator} · {audit.confirmed ? '已确认' : '未确认'}</li>)}</ul> : <div className="mt-1 text-slate-500">暂无操作审计记录</div>}</div>;
  if (loading) {
    return <><div className="flex h-28 items-center gap-2 px-4 text-sm text-slate-500"><Clock3 size={16} className="animate-pulse" />正在加载执行时间线…</div>{contextPanel}</>;
  }
  if (error) {
    return <><div role="alert" className="m-4 border-l-2 border-red-500 bg-red-50 px-3 py-2 text-sm text-red-800">时间线加载失败：{error}</div>{contextPanel}</>;
  }
  if (events.length === 0) {
    return <><div className="m-4 border border-dashed border-slate-300 px-4 py-5 text-sm text-slate-500">此任务尚未记录阶段事件。</div>{contextPanel}</>;
  }

  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <TraceId traceId={resolvedTraceId} />
        {hiddenCount > 0 && (
          <button type="button" onClick={() => setExpanded((value) => !value)} className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">
            <ChevronDown size={13} className={expanded ? 'rotate-180' : ''} />
            {expanded ? '收起较早事件' : `显示较早的 ${hiddenCount} 条事件`}
          </button>
        )}
      </div>
      <ol className="max-h-[480px] space-y-2 overflow-y-auto pr-1" aria-label="任务执行阶段时间线">
        {visibleEvents.map((event) => (
          <li key={event.event_id} className={`border p-3 ${eventTone(event)}`}>
            <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                  <span>{event.phase || '任务'}</span><span className="text-slate-400">/</span><span>{event.stage || '未命名阶段'}</span>
                  <span className="rounded bg-white/70 px-1.5 py-0.5 font-mono text-[10px] font-semibold">{event.event_type || 'event'}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] opacity-80">
                  <span>{formatDate(event.started_at)}</span><span>耗时：{formatStageDuration(event)}</span>
                  {event.finished_at && <span>结束：{formatDate(event.finished_at)}</span>}
                  {event.retry_count > 0 && <span className="inline-flex items-center gap-1"><RotateCcw size={11} />第 {event.retry_count} 次重试</span>}
                </div>
              </div>
              {event.error_code && <span className="rounded bg-white/70 px-1.5 py-0.5 font-mono text-[10px] font-bold">{event.error_code}</span>}
            </div>
            {event.warning && <div className="mt-2 flex gap-1.5 text-xs"><TriangleAlert size={14} className="mt-0.5 shrink-0" />{event.warning}</div>}
            {event.error_message && <div className="mt-2 flex gap-1.5 text-xs"><AlertTriangle size={14} className="mt-0.5 shrink-0" />{event.error_message}</div>}
            {event.recommended_action && <div className="mt-2 border-t border-current/15 pt-2 text-xs"><span className="font-bold">建议操作：</span>{event.recommended_action}</div>}
          </li>
        ))}
      </ol>
      {contextPanel}
    </div>
  );
}
