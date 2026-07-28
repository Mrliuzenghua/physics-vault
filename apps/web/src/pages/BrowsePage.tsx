import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import BatchMoveDialog from '../components/shared/BatchMoveDialog';
import FilterBar from '../components/shared/FilterBar';
import KnowledgeTree from '../components/shared/KnowledgeTree';
import QueryParamsPopover from '../components/shared/QueryParamsPopover';
import QuestionCard from '../components/shared/QuestionCard';
import RandomPickModal from '../components/shared/RandomPickModal';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { useBasket } from '../hooks/useBasket';
import { batchMarkMistake, batchUnmarkMistake, searchQuestions } from '../services/api';
import type { Question, SearchFilters } from '../types';

const SEARCH_CHIPS = ['年份', '标题', '题号', '标签', '知识点', '关键词检索', '排序', 'ID', '相似题', '重置'];

const QUICK_ACTIONS: Array<{ label: string; tone: 'blue' | 'teal' | 'red' }> = [
  { label: '新建题目', tone: 'teal' },
  { label: '随机选题', tone: 'blue' },
  { label: '查询参数', tone: 'blue' },
  { label: '刷新题目', tone: 'blue' },
  { label: '显示答案', tone: 'blue' },
  { label: '批量操作', tone: 'blue' },
  { label: '分享多题', tone: 'blue' },
  { label: '分享历史', tone: 'blue' },
  { label: '删除题目', tone: 'red' },
  { label: '加入篮子', tone: 'blue' },
];

const SEARCH_MODE_LABELS: Record<NonNullable<SearchFilters['search_mode']>, string> = {
  browse: '浏览',
  strict: '精确',
  hybrid: '混合',
  similar: '相似',
};

const QUESTION_TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multi_choice: '多选题',
  fill: '填空题',
  experiment: '实验题',
  calculation: '解答题',
};

function pillToneClass(tone: 'blue' | 'teal' | 'red') {
  if (tone === 'teal') return 'bg-[var(--color-teal)] text-white shadow-sm';
  if (tone === 'red') return 'bg-[var(--color-danger)] text-white shadow-sm';
  return 'bg-[var(--color-accent)] text-white shadow-sm';
}

