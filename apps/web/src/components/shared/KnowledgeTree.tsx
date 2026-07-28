import { useCallback, useEffect, useMemo, useState } from 'react';

import { fetchKnowledgePointCounts, fetchKnowledgePoints } from '../../services/api';
import type { KnowledgePointFlatItem, KnowledgeTreeLevel2, KnowledgeTreeNode } from '../../types';

interface Props {
  onSelect: (topic1Id?: string, topic2Id?: string, topic3Id?: string) => void;
  selectedTopic1?: string;
  selectedTopic2?: string;
  selectedTopic3?: string;
}

function buildKnowledgeTree(items: KnowledgePointFlatItem[]): KnowledgeTreeNode[] {
  const topic1Map = new Map<string, KnowledgeTreeNode>();

  for (const item of items) {
    if (!topic1Map.has(item.topic1_id)) {
      topic1Map.set(item.topic1_id, {
        topic1_id: item.topic1_id,
        topic1_name: item.topic1_name,
        children: [],
      });
    }

    const topic1 = topic1Map.get(item.topic1_id)!;
    const topic2List = topic1.children as KnowledgeTreeLevel2[];

    let topic2 = topic2List.find((node) => node.topic2_id === item.topic2_id);
    if (!topic2) {
      topic2 = { topic2_id: item.topic2_id, topic2_name: item.topic2_name, children: [] };
      topic2List.push(topic2);
    }

    if (!topic2.children?.find((node) => node.topic3_id === item.topic3_id)) {
      topic2.children?.push({ topic3_id: item.topic3_id, topic3_name: item.topic3_name });
    }
  }

  return Array.from(topic1Map.values());
}

function matchText(text: string, query: string): boolean {
  return text.toLowerCase().includes(query.toLowerCase());
}

function isSelected(
  topic1Id: string,
  topic2Id: string | undefined,
  topic3Id: string | undefined,
  selectedTopic1?: string,
  selectedTopic2?: string,
  selectedTopic3?: string,
): boolean {
  if (selectedTopic3 !== undefined && topic3Id !== undefined) {
    return topic3Id === selectedTopic3;
  }
  if (selectedTopic2 !== undefined && topic2Id !== undefined) {
    return topic2Id === selectedTopic2 && selectedTopic3 === undefined;
  }
  return topic1Id === selectedTopic1 && selectedTopic2 === undefined;
}

