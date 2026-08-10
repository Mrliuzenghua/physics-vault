import { FileText, ImagePlus, Search, Upload, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchQuestionImageCache, uploadQuestionImageCache } from '../../services/imageCacheApi';
import type { ImageCacheAsset } from '../../services/api';
import { imageFileUrl } from '../../utils/imageUrl';

export type CachedImageAsset = ImageCacheAsset;

interface Props {
  open: boolean;
  usedPaths?: ReadonlySet<string>;
  busyPath?: string | null;
  error?: string | null;
  onClose: () => void;
  onSelect: (asset: CachedImageAsset) => void | Promise<void>;
}

export default function ImageCachePickerDialog({
  open,
  usedPaths = new Set(),
  busyPath = null,
  error = null,
  onClose,
  onSelect,
}: Props) {
  const [keyword, setKeyword] = useState('');
  const [assets, setAssets] = useState<CachedImageAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadAssets = useCallback(async (search: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      setAssets(await fetchQuestionImageCache(search.trim()));
    } catch (loadFailure) {
      setLoadError(loadFailure instanceof Error ? loadFailure.message : '图片缓存加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void loadAssets('');
  }, [loadAssets, open]);

  async function uploadFiles(files: FileList | File[]) {
    const selected = Array.from(files);
    if (selected.length === 0) return;
    setUploading(true);
    setLoadError(null);
    setUploadMessage(null);
    try {
      const result = await uploadQuestionImageCache(selected);
      const notices = [`已加入 ${result.images.length} 张图片`];
      if (result.skipped.length > 0) notices.push(`跳过 ${result.skipped.length} 个文件`);
      setUploadMessage(notices.join('，'));
      await loadAssets(keyword);
    } catch (uploadFailure) {
      setLoadError(uploadFailure instanceof Error ? uploadFailure.message : '图片上传失败');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[110] flex justify-end bg-slate-950/25" role="dialog" aria-modal="true" aria-label="图片缓存">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭图片缓存" onClick={onClose} />
      <section
        className={`relative z-10 flex h-full w-[min(720px,94vw)] flex-col border-l bg-white shadow-2xl ${dragging ? 'border-[#2567b8] ring-2 ring-inset ring-[#93c5fd]' : 'border-[#d7e0ea]'}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
        onDrop={(event) => { event.preventDefault(); setDragging(false); void uploadFiles(event.dataTransfer.files); }}
      >
        <header className="flex items-center justify-between border-b border-[#dfe6ee] px-5 py-4">
          <div>
            <h2 className="text-sm font-bold text-[#1f344b]">图片缓存</h2>
            <p className="mt-1 text-[11px] text-[#71849a]">可拖入图片或 Word；选中后会转存正式题库并清除缓存</p>
          </div>
          <div className="flex items-center gap-1">
            <input ref={fileInputRef} type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,.docx" className="hidden" onChange={(event) => void uploadFiles(event.target.files || [])} />
            <button type="button" disabled={uploading} onClick={() => fileInputRef.current?.click()} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#93bce4] px-2.5 text-xs font-semibold text-[#2567b8] hover:bg-[#eff6ff] disabled:opacity-50" title="上传图片或 Word"><Upload size={14} />{uploading ? '处理中…' : '上传 / 拖入'}</button>
            <button type="button" onClick={onClose} className="rounded-md p-2 text-[#657a90] hover:bg-[#eef3f8]" title="关闭"><X size={17} /></button>
          </div>
        </header>

        <form
          className="flex gap-2 border-b border-[#e3e9f0] px-5 py-3"
          onSubmit={(event) => { event.preventDefault(); void loadAssets(keyword); }}
        >
          <label className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8a9bad]" size={15} />
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} className="h-9 w-full rounded-md border border-[#cfdae6] bg-[#f8fafc] pl-9 pr-3 text-sm text-[#1f344b] outline-none focus:border-[#4d8fd1] focus:bg-white" placeholder="搜索文件名或路径" autoFocus />
          </label>
          <button type="submit" disabled={loading} className="h-9 rounded-md bg-[#2567b8] px-4 text-xs font-semibold text-white disabled:opacity-50">搜索</button>
        </form>

        {(error || loadError) && <div className="mx-5 mt-3 rounded-md border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-xs text-[#b42318]">{error || loadError}</div>}
        {uploadMessage && <div className="mx-5 mt-3 rounded-md border border-[#bbf7d0] bg-[#f0fdf4] px-3 py-2 text-xs text-[#15804b]">{uploadMessage}</div>}

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {loading && assets.length === 0 && <div className="py-16 text-center text-sm text-[#71849a]">正在读取图片缓存...</div>}
          {!loading && assets.length === 0 && <div className="flex flex-col items-center py-16 text-center text-[#71849a]"><ImagePlus size={28} /><p className="mt-3 text-sm font-semibold">缓存中暂无图片</p><p className="mt-1 inline-flex items-center gap-1 text-xs"><FileText size={13} />把图片或 Word 直接拖到这里，Word 中的图片会自动提取。</p></div>}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {assets.map((asset) => {
              const used = usedPaths.has(asset.relative_path);
              const busy = busyPath === asset.relative_path;
              return (
                <button key={asset.relative_path} type="button" disabled={Boolean(busyPath)} onClick={() => void onSelect(asset)} className="group overflow-hidden rounded-md border border-[#d9e2ec] bg-white text-left transition hover:border-[#4d8fd1] hover:shadow-md disabled:cursor-wait disabled:opacity-60">
                  <div className="relative flex h-36 items-center justify-center bg-[#f4f7fa] p-2">
                    <img src={imageFileUrl(asset.file_path) || ''} alt={asset.filename} loading="lazy" className="h-full w-full object-contain" />
                    <span className="absolute inset-x-2 bottom-2 rounded bg-slate-900/75 px-2 py-1 text-center text-[10px] font-semibold text-white opacity-0 transition-opacity group-hover:opacity-100">{busy ? '正在插入...' : used ? '再次插入' : '插入图片'}</span>
                  </div>
                  <div className="border-t border-[#e4eaf0] px-2.5 py-2">
                    <div className="truncate text-[11px] font-semibold text-[#405873]" title={asset.filename}>{asset.filename || asset.relative_path}</div>
                    <div className="mt-1 flex items-center justify-between gap-2 text-[9px] text-[#8a9bad]"><span className="truncate">{asset.size > 0 ? `${Math.ceil(asset.size / 1024)} KB` : asset.relative_path}</span>{used && <span className="shrink-0 text-[#15804b]">已绑定</span>}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </section>
    </div>
  );
}
