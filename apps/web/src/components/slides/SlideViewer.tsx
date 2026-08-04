import type { Question, SlidesDisplayMode } from '../../types';
import { imageFileUrl } from '../../utils/imageUrl';
import LatexRenderer from '../render/LatexRenderer';

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
  revealStep?: number;
}

export default function SlideViewer({
  question,
  index,
  total,
  displayMode,
  zoomLevel,
  fitToViewport = false,
  revealStep,
}: SlideViewerProps) {
  const maxRevealStep = displayMode === 'full' ? 2 : displayMode === 'stem_answer' ? 1 : 0;
  const activeRevealStep = Math.max(0, Math.min(revealStep ?? maxRevealStep, maxRevealStep));
  const showOptions = true;
  const showAnswer = activeRevealStep >= 1 && displayMode !== 'stem_only';
  const showAnalysis = activeRevealStep >= 2 && displayMode === 'full';

  const typeLabel = TYPE_LABELS[question.question_type] || question.question_type;
  const scale = Math.max(0.5, Math.min(2.0, zoomLevel));
  const baseFontSize = fitToViewport ? 'clamp(28px, 2.15vw, 44px)' : `${Math.round(20 * scale)}px`;
  const largeFontSize = fitToViewport ? 'clamp(32px, 2.55vw, 52px)' : `${Math.round(24 * scale)}px`;
  const smallFontSize = fitToViewport ? 'clamp(18px, 1.3vw, 24px)' : `${Math.round(15 * scale)}px`;
  const figureMap = new Map(question.figures.map((figure) => [figure.fig_uuid, figure]));
  const optionFigureIds = new Set(question.options.flatMap((option) => extractFigureIds(option.content)));
  const stemFigureIds = extractFigureIds(question.title || question.stem_text);
  const figures = Array.from(new Map((stemFigureIds.length > 0
    ? stemFigureIds.map((id) => figureMap.get(id)).filter(Boolean)
    : question.figures.filter((figure) => !optionFigureIds.has(figure.fig_uuid)))
    .filter((figure) => Boolean(imageFileUrl(figure!.local_path)))
    .map((figure) => [figure!.local_path || figure!.fig_uuid, figure!])).values()).slice(0, 2);
  const hasFigures = figures.length > 0;
  const optionsHaveFigures = optionFigureIds.size > 0;
  const cleanAnalysis = stripFigurePlaceholders(question.analysis || '');

  return (
    <div className="flex-1 overflow-y-auto">
      <div
        style={{
          width: fitToViewport ? '100vw' : '100%',
          height: fitToViewport ? '100vh' : undefined,
          maxWidth: fitToViewport ? 'none' : 1600,
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
            background: '#f8fafc',
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
              className="mx-auto"
              style={{
                maxWidth: fitToViewport
                  ? (hasFigures ? 'min(96vw, 1840px)' : 'min(88vw, 1540px)')
                  : (hasFigures ? 'min(100%, 1440px)' : 1120),
                padding: fitToViewport ? 'clamp(24px, 2.25vw, 44px)' : '24px 32px',
                minHeight: '100%',
                boxSizing: 'border-box',
                display: 'flex',
                flexDirection: 'column',
              }}
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
          className="mb-5"
          style={{
            display: hasFigures ? 'grid' : 'block',
            gridTemplateColumns: hasFigures ? 'minmax(0, 1.15fr) minmax(420px, 0.95fr)' : undefined,
            gap: hasFigures ? 'clamp(20px, 2.2vw, 40px)' : undefined,
            alignItems: 'center',
          }}
        >
          <div
            style={{
              display: hasFigures ? 'flex' : undefined,
              alignItems: hasFigures ? 'center' : undefined,
              background: fitToViewport ? 'transparent' : 'var(--color-bg-card)',
              boxShadow: fitToViewport ? 'none' : 'var(--shadow-card)',
              borderRadius: fitToViewport ? 0 : 12,
              padding: fitToViewport ? 0 : 24,
              fontSize: largeFontSize,
              fontWeight: 500,
              lineHeight: 2,
            }}
          >
          <LatexRenderer
            className="slide-question-content"
            text={stripFigurePlaceholders(question.title || question.stem_text || '(无题干)')}
          />

          {/* Inline figure placeholders */}
          </div>
          {hasFigures && <QuestionFigurePanel figures={figures} />}
        </div>

        {/* ── Options ── */}
        {showOptions && question.options.length > 0 && (
          <div
            className="mb-5 grid gap-3"
            style={{
              gridTemplateColumns: question.options.length > 1 ? 'repeat(2, minmax(0, 1fr))' : '1fr',
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
                <div className="min-w-0 flex-1">
                  {stripFigurePlaceholders(opt.content) && (
                    <LatexRenderer inline className="slide-question-content" text={stripFigurePlaceholders(opt.content)} />
                  )}
                  {extractFigureIds(opt.content).map((figureId) => {
                    const figure = figureMap.get(figureId);
                    const src = imageFileUrl(figure?.local_path);
                    return src ? (
                      <img
                        key={figureId}
                        src={src}
                        alt={`${opt.opt} 选项图`}
                        style={{
                          display: 'block',
                          width: 'auto',
                          maxWidth: '100%',
                          maxHeight: optionsHaveFigures ? 'min(24vh, 240px)' : 'min(32vh, 320px)',
                          objectFit: 'contain',
                          marginTop: 8,
                        }}
                      />
                    ) : null;
                  })}
                </div>
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
                <LatexRenderer
                  className="mb-2 slide-question-content"
                  text={sq.title}
                />
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
                    <LatexRenderer inline text={sq.answer} />
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
                    <LatexRenderer inline text={stripFigurePlaceholders(sq.analysis)} />
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
            <LatexRenderer
              className="font-medium slide-question-content"
              text={question.answer}
              style={{ color: 'var(--color-text)', fontSize: largeFontSize }}
            />
          </div>
        )}

        {/* ── Analysis ── */}
        {showAnalysis && cleanAnalysis && (
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
            <LatexRenderer
              className="leading-relaxed slide-question-content"
              text={cleanAnalysis}
              style={{ color: 'var(--color-text-secondary)' }}
            />
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

function stripFigurePlaceholders(text: string): string {
  return text.replace(/!\[fig:[^\]]+\]/g, '').replace(/\n{3,}/g, '\n\n').trim();
}

function extractFigureIds(text?: string | null): string[] {
  return Array.from(String(text || '').matchAll(/!\[fig:([^\]]+)\]/g), (match) => match[1]);
}

function QuestionFigurePanel({ figures }: { figures: Question['figures'] }) {
  return (
    <div
      style={{
        height: '100%',
        display: 'grid',
        gridTemplateColumns: figures.length > 1 ? 'repeat(2, minmax(0, 1fr))' : '1fr',
        gap: 16,
        alignItems: 'center',
        alignContent: 'center',
      }}
    >
      {figures.map((figure, index) => (
        <figure
          key={figure.fig_uuid}
          style={{
            margin: 0,
            minWidth: 0,
            border: '1px solid #d7e0eb',
            background: '#ffffff',
            padding: 12,
          }}
        >
          <img
            src={imageFileUrl(figure.local_path) || ''}
            alt={`题图 ${index + 1}`}
            style={{
              display: 'block',
              width: `${Math.min(100, Math.max(25, figure.display_scale ?? 100))}%`,
              maxWidth: '100%',
              maxHeight: `min(${Math.round(42 * ((figure.display_scale ?? 100) / 100))}vh, 460px)`,
              objectFit: 'contain',
              margin: '0 auto',
            }}
          />
        </figure>
      ))}
    </div>
  );
}