export default function KnowledgeTree({
  onSelect,
  selectedTopic1,
  selectedTopic2,
  selectedTopic3,
}: Props) {
  const [tree, setTree] = useState<KnowledgeTreeNode[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetchKnowledgePoints(),
      fetchKnowledgePointCounts().catch(() => ({})),
    ])
      .then(([flatItems, countMap]) => {
        if (!cancelled) {
          const nextTree = buildKnowledgeTree(Array.isArray(flatItems) ? flatItems : []);
          setTree(nextTree);
          setCounts(countMap || {});
          setExpanded((prev) => {
            if (prev.size > 0) return prev;
            return new Set(nextTree.map((node) => node.topic1_id));
          });
        }
      })
      .catch(() => {
        if (!cancelled) setTree([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedTopic1) {
      setExpanded((prev) => {
        const next = new Set(prev);
        next.add(selectedTopic1);
        if (selectedTopic2) next.add(selectedTopic2);
        return next;
      });
    }
  }, [selectedTopic1, selectedTopic2]);

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleClear = useCallback(() => {
    onSelect(undefined, undefined, undefined);
  }, [onSelect]);

  const filteredTree = useMemo(() => {
    if (!search.trim()) return tree;

    const query = search.trim();
    const result: KnowledgeTreeNode[] = [];

    for (const topic1 of tree) {
      const topic1Matches = matchText(topic1.topic1_name, query);
      const topic2Filtered: KnowledgeTreeLevel2[] = [];

      for (const topic2 of topic1.children || []) {
        const topic2Matches = matchText(topic2.topic2_name, query);
        const topic3Filtered = (topic2.children || []).filter((topic3) => matchText(topic3.topic3_name, query));

        if (topic2Matches || topic3Filtered.length > 0) {
          topic2Filtered.push({ ...topic2, children: topic3Filtered });
        }
      }

      if (topic1Matches || topic2Filtered.length > 0) {
        result.push({ ...topic1, children: topic2Filtered });
      }
    }

    return result;
  }, [tree, search]);

  const hasSelection = selectedTopic1 !== undefined;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-shrink-0 space-y-1.5 border-b p-2" style={{ borderColor: 'var(--color-border)' }}>
        <input
          type="text"
          placeholder="搜索知识点"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="w-full rounded-md border px-2 py-1.5 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
          }}
        />
        {hasSelection && (
          <button
            onClick={handleClear}
            className="w-full cursor-pointer rounded px-2 py-1 text-xs transition-colors"
            style={{
              background: 'var(--color-accent-light)',
              color: 'var(--color-accent-dark)',
            }}
          >
            清除选择
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-1">
        {loading ? (
          <div className="p-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
            加载中...
          </div>
        ) : tree.length === 0 ? (
          <div className="p-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
            暂无知识点数据
          </div>
        ) : (
          <>
            {filteredTree.map((topic1) => {
              const topic1Expanded = search ? true : expanded.has(topic1.topic1_id);
              const topic1Selected = isSelected(
                topic1.topic1_id,
                undefined,
                undefined,
                selectedTopic1,
                selectedTopic2,
                selectedTopic3,
              );

              return (
                <div key={topic1.topic1_id}>
                  <button
                    onClick={() => {
                      toggle(topic1.topic1_id);
                      onSelect(topic1.topic1_id, undefined, undefined);
                    }}
                    className="flex w-full cursor-pointer items-center gap-1 rounded px-1.5 py-1 text-left text-xs transition-colors"
                    style={{
                      background: topic1Selected ? 'var(--color-accent-light)' : 'transparent',
                      color: topic1Selected ? 'var(--color-accent-dark)' : 'var(--color-text)',
                      fontWeight: topic1Selected ? 600 : 400,
                    }}
                  >
                    <span className="w-3 shrink-0 text-xs">{topic1Expanded ? '▾' : '▸'}</span>
                    <span className="truncate">{topic1.topic1_name}</span>
                  </button>

                  {topic1Expanded &&
                    (topic1.children || []).map((topic2) => {
                      const topic2Expanded = search ? true : expanded.has(topic2.topic2_id);
                      const topic2Selected = isSelected(
                        topic1.topic1_id,
                        topic2.topic2_id,
                        undefined,
                        selectedTopic1,
                        selectedTopic2,
                        selectedTopic3,
                      );

                      return (
                        <div key={topic2.topic2_id} className="ml-3">
                          <button
                            onClick={() => {
                              toggle(topic2.topic2_id);
                              onSelect(topic1.topic1_id, topic2.topic2_id, undefined);
                            }}
                            className="flex w-full cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-left text-xs transition-colors"
                            style={{
                              background: topic2Selected ? 'var(--color-accent-light)' : 'transparent',
                              color: topic2Selected ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)',
                              fontWeight: topic2Selected ? 600 : 400,
                            }}
                          >
                            <span className="w-3 shrink-0 text-xs">{topic2Expanded ? '▾' : '▸'}</span>
                            <span className="truncate">{topic2.topic2_name}</span>
                          </button>

                          {topic2Expanded &&
                            (topic2.children || []).map((topic3) => {
                              const topic3Selected = isSelected(
                                topic1.topic1_id,
                                topic2.topic2_id,
                                topic3.topic3_id,
                                selectedTopic1,
                                selectedTopic2,
                                selectedTopic3,
                              );
                              const count = counts[topic3.topic3_id];

                              return (
                                <button
                                  key={topic3.topic3_id}
                                  onClick={() => onSelect(topic1.topic1_id, topic2.topic2_id, topic3.topic3_id)}
                                  className="ml-3 flex w-full cursor-pointer items-center gap-1 rounded px-3 py-0.5 text-left text-xs transition-colors"
                                  style={{
                                    background: topic3Selected ? 'var(--color-accent-light)' : 'transparent',
                                    color: topic3Selected ? 'var(--color-accent-dark)' : 'var(--color-text-muted)',
                                    fontWeight: topic3Selected ? 500 : 400,
                                    borderLeft: topic3Selected
                                      ? '2px solid var(--color-accent)'
                                      : '2px solid transparent',
                                  }}
                                >
                                  <span className="min-w-0 flex-1 truncate">{topic3.topic3_name}</span>
                                  {count !== undefined && count > 0 && (
                                    <span
                                      className="shrink-0 rounded-full px-1.5 text-xs"
                                      style={{
                                        background: 'var(--color-bg-hover)',
                                        color: 'var(--color-text-muted)',
                                      }}
                                    >
                                      {count}
                                    </span>
                                  )}
                                </button>
                              );
                            })}
                        </div>
                      );
                    })}
                </div>
              );
            })}

            <button
              onClick={handleClear}
              className="mt-2 w-full cursor-pointer rounded px-2 py-1.5 text-left text-xs transition-colors"
              style={{
                background: !hasSelection ? 'var(--color-accent-light)' : 'transparent',
                color: !hasSelection ? 'var(--color-accent-dark)' : 'var(--color-text-muted)',
                fontWeight: !hasSelection ? 600 : 400,
              }}
            >
              全部题目
            </button>
          </>
        )}
      </div>
    </div>
  );
}
