import { useCallback, useEffect, useMemo, useState } from 'react';

import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { createCollection, fetchCollectionTree } from '../services/api';
import type { CollectionNode } from '../types';

type CollectionType = 'directory' | 'topic' | 'subtopic';

const TYPE_LABELS: Record<CollectionType, string> = {
  directory: '目录',
  topic: '专题',
  subtopic: '子专题',
};

const TYPE_OPTIONS = [
  { value: 'directory', label: '目录' },
  { value: 'topic', label: '专题' },
  { value: 'subtopic', label: '子专题' },
];

const TYPE_BADGE_CLASS: Record<CollectionType, string> = {
  directory: 'bg-[var(--color-accent-light)] text-[var(--color-accent)]',
  topic: 'bg-[var(--color-teal-light)] text-[var(--color-teal)]',
  subtopic: 'bg-[var(--color-purple-light)] text-[var(--color-purple)]',
};

function flattenTree(nodes: CollectionNode[], depth = 0): Array<{ id: string; name: string; depth: number }> {
  return nodes.flatMap((node) => [
    { id: node.id, name: node.name, depth },
    ...flattenTree(node.children || [], depth + 1),
  ]);
}

function countNodes(nodes: CollectionNode[]): number {
  return nodes.reduce((sum, node) => sum + 1 + countNodes(node.children || []), 0);
}

function countQuestions(nodes: CollectionNode[]): number {
  return nodes.reduce((sum, node) => sum + (node.question_count || 0) + countQuestions(node.children || []), 0);
}

export default function CollectionsPage() {
  const [tree, setTree] = useState<CollectionNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<CollectionType>('directory');
  const [parentId, setParentId] = useState('');
  const [message, setMessage] = useState<string | null>(null);

  const flatNodes = useMemo(() => flattenTree(tree), [tree]);
  const totalNodes = useMemo(() => countNodes(tree), [tree]);
  const totalQuestions = useMemo(() => countQuestions(tree), [tree]);

  const parentOptions = useMemo(
    () => [
      { value: '', label: '作为根节点' },
      ...flatNodes.map((node) => ({
        value: node.id,
        label: `${'　'.repeat(node.depth)}${node.name}`,
      })),
    ],
    [flatNodes],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCollectionTree();
      setTree(data);
      setExpanded((prev) => {
        if (prev.size > 0) return prev;
        return new Set(data.map((node) => node.id));
      });
    } catch (err: unknown) {
      setError((err as Error).message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const created = await createCollection({
        name: newName.trim(),
        type: newType,
        parent_id: parentId || null,
      });
      setNewName('');
      setMessage('创建成功');
      setExpanded((prev) => {
        const next = new Set(prev);
        if (created.parent_id) next.add(created.parent_id);
        return next;
      });
      window.setTimeout(() => setMessage(null), 2000);
      await load();
    } catch (err: unknown) {
      setMessage(`创建失败: ${(err as Error).message || '未知错误'}`);
    }
  };

  const renderNode = (node: CollectionNode, depth = 0) => {
    const hasChildren = node.children && node.children.length > 0;
    const isOpen = expanded.has(node.id);
    const type = node.type as CollectionType;

    return (
      <div key={node.id}>
        <div
          className="flex items-center gap-2 rounded-md px-2 py-2 transition-colors hover:bg-[var(--color-bg-hover)]"
          style={{ paddingLeft: 16 + depth * 20, background: isOpen ? 'var(--color-bg-hover)' : 'transparent' }}
        >
          <button
            type="button"
            onClick={() => hasChildren && toggleExpand(node.id)}
            className="flex h-5 w-5 items-center justify-center rounded text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-bg-card)]"
            aria-label={isOpen ? '收起' : '展开'}
          >
            {hasChildren ? (isOpen ? '▾' : '▸') : ''}
          </button>
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${TYPE_BADGE_CLASS[type] || TYPE_BADGE_CLASS.directory}`}>
            {TYPE_LABELS[type] || node.type}
          </span>
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-[var(--color-text)]">{node.name}</span>
          <Badge variant="accent" size="sm">{node.question_count ?? 0} 题</Badge>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setParentId(node.id);
              setNewType(node.type === 'directory' ? 'topic' : 'subtopic');
            }}
          >
            在此新建
          </Button>
        </div>
        {hasChildren && isOpen && node.children?.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-pulse space-y-3 text-center">
          <div className="mx-auto h-4 w-48 rounded bg-[var(--color-border)]" />
          <div className="mx-auto h-3 w-32 rounded bg-[var(--color-border)]" />
        </div>
      </div>
    );
  }

  if (error) {
    return <EmptyState icon="!" title="加载失败" description={error} action={{ label: '重试', onClick: load }} />;
  }

  return (
    <div className="flex h-full flex-col bg-[var(--color-bg)]">
      <div className="flex flex-shrink-0 flex-wrap items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
        <div>
          <h1 className="text-base font-bold text-[var(--color-text)]">目录与合集管理</h1>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            用目录、专题、子专题组织私人题库，后续可作为组卷和教学资源包的筛选入口。
          </p>
        </div>
        <Badge variant="accent" size="md">{totalNodes} 个节点</Badge>
        <Badge variant="default" size="md">{totalQuestions} 道题</Badge>
        <div className="flex-1" />

        <div className="flex flex-wrap items-end gap-2">
          <Input
            label="名称"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void handleCreate();
            }}
            placeholder="如：高一力学基础"
            size="sm"
            wrapperClassName="w-44"
          />
          <Select
            label="类型"
            options={TYPE_OPTIONS}
            value={newType}
            onChange={(event) => setNewType(event.target.value as CollectionType)}
            size="sm"
            wrapperClassName="w-28"
          />
          <Select
            label="父级"
            options={parentOptions}
            value={parentId}
            onChange={(event) => setParentId(event.target.value)}
            size="sm"
            wrapperClassName="w-44"
          />
          <Button variant="primary" size="sm" onClick={() => void handleCreate()} disabled={!newName.trim()}>
            新建
          </Button>
        </div>
        {message && (
          <span className={`text-xs ${message.includes('失败') ? 'text-[var(--color-red)]' : 'text-[var(--color-green)]'}`}>
            {message}
          </span>
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[1fr_280px] gap-4 overflow-hidden p-4">
        <div className="overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 shadow-sm">
          {tree.length === 0 ? (
            <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)]">
              <div className="text-center">
                <div className="text-sm font-semibold text-[var(--color-text)]">暂无目录</div>
                <p className="mt-1 text-sm text-[var(--color-text-muted)]">先新建一个根目录，再继续添加专题和子专题。</p>
              </div>
            </div>
          ) : (
            <div className="space-y-0.5">{tree.map((node) => renderNode(node))}</div>
          )}
        </div>

        <aside className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 shadow-sm">
          <h2 className="text-sm font-bold text-[var(--color-text)]">推荐结构</h2>
          <div className="mt-3 space-y-3 text-sm text-[var(--color-text-secondary)]">
            <div>
              <div className="font-semibold text-[var(--color-text)]">目录</div>
              <p className="mt-1 text-xs leading-5">适合放学科、年级、教材版本或校内资源库。</p>
            </div>
            <div>
              <div className="font-semibold text-[var(--color-text)]">专题</div>
              <p className="mt-1 text-xs leading-5">适合放章节、考试主题、竞赛模块或讲义单元。</p>
            </div>
            <div>
              <div className="font-semibold text-[var(--color-text)]">子专题</div>
              <p className="mt-1 text-xs leading-5">适合细分到具体模型、题型策略或易错点。</p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
