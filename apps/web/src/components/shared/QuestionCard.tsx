import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Bot, ChevronDown, ChevronUp, MoreHorizontal, Pencil, RotateCcw, ShoppingBasket, Star, Trash2 } from 'lucide-react';

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
    return [...new Set([...(kpNames || []), ...(question.tags || [])])]
      .filter((tag) => tag && tag !== question.module && !/^难度\s*\d/i.test(tag))
      .slice(0, 3);
  }, [question.knowledge_points, question.module, question.tags]);

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
  const longestOption = Math.max(0, ...options.map((option) => option.content.replace(/!\[fig:[^\]]+\]/g, '').length));
  const optionColumns = longestOption <= 18
    ? 'sm:grid-cols-2 xl:grid-cols-4'
    : longestOption <= 42
      ? 'md:grid-cols-2'
      : 'grid-cols-1';

  return (
    <article
      className={`rounded border bg-white px-3 py-2.5 transition-colors sm:px-4 ${
        checked ? 'border-[var(--color-accent)] ring-2 ring-[var(--color-accent)]/10' : 'border-[#d9e0e8] hover:border-[#b9c7d8]'
      }`}
    >
      <div className="mb-2 flex items-center gap-2 border-b border-[#e5e9ef] pb-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
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

          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[#6c7d90]">
              <span
                className="max-w-[520px] truncate text-left font-semibold text-[#41566e]"
                title={`${sourceLabel} · ${question.question_id}`}
              >
                {sourceLabel}
              </span>
              <span>{questionType}</span>
              <span title={`难度 ${question.difficulty || 0}`}>{buildDifficultyStars(question.difficulty)}</span>
              {question.year && (
                <span>
                  {question.year} 年
                </span>
              )}
              {question.primary_question_no && (
                <span>
                  第 {question.primary_question_no} 题
                </span>
              )}
              {question.module && <span>{question.module}</span>}
              {displayTags.map((tag, tagIndex) => (
                <span key={`${tag}-${tagIndex}`} className="max-w-[180px] truncate rounded bg-[#f1f4f8] px-1.5 py-0.5 text-[#52657b]">{tag}</span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="text-[14px] leading-6 text-[#111827]">
          <ImportStemRenderer title={question.title || question.canonical_title || '(无题干)'} figures={figures} maxImageHeight={200} thumbnailWidth={640} questionId={question.question_id} compactImages />
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
          <div className={`mt-2.5 grid gap-x-8 gap-y-1.5 text-[14px] leading-6 text-[#111827] ${optionColumns}`}>
            {options.map((option) => (
              <div key={option.opt} className="flex items-start gap-2">
                <span className="font-semibold text-[var(--color-text-secondary)]">{option.opt}.</span>
                <div className="min-w-0 flex-1">
                  <ImportStemRenderer title={option.content} figures={figures} maxImageHeight={100} thumbnailWidth={360} questionId={question.question_id} compactImages />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-end gap-1.5 border-t border-[#edf0f4] pt-2 text-sm text-[var(--color-text-secondary)]">
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
              title="实时编辑"
              aria-label="实时编辑"
            >
              <Pencil size={14} />
              <span className="hidden sm:inline">实时编辑</span>
            </button>
          )}
          {(onReturnToReview || onToggleFavorite || onAddToAiContext || onDelete) && (
            <details className="group/more relative">
              <summary className="flex h-7 w-7 cursor-pointer list-none items-center justify-center rounded-md text-[var(--color-text-secondary)] hover:bg-[#eef3f8]" title="更多操作" aria-label="更多操作">
                <MoreHorizontal size={16} />
              </summary>
              <div className="absolute bottom-9 right-0 z-20 w-40 overflow-hidden rounded-md border border-[var(--color-border)] bg-white p-1 shadow-lg">
                {onReturnToReview && <MenuAction onClick={() => !returningToReview && onReturnToReview(question.question_id)}><RotateCcw size={14} />{returningToReview ? '送回中...' : '打回校对'}</MenuAction>}
                {onToggleFavorite && <MenuAction onClick={() => onToggleFavorite(question.question_id)}><Star size={14} />{favorite ? '已收藏' : '收藏'}</MenuAction>}
                {onAddToAiContext && <MenuAction onClick={() => !inAiContext && onAddToAiContext(question)} disabled={inAiContext}><Bot size={14} />{inAiContext ? '已在 AI 上下文' : '加入 AI 上下文'}</MenuAction>}
                {onDelete && <MenuAction onClick={() => onDelete(question)} disabled={deleting} danger><Trash2 size={14} />{deleting ? '删除中...' : '删除题目'}</MenuAction>}
              </div>
            </details>
          )}
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

function MenuAction({ children, onClick, disabled = false, danger = false }: { children: ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs font-semibold transition-colors disabled:opacity-50 ${danger ? 'text-rose-600 hover:bg-rose-50' : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'}`}
    >
      {children}
    </button>
  );
}
