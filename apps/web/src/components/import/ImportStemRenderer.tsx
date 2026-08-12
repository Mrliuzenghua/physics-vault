import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { SyntheticEvent } from 'react';
import type { Figure } from '../../types';
import { updateQuestionImage } from '../../services/assetsApi';
import { readStorageValue, writeStorageValue } from '../../services/safeStorage';
import { imageFileUrl, imageThumbnailUrl } from '../../utils/imageUrl';
import LatexRenderer from '../render/LatexRenderer';

interface Props {
  title?: string | null;
  figures?: Figure[];
  maxImageHeight?: number;
  thumbnailWidth?: number;
  questionId?: string;
  onScaleChange?: (figure: Figure, scale: number) => void;
  onLayoutChange?: (figure: Figure, patch: Pick<Figure, 'display_align' | 'caption'>) => void;
  compactImages?: boolean;
}

const STEM_IMAGE_SCALE_KEY = 'physics-vault.stem-image-scale';
const IMAGE_SCALE_PRESETS = [
  { label: '小', value: 40 },
  { label: '中', value: 60 },
  { label: '大', value: 80 },
  { label: '满', value: 100 },
] as const;

function getFigureKey(figure: Figure) {
  return figure.fig_uuid || figure.local_path;
}

function loadScale(figure: Figure) {
  if (typeof figure.display_scale === 'number' && figure.display_scale >= 25 && figure.display_scale <= 100) {
    return figure.display_scale;
  }
  const raw = readStorageValue(`${STEM_IMAGE_SCALE_KEY}.${getFigureKey(figure)}`);
  const scale = Number(raw);
  if (scale >= 25 && scale <= 100) return scale;
  return 60;
}

function saveScale(figure: Figure, scale: number) {
  writeStorageValue(`${STEM_IMAGE_SCALE_KEY}.${getFigureKey(figure)}`, String(scale));
}

/**
 * Render a question stem with ![fig:uuid] placeholders.
 * Each placeholder becomes an image from the import media library.
 */
export default function ImportStemRenderer({ title, figures, maxImageHeight = 180, thumbnailWidth, questionId, onScaleChange, onLayoutChange, compactImages = false }: Props) {
  const safeTitle = String(title ?? '');
  const safeFigures = useMemo(() => figures || [], [figures]);
  const parts = safeTitle.split(/(!\[fig:[^\]]+\])/g);

  return (
    <div>
      {parts.map((part, i) => {
        const match = part.match(/!\[fig:([^\]]+)\]/);
        if (match) {
          const fig = safeFigures.find((item) => item.fig_uuid === match[1]);
          if (!fig) {
            return (
              <span
                key={i}
                className="my-1 inline-flex items-center rounded border border-dashed px-2 py-1 text-xs"
                style={{ borderColor: 'var(--color-red)', color: 'var(--color-red)' }}
              >
                图片缺失 {match[1].slice(0, 12)}
              </span>
            );
          }
          return <ResizableStemFigure key={i} figure={fig} figureIndex={Math.max(1, safeFigures.findIndex((item) => item.fig_uuid === fig.fig_uuid) + 1)} maxImageHeight={maxImageHeight} thumbnailWidth={thumbnailWidth} questionId={questionId} onScaleChange={onScaleChange} onLayoutChange={onLayoutChange} compact={compactImages} />;
        }
        if (!part.trim()) return null;
        return <LatexRenderer key={i} text={part} />;
      })}
    </div>
  );
}

