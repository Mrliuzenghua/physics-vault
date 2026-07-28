import { useState, useEffect, useCallback } from 'react';
import type { Question, QuestionImageDetail } from '../../types';
import LatexRenderer from '../render/LatexRenderer';

const SIZE_PRESETS = [
  { label: '小', value: 40 },
  { label: '中', value: 65 },
  { label: '大', value: 90 },
  { label: '满', value: 100 },
] as const;

const IMG_SCALE_KEY_PREFIX = 'physics-vault.img-scale';

function loadImgScale(questionId: string, index: number): number {
  try {
    const v = localStorage.getItem(`${IMG_SCALE_KEY_PREFIX}.${questionId}.${index}`);
    if (v != null) {
      const n = Number(v);
      if (n >= 20 && n <= 100) return n;
    }
  } catch {
    // ignore
  }
  return 90;
}

function saveImgScale(questionId: string, index: number, scale: number): void {
  try {
    localStorage.setItem(`${IMG_SCALE_KEY_PREFIX}.${questionId}.${index}`, String(scale));
  } catch {
    // ignore
  }
}

interface Props {
  question: Question;
  editMode: boolean;
  form?: Partial<Question>;
  onUpdateField?: (field: string, value: unknown) => void;
  dirtyFields?: Set<string>;
  images?: QuestionImageDetail[];
}

