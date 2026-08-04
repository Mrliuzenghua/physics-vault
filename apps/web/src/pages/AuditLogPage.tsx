import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchChangeBatch, fetchChangeBatches, rollbackChangeBatch } from '../services/api';
import type {
  ChangeBatch,
  ChangeBatchDetailResponse,
  ChangeBatchListResponse,
  RollbackChangeBatchResponse,
  RollbackPreviewItem,
} from '../types';

const CHANGE_TYPE_LABELS: Record<string, string> = {
  tag_normalization: '标签规范化',
  knowledge_binding_normalization: '知识点绑定规范化',
  return_to_review: '退回审核',
};

const STATUS_LABELS: Record<string, string> = {
  applied: '已应用',
  rolled_back: '已回滚',
  will_rollback: '将回滚',
  already_rolled_back: '已是旧值',
  current_value_conflict: '当前值冲突',
};

const STATUS_TONE: Record<string, { bg: string; fg: string; border?: string }> = {
  applied: { bg: 'var(--color-accent-light)', fg: 'var(--color-accent)' },
  rolled_back: { bg: 'var(--color-bg-hover)', fg: 'var(--color-text-muted)' },
  will_rollback: { bg: 'var(--color-green-light)', fg: 'var(--color-green)' },
  already_rolled_back: { bg: 'var(--color-bg-hover)', fg: 'var(--color-text-muted)' },
  current_value_conflict: { bg: 'var(--color-red-light)', fg: 'var(--color-red)' },
};

function labelChangeType(type: string): string {
  return CHANGE_TYPE_LABELS[type] || type;
}

function labelStatus(status: string): string {
  return STATUS_LABELS[status] || status;
}

function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN');
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (Array.isArray(value)) return value.length ? value.join('、') : '[]';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function pillStyle(status: string) {
  return STATUS_TONE[status] || { bg: 'var(--color-bg-hover)', fg: 'var(--color-text-secondary)' };
}