function clampNumber(value: number, min: number, max: number) {
  if (Number.isNaN(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function buildDifficultyStars(level?: number) {
  const safeLevel = clampNumber(level || 0, 0, 5);
  return `${'★'.repeat(safeLevel)}${'☆'.repeat(5 - safeLevel)}`;
}

function shuffleQuestions(items: Question[]) {
  const next = [...items];
  for (let i = next.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [next[i], next[j]] = [next[j], next[i]];
  }
  return next;
}

function parseExcludedIds(text: string) {
  return new Set(
    text
      .split(/[\s,，;；]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

export default function BrowsePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { items: basketItems, add: addToBasket } = useBasket();
  const basketIds = useMemo(() => new Set(basketItems.map((item) => item.question_id)), [basketItems]);

  const [questions, setQuestions] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [batchMarking, setBatchMarking] = useState(false);
  const [moveDialogOpen, setMoveDialogOpen] = useState(false);
  const [showAnswers, setShowAnswers] = useState(false);
  const [queryPopoverOpen, setQueryPopoverOpen] = useState(false);
  const [randomModalOpen, setRandomModalOpen] = useState(false);
  const [randomLoading, setRandomLoading] = useState(false);
  const [randomPerSet, setRandomPerSet] = useState(10);
  const [randomCopies, setRandomCopies] = useState(1);
  const [randomAllowRepeat, setRandomAllowRepeat] = useState(false);
  const [randomExcludedIdsText, setRandomExcludedIdsText] = useState('');
  const [randomQuestions, setRandomQuestions] = useState<Question[]>([]);

  const filters: SearchFilters = useMemo(
    () => ({
      search_mode: (searchParams.get('search_mode') as SearchFilters['search_mode']) || 'browse',
      query: searchParams.get('query') || undefined,
      year: searchParams.get('year') ? Number(searchParams.get('year')) : undefined,
      module: searchParams.get('module') || undefined,
      question_type: searchParams.get('question_type') || undefined,
      difficulty: searchParams.get('difficulty') || undefined,
      status: searchParams.get('status') || undefined,
      is_mistake: searchParams.get('is_mistake') ? searchParams.get('is_mistake') === 'true' : undefined,
      topic1_id: searchParams.get('topic1_id') || undefined,
      topic2_id: searchParams.get('topic2_id') || undefined,
      topic3_id: searchParams.get('topic3_id') || undefined,
      limit: Number(searchParams.get('limit') || 20),
      offset: Number(searchParams.get('offset') || 0),
    }),
    [searchParams],
  );

  const updateFilters = useCallback(
    (nextFilters: SearchFilters) => {
      const params = new URLSearchParams();
      Object.entries(nextFilters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.set(key, String(value));
        }
      });
      setSearchParams(params, { replace: true });
    },
    [setSearchParams],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    searchQuestions(filters)
      .then((data) => {
        if (!cancelled) {
          setQuestions(data.items || []);
          setTotal(data.total || 0);
        }
      })
      .catch((requestError: Error) => {
        if (!cancelled) {
          setError(requestError.message);
          setQuestions([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [filters]);

  const totalPages = Math.max(1, Math.ceil(total / (filters.limit || 20)));
  const currentPage = Math.floor((filters.offset || 0) / (filters.limit || 20)) + 1;
  const requestedRandomCount = randomPerSet * randomCopies;

  const activeSummary = useMemo(
    () =>
      [
        filters.question_type && `题型: ${QUESTION_TYPE_LABELS[filters.question_type] || filters.question_type}`,
        filters.difficulty && `难度: ${buildDifficultyStars(Number(filters.difficulty))}`,
        filters.module && `模块: ${filters.module}`,
        filters.topic3_id && `考点: ${filters.topic3_id}`,
        filters.query && `关键词: ${filters.query}`,
      ].filter(Boolean) as string[],
    [filters.difficulty, filters.module, filters.query, filters.question_type, filters.topic3_id],
  );

  const randomConditionSummary = useMemo(
    () =>
      [
        `模式: ${SEARCH_MODE_LABELS[filters.search_mode || 'browse']}`,
        ...(activeSummary.length > 0 ? activeSummary : ['当前未设置额外筛选条件']),
        filters.is_mistake === true ? '仅错题' : filters.is_mistake === false ? '排除错题' : '全部题目',
      ],
    [activeSummary, filters.is_mistake, filters.search_mode],
  );

  const goToPage = useCallback(
    (page: number) => {
      if (page < 1 || page > totalPages) return;
      updateFilters({ ...filters, offset: (page - 1) * (filters.limit || 20) });
    },
    [filters, totalPages, updateFilters],
  );

  const navigateToDetail = useCallback((id: string) => {
    window.open(`/question/${id}`, '_blank');
  }, []);

  const handleKnowledgeSelect = useCallback(
    (topic1Id?: string, topic2Id?: string, topic3Id?: string) => {
      updateFilters({
        ...filters,
        topic1_id: topic1Id,
        topic2_id: topic2Id,
        topic3_id: topic3Id,
        offset: 0,
      });
    },
    [filters, updateFilters],
  );

  const handleCheck = useCallback((id: string) => {
    setCheckedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearAllFilters = useCallback(() => {
    updateFilters({ limit: filters.limit || 20, offset: 0, search_mode: 'browse' });
  }, [filters.limit, updateFilters]);

  const handleBatchMark = useCallback(async () => {
    setBatchMarking(true);
    try {
      await batchMarkMistake([...checkedIds]);
      setCheckedIds(new Set());
      updateFilters({ ...filters });
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : '批量标记错题失败');
    } finally {
      setBatchMarking(false);
    }
  }, [checkedIds, filters, updateFilters]);

  const handleBatchUnmark = useCallback(async () => {
    setBatchMarking(true);
    try {
      await batchUnmarkMistake([...checkedIds]);
      setCheckedIds(new Set());
      updateFilters({ ...filters });
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : '批量取消错题失败');
    } finally {
      setBatchMarking(false);
    }
  }, [checkedIds, filters, updateFilters]);

  const runRandomPick = useCallback(async () => {
    setRandomLoading(true);
    try {
      const excludedIds = parseExcludedIds(randomExcludedIdsText);
      const candidateLimit = Math.max(60, Math.min(200, Math.max(requestedRandomCount * 4, 120)));
      const response = await searchQuestions({
        ...filters,
        offset: 0,
        limit: candidateLimit,
      });

      const deduped = response.items.filter((question, index, list) => {
        if (excludedIds.has(question.question_id)) return false;
        return list.findIndex((item) => item.question_id === question.question_id) === index;
      });

      if (deduped.length === 0) {
        setRandomQuestions([]);
        return;
      }

      if (randomAllowRepeat) {
        const sampled = Array.from({ length: requestedRandomCount }, () => {
          const idx = Math.floor(Math.random() * deduped.length);
          return deduped[idx];
        });
        setRandomQuestions(sampled);
      } else {
        setRandomQuestions(shuffleQuestions(deduped).slice(0, requestedRandomCount));
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '随机选题失败');
      setRandomQuestions([]);
    } finally {
      setRandomLoading(false);
    }
  }, [filters, randomAllowRepeat, randomExcludedIdsText, requestedRandomCount]);

  useEffect(() => {
    if (!randomModalOpen) return;
    if (randomQuestions.length > 0) return;
    void runRandomPick();
  }, [randomModalOpen, randomQuestions.length, runRandomPick]);

  const handleAddCheckedToBasket = useCallback(() => {
    if (checkedIds.size === 0) {
      alert('请先勾选题目');
      return;
    }
    checkedIds.forEach((id) => addToBasket(id));
  }, [addToBasket, checkedIds]);

  const handleAddRandomQuestionsToBasket = useCallback(() => {
    if (randomQuestions.length === 0) {
      alert('当前没有可加入选题篮的随机题目');
      return;
    }
    randomQuestions.forEach((question) => addToBasket(question.question_id));
  }, [addToBasket, randomQuestions]);

  const handleQuickAction = useCallback(
    (label: string) => {
      if (label === '随机选题') {
        setQueryPopoverOpen(false);
        setRandomModalOpen(true);
        return;
      }

      if (label === '新建题目') {
        window.open('/question/new', '_blank');
        return;
      }

      if (label === '查询参数') {
        setQueryPopoverOpen((prev) => !prev);
        return;
      }

      if (label === '刷新题目') {
        updateFilters({ ...filters });
        return;
      }

      if (label === '显示答案') {
        setShowAnswers((prev) => !prev);
        return;
      }

      if (label === '批量操作') {
        if (basketItems.length === 0) {
          alert('请先把题目加入选题篮');
          return;
        }
        setMoveDialogOpen(true);
        return;
      }

      if (label === '加入篮子') {
        handleAddCheckedToBasket();
        return;
      }

      if (label === '删除题目') {
        setCheckedIds(new Set());
        return;
      }

      alert(`${label} 功能下一步继续补齐。`);
    },
    [basketItems.length, filters, handleAddCheckedToBasket, updateFilters],
  );

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[var(--color-bg)]">
      <div className="border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="rounded-md bg-[var(--color-bg-hover)] p-1">
              <button className="rounded bg-[var(--color-bg-card)] px-3 py-1.5 text-sm font-semibold text-[var(--color-text-main)] shadow-sm">
                题目
              </button>
              <button className="rounded px-3 py-1.5 text-sm text-[var(--color-text-muted)]">知识</button>
            </div>
            {SEARCH_CHIPS.map((chip) => (
              <button
                key={chip}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 py-1.5 text-sm text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-bg-hover)]"
              >
                {chip}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--color-text-secondary)]">
            <button
              onClick={() => goToPage(currentPage - 1)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={currentPage <= 1}
            >
              上一页
            </button>
            <button
              onClick={() => goToPage(currentPage + 1)}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={currentPage >= totalPages}
            >
              下一页
            </button>
            <span className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-1.5">
              {currentPage} / {totalPages} 页
            </span>
            <span className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-1.5">
              {questions.length} / {total}
            </span>
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 gap-3 p-3">
        <aside className="flex w-72 shrink-0 flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-sm">
          <div className="border-b border-[var(--color-border)] p-3">
            <div className="mb-3 flex items-center gap-2">
              <button className="rounded-md bg-[var(--color-teal)] px-3 py-1.5 text-sm font-semibold text-white">
                高中物理
              </button>
              <button className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-1.5 text-sm text-[var(--color-text-secondary)]">
                目录管理
              </button>
            </div>
          </div>

          <div className="min-h-0 flex-1">
            <KnowledgeTree
              onSelect={handleKnowledgeSelect}
              selectedTopic1={filters.topic1_id}
              selectedTopic2={filters.topic2_id}
              selectedTopic3={filters.topic3_id}
            />
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-hover)] shadow-sm">
          <div className="border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                  <span className="font-semibold text-[var(--color-text-main)]">题库中心</span>
                  {activeSummary.length > 0 ? (
                    activeSummary.map((item, index) => (
                      <span key={`${item}-${index}`} className="pv-chip bg-[var(--color-accent-light)] text-[var(--color-accent-dark)]">
                        {item}
                      </span>
                    ))
                  ) : (
                    <span className="text-[var(--color-text-muted)]">当前为全库浏览</span>
                  )}
                </div>
                <div className="text-xs text-[var(--color-text-muted)]">
                  已选 {checkedIds.size} 题 · 选题篮 {basketItems.length} 题 · 总计 {total} 题
                </div>
              </div>
              <div className="text-xs text-[var(--color-text-muted)]">支持按知识点、题型、难度、关键词组合筛选</div>
            </div>

            <FilterBar filters={filters} onChange={updateFilters} />

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {([
                [undefined, '全部'],
                [false, '非错题'],
                [true, '仅错题'],
              ] as const).map(([value, label]) => {
                const active = filters.is_mistake === value;
                return (
                  <button
                    key={String(value)}
                    onClick={() => updateFilters({ ...filters, is_mistake: value })}
                    className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                      active ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-hover)] text-[var(--color-text-secondary)] hover:bg-[var(--color-accent-light)]'
                    }`}
                  >
                    {label}
                  </button>
                );
              })}

              {checkedIds.size > 0 && (
                <>
                  <button
                    onClick={handleBatchMark}
                    className="rounded-md bg-[var(--color-danger-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--color-danger)]"
                  >
                    {batchMarking ? '处理中...' : '批量标记错题'}
                  </button>
                  <button
                    onClick={handleBatchUnmark}
                    className="rounded-md bg-[var(--color-accent-light)] px-3 py-1.5 text-xs font-semibold text-[var(--color-accent)]"
                  >
                    {batchMarking ? '处理中...' : '批量取消错题'}
                  </button>
                </>
              )}

              {(activeSummary.length > 0 || filters.is_mistake !== undefined) && (
                <button
                  onClick={clearAllFilters}
                  className="ml-auto rounded-md bg-[var(--color-bg-card)] px-3 py-1.5 text-xs font-semibold text-[var(--color-danger)] shadow-sm"
                >
                  清空筛选
                </button>
              )}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {loading ? (
              <div className="space-y-4">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div
                    key={index}
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-5 py-4 shadow-sm"
                  >
                    <div className="mb-3 flex items-center gap-2">
                      <div className="h-7 w-7 animate-pulse rounded-full bg-[var(--color-bg-hover)]" />
                      <div className="h-6 w-56 animate-pulse rounded bg-[var(--color-bg-hover)]" />
                      <div className="h-6 w-20 animate-pulse rounded bg-[var(--color-bg-hover)]" />
                    </div>
                    <div className="rounded-md border border-dashed border-[var(--color-border)] px-4 py-4">
                      <div className="mb-3 h-5 w-full animate-pulse rounded bg-[var(--color-bg-hover)]" />
                      <div className="h-5 w-4/5 animate-pulse rounded bg-[var(--color-bg-hover)]" />
                    </div>
                  </div>
                ))}
              </div>
            ) : error ? (
              <EmptyState
                icon="!"
                title="加载失败"
                description={error}
                action={{ label: '重试', onClick: () => updateFilters({ ...filters }) }}
              />
            ) : questions.length === 0 ? (
              <EmptyState
                icon="0"
                title="没有找到匹配的题目"
                description="试试调整筛选条件或搜索关键词"
                action={{ label: '清除所有筛选', onClick: clearAllFilters }}
              />
            ) : (
              <div className="space-y-4">
                {questions.map((question, index) => (
                  <QuestionCard
                    key={question.question_id}
                    question={question}
                    index={(filters.offset || 0) + index + 1}
                    onViewDetail={navigateToDetail}
                    onAddToBasket={addToBasket}
                    inBasket={basketIds.has(question.question_id)}
                    checked={checkedIds.has(question.question_id)}
                    onCheck={handleCheck}
                    showAnswer={showAnswers}
                  />
                ))}

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--color-bg-card)] px-4 py-3 shadow-sm">
                  <div className="text-sm text-[var(--color-text-secondary)]">
                    当前第 {currentPage} / {totalPages} 页，共 {total} 题
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1}>
                      上一页
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= totalPages}>
                      下一页
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>

        <aside className="relative flex w-[118px] shrink-0 flex-col items-stretch gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 py-3 shadow-sm">
          {QUICK_ACTIONS.map((action) => (
            <div key={action.label} className="relative">
              <button
                onClick={() => handleQuickAction(action.label)}
                className={`w-full rounded-md px-2.5 py-2 text-sm font-semibold transition-transform hover:-translate-y-0.5 ${pillToneClass(action.tone)}`}
              >
                {action.label === '显示答案' ? (showAnswers ? '隐藏答案' : '显示答案') : action.label}
              </button>
              {action.label === '查询参数' && (
                <QueryParamsPopover
                  open={queryPopoverOpen}
                  onClose={() => setQueryPopoverOpen(false)}
                  filters={filters}
                  total={total}
                />
              )}
            </div>
          ))}

          <div className="mt-2 rounded-md bg-[var(--color-bg-hover)] p-3 text-center shadow-inner">
            <div className="text-xs text-[var(--color-text-muted)]">选题篮</div>
            <div className="mt-1 text-3xl font-bold text-[var(--color-accent)]">{basketItems.length}</div>
            {basketItems.length > 0 && (
              <button
                onClick={() => window.open('/compose', '_blank')}
                className="mt-3 rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white"
              >
                去组卷
              </button>
            )}
          </div>

          <div className="mt-auto space-y-2">
            <button className="w-full rounded-md bg-[var(--color-bg-hover)] px-3 py-2 text-sm font-semibold text-[var(--color-text-secondary)]">
              收藏夹
            </button>
            <button className="w-full rounded-md bg-[var(--color-bg-hover)] px-3 py-2 text-sm font-semibold text-[var(--color-text-secondary)]">
              历史
            </button>
          </div>
        </aside>
      </div>

      <RandomPickModal
        open={randomModalOpen}
        onClose={() => setRandomModalOpen(false)}
        previewQuestions={randomQuestions}
        loading={randomLoading}
        requestedCount={requestedRandomCount}
        actualCount={randomQuestions.length}
        totalCandidates={total}
        perSet={randomPerSet}
        copies={randomCopies}
        allowRepeat={randomAllowRepeat}
        excludedIdsText={randomExcludedIdsText}
        conditionSummary={randomConditionSummary}
        onChangePerSet={(value) => setRandomPerSet(clampNumber(value, 1, 50))}
        onChangeCopies={(value) => setRandomCopies(clampNumber(value, 1, 20))}
        onChangeAllowRepeat={setRandomAllowRepeat}
        onChangeExcludedIdsText={setRandomExcludedIdsText}
        onStart={() => void runRandomPick()}
        onAddAllToBasket={handleAddRandomQuestionsToBasket}
        onViewDetail={navigateToDetail}
        onAddToBasket={addToBasket}
        inBasketIds={basketIds}
      />

      <BatchMoveDialog
        questionIds={basketItems.map((item) => item.question_id)}
        open={moveDialogOpen}
        onClose={() => setMoveDialogOpen(false)}
      />
    </div>
  );
}
