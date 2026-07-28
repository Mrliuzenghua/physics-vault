import type { HandoutConfig } from '../../types';

interface Props {
  config: HandoutConfig;
  onChangeConfig: (updates: Partial<HandoutConfig>) => void;
  questionCount: number;
  onPrint: () => void;
}

export default function HandoutToolbar({
  config,
  onChangeConfig,
  questionCount,
  onPrint,
}: Props) {
  const isTeacher = config.showAnswers;

  return (
    <div
      className="flex-shrink-0 border-b px-4 py-2"
      style={{
        borderColor: 'var(--color-border)',
        background: 'var(--color-bg-card)',
      }}
    >
      <div className="flex items-center justify-between gap-4">
        {/* Left: title config */}
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={config.title}
            onChange={(e) => onChangeConfig({ title: e.target.value })}
            placeholder="讲义标题"
            className="rounded border px-2.5 py-1.5 text-sm outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-card)',
              color: 'var(--color-text)',
              width: 200,
            }}
          />
          <input
            type="text"
            value={config.subtitle}
            onChange={(e) => onChangeConfig({ subtitle: e.target.value })}
            placeholder="副标题（可选）"
            className="rounded border px-2.5 py-1.5 text-sm outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-card)',
              color: 'var(--color-text)',
              width: 160,
            }}
          />
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {questionCount} 题
          </span>
        </div>

        {/* Right: mode toggle + print */}
        <div className="flex items-center gap-2">
          {/* Student / Teacher toggle */}
          <div
            className="flex rounded-lg border overflow-hidden"
            style={{ borderColor: 'var(--color-border)' }}
          >
            <button
              onClick={() => onChangeConfig({ showAnswers: false, showAnalysis: false })}
              className="cursor-pointer border-none px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                background: !isTeacher ? 'var(--color-accent)' : 'transparent',
                color: !isTeacher ? '#fff' : 'var(--color-text-secondary)',
              }}
            >
              学生版
            </button>
            <button
              onClick={() => onChangeConfig({ showAnswers: true, showAnalysis: true })}
              className="cursor-pointer border-none px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                background: isTeacher ? 'var(--color-accent)' : 'transparent',
                color: isTeacher ? '#fff' : 'var(--color-text-secondary)',
              }}
            >
              教师版
            </button>
          </div>

          {/* Print */}
          <button
            onClick={onPrint}
            className="cursor-pointer rounded-lg border-none px-4 py-1.5 text-xs font-semibold text-white transition-colors"
            style={{ background: 'var(--color-accent)' }}
          >
            打印讲义
          </button>
        </div>
      </div>
    </div>
  );
}