export default function AuditLogPage() {
  const [batches, setBatches] = useState<ChangeBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ChangeBatchDetailResponse | null>(null);
  const [preview, setPreview] = useState<RollbackChangeBatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [changeType, setChangeType] = useState('');
  const [status, setStatus] = useState('applied');
  const [reason, setReason] = useState('');
  const [allowConflicts, setAllowConflicts] = useState(false);

  const selectedBatch = useMemo(
    () => batches.find((item) => item.batch_id === selectedBatchId) || detail?.batch || null,
    [batches, detail, selectedBatchId],
  );

  const loadBatches = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data: ChangeBatchListResponse = await fetchChangeBatches({
        change_type: changeType || undefined,
        status: status || undefined,
        limit: 80,
      });
      setBatches(data.items);
      if (!selectedBatchId && data.items.length > 0) {
        setSelectedBatchId(data.items[0].batch_id);
      }
      if (selectedBatchId && !data.items.some((item) => item.batch_id === selectedBatchId)) {
        setSelectedBatchId(data.items[0]?.batch_id ?? null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载审计批次失败');
    } finally {
      setLoading(false);
    }
  }, [changeType, selectedBatchId, status]);

  const loadDetail = useCallback(async (batchId: string) => {
    setDetailLoading(true);
    setError(null);
    setPreview(null);
    try {
      const data = await fetchChangeBatch(batchId);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取批次详情失败');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBatches();
  }, [loadBatches]);

  useEffect(() => {
    if (selectedBatchId) {
      void loadDetail(selectedBatchId);
    } else {
      setDetail(null);
      setPreview(null);
    }
  }, [loadDetail, selectedBatchId]);

  const previewRollback = async () => {
    if (!selectedBatchId) return;
    setActionLoading(true);
    setError(null);
    setNotice(null);
    try {
      const data = await rollbackChangeBatch(selectedBatchId, { dry_run: true, allow_conflicts: allowConflicts });
      setPreview(data);
      setNotice(`预览完成：可回滚 ${data.changed_count} 项，冲突 ${data.conflict_count} 项。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '回滚预览失败');
    } finally {
      setActionLoading(false);
    }
  };

  const confirmRollback = async () => {
    if (!selectedBatchId) return;
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setError('确认回滚前请填写原因。');
      return;
    }
    if (!window.confirm(`确认回滚批次 ${selectedBatchId}？`)) return;
    setActionLoading(true);
    setError(null);
    setNotice(null);
    try {
      const data = await rollbackChangeBatch(selectedBatchId, {
        dry_run: false,
        reason: trimmedReason,
        allow_conflicts: allowConflicts,
      });
      setPreview(data);
      setNotice(`回滚完成：已处理 ${data.changed_count} 项。`);
      await loadBatches();
      await loadDetail(selectedBatchId);
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认回滚失败');
    } finally {
      setActionLoading(false);
    }
  };

  const previewItems = preview?.items ?? [];
  const diffItems = detail?.items ?? [];

  return (
    <div className="flex h-full flex-col" style={{ background: 'var(--color-bg)' }}>
      <div
        className="flex flex-shrink-0 items-center gap-3 border-b px-4 py-3"
        style={{ background: 'var(--color-bg-card)', borderColor: 'var(--color-border)' }}
      >
        <div>
          <h1 className="text-base font-bold" style={{ color: 'var(--color-text)' }}>审计回滚</h1>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>标准库受控修改记录</p>
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-semibold"
          style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}
        >
          {batches.length}
        </span>
        <div className="flex-1" />
        <select
          value={changeType}
          onChange={(event) => setChangeType(event.target.value)}
          className="rounded border px-2 py-1.5 text-xs outline-none"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text)' }}
        >
          <option value="">全部类型</option>
          <option value="tag_normalization">标签规范化</option>
          <option value="knowledge_binding_normalization">知识点绑定规范化</option>
          <option value="return_to_review">退回审核</option>
        </select>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="rounded border px-2 py-1.5 text-xs outline-none"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text)' }}
        >
          <option value="">全部状态</option>
          <option value="applied">已应用</option>
          <option value="rolled_back">已回滚</option>
        </select>
        <button
          type="button"
          onClick={() => void loadBatches()}
          className="rounded-md px-3 py-1.5 text-xs font-semibold"
          style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text)' }}
          disabled={loading}
        >
          {loading ? '刷新中' : '刷新'}
        </button>
      </div>

      {(error || notice) && (
        <div className="border-b px-4 py-2 text-sm" style={{ borderColor: 'var(--color-border)' }}>
          {error && <span style={{ color: 'var(--color-red)' }}>{error}</span>}
          {notice && !error && <span style={{ color: 'var(--color-green)' }}>{notice}</span>}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[380px_1fr]">
        <aside className="min-h-0 overflow-y-auto border-r p-3" style={{ borderColor: 'var(--color-border)' }}>
          {batches.length === 0 ? (
            <EmptyState label={loading ? '正在读取审计批次' : '暂无审计批次'} />
          ) : (
            <div className="space-y-2">
              {batches.map((batch) => (
                <BatchRow
                  key={batch.batch_id}
                  batch={batch}
                  active={batch.batch_id === selectedBatchId}
                  onClick={() => setSelectedBatchId(batch.batch_id)}
                />
              ))}
            </div>
          )}
        </aside>

        <main className="min-h-0 overflow-y-auto p-4">
          {!selectedBatch ? (
            <EmptyState label="请选择一个变更批次" />
          ) : (
            <div className="mx-auto max-w-6xl space-y-3">
              <section
                className="rounded-lg border p-4"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
              >
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-mono text-sm font-bold" style={{ color: 'var(--color-text)' }}>
                        {selectedBatch.batch_id}
                      </h2>
                      <StatusPill status={selectedBatch.status} />
                      <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                        {labelChangeType(selectedBatch.change_type)}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-x-5 gap-y-1 text-xs md:grid-cols-4" style={{ color: 'var(--color-text-muted)' }}>
                      <span>目标：{selectedBatch.target_count}</span>
                      <span>变更：{selectedBatch.changed_count}</span>
                      <span>应用：{formatDate(selectedBatch.applied_at || selectedBatch.created_at)}</span>
                      <span>来源：{selectedBatch.source}</span>
                    </div>
                    {selectedBatch.reason && (
                      <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                        {selectedBatch.reason}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => void previewRollback()}
                    disabled={actionLoading || selectedBatch.status !== 'applied'}
                    className="rounded-md px-3 py-2 text-xs font-bold disabled:opacity-45"
                    style={{ background: 'var(--color-accent)', color: '#fff' }}
                  >
                    {actionLoading ? '处理中' : '预览回滚'}
                  </button>
                </div>
              </section>

              <section
                className="rounded-lg border p-4"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
              >
                <div className="mb-3 flex items-center gap-3">
                  <h3 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>确认回滚</h3>
                  <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    先预览，再写入原因确认
                  </span>
                </div>
                <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                  <input
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="填写回滚原因，例如：标签批量替换误操作"
                    className="rounded-md border px-3 py-2 text-sm outline-none"
                    style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)' }}
                  />
                  <button
                    type="button"
                    onClick={() => void confirmRollback()}
                    disabled={actionLoading || selectedBatch.status !== 'applied' || !preview?.requires_confirmation}
                    className="rounded-md px-4 py-2 text-sm font-bold disabled:opacity-45"
                    style={{ background: 'var(--color-red)', color: '#fff' }}
                  >
                    确认回滚
                  </button>
                </div>
                <label className="mt-3 flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  <input
                    type="checkbox"
                    checked={allowConflicts}
                    onChange={(event) => setAllowConflicts(event.target.checked)}
                  />
                  允许冲突回滚
                </label>
              </section>

              <section
                className="rounded-lg border"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
              >
                <SectionTitle title="回滚预览" count={previewItems.length} loading={actionLoading} />
                {previewItems.length === 0 ? (
                  <EmptyState label="点击“预览回滚”后查看当前库值比对" compact />
                ) : (
                  <PreviewTable items={previewItems} />
                )}
              </section>

              <section
                className="rounded-lg border"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
              >
                <SectionTitle title="原始变更明细" count={diffItems.length} loading={detailLoading} />
                {diffItems.length === 0 ? (
                  <EmptyState label={detailLoading ? '正在读取明细' : '暂无明细'} compact />
                ) : (
                  <DiffTable items={diffItems} />
                )}
              </section>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function BatchRow({ batch, active, onClick }: { batch: ChangeBatch; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-lg border p-3 text-left transition"
      style={{
        borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
        background: active ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
      }}
    >
      <div className="flex items-center gap-2">
        <span className="truncate font-mono text-xs font-bold" style={{ color: 'var(--color-text)' }}>
          {batch.batch_id}
        </span>
        <StatusPill status={batch.status} />
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
        <span>{labelChangeType(batch.change_type)}</span>
        <span>·</span>
        <span>{batch.changed_count}/{batch.target_count}</span>
      </div>
      <div className="mt-1 truncate text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {formatDate(batch.applied_at || batch.created_at)}
      </div>
      {batch.reason && (
        <div className="mt-2 line-clamp-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {batch.reason}
        </div>
      )}
    </button>
  );
}

function SectionTitle({ title, count, loading }: { title: string; count: number; loading?: boolean }) {
  return (
    <div className="flex items-center gap-2 border-b px-4 py-3" style={{ borderColor: 'var(--color-border)' }}>
      <h3 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>{title}</h3>
      <span className="rounded-full px-2 py-0.5 text-xs" style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text-muted)' }}>
        {loading ? '...' : count}
      </span>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone = pillStyle(status);
  return (
    <span className="rounded-full px-2 py-0.5 text-[11px] font-bold" style={{ background: tone.bg, color: tone.fg }}>
      {labelStatus(status)}
    </span>
  );
}

function PreviewTable({ items }: { items: RollbackPreviewItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-left text-xs">
        <thead style={{ color: 'var(--color-text-muted)' }}>
          <tr className="border-b" style={{ borderColor: 'var(--color-border)' }}>
            <th className="px-4 py-2 font-semibold">题目</th>
            <th className="px-4 py-2 font-semibold">字段</th>
            <th className="px-4 py-2 font-semibold">当前值</th>
            <th className="px-4 py-2 font-semibold">回滚到</th>
            <th className="px-4 py-2 font-semibold">状态</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.question_id}-${item.field_name}`} className="border-b last:border-0" style={{ borderColor: 'var(--color-border)' }}>
              <td className="px-4 py-3 font-mono" style={{ color: 'var(--color-text)' }}>{item.question_id}</td>
              <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>{item.field_name}</td>
              <td className="max-w-xs px-4 py-3"><ValueBlock value={item.current_value} /></td>
              <td className="max-w-xs px-4 py-3"><ValueBlock value={item.rollback_to} /></td>
              <td className="px-4 py-3"><StatusPill status={item.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DiffTable({ items }: { items: ChangeBatchDetailResponse['items'] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-left text-xs">
        <thead style={{ color: 'var(--color-text-muted)' }}>
          <tr className="border-b" style={{ borderColor: 'var(--color-border)' }}>
            <th className="px-4 py-2 font-semibold">对象</th>
            <th className="px-4 py-2 font-semibold">字段</th>
            <th className="px-4 py-2 font-semibold">修改前</th>
            <th className="px-4 py-2 font-semibold">修改后</th>
            <th className="px-4 py-2 font-semibold">风险</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.item_id} className="border-b last:border-0" style={{ borderColor: 'var(--color-border)' }}>
              <td className="px-4 py-3 font-mono" style={{ color: 'var(--color-text)' }}>{item.entity_id}</td>
              <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>{item.field_name}</td>
              <td className="max-w-xs px-4 py-3"><ValueBlock value={item.before_value} /></td>
              <td className="max-w-xs px-4 py-3"><ValueBlock value={item.after_value} /></td>
              <td className="px-4 py-3" style={{ color: item.risk_level === 'high' ? 'var(--color-red)' : 'var(--color-text-muted)' }}>
                {item.risk_level}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValueBlock({ value }: { value: unknown }) {
  return (
    <pre
      className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded px-2 py-1 font-sans"
      style={{ background: 'var(--color-bg)', color: 'var(--color-text-secondary)' }}
    >
      {renderValue(value)}
    </pre>
  );
}

function EmptyState({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div className={`flex items-center justify-center ${compact ? 'h-28' : 'h-64'}`}>
      <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{label}</p>
    </div>
  );
}
