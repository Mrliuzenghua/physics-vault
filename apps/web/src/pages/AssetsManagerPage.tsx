import { useCallback, useEffect, useState } from 'react';

import {
  cleanupUnreferencedAssets,
  deleteSingleAsset,
  fetchAssetList,
} from '../services/api';
import type { AssetItem, AssetListResponse } from '../types';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const FILTER_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'referenced', label: '已引用' },
  { value: 'unreferenced', label: '无引用' },
] as const;

export default function AssetsManagerPage() {
  const [data, setData] = useState<AssetListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<string>('all');
  const [keyword, setKeyword] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [cleaning, setCleaning] = useState(false);
  const [cleanResult, setCleanResult] = useState<string | null>(null);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [previewAsset, setPreviewAsset] = useState<AssetItem | null>(null);

  // ── Load ──
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAssetList(filterMode, keyword);
      setData(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '加载失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [filterMode, keyword]);

  useEffect(() => {
    load();
  }, [load]);

  // ── Search ──
  const handleSearch = useCallback(() => {
    setKeyword(searchInput);
  }, [searchInput]);

  // ── Cleanup ──
  const handleCleanup = useCallback(async () => {
    const unreferencedCount = data?.stats.unreferenced ?? 0;
    if (unreferencedCount === 0) {
      setCleanResult('没有可清理的无引用素材');
      return;
    }

    const confirmed = window.confirm(
      `确定要删除全部 ${unreferencedCount} 个无引用素材吗？此操作不可撤销。`,
    );
    if (!confirmed) return;

    setCleaning(true);
    setCleanResult(null);
    try {
      const result = await cleanupUnreferencedAssets();
      const msg = result.deleted_count > 0
        ? `已清理 ${result.deleted_count} 个文件，释放 ${formatSize(result.freed_bytes)}`
        : '没有需要清理的素材';
      setCleanResult(msg);
      if (result.errors.length > 0) {
        setCleanResult((prev) => `${prev}（${result.errors.length} 个错误）`);
      }
      // Reload
      await load();
    } catch (err: unknown) {
      setCleanResult(`清理失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setCleaning(false);
    }
  }, [data, load]);

  // ── Single delete ──
  const handleDeleteSingle = useCallback(
    async (asset: AssetItem) => {
      if (asset.is_referenced) {
        alert('该素材仍被题目引用，不能删除。');
        return;
      }

      const confirmed = window.confirm(`确定要删除 "${asset.filename}" 吗？`);
      if (!confirmed) return;

      setDeletingFile(asset.filename);
      try {
        const result = await deleteSingleAsset(asset.filename);
        if (result.success) {
          await load();
        } else {
          alert(result.message);
        }
      } catch (err: unknown) {
        alert(`删除失败：${err instanceof Error ? err.message : '未知错误'}`);
      } finally {
        setDeletingFile(null);
      }
    },
    [load],
  );

  // ── Filter change ──
  const handleFilterChange = useCallback((mode: string) => {
    setFilterMode(mode);
  }, []);

  // ── Derived ──
  const stats = data?.stats;
  const assets = data?.assets ?? [];

  // ── Render ──
  return (
    <div className="flex h-full flex-col" style={{ background: 'var(--color-bg)' }}>
      {/* Header */}
      <div
        className="flex-shrink-0 border-b px-4 py-3"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
      >
        <h1 className="text-lg font-bold" style={{ color: 'var(--color-text)' }}>
          素材管理
        </h1>
        <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          管理题图素材，清理无引用文件
        </p>
      </div>

      {/* Stats bar */}
      {stats && (
        <div
          className="flex-shrink-0 border-b px-4 py-2"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-sidebar)' }}
        >
          <div className="flex items-center gap-6 text-xs">
            <span style={{ color: 'var(--color-text-muted)' }}>
              素材总数{' '}
              <strong style={{ color: 'var(--color-text)' }}>{stats.total}</strong>
            </span>
            <span style={{ color: 'var(--color-text-muted)' }}>
              已引用{' '}
              <strong style={{ color: 'var(--color-green)' }}>{stats.referenced}</strong>
            </span>
            <span style={{ color: 'var(--color-text-muted)' }}>
              无引用{' '}
              <strong style={{ color: 'var(--color-red)' }}>
                {stats.unreferenced}
              </strong>
            </span>
            <span style={{ color: 'var(--color-text-muted)' }}>
              总占用{' '}
              <strong style={{ color: 'var(--color-text)' }}>
                {formatSize(stats.total_size_bytes)}
              </strong>
            </span>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div
        className="flex-shrink-0 flex items-center gap-3 border-b px-4 py-2"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
      >
        {/* Filters */}
        <div className="flex rounded-lg border overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleFilterChange(opt.value)}
              className="cursor-pointer border-none px-3 py-1 text-xs font-medium transition-colors"
              style={{
                background: filterMode === opt.value ? 'var(--color-accent)' : 'transparent',
                color: filterMode === opt.value ? '#fff' : 'var(--color-text-secondary)',
                borderRight: '1px solid var(--color-border)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
          placeholder="搜索文件名..."
          className="rounded border px-2 py-1 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
            width: 180,
          }}
        />
        <button
          onClick={handleSearch}
          className="cursor-pointer rounded border px-2.5 py-1 text-xs transition-colors"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-hover)',
            color: 'var(--color-text-secondary)',
          }}
        >
          搜索
        </button>

        <div style={{ flex: 1 }} />

        {/* Cleanup button */}
        <button
          onClick={handleCleanup}
          disabled={cleaning || (stats?.unreferenced ?? 0) === 0}
          className="cursor-pointer rounded-lg border-none px-4 py-1.5 text-xs font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--color-red)' }}
        >
          {cleaning ? '清理中...' : '清理无引用素材'}
        </button>

        {/* Refresh */}
        <button
          onClick={load}
          disabled={loading}
          className="cursor-pointer rounded border px-3 py-1 text-xs transition-colors"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-hover)',
            color: 'var(--color-text-secondary)',
          }}
        >
          刷新
        </button>
      </div>

      {/* Result message */}
      {cleanResult && (
        <div
          className="flex-shrink-0 px-4 py-1.5 text-xs"
          style={{
            background: 'var(--color-green-light)',
            color: 'var(--color-green)',
          }}
        >
          {cleanResult}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex-shrink-0 px-4 py-1.5 text-xs" style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
            加载中...
          </p>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && assets.length === 0 && (
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <div className="mb-3 text-4xl">🖼</div>
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              暂无素材文件
            </p>
            <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
              {filterMode !== 'all' ? '当前筛选条件下无结果' : '素材目录为空或不存在支持的图片格式'}
            </p>
          </div>
        </div>
      )}

      {/* Asset grid with thumbnails */}
      {!loading && !error && assets.length > 0 && (
        <div className="flex-1 overflow-y-auto p-4">
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
            {assets.map((asset) => (
              <div
                key={asset.relative_path}
                className="rounded-lg border overflow-hidden transition-all hover:-translate-y-0.5"
                style={{
                  borderColor: 'var(--color-border)',
                  background: 'var(--color-bg-card)',
                  boxShadow: 'var(--shadow-card)',
                  opacity: asset.is_referenced ? 1 : 0.75,
                }}
              >
                {/* Thumbnail — click to preview */}
                <div
                  onClick={() => setPreviewAsset(previewAsset?.relative_path === asset.relative_path ? null : asset)}
                  className="cursor-pointer flex items-center justify-center"
                  style={{
                    height: 120,
                    background: 'var(--color-bg-code)',
                    borderBottom: '1px solid var(--color-border)',
                    overflow: 'hidden',
                  }}
                >
                  <img
                    src={`/files/data/assets/questions/${asset.relative_path}`}
                    alt={asset.filename}
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                    }}
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                      const ph = (e.target as HTMLImageElement).nextElementSibling;
                      if (ph) (ph as HTMLElement).style.display = 'flex';
                    }}
                  />
                  <span
                    style={{
                      display: 'none',
                      fontSize: 36,
                      color: 'var(--color-text-muted)',
                    }}
                  >
                    🖼
                  </span>
                </div>

                {/* Info */}
                <div className="p-2 space-y-1">
                  <div className="text-xs font-medium truncate" style={{ color: 'var(--color-text)' }} title={asset.filename}>
                    {asset.filename}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    {formatSize(asset.size_bytes)}
                    {asset.is_referenced ? (
                      <span className="ml-1" style={{ color: 'var(--color-green)' }}>· 已引用</span>
                    ) : (
                      <span className="ml-1" style={{ color: 'var(--color-red)' }}>· 无引用</span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="px-2 pb-2">
                  <button
                    onClick={() => handleDeleteSingle(asset)}
                    disabled={asset.is_referenced || deletingFile === asset.filename}
                    className="w-full cursor-pointer rounded border px-2 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-30"
                    style={{
                      borderColor: 'var(--color-red)',
                      color: 'var(--color-red)',
                      background: 'transparent',
                    }}
                    title={asset.is_referenced ? '仅可删除未被引用的素材' : '删除此素材'}
                  >
                    {deletingFile === asset.filename ? '删除中...' : '删除'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Preview modal */}
      {previewAsset && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.7)' }}
          onClick={() => setPreviewAsset(null)}
        >
          <div
            className="rounded-xl overflow-hidden"
            style={{ maxWidth: '90vw', maxHeight: '90vh' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-2" style={{ background: 'var(--color-bg-card)' }}>
              <span className="text-sm font-medium truncate" style={{ color: 'var(--color-text)' }}>
                {previewAsset.filename}
              </span>
              <span className="text-xs ml-4" style={{ color: 'var(--color-text-muted)' }}>
                {formatSize(previewAsset.size_bytes)}
              </span>
              <button
                onClick={() => setPreviewAsset(null)}
                className="ml-4 cursor-pointer rounded px-2 py-1 text-lg leading-none"
                style={{ color: 'var(--color-text-muted)', background: 'none', border: 'none' }}
              >
                ×
              </button>
            </div>
            <img
              src={`/files/data/assets/questions/${previewAsset.relative_path}`}
              alt={previewAsset.filename}
              style={{ maxWidth: '90vw', maxHeight: '80vh', display: 'block' }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
