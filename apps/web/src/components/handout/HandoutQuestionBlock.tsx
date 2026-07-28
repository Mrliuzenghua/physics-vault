import type { HandoutConfig, Question } from '../../types';
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

  return (
    <div
      className="question-block"
      style={{
        breakInside: 'avoid',
        pageBreakInside: 'avoid',
        marginBottom: sc.questionSpacing,
        padding: '8px 0 10px',
        borderBottom: '1px solid #e2e8f0',
      }}
    >
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
      </div>

      {/* Stem */}
      <div
        style={{
          fontSize: fs,
          lineHeight: lh,
          color: 'var(--color-text, #1f2333)',
          marginBottom: sc.paragraphSpacing,
        }}
      >
        <LatexRenderer text={question.title || question.stem_text || ''} />
      </div>

      {/* Figures — placed between stem and options, matching QuestionCard / QuestionContentCard */}
      {question.figures && question.figures.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 10,
            marginBottom: sc.paragraphSpacing,
          }}
        >
          {question.figures.map((fig) => (
            <div
              key={fig.fig_uuid}
              style={{
                maxWidth: `${48 * sc.figureScale}%`,
                borderRadius: 0,
                border: '1px solid var(--color-border, #e3e7ee)',
                overflow: 'hidden',
                background: '#fff',
              }}
            >
              {fig.local_path ? (
                <img
                  src={`/files/${fig.local_path}`}
                  alt={fig.fig_uuid}
                  style={{
                    width: '100%',
                    maxHeight: '90mm',
                    objectFit: 'contain',
                    display: 'block',
                  }}
                  onError={(e) => {
                    const el = e.currentTarget;
                    el.style.display = 'none';
                    const placeholder = el.nextElementSibling;
                    if (placeholder) (placeholder as HTMLElement).style.display = 'flex';
                  }}
                />
              ) : null}
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

      {/* Options */}
      {question.options && question.options.length > 0 && (
        <div style={{ marginBottom: sc.paragraphSpacing, paddingLeft: 16 }}>
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
              <span style={{ fontWeight: 600, flexShrink: 0 }}>{opt.opt}.</span>
              <LatexRenderer text={opt.content} inline />
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
                  解析：<LatexRenderer text={sub.analysis} inline />
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
      {config.showAnalysis && question.analysis && (
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
          <LatexRenderer text={question.analysis} inline />
        </div>
      )}
    </div>
  );
}
