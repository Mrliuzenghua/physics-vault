import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Bot, ChevronDown, ChevronUp, Pencil, RotateCcw, ShoppingBasket, Star, Trash2 } from 'lucide-react';

import type { FavoriteItemView, Question } from '../../types';
import { imageThumbnailUrl } from '../../utils/imageUrl';
import ImportStemRenderer from '../import/ImportStemRenderer';

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multi_choice: '多选题',
  fill: '填空题',
  experiment: '实验题',
  calculation: '解答题',
};

interface Props {
  question: Question;
  onReturnToReview?: (id: string) => void;
  onAddToBasket: (id: string) => void;
  onEdit?: (question: Question) => void;
  onAddToAiContext?: (question: Question) => void;
  onDelete?: (question: Question) => void;
  onToggleFavorite?: (id: string) => void;
  favorite?: FavoriteItemView | null;
  inBasket: boolean;
  inAiContext?: boolean;
  index?: number;
  checked?: boolean;
  onCheck?: (id: string) => void;
  showAnswer?: boolean;
  returningToReview?: boolean;
  deleting?: boolean;
}

function buildDifficultyStars(level?: number): string {
  if (!level || level < 1) return '☆☆☆☆☆';
  const safeLevel = Math.min(level, 5);
  return `${'★'.repeat(safeLevel)}${'☆'.repeat(5 - safeLevel)}`;
}

function collectFigureRefs(text?: string | null): Set<string> {
  const refs = new Set<string>();
  const source = text || '';
  for (const match of source.matchAll(/!\[fig:([^\]]+)\]/g)) {
    refs.add(match[1]);
  }
  return refs;
}

