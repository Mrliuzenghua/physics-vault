import type { Question } from '../../types';
import { Trash2 } from 'lucide-react';
import LatexRenderer from '../render/LatexRenderer';

interface Props {
  question: Question;
  checked: boolean;
  inBasket: boolean;
  onCheck: (id: string) => void;
  onPreview: (question: Question) => void;
  onAddToBasket: (id: string) => void;
  onDelete?: (question: Question) => void;
  deleting?: boolean;
}

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选',
  multi_choice: '多选',
  fill: '填空',
  experiment: '实验',
  calculation: '计算',
};

export default function QuestionCompactRow({ question, checked, inBasket, onCheck, onPreview, onAddToBasket, onDelete, deleting = false }: Props) {
  const knowledge = (question.knowledge_points || [])
    .map((item) => item.topic3_name || item.topic2_name || item.topic1_name)
    .filter(Boolean)[0] || question.knowledge_point || '';
  const optionPreview = (question.options || [])
    .slice(0, 4)
    .map((item) => `${item.opt}. ${item.content}`)
    .join('    ');

  return (
    <article className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-[var(--color-border)] px-3 py-2 transition-colors hover:bg-[var(--color-bg-hover)] ${checked ? 'bg-[var(--color-accent-light)]/40' : 'bg-white'}`}>
      <input
        aria-label={`选择题目 ${question.question_id}`}
        type="checkbox"
        checked={checked}
        onChange={() => onCheck(question.question_id)}
        className="h-4 w-4 cursor-pointer accent-[var(--color-accent)]"
      />
      <button type="button" onClick={() => onPreview(question)} className="min-w-0 text-left">
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="font-semibold text-[var(--color-accent)]">{question.question_id}</span>
          <span className="rounded bg-[var(--color-bg-hover)] px-1.5 py-0.5 text-[var(--color-text-secondary)]">{TYPE_LABELS[question.question_type] || '题目'}</span>
          {question.year && <span className="text-[var(--color-text-muted)]">{question.year} 年</span>}
          {question.figures?.length ? <span className="text-[var(--color-text-muted)]">含图</span> : null}
          {knowledge && <span className="max-w-[180px] truncate text-[var(--color-text-muted)]">{knowledge}</span>}
        </div>
        <div className="line-clamp-3 text-[13px] leading-5 text-[var(--color-text-main)]">
          <LatexRenderer text={question.title || question.canonical_title || '无题干'} />
        </div>
        {optionPreview && <div className="mt-1 line-clamp-1 text-xs leading-5 text-[var(--color-text-secondary)]"><LatexRenderer text={optionPreview} /></div>}
        <div className="mt-1 truncate text-[11px] text-[var(--color-text-muted)]">{question.source || question.origin_file || '未标注来源'}</div>
      </button>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={inBasket}
          onClick={() => onAddToBasket(question.question_id)}
          className={`rounded-md px-2.5 py-1.5 text-xs font-semibold ${inBasket ? 'bg-[var(--color-green-light)] text-[var(--color-green)]' : 'bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-dark)]'}`}
        >
          {inBasket ? '已加入' : '加入'}
        </button>
        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(question)}
            disabled={deleting}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-rose-200 bg-white text-rose-600 hover:bg-rose-50 disabled:cursor-wait disabled:opacity-50"
            aria-label={`删除题目 ${question.question_id}`}
            title="删除题目"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </article>
  );
}