function ResizableStemFigure({
  figure,
  figureIndex,
  maxImageHeight,
  thumbnailWidth,
  questionId,
  onScaleChange,
  onLayoutChange,
  compact,
}: {
  figure: Figure;
  figureIndex: number;
  maxImageHeight: number;
  thumbnailWidth?: number;
  questionId?: string;
  onScaleChange?: (figure: Figure, scale: number) => void;
  onLayoutChange?: (figure: Figure, patch: Pick<Figure, 'display_align' | 'caption'>) => void;
  compact: boolean;
}) {
  const [scale, setScale] = useState(() => loadScale(figure));
  const [loaded, setLoaded] = useState(false);
  const [broken, setBroken] = useState(false);
  const [activeSrc, setActiveSrc] = useState<string | null>(null);
  const [loadRequested, setLoadRequested] = useState(false);
  const figureRef = useRef<HTMLSpanElement>(null);
  const originalSrc = imageFileUrl(figure.local_path);
  const thumbnailSrc = thumbnailWidth ? imageThumbnailUrl(figure.local_path, thumbnailWidth) : null;
  const alignment = figure.display_align || 'center';

  useEffect(() => {
    const node = figureRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setLoadRequested(true);
      return;
    }

    setLoadRequested(false);
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        setLoadRequested(true);
        observer.disconnect();
      },
      { rootMargin: '240px 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [figure, originalSrc, thumbnailSrc]);

  useEffect(() => {
    setScale(loadScale(figure));
    setLoaded(false);
    setBroken(false);
    setActiveSrc(null);

    if (!loadRequested) return;

    const candidates = [thumbnailSrc, originalSrc].filter((item, index, all): item is string => Boolean(item) && all.indexOf(item) === index);
    let cancelled = false;

    const loadCandidate = (index: number) => {
      const nextSrc = candidates[index];
      if (!nextSrc) {
        if (!cancelled) setBroken(true);
        return;
      }

      const image = new Image();
      image.onload = () => {
        if (cancelled) return;
        setActiveSrc(nextSrc);
        setLoaded(true);
        setBroken(false);
      };
      image.onerror = () => {
        loadCandidate(index + 1);
      };
      image.src = nextSrc;
    };

    loadCandidate(0);
    return () => {
      cancelled = true;
    };
  }, [figure, loadRequested, originalSrc, thumbnailSrc]);

  const updateScale = useCallback((nextScale: number) => {
    const safeScale = Math.min(100, Math.max(25, nextScale));
    setScale(safeScale);
    saveScale(figure, safeScale);
    onScaleChange?.(figure, safeScale);
    if (questionId && figure.fig_uuid) {
      void updateQuestionImage(questionId, figure.fig_uuid, { display_scale: safeScale });
    }
  }, [figure, onScaleChange, questionId]);

  const stopImageInteraction = useCallback((event: SyntheticEvent) => {
    event.stopPropagation();
  }, []);
  const updateLayout = useCallback((patch: Pick<Figure, 'display_align' | 'caption'>) => {
    onLayoutChange?.(figure, patch);
    if (questionId && figure.fig_uuid) void updateQuestionImage(questionId, figure.fig_uuid, patch);
  }, [figure, onLayoutChange, questionId]);

  return (
    <span
      ref={figureRef}
      className={`group my-3 cursor-default ${compact ? 'flex max-w-full' : 'block'}`}
      style={compact ? { justifyContent: alignment === 'left' ? 'flex-start' : alignment === 'right' ? 'flex-end' : 'center' } : undefined}
      onClick={stopImageInteraction}
      onDoubleClick={stopImageInteraction}
      onMouseDown={stopImageInteraction}
      onPointerDown={stopImageInteraction}
      onTouchStart={stopImageInteraction}
    >
      <span
        className={`relative max-w-full bg-white ${compact ? 'inline-block' : 'block rounded-md border p-2'}`}
        style={compact ? undefined : { borderColor: 'var(--color-border)' }}
      >
        {activeSrc && loaded && !broken && (
          <span style={compact
            ? { display: 'block', maxWidth: '100%' }
            : { display: 'block', width: `${scale}%`, marginLeft: alignment === 'left' ? 0 : 'auto', marginRight: alignment === 'right' ? 0 : 'auto', transition: 'width 0.16s ease' }}>
          <img
            src={activeSrc}
            alt={figure.caption?.trim() ? `题图 ${figureIndex}：${figure.caption.trim()}` : `题图 ${figureIndex}`}
            loading="lazy"
            decoding="async"
              onError={() => setBroken(true)}
              draggable={false}
              onClick={stopImageInteraction}
              onMouseDown={stopImageInteraction}
              style={{ width: compact ? 'auto' : '100%', maxWidth: '100%', maxHeight: maxImageHeight, objectFit: 'contain', borderRadius: 4, display: 'block' }}
            />
            {figure.caption && <span style={{ display: 'block', marginTop: 5, textAlign: 'center', fontSize: 11, lineHeight: 1.5, color: 'var(--color-text-muted)' }}>{figure.caption}</span>}
          </span>
        )}

        {!broken && !loaded && (
          <span
            className="block rounded bg-[var(--color-bg-hover)] px-3 py-8 text-center text-xs"
            style={{ color: 'var(--color-text-muted)', minHeight: Math.min(maxImageHeight, 120) }}
          >
            正在准备图片...
          </span>
        )}

        {broken && (
          <span className="block py-6 text-center text-xs" style={{ color: 'var(--color-red)' }}>
            图片不可用
          </span>
        )}

        {loaded && !broken && !compact && (
          <span
            className="absolute right-2 top-2 flex items-center gap-1 rounded-full border bg-white/95 px-2 py-1 opacity-0 shadow-sm transition-opacity group-hover:opacity-100"
            onClick={stopImageInteraction}
            onMouseDown={stopImageInteraction}
            onPointerDown={stopImageInteraction}
            onTouchStart={stopImageInteraction}
          >
            {IMAGE_SCALE_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  updateScale(preset.value);
                }}
                className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                style={{
                  background: scale === preset.value ? 'var(--color-accent)' : 'transparent',
                  color: scale === preset.value ? '#fff' : 'var(--color-text-secondary)',
                }}
              >
                {preset.label}
              </button>
            ))}
            {(['left', 'center', 'right'] as const).map((value) => (
              <button key={value} type="button" title={`${value === 'left' ? '左' : value === 'center' ? '中' : '右'}对齐`} onClick={(event) => { event.stopPropagation(); updateLayout({ display_align: value }); }} className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: alignment === value ? 'var(--color-accent)' : 'transparent', color: alignment === value ? '#fff' : 'var(--color-text-secondary)' }}>{value === 'left' ? '左' : value === 'center' ? '中' : '右'}</button>
            ))}
            <input
              type="range"
              min={25}
              max={100}
              value={scale}
              onClick={stopImageInteraction}
              onMouseDown={stopImageInteraction}
              onPointerDown={stopImageInteraction}
              onChange={(event) => {
                event.stopPropagation();
                updateScale(Number(event.target.value));
              }}
              className="w-16"
              style={{ accentColor: 'var(--color-accent)' }}
            />
            <span className="w-8 text-center text-[10px] tabular-nums" style={{ color: 'var(--color-text-secondary)' }}>
              {scale}%
            </span>
            <input value={figure.caption || ''} placeholder="题注" aria-label="图片题注" onClick={stopImageInteraction} onMouseDown={stopImageInteraction} onChange={(event) => updateLayout({ caption: event.target.value })} className="h-6 w-20 rounded border px-1 text-[10px]" />
          </span>
        )}
      </span>
    </span>
  );
}