export default function QuestionContentCard({
  question,
  editMode,
  form,
  onUpdateField,
  dirtyFields,
  images,
}: Props) {
  const data = editMode && form ? form : question;
  const dirty = (f: string) => dirtyFields?.has(f) ?? false;

  const allImages: QuestionImageDetail[] = images && images.length > 0
    ? images
    : (question.figures || []).map((fig): QuestionImageDetail => ({
        asset_id: fig.fig_uuid,
        filename: fig.local_path || fig.fig_uuid,
        file_path: fig.local_path || '',
        role: 'stem',
        sort_order: 0,
        link_id: '',
        placeholder_key: null,
        is_primary: false,
        is_verified: false,
        mime_type: null,
        width: null,
        height: null,
        description: null,
      }));

  return (
    <section
      className="mb-5 overflow-hidden rounded-[24px] border"
      style={{
        borderColor: 'rgba(148, 163, 184, 0.18)',
        background: '#ffffff',
        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
      }}
    >
      <div
        className="flex items-center justify-between border-b px-6 py-4"
        style={{ borderColor: 'rgba(226, 232, 240, 0.9)', background: 'linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)' }}
      >
        <div className="flex items-center gap-3">
          <span
            className="rounded-full px-3 py-1 text-xs font-semibold"
            style={{ background: '#2f76dd', color: '#ffffff' }}
          >
            题目
          </span>
          <span className="text-sm font-medium" style={{ color: '#475569' }}>
            题干、图片与选项统一阅读区
          </span>
          {dirty('title') && (
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: '#f59e0b' }}
              title="题干已修改"
            />
          )}
        </div>
        {!editMode && (
          <div className="text-xs" style={{ color: '#94a3b8' }}>
            适合课堂阅读的清爽排版
          </div>
        )}
      </div>

      <div className="space-y-6 px-6 py-6">
        <div
          className="rounded-[20px] border px-6 py-5"
          style={{
            borderColor: 'rgba(191, 219, 254, 0.9)',
            background: 'linear-gradient(180deg, #ffffff 0%, #fbfdff 100%)',
          }}
        >
          {editMode ? (
            <textarea
              value={(form?.title as string) ?? ''}
              onChange={(e) => onUpdateField?.('title', e.target.value)}
              rows={8}
              className="w-full rounded-2xl border px-4 py-3 text-sm leading-8 outline-none"
              style={{
                borderColor: '#dbe5f0',
                background: '#ffffff',
                color: '#0f172a',
                resize: 'vertical',
              }}
            />
          ) : (
            <div className="text-[19px] leading-[2.05]" style={{ color: '#0f172a' }}>
              <LatexRenderer text={data.title || '（暂无题干）'} />
            </div>
          )}
        </div>

        {allImages.length > 0 && (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <span
                className="rounded-full px-2.5 py-1 text-xs font-semibold"
                style={{ background: '#eff6ff', color: '#2563eb' }}
              >
                题目配图
              </span>
              <span className="text-xs" style={{ color: '#94a3b8' }}>
                共 {allImages.length} 张
              </span>
            </div>
            <div
              className="grid gap-4"
              style={{
                gridTemplateColumns: allImages.length === 1 ? '1fr' : 'repeat(auto-fill, minmax(260px, 1fr))',
              }}
            >
              {allImages.map((img, i) => (
                <FigureThumbnail
                  key={`${question.question_id}-${img.asset_id || i}`}
                  img={img}
                  index={i}
                  questionId={question.question_id}
                />
              ))}
            </div>
          </div>
        )}

        {data.options && data.options.length > 0 && (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <span
                className="rounded-full px-2.5 py-1 text-xs font-semibold"
                style={{ background: '#f8fafc', color: '#475569' }}
              >
                选项
              </span>
              <span className="text-xs" style={{ color: '#94a3b8' }}>
                单独包裹，方便阅读
              </span>
            </div>
            <div
              className="grid gap-3"
              style={{
                gridTemplateColumns: data.options.length <= 2 ? 'repeat(2, minmax(0, 1fr))' : '1fr',
              }}
            >
              {editMode && form
                ? form.options?.map((opt, i) => (
                    <div
                      key={`${opt.opt}-${i}`}
                      className="flex items-start gap-3 rounded-[18px] border px-4 py-3"
                      style={{ borderColor: '#dbe5f0', background: '#fbfdff' }}
                    >
                      <span
                        className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold"
                        style={{ background: '#e8f1ff', color: '#2f76dd' }}
                      >
                        {opt.opt}
                      </span>
                      <input
                        value={opt.content}
                        onChange={(e) => {
                          const next = [...(form.options || [])];
                          next[i] = { ...next[i], content: e.target.value };
                          onUpdateField?.('options', next);
                        }}
                        className="flex-1 rounded-xl border px-3 py-2 text-sm outline-none"
                        style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
                      />
                    </div>
                  ))
                : data.options.map((opt, i) => (
                    <div
                      key={`${opt.opt}-${i}`}
                      className="flex items-start gap-3 rounded-[18px] border px-4 py-3"
                      style={{ borderColor: '#e2e8f0', background: '#ffffff' }}
                    >
                      <span
                        className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold"
                        style={{ background: '#eef4ff', color: '#2f76dd' }}
                      >
                        {opt.opt}
                      </span>
                      <span className="flex-1 text-[15px] leading-7" style={{ color: '#0f172a' }}>
                        <LatexRenderer text={opt.content} />
                      </span>
                    </div>
                  ))}
            </div>
          </div>
        )}

        {data.sub_questions && data.sub_questions.length > 0 && (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <span
                className="rounded-full px-2.5 py-1 text-xs font-semibold"
                style={{ background: '#fef3c7', color: '#92400e' }}
              >
                子问
              </span>
              <span className="text-xs" style={{ color: '#94a3b8' }}>
                大题拆分展示
              </span>
            </div>
            <div className="space-y-3">
              {data.sub_questions.map((sq, i) => (
                <div
                  key={sq.sub_id || i}
                  className="rounded-[18px] border px-4 py-4"
                  style={{
                    borderColor: '#e2e8f0',
                    background: '#fcfdff',
                  }}
                >
                  <div className="mb-2 text-sm font-semibold" style={{ color: '#2f76dd' }}>
                    {sq.sub_id || `第 ${i + 1} 问`}
                  </div>
                  <div className="text-[15px] leading-7" style={{ color: '#0f172a' }}>
                    <LatexRenderer text={sq.title} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function FigureThumbnail({ img, index, questionId }: { img: QuestionImageDetail; index: number; questionId: string }) {
  const [loaded, setLoaded] = useState(false);
  const [broken, setBroken] = useState(false);
  const [scale, setScale] = useState(() => loadImgScale(questionId, index));
  const [showControls, setShowControls] = useState(false);

  useEffect(() => {
    setScale(loadImgScale(questionId, index));
  }, [questionId, index]);

  const handleScaleChange = useCallback((newScale: number) => {
    setScale(newScale);
    saveImgScale(questionId, index, newScale);
  }, [questionId, index]);

  const src = img.file_path ? `/files/${img.file_path}` : null;

  return (
    <div
      className="overflow-hidden rounded-[18px] border"
      style={{
        borderColor: '#e2e8f0',
        background: '#ffffff',
        boxShadow: '0 8px 18px rgba(15, 23, 42, 0.04)',
      }}
      onMouseEnter={() => setShowControls(true)}
      onMouseLeave={() => setShowControls(false)}
    >
      <div
        className="relative flex items-center justify-center px-3 py-5 transition-all"
        style={{
          minHeight: 140,
          background: loaded ? '#ffffff' : '#f8fafc',
        }}
      >
        {src && !broken ? (
          <img
            src={src}
            alt={img.filename || img.asset_id}
            onLoad={() => setLoaded(true)}
            onError={() => setBroken(true)}
            style={{
              width: `${scale}%`,
              maxWidth: '100%',
              maxHeight: 820,
              objectFit: 'contain',
              display: loaded ? 'block' : 'none',
              transition: 'width 0.2s ease',
            }}
          />
        ) : null}

        {(!src || broken) && (
          <div className="flex flex-col items-center gap-1 py-8 text-xs" style={{ color: '#94a3b8' }}>
            <span style={{ fontSize: 20 }}>{broken ? '×' : '图'}</span>
            <span>{broken ? '图片加载失败' : '暂无图片文件'}</span>
          </div>
        )}

        {src && !broken && !loaded && (
          <div className="py-8 text-xs" style={{ color: '#94a3b8' }}>
            图片加载中…
          </div>
        )}

        {loaded && !broken && (
          <div
            className="absolute right-3 top-3 flex items-center gap-1 rounded-full px-2 py-1 transition-opacity"
            style={{
              background: 'rgba(255, 255, 255, 0.96)',
              border: '1px solid #dbe5f0',
              boxShadow: '0 10px 18px rgba(15, 23, 42, 0.08)',
              opacity: showControls ? 1 : 0,
              pointerEvents: showControls ? 'auto' : 'none',
            }}
          >
            <div className="flex items-center gap-0.5">
              {SIZE_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  onClick={() => handleScaleChange(preset.value)}
                  className="cursor-pointer rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors"
                  style={{
                    background: scale === preset.value ? '#2f76dd' : 'transparent',
                    color: scale === preset.value ? '#ffffff' : '#64748b',
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <div className="h-4 w-px" style={{ background: '#dbe5f0' }} />
            <input
              type="range"
              min={20}
              max={100}
              value={scale}
              onChange={(e) => handleScaleChange(Number(e.target.value))}
              className="w-16 cursor-pointer"
              style={{ accentColor: '#2f76dd' }}
            />
            <span className="w-8 text-center text-[10px] font-medium tabular-nums" style={{ color: '#475569' }}>
              {scale}%
            </span>
          </div>
        )}
      </div>

      <div
        className="flex items-center gap-2 border-t px-3 py-2 text-xs"
        style={{ borderColor: '#eef2f7', background: '#fbfdff' }}
      >
        <span style={{ color: '#94a3b8' }}>#{index + 1}</span>
        <span className="truncate" style={{ color: '#475569' }}>
          {img.filename || img.asset_id}
        </span>
        {img.role && img.role !== 'stem' && (
          <span
            className="ml-auto rounded-full px-2 py-0.5 text-[11px]"
            style={{ background: '#eff6ff', color: '#2563eb' }}
          >
            {img.role === 'analysis' ? '解析图' : img.role === 'answer' ? '答案图' : img.role === 'step' ? '步骤图' : img.role}
          </span>
        )}
      </div>
    </div>
  );
}
