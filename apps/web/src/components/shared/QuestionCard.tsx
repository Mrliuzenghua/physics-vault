import { useMemo } from 'react';
import type { ReactNode } from 'react';

import type { FavoriteItemView, Question } from '../../types';
import LatexRenderer from '../render/LatexRenderer';

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multi_choice: '多选题',
  fill: '填空题',
  experiment: '实验题',
  calculation: '解答题',
};

interface Props {
  question: Question;
  onViewDetail: (id: string) => void;
  onAddToBasket: (id: string) => void;
  onToggleFavorite?: (id: string) => void;
  favorite?: FavoriteItemView | null;
  inBasket: boolean;
  index?: number;
  checked?: boolean;
  onCheck?: (id: string) => void;
  showAnswer?: boolean;
}

function buildDifficultyStars(level?: number): string {
  if (!level || level < 1) return '☆☆☆☆☆';
  const safeLevel = Math.min(level, 5);
  return `${'★'.repeat(safeLevel)}${'☆'.repeat(5 - safeLevel)}`;
}

export default function QuestionCard({
  question,
  onViewDetail,
  onAddToBasket,
  onToggleFavorite,
  favorite,
  inBasket,
  index,
  checked,
  onCheck,
  showAnswer = false,
}: Props) {
  const displayTags = useMemo(() => {
    const kpNames = (question.knowledge_points || [])
      .map((item) => item.topic3_name || item.topic2_name || item.topic1_name)
      .filter(Boolean);
    return [...new Set([...(kpNames || []), ...(question.tags || [])])].slice(0, 5);
  }, [question.knowledge_points, question.tags]);

  const figures = question.figures || [];
  const options = question.options || [];
  const questionType = TYPE_LABELS[question.question_type] || '题目';
  const showChoiceOptions = question.question_type === 'single_choice' || question.question_type === 'multi_choice';

  return (
    <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3 shadow-sm transition-all duration-200 hover:border-[var(--color-border-strong)] hover:shadow-[var(--shadow-card)]">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex items-center gap-2">
            {onCheck && (
              <input
                type="checkbox"
                checked={checked ?? false}
                onChange={() => onCheck(question.question_id)}
                className="h-4 w-4 cursor-pointer accent-[var(--color-accent)]"
              />
            )}
            <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-md bg-[var(--color-teal)] px-2 text-xs font-bold text-white">
              {index ?? '#'}
            </span>
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => onViewDetail(question.question_id)}
                className="cursor-pointer truncate rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-2.5 py-1 text-left text-sm font-semibold text-[var(--color-accent)]"
              >
                {question.source || question.canonical_title || question.question_id}
              </button>
              {question.year && (
                <span className="rounded-md border border-[var(--color-green-light)] bg-[var(--color-green-light)] px-2.5 py-1 text-xs font-semibold text-[var(--color-green)]">
                  {question.year} 年
                </span>
              )}
              {question.primary_question_no && (
                <span className="rounded-md border border-[var(--color-orange-light)] bg-[var(--color-orange-light)] px-2.5 py-1 text-xs font-semibold text-[var(--color-orange)]">
                  第 {question.primary_question_no} 题
                </span>
              )}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-secondary)]">
              <span>题型: {questionType}</span>
              <span>难度: {buildDifficultyStars(question.difficulty)}</span>
              {question.module && <span>模块: {question.module}</span>}
            </div>
          </div>
        </div>

        <div className="shrink-0 text-xs text-[var(--color-text-muted)]">
          {question.updated_at ? question.updated_at.slice(0, 10) : ''}
        </div>
      </div>

      <div
        className="cursor-pointer rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3"
        onClick={() => onViewDetail(question.question_id)}
      >
        <div className="text-[15px] leading-8 text-[var(--color-text-main)]">
          <LatexRenderer text={question.title || '(无题干)'} />
        </div>

        {figures.length > 0 && (
          <div className="mt-4 flex flex-wrap items-start gap-4">
            {figures.map((figure, figureIndex) => (
              <img
                key={figure.fig_uuid || `${question.question_id}-${figureIndex}`}
                src={`/files/${figure.local_path}`}
                alt=""
                className="max-h-[280px] rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] object-contain shadow-sm"
                onError={(event) => {
                  (event.target as HTMLImageElement).style.display = 'none';
                }}
              />
            ))}
          </div>
        )}

        {showChoiceOptions && options.length > 0 && (
          <div className="mt-4 grid gap-3 text-[15px] text-[var(--color-text-main)] md:grid-cols-2">
            {options.map((option) => (
              <div key={option.opt} className="flex items-start gap-2">
                <span className="font-semibold text-[var(--color-text-secondary)]">{option.opt}.</span>
                <div className="min-w-0 flex-1">
                  <LatexRenderer text={option.content} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {displayTags.map((tag, tagIndex) => (
            <span
              key={`${tag}-${tagIndex}`}
              className="rounded-md bg-[var(--color-purple-light)] px-2.5 py-1 text-xs text-[var(--color-purple)]"
            >
              {tag}
            </span>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-3 text-sm text-[var(--color-text-secondary)]">
          <ActionLink onClick={() => onViewDetail(question.question_id)}>答案</ActionLink>
          <ActionLink onClick={() => onViewDetail(question.question_id)}>详情</ActionLink>
          <ActionLink onClick={() => onViewDetail(question.question_id)}>纠错</ActionLink>
          {onToggleFavorite && (
            <ActionLink onClick={() => onToggleFavorite(question.question_id)}>
              {favorite ? '已收藏' : '收藏'}
            </ActionLink>
          )}
          <button
            onClick={() => !inBasket && onAddToBasket(question.question_id)}
            disabled={inBasket}
            className={`cursor-pointer rounded-md px-3 py-1.5 text-sm font-semibold transition-all ${
              inBasket
                ? 'bg-[var(--color-green-light)] text-[var(--color-green)]'
                : 'bg-[var(--color-accent)] text-white shadow-sm hover:bg-[var(--color-accent-dark)]'
            }`}
          >
            {inBasket ? '已加入选题篮' : '加入选题篮'}
          </button>
        </div>
      </div>

      {showAnswer && (question.answer || question.analysis) && (
        <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-4 py-3">
          {question.answer && (
            <div className="mb-2">
              <div className="mb-1 text-xs font-semibold tracking-wide text-[var(--color-green)]">答案</div>
              <div className="text-sm leading-7 text-[var(--color-text-main)]">
                <LatexRenderer text={question.answer} />
              </div>
            </div>
          )}
          {question.analysis && (
            <div>
              <div className="mb-1 text-xs font-semibold tracking-wide text-[var(--color-accent)]">解析摘要</div>
              <div className="line-clamp-4 text-sm leading-7 text-[var(--color-text-secondary)]">
                <LatexRenderer text={question.analysis} />
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
      className="cursor-pointer border-none bg-transparent p-0 text-sm text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-accent)]"
    >
      {children}
    </button>
  );
}
