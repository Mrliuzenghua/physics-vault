import type { ImportMediaAsset } from '../../types';

interface Props {
  assets: ImportMediaAsset[];
  /** Map: relative_path → question numbers referencing it */
  usageMap: Map<string, number[]>;
  onPick: (asset: ImportMediaAsset) => void;
  onUpload: (file: File) => void;
  onClose: () => void;
  uploading: boolean;
}

/**
 * Modal grid of every image extracted from the document. The user picks one
 * to attach to the current question — the fix for misaligned figure-question
 * associations.
 */
export default function FigurePickerModal({ assets, usageMap, onPick, onUpload, onClose, uploading }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(10,20,40,0.45)' }}
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-[640px] flex-col rounded-xl overflow-hidden"
        style={{ background: 'var(--color-bg-card)', boxShadow: 'var(--shadow-xl)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex flex-shrink-0 items-center justify-between border-b px-4 py-3"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <div>
            <h3 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>
              批次图片库
            </h3>
            <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
              共 {assets.length} 张 · 点击图片插入当前题目 · 角标显示该图被哪些题引用
            </p>
          </div>
          <button
            onClick={onClose}
            className="cursor-pointer rounded-md border-none px-2 py-1 text-lg leading-none"
            style={{ background: 'none', color: 'var(--color-text-muted)' }}
          >
            ×
          </button>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {assets.length === 0 ? (
            <div className="py-10 text-center text-sm" style={{ color: 'var(--color-text-muted)' }}>
              本文档未提取到图片，可点击下方按钮上传
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-3">
              {assets.map((asset) => {
                const usedBy = usageMap.get(asset.relative_path) ?? [];
                return (
                  <button
                    key={asset.image_id}
                    onClick={() => onPick(asset)}
                    className="group relative cursor-pointer overflow-hidden rounded-lg border text-left transition-all hover:-translate-y-0.5"
                    style={{
                      borderColor: usedBy.length > 0 ? 'var(--color-accent)' : 'var(--color-border)',
                      background: 'var(--color-bg)',
                    }}
                    title={asset.filename}
                  >
                    <div
                      className="flex items-center justify-center overflow-hidden"
                      style={{ height: 90, background: 'var(--color-bg-code)' }}
                    >
                      <img
                        src={`/files/${asset.relative_path}`}
                        alt={asset.filename}
                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = 'none';
                        }}
                      />
                    </div>
                    <div className="truncate px-1.5 py-1 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                      {asset.filename}
                    </div>
                    {usedBy.length > 0 && (
                      <span
                        className="absolute right-1 top-1 rounded-full px-1.5 py-0.5 text-[9px] font-bold text-white"
                        style={{ background: 'var(--color-accent)' }}
                      >
                        题{usedBy.join(',')}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer: upload */}
        <div
          className="flex flex-shrink-0 items-center justify-between border-t px-4 py-2.5"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            缺少图片？直接上传到图片库
          </span>
          <label
            className="cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium text-white transition-opacity"
            style={{ background: 'var(--color-accent)', opacity: uploading ? 0.6 : 1 }}
          >
            {uploading ? '上传中…' : '上传图片'}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onUpload(f);
                e.target.value = '';
              }}
            />
          </label>
        </div>
      </div>
    </div>
  );
}
