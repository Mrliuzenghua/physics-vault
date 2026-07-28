import { useCallback, useEffect, useState } from 'react';

import {
  batchMoveQuestions,
  createCollection,
  fetchCollectionTree,
} from '../../services/api';
import type { BatchMoveResponse, CollectionNode } from '../../types';

interface Props {
  questionIds: string[];
  open: boolean;
  onClose: () => void;
}

export default function BatchMoveDialog({ questionIds, open, onClose }: Props) {
  const [tree, setTree] = useState<CollectionNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [newParentId, setNewParentId] = useState<string | null>(null);
  void setNewParentId; // referenced in JSX by linter-generated code
  const [newType, setNewType] = useState<string>('directory');
  const [moving, setMoving] = useState(false);
  const [result, setResult] = useState<BatchMoveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTree = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchCollectionTree();
      setTree(data);
    } catch {
      setError('加载目录树失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadTree();
      setResult(null);
      setError(null);
      setNewName('');
    }
  }, [open, loadTree]);

  const handleMove = useCallback(async () => {
    if (!selectedId || questionIds.length === 0) return;
    setMoving(true);
    setError(null);
    try {
      const res = await batchMoveQuestions({
        question_ids: questionIds,
        target_collection_id: selectedId,
      });
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '移动失败');
    } finally {
      setMoving(false);
    }
  }, [selectedId, questionIds]);

  const handleCreate = useCallback(async () => {
    if (!newName.trim()) return;
    try {
      await createCollection({
        name: newName.trim(),
        parent_id: newParentId,
        type: newType,
      });
      setNewName('');
      await loadTree();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '创建失败');
    }
  }, [newName, newParentId, newType, loadTree]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={onClose}
    >
      <div
        className="rounded-xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col"
        style={{ background: 'var(--color-bg-card)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <h2 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>
            批量移动到目录/专题
          </h2>
          <button
            onClick={onClose}
            className="cursor-pointer rounded px-2 py-0.5 text-lg leading-none"
            style={{ color: 'var(--color-text-muted)' }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            已选 {questionIds.length} 道题 · 选择目标目录或专题
          </p>

          {/* Error */}
          {error && (
            <div
              className="rounded p-2 text-xs"
              style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
            >
              {error}
            </div>
          )}

          {/* Result */}
          {result && (
            <div
              className="rounded p-3 text-xs space-y-1"
              style={{ background: 'var(--color-green-light)', color: 'var(--color-green)' }}
            >
              <div className="font-semibold">移动完成</div>
              <div>
                成功 {result.success_count} · 跳过 {result.skipped_count} · 失败 {result.failed_count}
              </div>
            </div>
          )}

          {/* Collection tree */}
          <div className="text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
            选择目标目录
          </div>
          {loading ? (
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>加载中...</p>
          ) : tree.length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>暂无目录，请先新建</p>
          ) : (
            <div className="space-y-0.5 max-h-48 overflow-y-auto rounded border p-2" style={{ borderColor: 'var(--color-border)' }}>
              {tree.map((node) => (
                <TreeNode
                  key={node.id}
                  node={node}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  depth={0}
                />
              ))}
            </div>
          )}

          {/* Create new */}
          <div
            className="rounded border p-3 space-y-2"
            style={{ borderColor: 'var(--color-border)' }}
          >
            <div className="text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
              新建目录/专题
            </div>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="输入名称"
              className="w-full rounded border px-2 py-1.5 text-xs outline-none"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg)',
                color: 'var(--color-text)',
              }}
            />
            <div className="flex gap-2">
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                className="rounded border px-2 py-1 text-xs outline-none"
                style={{
                  borderColor: 'var(--color-border)',
                  background: 'var(--color-bg)',
                  color: 'var(--color-text)',
                }}
              >
                <option value="directory">目录</option>
                <option value="topic">专题</option>
                <option value="subtopic">子专题</option>
              </select>
              <button
                onClick={handleCreate}
                disabled={!newName.trim()}
                className="cursor-pointer rounded border-none px-3 py-1 text-xs font-medium text-white transition-colors disabled:opacity-50"
                style={{ background: 'var(--color-accent)' }}
              >
                新建
              </button>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex-shrink-0 flex items-center gap-2 px-4 py-3 border-t"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <button
            onClick={onClose}
            className="cursor-pointer rounded border px-3 py-1.5 text-xs transition-colors"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-hover)',
              color: 'var(--color-text-secondary)',
            }}
          >
            取消
          </button>
          <button
            onClick={handleMove}
            disabled={!selectedId || moving || questionIds.length === 0}
            className="cursor-pointer rounded border-none px-4 py-1.5 text-xs font-semibold text-white transition-colors disabled:opacity-50"
            style={{ background: 'var(--color-accent)' }}
          >
            {moving ? '移动中...' : '确认移动'}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Recursive tree node renderer. */
function TreeNode({
  node,
  selectedId,
  onSelect,
  depth,
}: {
  node: CollectionNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  depth: number;
}) {
  const isSelected = node.id === selectedId;
  const icon = node.type === 'directory' ? '📁' : node.type === 'topic' ? '📘' : '📄';

  return (
    <div>
      <button
        onClick={() => onSelect(node.id)}
        className="w-full cursor-pointer flex items-center gap-2 rounded px-2 py-1 text-left text-xs transition-colors"
        style={{
          paddingLeft: 8 + depth * 16,
          background: isSelected ? 'var(--color-accent-light)' : 'transparent',
          color: isSelected ? 'var(--color-accent)' : 'var(--color-text)',
          fontWeight: isSelected ? 600 : 400,
        }}
      >
        <span>{icon}</span>
        <span className="flex-1 truncate">{node.name}</span>
        <span style={{ color: 'var(--color-text-muted)', fontSize: 10 }}>
          {node.question_count > 0 ? node.question_count : ''}
        </span>
      </button>
      {node.children?.map((child) => (
        <TreeNode
          key={child.id}
          node={child}
          selectedId={selectedId}
          onSelect={onSelect}
          depth={depth + 1}
        />
      ))}
    </div>
  );
}
