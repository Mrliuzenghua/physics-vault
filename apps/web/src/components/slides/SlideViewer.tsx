import type { Question, SlidesDisplayMode } from '../../types';

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multi_choice: '多选题',
  fill: '填空题',
  experiment: '实验题',
  calculation: '计算题',
};

interface SlideViewerProps {
  question: Question;
  index: number;
  total: number;
  displayMode: SlidesDisplayMode;
  zoomLevel: number;
  fitToViewport?: boolean;
}

export default function SlideViewer({
  question,
  index,
  total,
  displayMode,
  zoomLevel,
  fitToViewport = false,
}: SlideViewerProps) {
  const showAnswer = displayMode === 'stem_answer' || displayMode === 'full';
  const showAnalysis = displayMode === 'full';

  const typeLabel = TYPE_LABELS[question.question_type] || question.question_type;
  const scale = Math.max(0.5, Math.min(2.0, zoomLevel));
  const baseFontSize = `${Math.round(20 * scale)}px`;
  const largeFontSize = `${Math.round(24 * scale)}px`;
  const smallFontSize = `${Math.round(15 * scale)}px`;

  return (
    <div className="flex-1 overflow-y-auto">
      <div
        style={{
          width: fitToViewport ? '100vw' : '100%',
          height: fitToViewport ? '100vh' : undefined,
          maxWidth: fitToViewport ? 'none' : 1280,
          margin: '0 auto',
          padding: fitToViewport ? 0 : '24px 16px',
          display: fitToViewport ? 'flex' : undefined,
          alignItems: fitToViewport ? 'center' : undefined,
          justifyContent: fitToViewport ? 'center' : undefined,
        }}
      >
        {/* 16:9 slide frame */}
        <div
          style={{
            aspectRatio: '16 / 9',
            width: fitToViewport ? 'min(100vw, calc(100vh * 16 / 9))' : '100%',
            height: fitToViewport ? 'min(100vh, calc(100vw * 9 / 16))' : undefined,
            maxHeight: fitToViewport ? 'none' : 'calc(100vh - 96px)',
            display: 'flex',
            flexDirection: 'column',
            background: 'linear-gradient(135deg, #f8fafc 0%, #ffffff 50%, #f1f5f9 100%)',
            borderRadius: fitToViewport ? 0 : 16,
            boxShadow: fitToViewport ? 'none' : '0 4px 24px rgba(15, 23, 42, 0.10), 0 1px 4px rgba(15, 23, 42, 0.06)',
            border: '1px solid #e2e8f0',
            overflow: 'hidden',
          }}
        >
          <div
            className="flex-1 overflow-y-auto"
            style={{
              fontSize: baseFontSize,
              lineHeight: 1.8,
            }}
          >
            <div
              className="mx-auto px-8 py-6"
              style={{ maxWidth: 960 }}
            >
        {/* ── Header: question number + type ── */}
        <div
          className="mb-4 flex items-center gap-3"
          style={{ fontSize: smallFontSize }}
        >
          <span
            className="rounded-full px-3 py-0.5 font-bold"
            style={{
              background: 'var(--color-accent-light)',
              color: 'var(--color-accent)',
            }}
          >
            第 {index + 1} / {total} 题
          </span>
          <span
            className="rounded px-2 py-0.5"
            style={{
              background: 'var(--color-bg-hover)',
              color: 'var(--color-text-muted)',
            }}
          >
            {typeLabel}
          </span>
          {question.difficulty > 0 && (
            <span
              className="rounded px-2 py-0.5"
              style={{
                background: 'var(--color-bg-hover)',
                color: 'var(--color-text-muted)',
              }}
            >
              难度 {question.difficulty}
            </span>
          )}
          {question.source && (
            <span
              style={{
                color: 'var(--color-text-muted)',
                opacity: 0.7,
              }}
            >
              {question.source}
            </span>
          )}
        </div>

        {/* ── Stem ── */}
        <div
          className="mb-5 rounded-xl p-6"
          style={{
            background: 'var(--color-bg-card)',
            boxShadow: 'var(--shadow-card)',
            fontSize: largeFontSize,
            fontWeight: 500,
            lineHeight: 2,
          }}
        >
          <div
            className="whitespace-pre-wrap"
            style={{ color: 'var(--color-text)' }}
          >
            {question.title || '(无题干)'}
          </div>

          {/* Inline figure placeholders */}
          {renderFigurePlaceholders(question)}
        </div>

        {/* ── Options ── */}
        {question.options.length > 0 && (
          <div
            className="mb-5 grid gap-3"
            style={{
              gridTemplateColumns:
                question.options.length <= 2 ? '1fr 1fr' : '1fr',
            }}
          >
            {question.options.map((opt) => (
              <div
                key={opt.opt}
                className="flex items-start gap-3 rounded-lg p-4"
                style={{
                  background: 'var(--color-bg-card)',
                  boxShadow: 'var(--shadow-card)',
                }}
              >
                <span
                  className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold"
                  style={{
                    background: 'var(--color-accent-light)',
                    color: 'var(--color-accent)',
                  }}
                >
                  {opt.opt}
                </span>
                <span
                  className="flex-1 whitespace-pre-wrap"
                  style={{ color: 'var(--color-text)' }}
                >
                  {opt.content}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* ── Sub-questions ── */}
        {question.sub_questions.length > 0 && (
          <div className="mb-5 space-y-4">
            {question.sub_questions.map((sq, i) => (
              <div
                key={sq.sub_id || i}
                className="rounded-lg p-4"
                style={{
                  background: 'var(--color-bg-card)',
                  boxShadow: 'var(--shadow-card)',
                  borderLeft: '4px solid var(--color-accent)',
                }}
              >
                <div
                  className="mb-2 font-semibold"
                  style={{ color: 'var(--color-accent)' }}
                >
                  {sq.sub_id || `(${i + 1})`}
                </div>
                <div
                  className="mb-2 whitespace-pre-wrap"
                  style={{ color: 'var(--color-text)' }}
                >
                  {sq.title}
                </div>
                {showAnswer && sq.answer && (
                  <div
                    className="mt-2 rounded p-3"
                    style={{
                      background: 'var(--color-green-light)',
                      color: 'var(--color-green)',
                      fontSize: smallFontSize,
                    }}
                  >
                    <span className="font-bold">答案：</span>
                    {sq.answer}
                  </div>
                )}
                {showAnalysis && sq.analysis && (
                  <div
                    className="mt-2 rounded p-3 whitespace-pre-wrap"
                    style={{
                      background: 'var(--color-bg-code)',
                      color: 'var(--color-text-secondary)',
                      fontSize: smallFontSize,
                    }}
                  >
                    <span className="font-bold">解析：</span>
                    {sq.analysis}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ── Answer ── */}
        {showAnswer && question.answer && (
          <div
            className="mb-5 rounded-xl p-6"
            style={{
              background: 'var(--color-green-light)',
              borderLeft: '6px solid var(--color-green)',
            }}
          >
            <div
              className="mb-1 text-sm font-bold"
              style={{ color: 'var(--color-green)' }}
            >
              答案
            </div>
            <div
              className="whitespace-pre-wrap font-medium"
              style={{ color: 'var(--color-text)', fontSize: largeFontSize }}
            >
              {question.answer}
            </div>
          </div>
        )}

        {/* ── Analysis ── */}
        {showAnalysis && question.analysis && (
          <div
            className="mb-5 rounded-xl p-6"
            style={{
              background: 'var(--color-bg-code)',
              border: '1px solid var(--color-border)',
            }}
          >
            <div
              className="mb-1 text-sm font-bold"
              style={{ color: 'var(--color-text-muted)' }}
            >
              解析
            </div>
            <div
              className="whitespace-pre-wrap leading-relaxed"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {question.analysis}
            </div>
          </div>
        )}

        {/* ── Knowledge point + tags ── */}
        {(question.knowledge_points.length > 0 || question.tags.length > 0) && (
          <div
            className="flex flex-wrap items-center gap-2"
            style={{ fontSize: smallFontSize }}
          >
            {question.knowledge_points.map((kp) => (
              <span
                key={kp.rank}
                className="rounded-full px-3 py-1"
                style={{
                  background: 'var(--color-accent-light)',
                  color: 'var(--color-accent-dark)',
                }}
              >
                {kp.topic3_name || kp.topic2_name || kp.topic1_name}
              </span>
            ))}
            {question.tags.map((tag, i) => (
              <span
                key={`${tag}-${i}`}
                className="rounded-full px-3 py-1"
                style={{
                  background: 'var(--color-bg-hover)',
                  color: 'var(--color-text-muted)',
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Show figure references found in the question title. */
function renderFigurePlaceholders(question: Question) {
  const refs = question.title.match(/!\[fig:([^\]]+)\]/g);
  if (!refs || refs.length === 0) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2" style={{ fontSize: '0.75em' }}>
      {refs.map((ref, i) => {
        const uuid = ref.match(/!\[fig:([^\]]+)\]/)?.[1] || ref;
        const fig = question.figures.find((f) => f.fig_uuid === uuid);
        return (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded px-2 py-1"
            style={{
              background: 'var(--color-orange-light)',
              color: 'var(--color-orange)',
            }}
          >
            📷 {fig?.local_path || uuid}
          </span>
        );
      })}
    </div>
  );
}
