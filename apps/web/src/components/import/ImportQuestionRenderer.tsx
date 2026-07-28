import type { Question } from '../../types';
import LatexRenderer from '../render/LatexRenderer';

interface Props {
  questions: Question[];
  onEnterReview?: () => void;
  reviewDisabled?: boolean;
}

function renderTextWithFigures(text: string, figures: Question['figures']) {
  if (!text) {
    return <LatexRenderer text="（无题干）" />;
  }

  const figureMap = new Map(figures.map((figure) => [figure.fig_uuid, figure]));
  const parts = text.split(/(!\[fig:[^\]]+\])/g).filter(Boolean);

  return (
    <div className="space-y-3">
      {parts.map((part, index) => {
        const match = part.match(/^!\[fig:([^\]]+)\]$/);
        if (!match) {
          return <LatexRenderer key={`${index}-text`} text={part} />;
        }

        const figure = figureMap.get(match[1]);
        if (!figure?.local_path) {
          return (
            <div
              key={`${index}-missing`}
              className="rounded border px-3 py-2 text-xs"
              style={{ borderColor: 'var(--color-orange)', color: 'var(--color-orange)' }}
            >
              图片占位符未匹配：{match[1]}
            </div>
          );
        }

        return <QuestionFigure key={`${index}-figure`} figure={figure} />;
      })}
    </div>
  );
}

function QuestionFigure({ figure }: { figure: Question['figures'][number] }) {
  return (
    <figure
      className="mx-auto max-w-2xl rounded border p-3"
      style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
    >
      <img
        src={`/files/${figure.local_path}`}
        alt={figure.fig_uuid}
        className="mx-auto max-h-80 w-full object-contain"
      />
      <figcaption className="mt-2 text-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
        {figure.fig_uuid}
      </figcaption>
    </figure>
  );
}

export default function ImportQuestionRenderer({ questions, onEnterReview, reviewDisabled }: Props) {
  if (questions.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="text-3xl font-semibold" style={{ color: 'var(--color-text-muted)' }}>0</div>
          <p className="mt-1 text-sm" style={{ color: 'var(--color-text-muted)' }}>
            暂无可渲染题目
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div
        className="sticky top-0 z-10 flex items-center justify-between border-b py-3"
        style={{ background: 'var(--color-bg)', borderColor: 'var(--color-border)' }}
      >
        <div>
          <h2 className="text-base font-bold" style={{ color: 'var(--color-text)' }}>
            导入识别渲染预览
          </h2>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            已识别 {questions.length} 题，确认后进入校对中心精修。
          </p>
        </div>
        <button
          onClick={onEnterReview}
          disabled={reviewDisabled}
          className="cursor-pointer rounded border-none px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--color-accent)' }}
        >
          进入校对中心
        </button>
      </div>

      {questions.map((question, index) => (
        <article
          key={question.question_id || index}
          className="rounded-lg border"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', boxShadow: 'var(--shadow-card)' }}
        >
          <header
            className="flex flex-wrap items-center gap-2 border-b px-4 py-3"
            style={{ borderColor: 'var(--color-border)' }}
          >
            <span className="rounded px-2 py-0.5 text-xs font-semibold text-white" style={{ background: 'var(--color-accent)' }}>
              第 {index + 1} 题
            </span>
            <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              {question.question_type || '未判定题型'}
            </span>
            {question.figures?.length > 0 && (
              <span className="rounded px-2 py-0.5 text-xs" style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}>
                {question.figures.length} 张图
              </span>
            )}
          </header>

          <section className="px-5 py-4">
            <div className="text-base leading-loose" style={{ color: 'var(--color-text)' }}>
              {renderTextWithFigures(question.title, question.figures || [])}
            </div>

            {question.figures?.length > 0 && !question.title.includes('![fig:') && (
              <div className="mt-4 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                {question.figures.map((figure) => (
                  <QuestionFigure key={figure.fig_uuid || figure.local_path} figure={figure} />
                ))}
              </div>
            )}

            {question.options?.length > 0 && (
              <div className="mt-4 grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                {question.options.map((option, optionIndex) => (
                  <div
                    key={`${option.opt}-${optionIndex}`}
                    className="flex gap-2 rounded border p-3 text-sm"
                    style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
                  >
                    <span className="font-semibold" style={{ color: 'var(--color-accent)' }}>
                      {option.opt}.
                    </span>
                    <LatexRenderer text={option.content} />
                  </div>
                ))}
              </div>
            )}
          </section>

          {(question.answer || question.analysis) && (
            <section
              className="border-t px-5 py-4"
              style={{ borderColor: 'var(--color-green)', background: 'var(--color-green-light)' }}
            >
              {question.answer && (
                <div className="mb-3">
                  <div className="mb-1 text-xs font-semibold" style={{ color: 'var(--color-green)' }}>答案</div>
                  <LatexRenderer text={String(question.answer)} />
                </div>
              )}
              {question.analysis && (
                <div>
                  <div className="mb-1 text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>解析</div>
                  <LatexRenderer text={String(question.analysis)} />
                </div>
              )}
            </section>
          )}
        </article>
      ))}
    </div>
  );
}
