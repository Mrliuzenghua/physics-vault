import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Clipboard,
  Database,
  FolderArchive,
  HardDrive,
  Image as ImageIcon,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';

import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import {
  cleanupUnusedCache,
  deleteSingleAsset,
  fetchAssetList,
  fetchAssetStorageAnalysis,
  fetchUnusedCacheCleanupPreview,
} from '../services/assetsApi';
import type {
  AssetItem,
  AssetListResponse,
  CacheCleanupPreviewResponse,
  StorageAnalysisResponse,
} from '../types';
import { imageThumbnailUrl } from '../utils/imageUrl';

const PAGE_SIZE = 48;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDate(value: string): string {
  if (!value) return '未知时间';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

function shortBatchId(batchId?: string | null): string {
  if (!batchId) return '未识别批次';
  return batchId.replace(/^batch_/, '').replace(/_/g, ' · ');
}

function statusDisplay(asset: AssetItem): { label: string; className: string } {
  switch (asset.lifecycle_status) {
    case 'referenced':
      return { label: `被 ${asset.reference_count} 道题引用`, className: 'bg-[var(--color-green-light)] text-[var(--color-green)]' };
    case 'imported':
      return { label: `已入库引用 ${asset.reference_count}`, className: 'bg-[var(--color-green-light)] text-[var(--color-green)]' };
    case 'staged':
      return { label: '未使用', className: 'bg-[var(--color-orange-light)] text-[var(--color-orange)]' };
    case 'unreferenced':
      return { label: '未使用', className: 'bg-[var(--color-orange-light)] text-[var(--color-orange)]' };
    default:
      return { label: '引用状态未知', className: 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]' };
  }
}

function AssetThumbnail({ asset, className = '' }: { asset: AssetItem; className?: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={`flex items-center justify-center bg-[var(--color-bg-code)] ${className}`}>
      {!failed ? (
        <img
          src={imageThumbnailUrl(asset.relative_path, 360, 'data/assets/questions') || ''}
          alt={asset.filename}
          loading="lazy"
          decoding="async"
          className="h-full w-full object-contain p-2"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="flex flex-col items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <AlertTriangle size={24} />
          <span>图片无法预览</span>
        </div>
      )}
    </div>
  );
}

export default function AssetsManagerPage() {
  const [data, setData] = useState<AssetListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<'question_bank' | 'import_batch'>('import_batch');
  const [searchInput, setSearchInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [batchId, setBatchId] = useState('');
  const [sortBy, setSortBy] = useState('modified_at');
  const [sortOrder, setSortOrder] = useState('desc');
  const [page, setPage] = useState(1);
  const [previewAsset, setPreviewAsset] = useState<AssetItem | null>(null);
  const [deleteAsset, setDeleteAsset] = useState<AssetItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [cacheCleanupPreview, setCacheCleanupPreview] = useState<CacheCleanupPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  const [storageAnalysis, setStorageAnalysis] = useState<StorageAnalysisResponse | null>(null);
  const [analyzingStorage, setAnalyzingStorage] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAssetList({
        filterMode: source === 'question_bank' ? 'referenced' : 'unreferenced',
        keyword,
        source: 'all',
        batchId,
        sortBy,
        sortOrder,
        page,
        pageSize: PAGE_SIZE,
        refresh,
      });
      const normalized: AssetListResponse = {
        ...result,
        library_stats: result.library_stats ?? result.stats,
        batches: result.batches ?? [],
        pagination: result.pagination ?? {
          page,
          page_size: PAGE_SIZE,
          total_items: result.stats.total,
          total_pages: Math.ceil(result.stats.total / PAGE_SIZE),
        },
        reference_scan_available: result.reference_scan_available ?? true,
      };
      setData(normalized);
      if (normalized.pagination.total_pages > 0 && page > normalized.pagination.total_pages) {
        setPage(normalized.pagination.total_pages);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '素材加载失败');
    } finally {
      setLoading(false);
    }
  }, [batchId, keyword, page, sortBy, sortOrder, source]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setKeyword(searchInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreviewAsset(null);
        setDeleteAsset(null);
        setCacheCleanupPreview(null);
        setStorageAnalysis(null);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  const questionCount = data?.library_stats.referenced ?? 0;
  const importCount = data?.library_stats.unreferenced ?? 0;
  const groupedAssets = useMemo(() => {
    if (source === 'question_bank') return [{ id: 'question_bank', assets: data?.assets ?? [] }];
    const groups = new Map<string, AssetItem[]>();
    for (const asset of data?.assets ?? []) {
      const key = asset.batch_id || 'local-cache';
      groups.set(key, [...(groups.get(key) ?? []), asset]);
    }
    return Array.from(groups, ([id, assets]) => ({ id, assets }));
  }, [data?.assets, source]);

  const switchSource = (next: 'question_bank' | 'import_batch') => {
    setSource(next);
    setBatchId('');
    setPage(1);
    setPreviewAsset(null);
  };

  const analyzeStorage = async () => {
    setAnalyzingStorage(true);
    setMessage(null);
    try {
      setStorageAnalysis(await fetchAssetStorageAnalysis('all', false));
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : '存储分析失败');
    } finally {
      setAnalyzingStorage(false);
    }
  };

  const openCacheCleanupPreview = async () => {
    setPreviewLoading(true);
    setMessage(null);
    try {
      setCacheCleanupPreview(await fetchUnusedCacheCleanupPreview(batchId));
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : '缓存清理预览失败');
    } finally {
      setPreviewLoading(false);
    }
  };

  const confirmCacheCleanup = async () => {
    setClearingCache(true);
    try {
      const result = await cleanupUnusedCache(cacheCleanupPreview?.batch_id || '');
      setCacheCleanupPreview(null);
      setMessage(result.errors.length
        ? `已清除 ${result.deleted_count} 个缓存文件；另有 ${result.errors.length} 个文件未处理`
        : `已清除 ${result.deleted_count} 个缓存文件，释放 ${formatSize(result.freed_bytes)}`);
      await load(true);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : '缓存清理失败');
    } finally {
      setClearingCache(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteAsset) return;
    setDeleting(true);
    try {
      const result = await deleteSingleAsset(deleteAsset.relative_path);
      setMessage(result.message || '素材已删除');
      setDeleteAsset(null);
      if (previewAsset?.relative_path === deleteAsset.relative_path) setPreviewAsset(null);
      await load(true);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : '删除失败');
    } finally {
      setDeleting(false);
    }
  };

  const copyPath = async (path: string) => {
    await navigator.clipboard.writeText(path);
    setMessage('素材路径已复制');
  };

  const stats = data?.stats;
  const pagination = data?.pagination;
  const cacheBatches = (data?.batches ?? []).filter((batch) => batch.unreferenced > 0);
  const batchOptions = [
    { value: '', label: `全部批次（${cacheBatches.length}）` },
    ...cacheBatches.map((batch) => ({
      value: batch.batch_id,
      label: `${shortBatchId(batch.batch_id)} · ${batch.unreferenced} 张未使用`,
    })),
  ];

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--color-bg)]">
      <header className="flex-shrink-0 border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-[var(--color-text)]">素材管理</h1>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">已被题目采用的图片归入题库素材，未使用图片留在缓存中</p>
          </div>
          <Button variant="outline" size="sm" icon={<RefreshCw size={14} />} loading={loading} onClick={() => void load(true)}>
            重新扫描
          </Button>
        </div>

        <div className="mt-4 flex gap-1 border-b border-[var(--color-border)]">
          <SourceTab active={source === 'question_bank'} icon={<Database size={15} />} label="题库素材" count={questionCount} onClick={() => switchSource('question_bank')} />
          <SourceTab active={source === 'import_batch'} icon={<FolderArchive size={15} />} label="缓存" count={importCount} onClick={() => switchSource('import_batch')} />
        </div>
      </header>

      <div className="flex-shrink-0 border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-5 py-3">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <StatCard icon={<ImageIcon size={16} />} label="当前结果" value={`${stats?.total ?? 0} 项`} />
          <StatCard icon={<HardDrive size={16} />} label="当前占用" value={formatSize(stats?.total_size_bytes ?? 0)} />
          <StatCard label={source === 'question_bank' ? '引用中' : '可删除'} value={`${stats?.total ?? 0} 项`} tone={source === 'question_bank' ? 'success' : 'warning'} />
          <StatCard label="分类规则" value={source === 'question_bank' ? '已被题目使用' : '尚未被使用'} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Input
            size="sm"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="搜索文件名或路径"
            leftIcon={<Search size={14} />}
            wrapperClassName="min-w-[220px] flex-1 md:max-w-sm"
          />
          {source === 'import_batch' && (
            <Select size="sm" value={batchId} onChange={(event) => { setBatchId(event.target.value); setPage(1); }} options={batchOptions} className="max-w-[250px]" />
          )}
          <Select
            size="sm"
            value={`${sortBy}:${sortOrder}`}
            onChange={(event) => {
              const [nextSort, nextOrder] = event.target.value.split(':');
              setSortBy(nextSort);
              setSortOrder(nextOrder);
              setPage(1);
            }}
            options={[
              { value: 'modified_at:desc', label: '最近更新' },
              { value: 'modified_at:asc', label: '最早更新' },
              { value: 'name:asc', label: '名称 A–Z' },
              { value: 'size_bytes:desc', label: '文件从大到小' },
              { value: 'reference_count:desc', label: '引用数最多' },
            ]}
          />
          <Button variant="outline" size="sm" icon={<HardDrive size={14} />} loading={analyzingStorage} onClick={() => void analyzeStorage()}>
            存储分析
          </Button>
          {source === 'import_batch' && (
            <Button
              variant="danger"
              size="sm"
              icon={<Trash2 size={14} />}
              loading={previewLoading}
              disabled={!data?.reference_scan_available || (stats?.total ?? 0) === 0}
              onClick={() => void openCacheCleanupPreview()}
            >
              {batchId ? '删除此批次缓存' : '清空未使用缓存'}
            </Button>
          )}
        </div>
      </div>

      {!data?.reference_scan_available && (
        <div className="flex items-center gap-2 bg-[var(--color-orange-light)] px-5 py-2 text-xs text-[var(--color-orange)]">
          <AlertTriangle size={14} />引用数据库不可用，当前状态显示为未知，删除与清理已自动禁用。
        </div>
      )}
      {message && (
        <div className="flex items-center justify-between bg-[var(--color-accent-light)] px-5 py-2 text-xs text-[var(--color-accent)]">
          <span>{message}</span>
          <button type="button" aria-label="关闭消息" onClick={() => setMessage(null)}><X size={14} /></button>
        </div>
      )}
      {error && <div className="bg-[var(--color-red-light)] px-5 py-2 text-xs text-[var(--color-red)]">{error}</div>}

      <section aria-label="素材列表" className="min-h-0 flex-1 overflow-y-auto p-5">
        {loading && !data ? (
          <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-muted)]">正在扫描素材…</div>
        ) : !error && (data?.assets.length ?? 0) === 0 ? (
          <EmptyState source={source} filtered={Boolean(keyword || batchId)} />
        ) : (
          <div className={`space-y-6 transition-opacity ${loading ? 'opacity-60' : 'opacity-100'}`}>
            {groupedAssets.map((group) => (
              <section key={group.id}>
                {source === 'import_batch' && (
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <h2 className="text-sm font-semibold text-[var(--color-text)]">{group.id === 'local-cache' ? '本地未使用素材' : `批次 ${shortBatchId(group.id)}`}</h2>
                      <p className="text-[11px] text-[var(--color-text-muted)]">本页显示 {group.assets.length} 张</p>
                    </div>
                    {group.id !== 'local-cache' && (
                      <button type="button" className="text-xs text-[var(--color-accent)] hover:underline" onClick={() => { setBatchId(group.id); setPage(1); }}>
                        仅看此批次
                      </button>
                    )}
                  </div>
                )}
                <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
                  {group.assets.map((asset) => {
                    const status = statusDisplay(asset);
                    return (
                      <article key={asset.relative_path} className="group overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-[var(--shadow-sm)] transition hover:-translate-y-0.5 hover:border-[var(--color-border-strong)] hover:shadow-[var(--shadow-card)]">
                        <button type="button" className="block h-36 w-full border-b border-[var(--color-border)]" onClick={() => setPreviewAsset(asset)} aria-label={`预览 ${asset.filename}`}>
                          <AssetThumbnail asset={asset} className="h-full w-full" />
                        </button>
                        <div className="space-y-2 p-3">
                          <div className="min-w-0">
                            <p className="truncate text-xs font-semibold text-[var(--color-text)]" title={asset.filename}>{asset.filename}</p>
                            <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">{formatSize(asset.size_bytes)} · {formatDate(asset.modified_at)}</p>
                          </div>
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.className}`}>{status.label}</span>
                          <div className="flex items-center gap-1 border-t border-[var(--color-border)] pt-2">
                            <Button variant="ghost" size="sm" className="flex-1" onClick={() => setPreviewAsset(asset)}>详情</Button>
                            <Button variant="ghost" size="sm" icon={<Clipboard size={13} />} onClick={() => void copyPath(asset.relative_path)}>复制</Button>
                            {source === 'import_batch' && !asset.is_referenced && asset.lifecycle_status !== 'unknown' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                icon={<Trash2 size={13} />}
                                className="text-[var(--color-red)]"
                                disabled={asset.is_referenced || asset.lifecycle_status === 'unknown'}
                                onClick={() => setDeleteAsset(asset)}
                              >删除</Button>
                            )}
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </section>

      {pagination && pagination.total_items > 0 && (
        <footer className="flex flex-shrink-0 items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-bg-card)] px-5 py-2 text-xs text-[var(--color-text-muted)]">
          <span>共 {pagination.total_items} 项 · 每页 {pagination.page_size} 项</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" icon={<ChevronLeft size={14} />} disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</Button>
            <span className="min-w-16 text-center">{page} / {Math.max(1, pagination.total_pages)}</span>
            <Button variant="outline" size="sm" icon={<ChevronRight size={14} />} disabled={page >= pagination.total_pages || loading} onClick={() => setPage((value) => value + 1)}>下一页</Button>
          </div>
        </footer>
      )}

      {previewAsset && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/35" onClick={() => setPreviewAsset(null)}>
          <aside className="flex h-full w-full max-w-lg flex-col bg-[var(--color-bg-card)] shadow-[var(--shadow-xl)]" onClick={(event) => event.stopPropagation()} aria-label="素材详情">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-[var(--color-text)]">{previewAsset.filename}</p>
                <p className="text-[11px] text-[var(--color-text-muted)]">{formatSize(previewAsset.size_bytes)} · {previewAsset.mime_type}</p>
              </div>
              <button type="button" aria-label="关闭详情" className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)]" onClick={() => setPreviewAsset(null)}><X size={19} /></button>
            </div>
            <AssetThumbnail asset={previewAsset} className="min-h-0 flex-1" />
            <div className="space-y-3 border-t border-[var(--color-border)] p-4 text-xs">
              <DetailRow label="状态" value={statusDisplay(previewAsset).label} />
              <DetailRow label="分类" value={previewAsset.is_referenced ? '题库素材' : '缓存'} />
              <DetailRow label="存储位置" value={previewAsset.source === 'import_batch' ? '导入批次' : '题库目录'} />
              {previewAsset.batch_id && <DetailRow label="导入批次" value={shortBatchId(previewAsset.batch_id)} />}
              <DetailRow label="更新时间" value={formatDate(previewAsset.modified_at)} />
              <div>
                <p className="text-[var(--color-text-muted)]">路径</p>
                <div className="mt-1 flex items-start gap-2 rounded bg-[var(--color-bg-code)] p-2 font-mono text-[11px] text-[var(--color-text-secondary)]">
                  <span className="min-w-0 flex-1 break-all">{previewAsset.relative_path}</span>
                  <button type="button" aria-label="复制路径" onClick={() => void copyPath(previewAsset.relative_path)}><Clipboard size={14} /></button>
                </div>
              </div>
              {(previewAsset.reference_question_ids ?? []).length > 0 && (
                <div>
                  <p className="text-[var(--color-text-muted)]">引用题目</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(previewAsset.reference_question_ids ?? []).map((id) => <span key={id} className="rounded bg-[var(--color-green-light)] px-2 py-1 text-[10px] text-[var(--color-green)]">{id}</span>)}
                  </div>
                </div>
              )}
            </div>
          </aside>
        </div>
      )}

      {cacheCleanupPreview && (
        <ConfirmDialog title={cacheCleanupPreview.batch_id ? '删除当前批次缓存' : '清空未使用缓存'} icon={<Trash2 size={20} />} onClose={() => setCacheCleanupPreview(null)}>
          <p>
            {cacheCleanupPreview.batch_id
              ? `将删除批次 ${shortBatchId(cacheCleanupPreview.batch_id)} 中尚未被题目使用的图片。`
              : '将删除所有尚未被题目使用的图片缓存。题库素材不会受到影响。'}
          </p>
          <div className="my-4 grid grid-cols-2 gap-2">
            <StatCard label="涉及批次" value={`${cacheCleanupPreview.batch_count} 个`} />
            <StatCard label="可清除文件" value={`${cacheCleanupPreview.candidate_count} 个`} tone="warning" />
            <StatCard label="预计释放" value={formatSize(cacheCleanupPreview.reclaimable_bytes)} tone="warning" />
            <StatCard label="受保护文件" value={`${cacheCleanupPreview.protected_count} 个`} />
          </div>
          {cacheCleanupPreview.active_batches.length > 0 && (
            <p className="rounded bg-[var(--color-orange-light)] p-2 text-xs text-[var(--color-orange)]">
              {cacheCleanupPreview.active_batches.length} 个正在处理或校对的批次已自动跳过。
            </p>
          )}
          <p className="mt-3 text-xs text-[var(--color-text-muted)]">正在导入或校对的批次会自动跳过。删除操作不可撤销。</p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCacheCleanupPreview(null)}>取消</Button>
            <Button variant="danger" loading={clearingCache} disabled={cacheCleanupPreview.candidate_count === 0} onClick={() => void confirmCacheCleanup()}>确认清除</Button>
          </div>
        </ConfirmDialog>
      )}

      {storageAnalysis && (
        <ConfirmDialog title="素材存储分析" icon={<HardDrive size={20} />} onClose={() => setStorageAnalysis(null)}>
          <p>已检查当前分类中的 {storageAnalysis.scanned_files} 个文件。本分析只读取文件，不会自动删除或修改素材。</p>
          <div className="my-4 grid grid-cols-2 gap-2">
            <StatCard label="重复副本" value={`${storageAnalysis.duplicate_files} 个`} tone={storageAnalysis.duplicate_files ? 'warning' : 'neutral'} />
            <StatCard label="可节省空间" value={formatSize(storageAnalysis.reclaimable_bytes)} tone={storageAnalysis.reclaimable_bytes ? 'warning' : 'neutral'} />
            <StatCard label="损坏文件" value={`${storageAnalysis.corrupt_files.length} 个`} tone={storageAnalysis.corrupt_files.length ? 'warning' : 'neutral'} />
            <StatCard label="异常大小" value={`${storageAnalysis.tiny_files.length + storageAnalysis.oversized_files.length} 个`} />
          </div>
          {storageAnalysis.groups.length > 0 && (
            <div className="max-h-48 space-y-2 overflow-y-auto">
              {storageAnalysis.groups.slice(0, 8).map((group) => (
                <div key={group.content_hash} className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-2 text-xs">
                  <div className="flex justify-between font-medium text-[var(--color-text)]">
                    <span>{group.copies} 个相同文件</span><span>可节省 {formatSize(group.reclaimable_bytes)}</span>
                  </div>
                  <p className="mt-1 truncate font-mono text-[10px] text-[var(--color-text-muted)]" title={group.paths[0]}>{group.paths[0]}</p>
                </div>
              ))}
            </div>
          )}
          <div className="mt-5 flex justify-end">
            <Button variant="primary" onClick={() => setStorageAnalysis(null)}>完成</Button>
          </div>
        </ConfirmDialog>
      )}

      {deleteAsset && (
        <ConfirmDialog title="删除素材" icon={<AlertTriangle size={20} />} onClose={() => setDeleteAsset(null)}>
          <p>确定删除“{deleteAsset.filename}”吗？</p>
          <p className="mt-2 break-all rounded bg-[var(--color-bg-code)] p-2 text-xs text-[var(--color-text-muted)]">{deleteAsset.relative_path}</p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteAsset(null)}>取消</Button>
            <Button variant="danger" loading={deleting} onClick={() => void confirmDelete()}>确认删除</Button>
          </div>
        </ConfirmDialog>
      )}
    </div>
  );
}

function SourceTab({ active, icon, label, count, onClick }: { active: boolean; icon: React.ReactNode; label: string; count: number; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`relative flex items-center gap-2 px-4 py-2 text-sm font-medium transition ${active ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'}`}>
      {icon}<span>{label}</span><span className="rounded-full bg-[var(--color-bg-hover)] px-1.5 py-0.5 text-[10px]">{count}</span>
      {active && <span className="absolute inset-x-2 bottom-[-1px] h-0.5 rounded bg-[var(--color-accent)]" />}
    </button>
  );
}

function StatCard({ icon, label, value, tone = 'neutral' }: { icon?: React.ReactNode; label: string; value: string; tone?: 'neutral' | 'success' | 'warning' }) {
  const toneClass = tone === 'success' ? 'text-[var(--color-green)]' : tone === 'warning' ? 'text-[var(--color-orange)]' : 'text-[var(--color-text)]';
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2">
      <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">{icon}{label}</div>
      <p className={`mt-0.5 text-sm font-bold ${toneClass}`}>{value}</p>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4"><span className="text-[var(--color-text-muted)]">{label}</span><span className="text-right font-medium text-[var(--color-text)]">{value}</span></div>;
}

function EmptyState({ source, filtered }: { source: 'question_bank' | 'import_batch'; filtered: boolean }) {
  return (
    <div className="flex h-full min-h-64 items-center justify-center">
      <div className="max-w-sm text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]">
          {source === 'import_batch' ? <FolderArchive size={24} /> : <Database size={24} />}
        </div>
        <p className="mt-3 text-sm font-semibold text-[var(--color-text)]">{filtered ? '没有符合条件的素材' : source === 'import_batch' ? '缓存为空' : '暂无题库素材'}</p>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">{filtered ? '尝试清除筛选条件或更换关键词' : '导入文档或为题目添加图片后，素材会显示在这里'}</p>
      </div>
    </div>
  );
}

function ConfirmDialog({ title, icon, onClose, children }: { title: string; icon: React.ReactNode; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 shadow-[var(--shadow-xl)]" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-base font-bold text-[var(--color-text)]">{icon}{title}</div>
          <button type="button" aria-label="关闭" className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)]" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="text-sm text-[var(--color-text-secondary)]">{children}</div>
      </div>
    </div>
  );
}
