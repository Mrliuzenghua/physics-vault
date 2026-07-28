import { useEffect, useState } from 'react';
import { fetchProcessingRuns } from '../services/api';
import type { TaskLog } from '../types';

const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  completed: { bg: 'var(--color-green-light)', fg: 'var(--color-green)' },
  running: { bg: 'var(--color-accent-light)', fg: 'var(--color-accent)' },
  failed: { bg: 'var(--color-red-light)', fg: 'var(--color-red)' },
};

export default function TaskLogsPage() {
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('');

  useEffect(() => {
    fetchProcessingRuns()
      .then(data => { setLogs(data); setLoading(false); })
      .catch(err => { setError(err.message || '加载失败'); setLoading(false); });
  }, []);

  const filtered = filter ? logs.filter(l => l.pipeline_name === filter || l.status === filter) : logs;
  const pipelines = [...new Set(logs.map(l => l.pipeline_name).filter(Boolean))];

  if (loading) return <div className="flex h-full items-center justify-center"><div className="animate-pulse space-y-3"><div className="mx-auto h-4 w-48 rounded" style={{background:'var(--color-border)'}} /><div className="mx-auto h-3 w-32 rounded" style={{background:'var(--color-border)'}} /></div></div>;
  if (error) return <div className="flex h-full items-center justify-center"><div className="text-center"><div className="mb-3 text-4xl">!</div><p style={{color:'var(--color-red)'}}>{error}</p></div></div>;

  return (
    <div className="flex h-full flex-col" style={{ background: 'var(--color-bg)' }}>
      <div className="flex flex-shrink-0 items-center gap-3 border-b px-4 py-3" style={{ background: 'var(--color-bg-card)', borderColor: 'var(--color-border)' }}>
        <h1 className="text-base font-bold" style={{ color: 'var(--color-text)' }}>任务日志</h1>
        <span className="rounded-full px-2 py-0.5 text-xs font-semibold" style={{ background: 'var(--color-accent)', color: '#fff' }}>{logs.length}</span>
        <div className="flex-1" />
        <select value={filter} onChange={e => setFilter(e.target.value)} className="rounded border px-2 py-1.5 text-xs outline-none" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text)' }}>
          <option value="">全部</option>
          <optgroup label="管线">
            {pipelines.map(p => <option key={p} value={p}>{p}</option>)}
          </optgroup>
          <optgroup label="状态">
            <option value="completed">已完成</option>
            <option value="running">运行中</option>
            <option value="failed">失败</option>
          </optgroup>
        </select>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {filtered.length === 0 ? (
          <div className="flex h-64 items-center justify-center"><p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>暂无任务记录</p></div>
        ) : (
          <div className="mx-auto space-y-2" style={{ maxWidth: 900 }}>
            {filtered.map(log => {
              const colors = STATUS_COLORS[log.status] || STATUS_COLORS.running;
              return (
                <div key={log.run_id} className="rounded-lg border p-3" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono font-semibold" style={{ color: 'var(--color-text)' }}>{log.run_id}</span>
                    <span className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: colors.bg, color: colors.fg }}>{log.status}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    <span>{log.pipeline_name || '未知管线'}</span>
                    {log.question_count != null && <span>{log.question_count} 题</span>}
                    {log.success_count != null && <span style={{ color: 'var(--color-green)' }}>成功 {log.success_count}</span>}
                    {log.fail_count != null && log.fail_count > 0 && <span style={{ color: 'var(--color-red)' }}>失败 {log.fail_count}</span>}
                    <span className="flex-1" />
                    <span>{log.started_at ? new Date(log.started_at).toLocaleString('zh-CN') : '-'}</span>
                    {log.finished_at && <span>→ {new Date(log.finished_at).toLocaleString('zh-CN')}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
