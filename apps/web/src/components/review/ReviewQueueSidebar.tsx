import { CheckCircle2, Search, TriangleAlert } from 'lucide-react';

import type { ReviewQuestionDraft } from '../../types';
import type { QueueKey, ReviewQueueCounts, RiskItem } from '../../utils/review/reviewQueue';

interface ReviewQueueSidebarProps {
  counts: ReviewQueueCounts;
  currentIndex: number;
  filteredDrafts: Array<{ draft: ReviewQuestionDraft; index: number }>;
  getRisks: (draft: ReviewQuestionDraft) => RiskItem[];
  onSelect: (index: number) => void;
  questionQuery: string;
  queue: QueueKey;
  setQuestionQuery: (value: string) => void;
  setQueue: (queue: QueueKey) => void;
  statusLabel: (status: ReviewQuestionDraft['status']) => string;
  typeLabels: Record<string, string>;
}

const INPUT_CLASS = 'w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 py-1.5 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]';

export default function ReviewQueueSidebar({
  counts,
  currentIndex,
  filteredDrafts,
  getRisks,
  onSelect,
  questionQuery,
  queue,
  setQuestionQuery,
  setQueue,
  statusLabel,
  typeLabels,
}: ReviewQueueSidebarProps) {
  const tabs: [QueueKey, string][] = [
    ['risk', `全部风险 ${counts.risk}`],
    ['missing_answer', `缺答案 ${counts.missingAnswer}`],
    ['missing_options', `缺选项 ${counts.missingOptions}`],
    ['image_issue', `图片异常 ${counts.imageIssue}`],
    ['ai_failed_page', `AI失败页 ${counts.failedPage}`],
    ['pending', `待确认 ${counts.pending}`],
    ['modified', `已修改 ${counts.modified}`],
    ['confirmed', `已确认 ${counts.confirmed}`],
    ['discarded', `已丢弃 ${counts.discarded}`],
    ['all', `全部 ${counts.total}`],
  ];

  return (
    <aside className="hidden min-h-0 border-r border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 lg:block">
      <label className="block text-[11px] font-semibold text-[var(--color-text-muted)]">
        审核队列
        <select className={`${INPUT_CLASS} mt-1`} value={queue} onChange={(event) => setQueue(event.target.value as QueueKey)}>
          {tabs.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
      <label className="mt-2 flex items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-2">
        <Search size={14} className="text-[var(--color-text-muted)]" />
        <input value={questionQuery} onChange={(event) => setQuestionQuery(event.target.value)} placeholder="搜索题干、知识点或答案" className="min-w-0 flex-1 border-none bg-transparent text-xs text-[var(--color-text)] outline-none" />
      </label>
      <div className="mt-2 h-[calc(100%-82px)] space-y-1.5 overflow-y-auto pr-1">
        {filteredDrafts.map(({ draft, index }) => {
          const risks = getRisks(draft);
          return (
            <button
              type="button"
              key={draft.question_id}
              onClick={() => onSelect(index)}
              className={`w-full rounded-md border px-2.5 py-2 text-left ${index === currentIndex ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)]' : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-border-strong)]'}`}
            >
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-bold text-[var(--color-accent)]">{index + 1}</span>
                <span className="text-[11px] text-[var(--color-text-muted)]">{typeLabels[draft.question_type] ?? draft.question_type}</span>
                {draft.figures.length > 0 && <span className="text-xs text-[var(--color-text-muted)]">图 {draft.figures.length}</span>}
                <span className="ml-auto text-xs text-[var(--color-text-muted)]">{statusLabel(draft.status)}</span>
              </div>
              <div className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-secondary)]">{draft.title || '无题干'}</div>
              {risks.length > 0 ? (
                <div className="mt-1 truncate text-[10px] font-semibold text-[var(--color-danger)]"><TriangleAlert size={10} className="mr-1 inline" />{risks[0]?.message}</div>
              ) : <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-semibold text-[var(--color-success)]"><CheckCircle2 size={11} />结构完整</div>}
            </button>
          );
        })}
        {filteredDrafts.length === 0 && <div className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-xs text-[var(--color-text-muted)]">当前筛选下没有题目</div>}
      </div>
    </aside>
  );
}
