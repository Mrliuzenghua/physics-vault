import { useCallback, useEffect, useState } from 'react';

import ImageCachePickerDialog from '../editor/ImageCachePickerDialog';
import type { CachedImageAsset } from '../editor/ImageCachePickerDialog';
import {
  addCachedQuestionImage,
  addQuestionImage,
  deleteQuestionImage,
  fetchAvailableImages,
  fetchQuestionImages,
  reorderQuestionImages,
  updateQuestionImage,
  validateQuestionImages,
} from '../../services/assetsApi';
import type { QuestionImageDetail, ValidationResponse } from '../../types';
import { imageFileUrl } from '../../utils/imageUrl';

const ROLE_LABELS: Record<string, string> = {
  stem: '题干图',
  analysis: '解析图',
  step: '步骤图',
  answer: '答案图',
};

interface Props {
  questionId: string;
  stemText: string;
  onImagesChanged?: (images: QuestionImageDetail[]) => void;
}

export default function ImageManager({ questionId, stemText, onImagesChanged }: Props) {
  const [images, setImages] = useState<QuestionImageDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResponse | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [available, setAvailable] = useState<{ asset_id: string; filename: string; file_path: string }[]>([]);
  const [pickSearch, setPickSearch] = useState('');
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [cachePickerOpen, setCachePickerOpen] = useState(false);
  const [cacheBusyPath, setCacheBusyPath] = useState<string | null>(null);
  const [replaceTargetId, setReplaceTargetId] = useState<string | null>(null);

  const load = useCallback(async (): Promise<QuestionImageDetail[]> => {
    if (!questionId) return [];
    setLoading(true);
    try {
      const data = await fetchQuestionImages(questionId);
      setImages(data.images);
      return data.images;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载图片失败');
      return [];
    } finally {
      setLoading(false);
    }
  }, [questionId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!questionId) return;
    validateQuestionImages(questionId).then(setValidation).catch(() => {});
  }, [questionId, images]);

  const handleAdd = useCallback(async (assetId: string) => {
    try {
      await addQuestionImage(questionId, { asset_id: assetId, role: 'stem', placeholder_key: assetId });
      setShowPicker(false);
      const nextImages = await load();
      onImagesChanged?.(nextImages);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '添加失败');
    }
  }, [questionId, load, onImagesChanged]);

  const handleDelete = useCallback(async (assetId: string) => {
    if (!window.confirm('确定移除此图片绑定？不会删除素材文件。')) return;
    try {
      await deleteQuestionImage(questionId, assetId);
      const nextImages = await load();
      onImagesChanged?.(nextImages);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  }, [questionId, load, onImagesChanged]);

  const handleCacheSelect = useCallback(async (asset: CachedImageAsset) => {
    setCacheBusyPath(asset.relative_path);
    setError(null);
    try {
      await addCachedQuestionImage(questionId, { relative_path: asset.relative_path, role: 'stem' });
      if (replaceTargetId) {
        await deleteQuestionImage(questionId, replaceTargetId);
      }
      const nextImages = await load();
      onImagesChanged?.(nextImages);
      setCachePickerOpen(false);
      setReplaceTargetId(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '图片缓存插入失败');
    } finally {
      setCacheBusyPath(null);
    }
  }, [load, onImagesChanged, questionId, replaceTargetId]);

  const handleReplace = useCallback((oldId: string) => {
    setReplaceTargetId(oldId);
    setCachePickerOpen(true);
  }, []);

  const handleReorder = useCallback(async (draggedIdx: number, dropIdx: number) => {
    if (draggedIdx === dropIdx) { setDragIdx(null); return; }
    const reordered = [...images];
    const [moved] = reordered.splice(draggedIdx, 1);
    reordered.splice(dropIdx, 0, moved);
    setImages(reordered);
    setDragIdx(null);
    try {
      await reorderQuestionImages(questionId, reordered.map((img) => img.asset_id));
    } catch {
      await load(); // revert on failure
    }
  }, [images, questionId, load]);

  const handleUpdate = useCallback(async (assetId: string, field: string, value: unknown) => {
    try {
      await updateQuestionImage(questionId, assetId, { [field]: value });
      const nextImages = images.map((img) => img.asset_id === assetId ? { ...img, [field]: value } : img);
      setImages(nextImages);
      onImagesChanged?.(nextImages);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '更新失败');
    }
  }, [images, onImagesChanged, questionId]);

  const openPicker = useCallback(async () => {
    setShowPicker(true);
    try {
      const data = await fetchAvailableImages(pickSearch);
      setAvailable(data);
    } catch { /* ignore */ }
  }, [pickSearch]);

  void images.find((img) => img.asset_id === previewId); // pre-loaded for preview modal

  if (loading) return <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>加载图片...</p>;
  if (error) return <p className="text-xs" style={{ color: 'var(--color-red)' }}>{error}</p>;

  return (
    <div className="space-y-2">
      {/* Validation status */}
      {validation && !validation.valid && (
        <div className="rounded p-2 text-xs space-y-0.5" style={{ background: 'var(--color-orange-light)', color: 'var(--color-orange)' }}>
          {validation.issues.map((issue, i) => (
            <div key={i}>⚠ {issue.message}</div>
          ))}
        </div>
      )}

      {/* Image count + add button header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
          配图 ({images.length})
        </span>
        <button
          onClick={openPicker}
          className="cursor-pointer rounded border-none px-2 py-1 text-xs font-medium text-white"
          style={{ background: 'var(--color-accent)' }}
        >
          + 添加已入库图片
        </button>
        <button
          onClick={() => { setReplaceTargetId(null); setCachePickerOpen(true); }}
          className="cursor-pointer rounded border px-2 py-1 text-xs font-medium"
          style={{ borderColor: 'var(--color-accent)', color: 'var(--color-accent)', background: 'var(--color-bg-card)' }}
        >
          + 从缓存添加
        </button>
      </div>

      {/* Picker modal */}
      {showPicker && (
        <div className="rounded border p-2 space-y-2" style={{ borderColor: 'var(--color-border)' }}>
          <input
            value={pickSearch}
            onChange={(e) => setPickSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') openPicker(); }}
            placeholder="搜索素材..."
            className="w-full rounded border px-2 py-1 text-xs outline-none"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)' }}
          />
          <div className="max-h-32 overflow-y-auto space-y-0.5">
            {available.slice(0, 20).map((img) => (
              <button
                key={img.asset_id}
                onClick={() => handleAdd(img.asset_id)}
                className="w-full cursor-pointer flex items-center justify-between rounded px-2 py-1 text-left text-xs"
                style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text)', border: 'none' }}
              >
                <span className="truncate">{img.filename}</span>
                <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{img.asset_id}</span>
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowPicker(false)}
            className="cursor-pointer text-xs underline"
            style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none' }}
          >
            取消
          </button>
        </div>
      )}

      {/* Empty state */}
      {images.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>暂无配图</p>
      )}

      {/* Image list */}
      {images.map((img, idx) => (
        <div
          key={img.asset_id}
          draggable
          onDragStart={() => setDragIdx(idx)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={() => handleReorder(dragIdx ?? idx, idx)}
          className="rounded border p-2 flex items-start gap-3"
          style={{
            borderColor: dragIdx === idx ? 'var(--color-accent)' : 'var(--color-border)',
            background: 'var(--color-bg-card)',
            opacity: dragIdx === idx ? 0.5 : 1,
            cursor: 'grab',
          }}
        >
          {/* Thumbnail */}
          <div
            onClick={() => setPreviewId(previewId === img.asset_id ? null : img.asset_id)}
            className="shrink-0 rounded overflow-hidden cursor-pointer"
            style={{ width: 64, height: 48, background: 'var(--color-bg-code)', border: '1px solid var(--color-border)' }}
          >
            {img.file_path ? (
              <img
                src={imageFileUrl(img.file_path || img.filename) || ''}
                alt={img.filename}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-xs" style={{ color: 'var(--color-text-muted)' }}>
                无预览
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium truncate" style={{ color: 'var(--color-text)' }}>{img.filename}</div>
            <div className="text-xs" style={{ color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>{img.asset_id}</div>
            <div className="flex items-center gap-2 mt-1">
              <select
                value={img.role}
                onChange={(e) => handleUpdate(img.asset_id, 'role', e.target.value)}
                className="rounded border px-1 py-0 text-xs outline-none"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)' }}
              >
                {Object.entries(ROLE_LABELS).map(([k, v]) => (<option key={k} value={k}>{v}</option>))}
              </select>
              <input
                value={img.placeholder_key || ''}
                onChange={(e) => handleUpdate(img.asset_id, 'placeholder_key', e.target.value || null)}
                placeholder="占位符 UUID"
                className="flex-1 rounded border px-1 py-0 text-xs outline-none"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)', fontFamily: 'monospace', fontSize: 10 }}
              />
            </div>
            <div className="mt-2 flex items-center gap-1.5">
              <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>尺寸</span>
              {[40, 60, 80, 100].map((scale) => (
                <button
                  key={scale}
                  type="button"
                  onClick={() => handleUpdate(img.asset_id, 'display_scale', scale)}
                  className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                  style={{
                    background: (img.display_scale || 60) === scale ? 'var(--color-accent)' : 'var(--color-bg-hover)',
                    color: (img.display_scale || 60) === scale ? '#fff' : 'var(--color-text-secondary)',
                  }}
                >
                  {scale}%
                </button>
              ))}
            </div>

            {/* Preview expanded */}
            {previewId === img.asset_id && (
              <div className="mt-2 rounded overflow-hidden border" style={{ borderColor: 'var(--color-border)' }}>
                <img
                  src={imageFileUrl(img.file_path || img.filename) || ''}
                  alt={img.filename}
                  style={{ maxWidth: '100%', maxHeight: 300, display: 'block' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-1 shrink-0">
            <button
              onClick={() => handleReplace(img.asset_id)}
              className="cursor-pointer rounded border px-1.5 py-0.5 text-xs"
              style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-hover)', color: 'var(--color-text-secondary)' }}
            >
              替换
            </button>
            <button
              onClick={() => handleDelete(img.asset_id)}
              className="cursor-pointer rounded border px-1.5 py-0.5 text-xs"
              style={{ borderColor: 'var(--color-red)', color: 'var(--color-red)' }}
            >
              移除
            </button>
          </div>
        </div>
      ))}

      {/* Placeholder reference helper */}
      {stemText && (
        <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          题干占位符：{(stemText.match(/!\[fig:([^\]]+)\]/g) || []).join(', ') || '无'}
        </div>
      )}
      <ImageCachePickerDialog
        open={cachePickerOpen}
        usedPaths={new Set(images.map((image) => image.file_path))}
        busyPath={cacheBusyPath}
        error={error}
        onClose={() => { setCachePickerOpen(false); setReplaceTargetId(null); }}
        onSelect={handleCacheSelect}
      />
    </div>
  );
}
