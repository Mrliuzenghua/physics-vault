import type { HandoutConfig, Question } from '../../types';
import { imageFileUrl } from '../../utils/imageUrl';
import { getQuestionSourceLabel } from '../../utils/questionSource';
import LatexRenderer from '../render/LatexRenderer';

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multi_choice: '多选题',
  fill: '填空题',
  experiment: '实验题',
  calculation: '计算题',
};

const NUMBER_CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩',
  '⑪', '⑫', '⑬', '⑭', '⑮', '⑯', '⑰', '⑱', '⑲', '⑳'];

function formatQuestionNumber(index: number, style: string): string {
  switch (style) {
    case 'circled':
      return NUMBER_CIRCLED[index - 1] || `${index}`;
    case 'bracket':
      return `(${index})`;
    default:
      return `${index}.`;
  }
}

function stripFigurePlaceholders(text?: string | null): string {
  return String(text || '').replace(/!\[fig:[^\]]+\]/g, '').replace(/\n{3,}/g, '\n\n').trim();
}

function extractFigureIds(text?: string | null): string[] {
  return Array.from(String(text || '').matchAll(/!\[fig:([^\]]+)\]/g), (match) => match[1]);
}

interface Props {
  question: Question;
  index: number;
  config: HandoutConfig;
}

export default function HandoutQuestionBlock({ question, index, config }: Props) {
  const typeLabel = TYPE_LABELS[question.question_type] || '题目';
  const sc = config.styleConfig;
  const fs = sc.fontSize;
  const lh = sc.lineHeight;
  const sourceLabel = getQuestionSourceLabel(question, '未标注来源');
  const cleanStem = stripFigurePlaceholders(question.title || question.stem_text || '');
  const cleanAnalysis = stripFigurePlaceholders(question.analysis);
  const figureMap = new Map((question.figures || []).map((figure) => [figure.fig_uuid, figure]));
  const optionFigureIds = new Set((question.options || []).flatMap((option) => extractFigureIds(option.content)));
  const stemFigureIds = extractFigureIds(question.title || question.stem_text);
  const visibleFigures = Array.from(new Map((stemFigureIds.length > 0
    ? stemFigureIds.map((id) => figureMap.get(id)).filter(Boolean)
    : (question.figures || []).filter((figure) => !optionFigureIds.has(figure.fig_uuid)))
    .filter((figure) => Boolean(imageFileUrl(figure!.local_path)))
    .map((figure) => [figure!.local_path || figure!.fig_uuid, figure!])).values());
  const optionsHaveFigures = optionFigureIds.size > 0;
  const isExperiment = question.question_type === 'experiment';
  const longestOptionLength = Math.max(0, ...(question.options || []).map((option) => stripFigurePlaceholders(option.content).length));
  // A two-column arrangement is a layout choice, not a question-type signal.
  // Keep single-choice options vertical in auto mode so they cannot be mistaken
  // for a multi-choice question; an explicit "双列" setting still wins.
  const useOptionColumns = sc.optionLayout === 'double'
    || (sc.optionLayout !== 'single'
      && question.question_type === 'multi_choice'
      && (optionsHaveFigures || ((question.options || []).length === 4 && longestOptionLength <= 26)));

  return (
    <div
      className={`question-block pv-handout-question${visibleFigures.length > 0 ? ' pv-handout-question--with-figures' : ''}`}
      style={{
        breakInside: 'avoid',
        pageBreakInside: 'avoid',
        marginBottom: sc.questionSpacing,
        padding: '8px 0 10px',
        borderBottom: '1px solid #e2e8f0',
      }}
    >
      <div className="pv-question-leading">
        {/* Question header: number + type */}
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 8,
            marginBottom: sc.paragraphSpacing,
          }}
        >
        <span
          style={{
            fontWeight: 700,
            fontSize: fs + 1,
            color: 'var(--color-text, #1f2333)',
          }}
        >
          {formatQuestionNumber(index, sc.questionNumberStyle)}
        </span>
        <span
          style={{
            fontSize: fs - 2,
            color: 'var(--color-text-muted, #98a0b3)',
          }}
        >
          {typeLabel}
        </span>
        <span
          style={{
            marginLeft: 'auto',
            maxWidth: '68%',
            fontSize: Math.max(10, fs - 2),
            color: 'var(--color-text-secondary, #4b5563)',
            textAlign: 'right',
            overflowWrap: 'anywhere',
          }}
        >
          来源：{sourceLabel}
        </span>
        </div>

      <div className="pv-question-stem-figure">
        {/* Stem */}
        <div
          style={{
            fontSize: fs,
            lineHeight: lh,
            color: 'var(--color-text, #1f2333)',
            marginBottom: sc.paragraphSpacing,
          }}
        >
          <LatexRenderer text={cleanStem} />
        </div>

      {/* Figures — placed between stem and options, matching QuestionCard / QuestionContentCard */}
      {visibleFigures.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: visibleFigures.length > 1 ? 'repeat(2, minmax(0, 1fr))' : 'minmax(0, 1fr)',
            gap: 10,
            marginBottom: sc.paragraphSpacing,
            justifyItems: visibleFigures.length > 1 ? 'center' : visibleFigures[0]?.display_align === 'left' ? 'start' : visibleFigures[0]?.display_align === 'right' ? 'end' : 'center',
            alignItems: 'center',
          }}
        >
          {visibleFigures.slice(0, 3).map((fig) => (
            <div
              key={fig.fig_uuid}
              style={{
                width: visibleFigures.length > 1 ? `${Math.min(100, Math.round(100 * sc.figureScale * ((fig.display_scale || 60) / 60)))}%` : `${Math.min(100, Math.round(72 * sc.figureScale * ((fig.display_scale || 60) / 60)))}%`,
                maxWidth: visibleFigures.length > 1 ? '76mm' : '128mm',
                borderRadius: 0,
                border: '1px solid var(--color-border, #e3e7ee)',
                overflow: 'hidden',
                background: '#fff',
                padding: 4,
              }}
            >
              {fig.local_path ? (
                <img
                  src={imageFileUrl(fig.local_path) || ''}
                  alt={fig.fig_uuid}
                  style={{
                    width: 'auto',
                    maxWidth: '100%',
                    maxHeight: `${Math.round((visibleFigures.length > 1 ? 48 : 62) * ((fig.display_scale || 60) / 60))}mm`,
                    objectFit: 'contain',
                    display: 'block',
                    margin: '0 auto',
                  }}
                  onError={(e) => {
                    const el = e.currentTarget;
                    el.style.display = 'none';
                    const placeholder = el.nextElementSibling;
                    if (placeholder) (placeholder as HTMLElement).style.display = 'flex';
                  }}
                />
              ) : null}
              {fig.caption && <div style={{ marginTop: 4, textAlign: 'center', color: 'var(--color-text-muted, #64748b)', fontSize: Math.max(10, fs - 2), lineHeight: 1.5 }}>{fig.caption}</div>}
              <div
                style={{
                  display: fig.local_path ? 'none' : 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  minHeight: 80 * sc.figureScale,
                  background: 'var(--color-bg-code, #f0f2f5)',
                  color: 'var(--color-text-muted, #98a0b3)',
                  fontSize: fs - 2,
                }}
              >
                题图 {fig.fig_uuid}
              </div>
            </div>
          ))}
        </div>
      )}
        </div>
      </div>

      {/* Choice options or experiment procedures */}
      {question.options && question.options.length > 0 && (
        <div style={{
          marginBottom: sc.paragraphSpacing,
          paddingLeft: isExperiment ? 0 : 16,
          display: !isExperiment && useOptionColumns ? 'grid' : 'block',
          gridTemplateColumns: !isExperiment && useOptionColumns ? 'repeat(2, minmax(0, 1fr))' : undefined,
          gap: !isExperiment && useOptionColumns ? '8px 12px' : undefined,
        }}>
          {isExperiment && <div style={{ marginBottom: 6, fontSize: fs - 1, fontWeight: 700, color: 'var(--color-text-secondary, #4b5563)' }}>实验步骤</div>}
          {question.options.map((opt, i) => (
            <div
              key={opt.opt ?? i}
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 6,
                fontSize: fs,
                lineHeight: lh,
                color: 'var(--color-text, #1f2333)',
                marginBottom: 2,
              }}
            >
              <span style={{ fontWeight: 600, flexShrink: 0 }}>{isExperiment ? `（${i + 1}）` : `${opt.opt}.`}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                {stripFigurePlaceholders(opt.content) && <LatexRenderer text={stripFigurePlaceholders(opt.content)} inline />}
                {extractFigureIds(opt.content).map((figureId) => {
                  const figure = figureMap.get(figureId);
                  const src = imageFileUrl(figure?.local_path);
                  return src ? (
                    <img
                      key={figureId}
                      src={src}
                      alt={`${opt.opt} 选项图`}
                      style={{ display: 'block', width: 'auto', maxWidth: '100%', maxHeight: '34mm', objectFit: 'contain', marginTop: 4 }}
                    />
                  ) : null;
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Sub-questions */}
      {question.sub_questions && question.sub_questions.length > 0 && (
        <div style={{ marginBottom: sc.paragraphSpacing, paddingLeft: 8 }}>
          {question.sub_questions.map((sub) => (
            <div
              key={sub.sub_id}
              style={{
                marginBottom: 8,
                padding: '4px 0 6px 10px',
                borderLeft: '2px solid #cbd5e1',
              }}
            >
              <div
                style={{
                  fontSize: fs - 1,
                  fontWeight: 600,
                  marginBottom: 4,
                  color: 'var(--color-text, #1f2333)',
                }}
              >
                <LatexRenderer text={sub.title} />
              </div>
              {config.showAnswers && (
                <div
                  style={{
                    fontSize: fs - 1,
                    color: 'var(--color-green, #1e9e50)',
                  }}
                >
                  答案：<LatexRenderer text={sub.answer || '（暂无）'} inline />
                </div>
              )}
              {config.showAnalysis && sub.analysis && (
                <div
                  style={{
                    fontSize: fs - 2,
                    color: 'var(--color-text-secondary, #5a6172)',
                    marginTop: 2,
                  }}
                >
                  解析：<LatexRenderer text={stripFigurePlaceholders(sub.analysis)} inline />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Answer (teacher version) */}
      {config.showAnswers && question.answer && (
        <div
          style={{
            fontSize: fs - 1,
            lineHeight: lh,
            color: 'var(--color-green, #1e9e50)',
            marginBottom: 2,
            paddingLeft: 8,
          }}
        >
          <span style={{ fontWeight: 600 }}>答案：</span>
          <LatexRenderer text={question.answer} inline />
        </div>
      )}

      {/* Analysis (teacher version) */}
      {config.showAnalysis && cleanAnalysis && (
        <div
          style={{
            fontSize: fs - 2,
            lineHeight: lh,
            color: 'var(--color-text-secondary, #5a6172)',
            marginTop: 4,
            padding: '4px 0 0 8px',
            borderLeft: '2px solid #d8dee8',
          }}
        >
          <span style={{ fontWeight: 600 }}>解析：</span>
          <LatexRenderer text={cleanAnalysis} inline />
        </div>
      )}
    </div>
  );
}