export default function QuestionCard({
  question,
  onReturnToReview,
  onAddToBasket,
  onEdit,
  onAddToAiContext,
  onDelete,
  onToggleFavorite,
  favorite,
  inBasket,
  inAiContext = false,
  index,
  checked,
  onCheck,
  showAnswer = false,
  returningToReview = false,
  deleting = false,
}: Props) {
  const displayTags = useMemo(() => {
    const kpNames = (question.knowledge_points || [])
      .map((item) => item.topic3_name || item.topic2_name || item.topic1_name)
      .filter(Boolean);
    return [...new Set([...(kpNames || []), ...(question.tags || [])])].slice(0, 5);
  }, [question.knowledge_points, question.tags]);

  const figures = useMemo(() => question.figures || [], [question.figures]);
  const options = useMemo(() => question.options || [], [question.options]);
  const questionType = TYPE_LABELS[question.question_type] || '题目';
  const showChoiceOptions = question.question_type === 'single_choice' || question.question_type === 'multi_choice';
  const sourceLabel = question.source || question.primary_paper_id || question.origin_file || '未标注来源';
  const referencedFigureIds = useMemo(() => {
    const refs = collectFigureRefs(question.title);
    options.forEach((option) => collectFigureRefs(option.content).forEach((ref) => refs.add(ref)));
    collectFigureRefs(question.answer).forEach((ref) => refs.add(ref));
    collectFigureRefs(question.analysis).forEach((ref) => refs.add(ref));
    return refs;
  }, [options, question.analysis, question.answer, question.title]);
  const unreferencedFigures = figures.filter((figure) => !referencedFigureIds.has(figure.fig_uuid));
  const [showUnreferencedFigures, setShowUnreferencedFigures] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const revealAnswer = showAnswer || detailsOpen;

  return (
    <article
      className={`rounded-md border bg-white px-3 py-3 shadow-sm transition-colors sm:px-4 ${
        checked ? 'border-[var(--color-accent)] ring-2 ring-[var(--color-accent)]/10' : 'border-[#d9e0e8] hover:border-[#b9c7d8]'
      }`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex items-center gap-2">
            {onCheck && (
              <input
                type="checkbox"
                checked={checked ?? false}
                onChange={() => onCheck(question.question_id)}
                className="h-4 w-4 cursor-pointer accent-[var(--color-accent)]"
                aria-label={`选择题目 ${question.question_id}`}
              />
            )}
            <span className="inline-flex h-6 min-w-6 items-center justify-center rounded bg-[#1565c0] px-1.5 text-[11px] font-bold text-white">
              {index ?? '#'}
            </span>
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="max-w-[420px] truncate text-left text-xs font-semibold text-[#26384d]"
                title={`${sourceLabel} · ${question.question_id}`}
              >
                {sourceLabel}
              </span>
              {question.year && (
                <span className="rounded bg-[#edf7f1] px-1.5 py-0.5 text-[11px] font-semibold text-[#287a4b]">
                  {question.year} 年
                </span>
              )}
              {question.primary_question_no && (
                <span className="rounded bg-[#fff5df] px-1.5 py-0.5 text-[11px] font-semibold text-[#9a6400]">
                  第 {question.primary_question_no} 题
                </span>
              )}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-[#6c7d90]">
              <span>{questionType}</span>
              <span>{buildDifficultyStars(question.difficulty)}</span>
              {question.module && <span>{question.module}</span>}
              <span className="max-w-[180px] truncate font-mono text-[11px] text-[#93a1b2] sm:max-w-[320px]" title={question.question_id}>{question.question_id}</span>
            </div>
          </div>
        </div>

        <div className="shrink-0 text-[11px] text-[var(--color-text-muted)]">
          {question.updated_at ? question.updated_at.slice(0, 10) : ''}
        </div>
      </div>

      <div className="border-t border-[#e5e9ef] pt-3">
        <div className="text-[14px] leading-7 text-[#111827]">
          <ImportStemRenderer title={question.title || question.canonical_title || '(无题干)'} figures={figures} maxImageHeight={260} thumbnailWidth={900} questionId={question.question_id} />
        </div>

        {unreferencedFigures.length > 0 && (
          <div className="mt-3">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setShowUnreferencedFigures((value) => !value);
              }}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-accent)]"
            >
              {showUnreferencedFigures ? '收起附图' : `查看附图 ${unreferencedFigures.length} 张`}
            </button>

            {showUnreferencedFigures && (
              <div className="mt-2 flex flex-wrap items-start gap-3">
                {unreferencedFigures.map((figure, figureIndex) => (
                  <img
                    key={figure.fig_uuid || `${question.question_id}-${figureIndex}`}
                    src={imageThumbnailUrl(figure.local_path, 640) || ''}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    draggable={false}
                    className="max-h-[240px] rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] object-contain shadow-sm"
                    onClick={(event) => event.stopPropagation()}
                    onMouseDown={(event) => event.stopPropagation()}
                    onPointerDown={(event) => event.stopPropagation()}
                    onError={(event) => {
                      (event.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {showChoiceOptions && options.length > 0 && (
          <div className="mt-3 grid gap-x-6 gap-y-2 text-[14px] leading-6 text-[#111827] sm:grid-cols-2 xl:grid-cols-4">
            {options.map((option) => (
              <div key={option.opt} className="flex items-start gap-2">
                <span className="font-semibold text-[var(--color-text-secondary)]">{option.opt}.</span>
                <div className="min-w-0 flex-1">
                  <ImportStemRenderer title={option.content} figures={figures} maxImageHeight={160} thumbnailWidth={520} questionId={question.question_id} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {displayTags.map((tag, tagIndex) => (
            <span
              key={`${tag}-${tagIndex}`}
              className="rounded bg-[#f1f4f8] px-1.5 py-0.5 text-[11px] text-[#52657b]"
            >
              {tag}
            </span>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-sm text-[var(--color-text-secondary)]">
          {(question.answer || question.analysis) && (
            <button
              type="button"
              onClick={() => setDetailsOpen((value) => !value)}
              className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11px] font-semibold text-[#36536f] hover:bg-[#eef3f8]"
            >
              {revealAnswer ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {revealAnswer ? '收起答案' : '答案与解析'}
            </button>
          )}
          {onReturnToReview && (
            <ActionLink onClick={() => !returningToReview && onReturnToReview(question.question_id)}>
              <RotateCcw size={14} />{returningToReview ? '送回中...' : '打回校对'}
            </ActionLink>
          )}
          {onToggleFavorite && (
            <ActionLink onClick={() => onToggleFavorite(question.question_id)}>
              <Star size={14} />{favorite ? '已收藏' : '收藏'}
            </ActionLink>
          )}
          <button
            onClick={() => !inBasket && onAddToBasket(question.question_id)}
            disabled={inBasket}
            className={`inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-[11px] font-semibold transition-colors ${
              inBasket
                ? 'bg-[var(--color-green-light)] text-[var(--color-green)]'
                : 'bg-[var(--color-accent)] text-white shadow-sm hover:bg-[var(--color-accent-dark)]'
            }`}
          >
            <ShoppingBasket size={14} />
            {inBasket ? '已加入选题篮' : '加入选题篮'}
          </button>
          {onEdit && (
            <button
              type="button"
              onClick={() => onEdit(question)}
              className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-[11px] font-semibold text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-light)]"
            >
              <Pencil size={14} />
              实时编辑
            </button>
          )}
          {onAddToAiContext && (
            <button
              onClick={() => !inAiContext && onAddToAiContext(question)}
              disabled={inAiContext}
              className={`inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-[11px] font-semibold transition-colors ${
                inAiContext
                  ? 'bg-[var(--color-green-light)] text-[var(--color-green)]'
                  : 'bg-[var(--color-purple-light)] text-[var(--color-purple)] hover:brightness-95'
              }`}
            >
              <Bot size={14} />
              {inAiContext ? '已在 AI 上下文' : '加入 AI 上下文'}
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              onClick={() => onDelete(question)}
              disabled={deleting}
              className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md px-2 text-[11px] font-semibold text-rose-600 transition-colors hover:bg-rose-50 disabled:cursor-wait disabled:opacity-50"
              title="从题库删除"
            >
              <Trash2 size={14} />{deleting ? '删除中...' : '删除'}
            </button>
          )}
        </div>
      </div>

      {revealAnswer && (question.answer || question.analysis) && (
        <div className="mt-2 grid gap-3 rounded-md border border-[#d8e5dc] bg-[#fbfdfb] px-3 py-3 lg:grid-cols-[minmax(140px,0.32fr)_minmax(0,1fr)]">
          {question.answer && (
            <div className="mb-2">
              <div className="mb-1 text-xs font-semibold tracking-wide text-[var(--color-green)]">答案</div>
              <div className="text-[13px] leading-6 text-[var(--color-text-main)]">
                  <ImportStemRenderer title={question.answer} figures={figures} maxImageHeight={140} thumbnailWidth={520} questionId={question.question_id} />
              </div>
            </div>
          )}
          {question.analysis && (
            <div>
              <div className="mb-1 text-xs font-semibold tracking-wide text-[var(--color-accent)]">解析摘要</div>
              <div className="text-[13px] leading-6 text-[#34475a]">
                  <ImportStemRenderer title={question.analysis} figures={figures} maxImageHeight={140} thumbnailWidth={520} questionId={question.question_id} />
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function ActionLink({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="inline-flex h-7 cursor-pointer items-center gap-1 rounded-md border-none bg-transparent px-2 text-[11px] font-semibold text-[var(--color-text-secondary)] transition-colors hover:bg-[#eef3f8] hover:text-[var(--color-accent)]"
    >
      {children}
    </button>
  );
}
