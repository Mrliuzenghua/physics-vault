import type { SlidesDisplayMode } from '../../types';

const MODE_OPTIONS: { value: SlidesDisplayMode; label: string }[] = [
  { value: 'stem_only', label: '仅题干' },
  { value: 'stem_answer', label: '题干 + 答案' },
  { value: 'full', label: '完整解析' },
];

interface SlidesToolbarProps {
  displayMode: SlidesDisplayMode;
  onModeChange: (mode: SlidesDisplayMode) => void;
  zoomLevel: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
  onFullscreen: () => void;
  questionCount: number;
  title?: string;
}

export default function SlidesToolbar({
  displayMode,
  onModeChange,
  zoomLevel,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  onFullscreen,
  questionCount,
  title,
}: SlidesToolbarProps) {
  return (
    <div
      className="flex flex-shrink-0 items-center gap-3 px-4 py-3"
      style={{
        background: 'var(--color-bg-card)',
        borderBottom: '1px solid var(--color-border)',
      }}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>
          {title || '课堂幻灯预览'}
        </span>
        <span
          className="rounded-full px-2 py-0.5 text-xs"
          style={{
            background: 'var(--color-accent-light)',
            color: 'var(--color-accent)',
          }}
        >
          {questionCount} 道题
        </span>
      </div>

      <div className="flex-1" />

      <div
        className="flex overflow-hidden rounded-md"
        style={{ border: '1px solid var(--color-border)' }}
      >
        {MODE_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onModeChange(option.value)}
            className="cursor-pointer border-none px-3 py-1 text-xs font-medium transition-colors"
            style={{
              background: displayMode === option.value ? 'var(--color-accent)' : 'var(--color-bg)',
              color: displayMode === option.value ? '#fff' : 'var(--color-text-secondary)',
              borderRight: option.value !== 'full' ? '1px solid var(--color-border)' : 'none',
            }}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onZoomOut}
          className="cursor-pointer rounded border-none px-2 py-1 text-xs font-bold"
          style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text-secondary)' }}
          title="缩小"
        >
          A-
        </button>
        <span
          className="px-2 text-xs font-medium tabular-nums"
          style={{ color: 'var(--color-text-secondary)', minWidth: 44, textAlign: 'center' }}
        >
          {Math.round(zoomLevel * 100)}%
        </span>
        <button
          type="button"
          onClick={onZoomIn}
          className="cursor-pointer rounded border-none px-2 py-1 text-xs font-bold"
          style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text-secondary)' }}
          title="放大"
        >
          A+
        </button>
        <button
          type="button"
          onClick={onZoomReset}
          className="cursor-pointer rounded border-none px-2 py-1 text-xs"
          style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text-muted)' }}
          title="恢复默认"
        >
          重置
        </button>
      </div>

      <button
        type="button"
        onClick={onFullscreen}
        className="cursor-pointer rounded-md border px-3 py-1.5 text-xs font-medium transition-colors"
        style={{
          borderColor: 'var(--color-border)',
          background: 'var(--color-bg-hover)',
          color: 'var(--color-text-secondary)',
        }}
      >
        全屏
      </button>
    </div>
  );
}
