import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Virtuoso } from 'react-virtuoso';
import { Eye, EyeOff, LayoutList, List, PanelLeftClose, PanelLeftOpen, RefreshCw } from 'lucide-react';

import BatchMoveDialog from '../components/shared/BatchMoveDialog';
import BasketWorkbenchDrawer from '../components/shared/BasketWorkbenchDrawer';
import FilterBar from '../components/shared/FilterBar';
import KnowledgeTree from '../components/shared/KnowledgeTree';
import QueryParamsPopover from '../components/shared/QueryParamsPopover';
import QuestionCard from '../components/shared/QuestionCard';
import QuestionCompactRow from '../components/shared/QuestionCompactRow';
import RandomPickModal from '../components/shared/RandomPickModal';
import QuestionEditorModal from '../components/editor/QuestionEditorModal';
import QuestionLiveEditor from '../components/editor/QuestionLiveEditor';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { useBasket } from '../hooks/useBasket';
import { batchMarkMistake, batchStarFavorites, batchUnmarkMistake, batchUpdateMetadata, deleteQuestions, fetchKnowledgePoints, returnQuestionToReview, searchQuestions, updateQuestion } from '../services/api';
import type { KnowledgePointFlatItem, MetadataField, Question, SearchFilters } from '../types';
import { addQuestionsToAiContext, readAiContextCache } from '../utils/aiContextCache';
import LatexRenderer from '../components/render/LatexRenderer';
import { loadCurrentLessonPackage } from '../services/lessonPackage';

const SHARE_HISTORY_KEY = 'physics_vault.question_share_history';
const SEARCH_PRESET_KEY = 'physics_vault.question_search_presets';
type BrowseMode = 'questions' | 'knowledge';

type QuickActionGroup = '浏览' | '选题' | '输出' | '整理';

interface QuickAction {
  label: string;
  tone: 'blue' | 'teal' | 'red' | 'neutral';
  group: QuickActionGroup;
  requiresSelection?: boolean;
}

const QUICK_ACTIONS: QuickAction[] = [
  { label: '随机选题', tone: 'blue', group: '浏览' },
  { label: '查询参数', tone: 'neutral', group: '浏览' },
  { label: '刷新题目', tone: 'neutral', group: '浏览' },
  { label: '显示答案', tone: 'neutral', group: '浏览' },
  { label: '加入篮子', tone: 'blue', group: '选题', requiresSelection: true },
  { label: '加入AI', tone: 'teal', group: '选题', requiresSelection: true },
  { label: '批量操作', tone: 'blue', group: '输出' },
  { label: '分享多题', tone: 'neutral', group: '输出', requiresSelection: true },
  { label: '分享历史', tone: 'neutral', group: '输出' },
  { label: '批量替换', tone: 'neutral', group: '整理', requiresSelection: true },
  { label: '删除题目', tone: 'red', group: '整理', requiresSelection: true },
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

function pillToneClass(tone: QuickAction['tone']) {
  if (tone === 'teal') return 'border-[var(--color-teal)] bg-[var(--color-teal)] text-white shadow-sm';
  if (tone === 'red') return 'border-[var(--color-danger)] bg-[var(--color-danger)] text-white shadow-sm';
  if (tone === 'neutral') return 'border-[var(--color-border)] bg-[var(--color-bg-card)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]';
  return 'border-[var(--color-accent)] bg-[var(--color-accent)] text-white shadow-sm';
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

interface ShareHistoryItem {
  createdAt: string;
  questionIds: string[];
  text: string;
}

interface SearchPreset {
  id: string;
  name: string;
  filters: SearchFilters;
}

function readSearchPresets(): SearchPreset[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(SEARCH_PRESET_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.filter((item): item is SearchPreset => Boolean(item?.id && item?.name && item?.filters)).slice(0, 8) : [];
  } catch {
    return [];
  }
}

function persistSearchPresets(items: SearchPreset[]) {
  localStorage.setItem(SEARCH_PRESET_KEY, JSON.stringify(items.slice(0, 8)));
}

function readShareHistory(): ShareHistoryItem[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(SHARE_HISTORY_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveShareHistory(item: ShareHistoryItem): ShareHistoryItem[] {
  const next = [item, ...readShareHistory()].slice(0, 20);
  localStorage.setItem(SHARE_HISTORY_KEY, JSON.stringify(next));
  return next;
}

function parseMetadataTags(text: string): string[] {
  return text
    .split(/[\n,，、;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeMetadataField(input: string): MetadataField | null {
  const value = input.trim().toLowerCase();
  if (['1', '知识点', '考点', 'knowledge', 'knowledge_points', 'kp'].includes(value)) return 'knowledge_points';
  if (['2', '标签', 'tag', 'tags'].includes(value)) return 'tags';
  if (['3', '来源', '试题来源', 'source'].includes(value)) return 'source';
  return null;
}

function metadataFieldLabel(field: MetadataField): string {
  if (field === 'knowledge_points') return '知识点';
  if (field === 'tags') return '标签';
  return '试题来源';
}

export default function BrowsePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { items: basketItems, add: addToBasket, remove: removeFromBasket, move: moveBasketItem } = useBasket();
  const basketIds = useMemo(() => new Set(basketItems.map((item) => item.question_id)), [basketItems]);
  const composedQuestionIds = useMemo(() => {
    const current = loadCurrentLessonPackage();
    return new Set(current?.questions.map((question) => question.question_id) || []);
  }, []);

  const [browseMode, setBrowseMode] = useState<BrowseMode>('questions');
  const [questions, setQuestions] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [knowledgePoints, setKnowledgePoints] = useState<KnowledgePointFlatItem[]>([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);
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
  const [notice, setNotice] = useState<string | null>(null);
  const [searchPresets, setSearchPresets] = useState<SearchPreset[]>(() => readSearchPresets());
  const [aiContextIds, setAiContextIds] = useState<Set<string>>(
    () => new Set(readAiContextCache().map((item) => item.question_id)),
  );
  const [returningReviewIds, setReturningReviewIds] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [deletingQuestionIds, setDeletingQuestionIds] = useState<Set<string>>(new Set());
  const [reloadToken, setReloadToken] = useState(0);
  const [editingDraft, setEditingDraft] = useState<Question | null>(null);
  const [savingQuestion, setSavingQuestion] = useState(false);
  const [resultView, setResultView] = useState<'cards' | 'compact'>('cards');
  const [catalogOpen, setCatalogOpen] = useState(() => typeof window !== 'undefined' && window.innerWidth >= 1440);
  const [previewQuestion, setPreviewQuestion] = useState<Question | null>(null);
  const [selectingAllResults, setSelectingAllResults] = useState(false);
  const [aiCandidates, setAiCandidates] = useState<Question[]>([]);
  const [basketDrawerOpen, setBasketDrawerOpen] = useState(false);
  const inlineEditorEnabled = false;

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
  }, [filters, reloadToken]);

  useEffect(() => {
    let cancelled = false;
    setKnowledgeLoading(true);
    setKnowledgeError(null);
    fetchKnowledgePoints()
      .then((items) => {
        if (!cancelled) setKnowledgePoints(Array.isArray(items) ? items : []);
      })
      .catch((requestError: Error) => {
        if (!cancelled) {
          setKnowledgeError(requestError.message);
          setKnowledgePoints([]);
        }
      })
      .finally(() => {
        if (!cancelled) setKnowledgeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const totalPages = Math.max(1, Math.ceil(total / (filters.limit || 20)));
  const currentPage = Math.floor((filters.offset || 0) / (filters.limit || 20)) + 1;
  const requestedRandomCount = randomPerSet * randomCopies;
  const filteredKnowledgePoints = useMemo(() => {
    const query = (filters.query || '').trim().toLowerCase();
    return knowledgePoints.filter((item) => {
      if (filters.topic1_id && item.topic1_id !== filters.topic1_id) return false;
      if (filters.topic2_id && item.topic2_id !== filters.topic2_id) return false;
      if (filters.topic3_id && item.topic3_id !== filters.topic3_id) return false;
      if (!query) return true;
      return [
        item.topic1_id,
        item.topic1_name,
        item.topic2_id,
        item.topic2_name,
        item.topic3_id,
        item.topic3_name,
        item.source_chapter || '',
        item.note || '',
      ].some((value) => value.toLowerCase().includes(query));
    });
  }, [filters.query, filters.topic1_id, filters.topic2_id, filters.topic3_id, knowledgePoints]);

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

  const handleReturnToReview = useCallback(
    async (id: string) => {
      if (returningReviewIds.has(id)) return;
      const confirmed = window.confirm('将这道题打回校对中心，等待回炉重造？');
      if (!confirmed) return;

      setReturningReviewIds((prev) => new Set(prev).add(id));
      try {
        await returnQuestionToReview(id);
        setNotice('已送回校对中心，等待回炉重造');
        setReloadToken((prev) => prev + 1);
      } catch (err) {
        alert(`送回校对中心失败：${err instanceof Error ? err.message : '未知错误'}`);
      } finally {
        setReturningReviewIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [returningReviewIds],
  );

  const handleOpenEditor = useCallback((question: Question) => {
    setEditingDraft(question);
  }, []);

  const handleSaveEditedQuestion = useCallback(async () => {
    if (!editingDraft) return;
    setSavingQuestion(true);
    try {
      const updated = await updateQuestion(editingDraft.question_id, editingDraft);
      setQuestions((prev) => prev.map((item) => item.question_id === updated.question_id ? updated : item));
      setEditingDraft(updated);
      setNotice('题目已保存');
    } catch (err) {
      setNotice(`保存失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setSavingQuestion(false);
    }
  }, [editingDraft]);

  const refreshQuestions = useCallback(() => {
    setReloadToken((prev) => prev + 1);
  }, []);

  const selectedQuestions = useMemo(
    () => questions.filter((question) => checkedIds.has(question.question_id)),
    [checkedIds, questions],
  );

  const selectedIds = useMemo(
    () => selectedQuestions.map((question) => question.question_id),
    [selectedQuestions],
  );

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

  const handleSelectCurrentPage = useCallback(() => {
    setCheckedIds(new Set(questions.map((question) => question.question_id)));
  }, [questions]);

  const handleSelectAllResults = useCallback(async () => {
    if (total === 0) return;
    setSelectingAllResults(true);
    try {
      const ids = new Set<string>();
      const pageSize = 200;
      for (let offset = 0; offset < total; offset += pageSize) {
        const response = await searchQuestions({ ...filters, offset, limit: pageSize });
        response.items.forEach((question) => ids.add(question.question_id));
        if (response.items.length === 0) break;
      }
      setCheckedIds(ids);
      setNotice(`已选中当前检索结果中的 ${ids.size} 道题`);
    } catch (err) {
      setNotice(`全结果选择失败：${err instanceof Error ? err.message : '请稍后重试'}`);
    } finally {
      setSelectingAllResults(false);
    }
  }, [filters, total]);

  const handlePrepareAiCandidates = useCallback(() => {
    const source = selectedQuestions.length > 0 ? selectedQuestions : questions;
    if (source.length === 0) {
      setNotice('请先检索或选择题目，再生成候选区');
      return;
    }
    const ranked = [...source]
      .sort((a, b) => (Number(a.difficulty || 0) - Number(b.difficulty || 0)) || a.question_id.localeCompare(b.question_id))
      .slice(0, 20);
    setAiCandidates(ranked);
  }, [questions, selectedQuestions]);

  const handleAddAiCandidatesToBasket = useCallback(() => {
    aiCandidates.forEach((question) => addToBasket(question.question_id));
    setNotice(`已将 ${aiCandidates.length} 道候选题加入选题篮`);
    setAiCandidates([]);
  }, [addToBasket, aiCandidates]);

  const clearAllFilters = useCallback(() => {
    updateFilters({ limit: filters.limit || 20, offset: 0, search_mode: 'browse' });
  }, [filters.limit, updateFilters]);

  const saveCurrentSearchPreset = useCallback(() => {
    const name = window.prompt('为当前筛选方案命名');
    if (!name?.trim()) return;
    const preset: SearchPreset = {
      id: `${Date.now()}`,
      name: name.trim().slice(0, 24),
      filters: { ...filters, offset: 0 },
    };
    setSearchPresets((current) => {
      const next = [preset, ...current.filter((item) => item.name !== preset.name)].slice(0, 8);
      persistSearchPresets(next);
      return next;
    });
    setNotice(`已保存筛选方案：${preset.name}`);
  }, [filters]);

  const applySearchPreset = useCallback((preset: SearchPreset) => {
    updateFilters({ ...preset.filters, limit: preset.filters.limit || filters.limit || 20, offset: 0 });
    setNotice(`已应用筛选方案：${preset.name}`);
  }, [filters.limit, updateFilters]);

  const removeSearchPreset = useCallback((presetId: string) => {
    setSearchPresets((current) => {
      const next = current.filter((item) => item.id !== presetId);
      persistSearchPresets(next);
      return next;
    });
  }, []);

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
    if (selectedIds.length === 0) {
      alert('请先勾选题目');
      return;
    }
    selectedIds.forEach((id) => addToBasket(id));
    setNotice(`已加入选题篮：${selectedIds.length} 题`);
  }, [addToBasket, selectedIds]);

  const handleAddQuestionsToAi = useCallback((items: Question[]) => {
    if (items.length === 0) {
      alert('请先选择要加入 AI 上下文的题目');
      return;
    }
    const next = addQuestionsToAiContext(items);
    setAiContextIds(new Set(next.map((item) => item.question_id)));
    setNotice(`已加入 AI 上下文：${items.length} 题。打开 AI 题库助手后会自动带入。`);
  }, []);

  const handleAddCheckedToAi = useCallback(() => {
    handleAddQuestionsToAi(selectedQuestions);
  }, [handleAddQuestionsToAi, selectedQuestions]);

  const handleAddRandomQuestionsToBasket = useCallback(() => {
    if (randomQuestions.length === 0) {
      alert('当前没有可加入选题篮的随机题目');
      return;
    }
    randomQuestions.forEach((question) => addToBasket(question.question_id));
  }, [addToBasket, randomQuestions]);

  const handleDeleteChecked = useCallback(async () => {
    if (selectedIds.length === 0) {
      alert('请先勾选要删除的题目');
      return;
    }
    const ok = window.confirm(`确认从题库中删除已勾选的 ${selectedIds.length} 道题？此操作会同时移除相关收藏、目录关系和批注。`);
    if (!ok) return;

    setDeleting(true);
    try {
      const result = await deleteQuestions(selectedIds);
      setQuestions((prev) => prev.filter((question) => !selectedIds.includes(question.question_id)));
      setTotal((prev) => Math.max(0, prev - result.deleted_count));
      setCheckedIds(new Set());
      setNotice(`已删除 ${result.deleted_count} 道题${result.missing_ids.length ? `，${result.missing_ids.length} 道未找到` : ''}`);
      refreshQuestions();
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除题目失败');
    } finally {
      setDeleting(false);
    }
  }, [refreshQuestions, selectedIds]);

  const handleDeleteQuestion = useCallback(async (question: Question) => {
    const questionId = question.question_id;
    const title = (question.canonical_title || question.title || questionId).replace(/\s+/g, ' ').trim();
    const ok = window.confirm(`确认从题库中删除这道题？\n\n${title.slice(0, 90)}\n\n此操作不可撤销，并会同时移除相关收藏、目录关系和批注。`);
    if (!ok) return;

    setDeletingQuestionIds((current) => new Set(current).add(questionId));
    try {
      const result = await deleteQuestions([questionId]);
      if (result.deleted_count === 0) {
        setNotice(result.missing_ids.includes(questionId) ? '这道题已经不在题库中' : '没有删除任何题目');
        return;
      }
      setQuestions((current) => current.filter((item) => item.question_id !== questionId));
      setTotal((current) => Math.max(0, current - 1));
      setCheckedIds((current) => {
        const next = new Set(current);
        next.delete(questionId);
        return next;
      });
      setPreviewQuestion((current) => current?.question_id === questionId ? null : current);
      removeFromBasket(questionId);
      setNotice('已从题库删除 1 道题');
      refreshQuestions();
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除题目失败');
    } finally {
      setDeletingQuestionIds((current) => {
        const next = new Set(current);
        next.delete(questionId);
        return next;
      });
    }
  }, [refreshQuestions, removeFromBasket]);

  const handleFavoriteChecked = useCallback(async () => {
    if (selectedIds.length === 0) {
      alert('请先勾选要收藏的题目');
      return;
    }
    try {
      const result = await batchStarFavorites({ question_ids: selectedIds, star_rating: 5 });
      setNotice(`已加入收藏：${result.success_count} 题`);
    } catch (err) {
      alert(err instanceof Error ? err.message : '收藏失败');
    }
  }, [selectedIds]);

  const handleReplaceMetadata = useCallback(async () => {
    if (selectedIds.length === 0) {
      alert('请先勾选要批量替换的题目');
      return;
    }

    const field = normalizeMetadataField(
      window.prompt('选择要替换的字段：\n1 知识点 / 2 标签 / 3 试题来源', '3') || '',
    );
    if (!field) return;

    const value = window.prompt(
      field === 'tags'
        ? '输入新的标签，支持逗号、顿号、分号或换行分隔'
        : `输入新的${metadataFieldLabel(field)}`,
      '',
    );
    if (!value?.trim()) return;

    const tags = field === 'tags' ? parseMetadataTags(value) : [];
    if (field === 'tags' && tags.length === 0) return;

    const ok = window.confirm(
      `确认将已勾选的 ${selectedIds.length} 道题的${metadataFieldLabel(field)}替换为：\n${
        field === 'tags' ? tags.join('、') : value.trim()
      }`,
    );
    if (!ok) return;

    try {
      const result = await batchUpdateMetadata({
        question_ids: selectedIds,
        fields: [field],
        mode: 'manual',
        manual_values: {
          ...(field === 'knowledge_points' ? { knowledge_points: value.trim() } : {}),
          ...(field === 'tags' ? { tags } : {}),
          ...(field === 'source' ? { source: value.trim() } : {}),
        },
        force_overwrite: true,
      });
      setNotice(`已替换${metadataFieldLabel(field)}：更新 ${result.updated} 题，跳过 ${result.skipped} 题，失败 ${result.failed} 题`);
      setCheckedIds(new Set());
      refreshQuestions();
    } catch (err) {
      alert(err instanceof Error ? err.message : '批量替换失败');
    }
  }, [refreshQuestions, selectedIds]);

  const handleShareChecked = useCallback(async () => {
    const shareQuestions = selectedQuestions.length > 0 ? selectedQuestions : questions.slice(0, Math.min(10, questions.length));
    if (shareQuestions.length === 0) {
      alert('当前没有可分享的题目');
      return;
    }
    const text = shareQuestions
      .map((question, index) => `${index + 1}. ${question.question_id}｜${question.title || question.canonical_title || '无题干'}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(text);
      saveShareHistory({
        createdAt: new Date().toISOString(),
        questionIds: shareQuestions.map((question) => question.question_id),
        text,
      });
      setNotice(`已复制 ${shareQuestions.length} 道题的分享清单`);
    } catch {
      window.prompt('复制下面的分享清单', text);
      saveShareHistory({
        createdAt: new Date().toISOString(),
        questionIds: shareQuestions.map((question) => question.question_id),
        text,
      });
    }
  }, [questions, selectedQuestions]);

  const handleShareHistory = useCallback(async () => {
    const history = readShareHistory();
    if (history.length === 0) {
      alert('还没有分享历史。先使用“分享多题”生成一次分享清单。');
      return;
    }
    const text = history
      .map((item, index) => {
        const time = new Date(item.createdAt).toLocaleString('zh-CN');
        return `#${index + 1} ${time}｜${item.questionIds.length} 题\n${item.text}`;
      })
      .join('\n\n---\n\n');
    try {
      await navigator.clipboard.writeText(text);
      setNotice(`已复制 ${history.length} 条分享历史`);
    } catch {
      window.prompt('复制下面的分享历史', text);
    }
  }, []);

  const handleQuickAction = useCallback(
    (label: string) => {
      if (label === '随机选题') {
        setQueryPopoverOpen(false);
        setRandomModalOpen(true);
        return;
      }

      if (label === '查询参数') {
        setQueryPopoverOpen((prev) => !prev);
        return;
      }

      if (label === '刷新题目') {
        refreshQuestions();
        setNotice('题目列表已刷新');
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
      if (label === '加入AI') {
        handleAddCheckedToAi();
        return;
      }

      if (label === '删除题目') {
        void handleDeleteChecked();
        return;
      }

      if (label === '批量替换') {
        void handleReplaceMetadata();
        return;
      }

      if (label === '分享多题') {
        void handleShareChecked();
        return;
      }

      if (label === '分享历史') {
        void handleShareHistory();
        return;
      }

      alert(`${label} 功能下一步继续补齐。`);
    },
    [basketItems.length, handleAddCheckedToAi, handleAddCheckedToBasket, handleDeleteChecked, handleReplaceMetadata, handleShareChecked, handleShareHistory, refreshQuestions],
  );

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#f3f6fa]">
      <div className="pv-page-toolbar flex min-h-12 shrink-0 items-center justify-between gap-2 overflow-x-auto px-3 py-2 sm:px-4">
          <div className="flex min-w-0 shrink-0 items-center gap-3">
            <div className="flex shrink-0 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] p-0.5">
              <button
                type="button"
                onClick={() => setBrowseMode('questions')}
                className={`h-8 rounded px-3 text-sm ${browseMode === 'questions' ? 'bg-white font-bold text-[var(--color-accent)] shadow-sm' : 'text-[var(--color-text-muted)]'}`}
              >
                题目
              </button>
              <button
                type="button"
                onClick={() => setBrowseMode('knowledge')}
                className={`h-8 rounded px-3 text-sm ${browseMode === 'knowledge' ? 'bg-white font-bold text-[var(--color-accent)] shadow-sm' : 'text-[var(--color-text-muted)]'}`}
              >
                <span className="md:hidden">目录</span><span className="hidden md:inline">知识目录</span>
              </button>
            </div>
            <div className="hidden min-w-0 lg:block">
              <div className="truncate text-sm font-bold text-[var(--color-text-main)]">
                {browseMode === 'questions' ? `题库 · ${total} 题` : `知识目录 · ${filteredKnowledgePoints.length} 条`}
              </div>
              <div className="hidden truncate text-[11px] text-[var(--color-text-muted)] sm:block">
                {browseMode === 'questions' ? (activeSummary.join(' · ') || '全库浏览') : '按知识层级浏览与筛选'}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() => setCatalogOpen((value) => !value)}
              className={`flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold ${catalogOpen ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)] text-[var(--color-accent)]' : 'border-[var(--color-border)] bg-white text-[var(--color-text-secondary)]'}`}
              title={catalogOpen ? '收起知识目录' : '展开知识目录'}
            >
              {catalogOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
              <span className="hidden sm:inline">目录</span>
            </button>
            {browseMode === 'questions' && <>
              <button
                type="button"
                onClick={() => setShowAnswers((value) => !value)}
                className={`flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold ${showAnswers ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-[var(--color-border)] bg-white text-[var(--color-text-secondary)]'}`}
                title={showAnswers ? '隐藏答案与解析' : '显示答案与解析'}
              >
                {showAnswers ? <EyeOff size={15} /> : <Eye size={15} />}
                <span className="hidden md:inline">{showAnswers ? '隐藏答案' : '显示答案'}</span>
              </button>
              <button type="button" onClick={refreshQuestions} className="flex h-8 w-8 items-center justify-center rounded-md border border-[var(--color-border)] bg-white text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]" title="刷新题目" aria-label="刷新题目">
                <RefreshCw size={15} />
              </button>
              <div className="flex rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] p-0.5">
                <button type="button" onClick={() => setResultView('cards')} className={`flex h-7 w-8 items-center justify-center rounded ${resultView === 'cards' ? 'bg-white text-[var(--color-accent)] shadow-sm' : 'text-[var(--color-text-muted)]'}`} title="阅读卡片" aria-label="阅读卡片"><LayoutList size={15} /></button>
                <button type="button" onClick={() => setResultView('compact')} className={`flex h-7 w-8 items-center justify-center rounded ${resultView === 'compact' ? 'bg-white text-[var(--color-accent)] shadow-sm' : 'text-[var(--color-text-muted)]'}`} title="紧凑列表" aria-label="紧凑列表"><List size={15} /></button>
              </div>
            </>}
          </div>
      </div>

      <div className="relative flex min-h-0 flex-1 gap-3 p-2 sm:p-3">
        {catalogOpen && <aside className="absolute inset-y-2 left-2 z-20 flex w-[calc(100%-1rem)] max-w-[300px] shrink-0 flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-white shadow-lg sm:static sm:inset-auto sm:w-60 sm:shadow-sm">
          <div className="border-b border-[var(--color-border)] p-3">
            <div className="mb-2 flex items-center gap-2">
              <div className="rounded-md bg-[var(--color-teal)] px-3 py-1.5 text-sm font-bold text-white">
                高中物理
              </div>
              <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                AI 自动归类
              </span>
            </div>
            <div className="text-xs leading-5 text-[var(--color-text-muted)]">
              {filters.topic3_id || filters.topic2_id || filters.topic1_id ? '已按当前知识点筛选题目' : '知识树由 AI 匹配并随题目入库自动更新'}
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
        </aside>}

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-[#eef2f7] shadow-sm">
          <div className="border-b border-[var(--color-border)] bg-white px-3 py-2 sm:px-4">
            {browseMode === 'questions' ? (
              <>
                <FilterBar filters={filters} onChange={updateFilters} />
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={saveCurrentSearchPreset}
                    className="rounded-md border border-[var(--color-border)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
                  >
                    保存当前筛选
                  </button>
                  {searchPresets.map((preset) => (
                    <span key={preset.id} className="inline-flex items-center overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] text-[11px] shadow-sm">
                      <button type="button" onClick={() => applySearchPreset(preset)} className="px-2.5 py-1 font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--color-accent-light)] hover:text-[var(--color-accent)]">
                        {preset.name}
                      </button>
                      <button type="button" aria-label={`删除筛选方案 ${preset.name}`} onClick={() => removeSearchPreset(preset.id)} className="border-l border-[var(--color-border)] px-1.5 py-1 text-[var(--color-text-muted)] hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]">
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <input
                value={filters.query || ''}
                onChange={(event) => updateFilters({ ...filters, query: event.target.value || undefined })}
                placeholder="搜索知识点名称、ID、章节或备注"
                className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
              />
            )}

            {notice && (
              <div className="mt-3 flex items-center justify-between rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
                <span>{notice}</span>
                <button onClick={() => setNotice(null)} className="font-semibold text-[var(--color-accent)]">知道了</button>
              </div>
            )}

            {browseMode === 'questions' && <div className="mt-2 flex flex-wrap items-center gap-2">
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

              <span className="mx-1 h-5 w-px bg-[var(--color-border)]" />
              <button
                type="button"
                onClick={handleSelectCurrentPage}
                disabled={questions.length === 0}
                className="rounded-md px-2.5 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] disabled:opacity-40"
              >
                选择本页
              </button>
              <button
                type="button"
                onClick={() => void handleSelectAllResults()}
                disabled={total === 0 || selectingAllResults}
                className="rounded-md px-2.5 py-1.5 text-xs font-semibold text-[var(--color-accent)] hover:bg-[var(--color-accent-light)] disabled:opacity-40"
              >
                {selectingAllResults ? '选择中...' : `全选结果 ${total}`}
              </button>

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
            </div>}
          </div>

          <div className="min-h-0 flex-1 overflow-hidden p-2 sm:p-3">
            {browseMode === 'knowledge' ? (
              <div className="h-full overflow-y-auto pr-1"><KnowledgePointBrowser
                items={filteredKnowledgePoints}
                loading={knowledgeLoading}
                error={knowledgeError}
                clearFilters={clearAllFilters}
              /></div>
            ) : loading ? (
              <div className="space-y-3">
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
              <div className="flex h-full min-h-0 flex-col gap-2">
                <div className="min-h-0 flex-1">
                  {resultView === 'cards' ? (
                    <Virtuoso
                      data={questions}
                      className="h-full"
                      increaseViewportBy={{ top: 520, bottom: 900 }}
                      itemContent={(index, question) => <div className="mx-auto w-full max-w-[1320px] pb-2"><QuestionCard
                        question={question}
                        index={(filters.offset || 0) + index + 1}
                        onReturnToReview={handleReturnToReview}
                        onAddToBasket={addToBasket}
                        onEdit={handleOpenEditor}
                        onAddToAiContext={(item) => handleAddQuestionsToAi([item])}
                        onDelete={handleDeleteQuestion}
                        inBasket={basketIds.has(question.question_id)}
                        inAiContext={aiContextIds.has(question.question_id)}
                        checked={checkedIds.has(question.question_id)}
                        onCheck={handleCheck}
                        showAnswer={showAnswers}
                        returningToReview={returningReviewIds.has(question.question_id)}
                        deleting={deletingQuestionIds.has(question.question_id)}
                      /></div>}
                    />
                  ) : (
                    <div className="h-full overflow-hidden rounded-md border border-[var(--color-border)] bg-white">
                      <Virtuoso
                        data={questions}
                        className="h-full"
                        increaseViewportBy={{ top: 520, bottom: 900 }}
                        itemContent={(_, question) => <QuestionCompactRow
                          question={question}
                          checked={checkedIds.has(question.question_id)}
                          inBasket={basketIds.has(question.question_id)}
                          onCheck={handleCheck}
                          onPreview={setPreviewQuestion}
                          onAddToBasket={addToBasket}
                          onDelete={handleDeleteQuestion}
                          deleting={deletingQuestionIds.has(question.question_id)}
                        />}
                      />
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-[var(--color-bg-card)] px-3 py-2 shadow-sm">
                  <div className="text-xs text-[var(--color-text-secondary)]">
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

        {browseMode === 'questions' && <aside className="browse-quick-panel relative flex w-52 shrink-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-[var(--shadow-card)]">
          <div className="border-b border-[var(--color-border)] px-4 py-4">
            <div className="text-xs font-bold text-[var(--color-text-muted)]">当前选择</div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div className="rounded-md bg-[var(--color-bg-hover)] px-2 py-2 text-center">
                <div className="text-2xl font-black text-[var(--color-accent)]">{checkedIds.size}</div>
                <div className="text-[11px] text-[var(--color-text-muted)]">已勾选</div>
              </div>
              <div className="rounded-md bg-[var(--color-bg-hover)] px-2 py-2 text-center">
                <div className="text-2xl font-black text-[var(--color-teal)]">{basketItems.length}</div>
                <div className="text-[11px] text-[var(--color-text-muted)]">选题篮</div>
              </div>
            </div>
            {basketItems.length > 0 && (
              <button
                onClick={() => window.open('/compose', '_blank')}
                className="mt-3 w-full rounded-md bg-[var(--color-accent)] px-3 py-2 text-xs font-bold text-white transition hover:bg-[var(--color-accent-dark)]"
              >
                去组卷
              </button>
            )}
          </div>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {inlineEditorEnabled && editingDraft && (
              <section className="hidden border-b border-[var(--color-border)] pb-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs font-bold text-[var(--color-text-main)]">实时编辑题目</div>
                  <button
                    type="button"
                    onClick={() => {
                      setEditingDraft(null);
                    }}
                    className="rounded px-2 py-1 text-[11px] font-semibold text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)]"
                  >
                    关闭
                  </button>
                </div>
                <QuestionLiveEditor
                  question={editingDraft}
                  compact
                  onChange={(patch) => setEditingDraft((current) => current ? { ...current, ...patch } : current)}
                  onSave={handleSaveEditedQuestion}
                  saving={savingQuestion}
                />
              </section>
            )}
            {(['浏览', '选题', '输出', '整理'] as QuickActionGroup[]).map((group) => (
              <section key={group}>
                <div className="mb-1.5 px-1 text-[10px] font-black text-[var(--color-text-subtle)]">{group}</div>
                <div className="space-y-1.5">
                  {QUICK_ACTIONS.filter((action) => action.group === group).map((action) => {
                    const disabled =
                      (action.label === '删除题目' && deleting) ||
                      Boolean(action.requiresSelection && checkedIds.size === 0);
                    return (
                      <div key={action.label} className="relative">
                        <button
                          onClick={() => handleQuickAction(action.label)}
                          disabled={disabled}
                          className={`w-full rounded-md border px-2.5 py-2 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-45 ${pillToneClass(action.tone)}`}
                        >
                          {action.label === '删除题目' && deleting ? '删除中...' : action.label === '显示答案' ? (showAnswers ? '隐藏答案' : '显示答案') : action.label}
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
                    );
                  })}
                </div>
              </section>
            ))}
          </div>

          <div className="border-t border-[var(--color-border)] px-4 py-4 pb-16">
            <button
              onClick={() => void handleFavoriteChecked()}
              disabled={checkedIds.size === 0}
              className="w-full rounded-md bg-[var(--color-bg-hover)] px-3 py-2 text-sm font-bold text-[var(--color-text-secondary)] disabled:cursor-not-allowed disabled:opacity-45"
            >
              收藏已选
            </button>
          </div>
        </aside>}
      </div>

      {browseMode === 'questions' && checkedIds.size > 0 && (
        <div className="pointer-events-none fixed inset-x-0 bottom-7 z-30 flex justify-center px-4">
          <div className="pointer-events-auto flex max-w-[calc(100vw-64px)] flex-wrap items-center justify-center gap-2 rounded-2xl border border-[#b8d7f7] bg-white/95 px-3 py-2 shadow-[0_14px_36px_rgba(30,91,160,0.22)] backdrop-blur">
            <span className="px-2 text-xs font-bold text-[var(--color-text-secondary)]">{checkedIds.size > 0 ? `已选 ${checkedIds.size} 题` : `选题篮 ${basketItems.length} 题`}</span>
            <button type="button" onClick={() => setBasketDrawerOpen(true)} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)]">选题篮 {basketItems.length}</button>
            {checkedIds.size === 0 ? <>
              <button type="button" onClick={handleSelectCurrentPage} disabled={questions.length === 0} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)] disabled:opacity-40">选择本页</button>
              <button type="button" onClick={() => void handleSelectAllResults()} disabled={total === 0 || selectingAllResults} className="rounded-lg border border-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-[var(--color-accent)] disabled:opacity-40">{selectingAllResults ? '正在选择…' : `选择全部结果 (${total})`}</button>
              <button type="button" onClick={handlePrepareAiCandidates} disabled={questions.length === 0} className="rounded-lg bg-[var(--color-purple)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">生成 AI 候选</button>
            </> : <>
              <button type="button" onClick={handleAddCheckedToBasket} className="rounded-lg bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white">加入选题篮</button>
              <button type="button" onClick={handlePrepareAiCandidates} className="rounded-lg bg-[var(--color-purple)] px-3 py-1.5 text-xs font-semibold text-white">AI 精选候选</button>
              <button type="button" onClick={() => void handleFavoriteChecked()} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)]">收藏</button>
              <button type="button" onClick={() => void handleReplaceMetadata()} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)]">批量标签</button>
              <button type="button" onClick={() => setCheckedIds(new Set())} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-[var(--color-text-muted)]">取消选择</button>
            </>}
          </div>
        </div>
      )}

      {aiCandidates.length > 0 && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-slate-950/20 p-4 sm:items-center" role="dialog" aria-modal="true" aria-label="AI 选题候选">
          <div className="max-h-[82vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-[#cfe1f5] bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-[var(--color-border)] px-5 py-4">
              <div><div className="text-sm font-bold text-[var(--color-text-main)]">AI 选题候选区</div><div className="mt-1 text-xs text-[var(--color-text-muted)]">先预览候选题，再确认加入选题篮；不会直接修改组卷内容。</div></div>
              <button type="button" onClick={() => setAiCandidates([])} className="rounded-md px-2 py-1 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)]">×</button>
            </div>
            <div className="max-h-[52vh] overflow-y-auto divide-y divide-[var(--color-border)]">
              {aiCandidates.map((question, index) => <button key={question.question_id} type="button" onClick={() => { setPreviewQuestion(question); setAiCandidates([]); }} className="block w-full px-5 py-3 text-left hover:bg-[var(--color-bg-hover)]"><div className="mb-1 text-xs font-semibold text-[var(--color-accent)]">候选 {index + 1} · {question.question_id}</div><div className="line-clamp-2 text-sm leading-6 text-[var(--color-text-main)]">{question.canonical_title || question.title}</div></button>)}
            </div>
            <div className="flex justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-bg-hover)] px-5 py-3"><button type="button" onClick={() => setAiCandidates([])} className="rounded-lg px-3 py-2 text-xs font-semibold text-[var(--color-text-secondary)]">返回筛选</button><button type="button" onClick={handleAddAiCandidatesToBasket} className="rounded-lg bg-[var(--color-accent)] px-3 py-2 text-xs font-semibold text-white">确认加入选题篮</button></div>
          </div>
        </div>
      )}

      {previewQuestion && (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/20" role="dialog" aria-modal="true" aria-label="题目详情">
          <div className="h-full w-full max-w-3xl overflow-y-auto bg-[var(--color-bg)] p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between"><div className="text-sm font-bold text-[var(--color-text-main)]">题目详情</div><button type="button" onClick={() => setPreviewQuestion(null)} className="rounded-md px-2 py-1 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)]">关闭</button></div>
            <QuestionCard question={previewQuestion} onReturnToReview={handleReturnToReview} onAddToBasket={addToBasket} onEdit={handleOpenEditor} onAddToAiContext={(item) => handleAddQuestionsToAi([item])} onDelete={handleDeleteQuestion} inBasket={basketIds.has(previewQuestion.question_id)} inAiContext={aiContextIds.has(previewQuestion.question_id)} checked={checkedIds.has(previewQuestion.question_id)} onCheck={handleCheck} showAnswer returningToReview={returningReviewIds.has(previewQuestion.question_id)} deleting={deletingQuestionIds.has(previewQuestion.question_id)} />
          </div>
        </div>
      )}

      <BasketWorkbenchDrawer
        open={basketDrawerOpen}
        items={basketItems}
        includedQuestionIds={composedQuestionIds}
        onClose={() => setBasketDrawerOpen(false)}
        onRemove={removeFromBasket}
        onMove={moveBasketItem}
        onCompose={() => navigate('/compose')}
      />

      {editingDraft && (
        <QuestionEditorModal
          question={editingDraft}
          onChange={(patch) => setEditingDraft((current) => current ? { ...current, ...patch } : current)}
          onClose={() => setEditingDraft(null)}
          onSave={handleSaveEditedQuestion}
          saving={savingQuestion}
        />
      )}

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
        onReturnToReview={handleReturnToReview}
        onAddToBasket={addToBasket}
        returningReviewIds={returningReviewIds}
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

function KnowledgePointBrowser({
  items,
  loading,
  error,
  clearFilters,
}: {
  items: KnowledgePointFlatItem[];
  loading: boolean;
  error: string | null;
  clearFilters: () => void;
}) {
  if (loading) {
    return (
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)]">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="grid grid-cols-[96px_minmax(0,1fr)_120px] gap-4 border-b border-[var(--color-border)] px-4 py-3 last:border-b-0">
            <div className="h-4 animate-pulse rounded bg-[var(--color-bg-hover)]" />
            <div className="h-4 animate-pulse rounded bg-[var(--color-bg-hover)]" />
            <div className="h-4 animate-pulse rounded bg-[var(--color-bg-hover)]" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return <EmptyState icon="!" title="知识点加载失败" description={error} action={{ label: '重试', onClick: clearFilters }} />;
  }

  if (items.length === 0) {
    return <EmptyState icon="0" title="没有找到匹配的知识目录" description="试试切换左侧目录或搜索关键词" action={{ label: '清除筛选', onClick: clearFilters }} />;
  }

  const directory = buildKnowledgeDirectory(items);

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-sm">
      <div className="grid grid-cols-[96px_minmax(0,1fr)_120px] gap-4 border-b border-[var(--color-border)] bg-[var(--color-bg-hover)] px-4 py-2 text-xs font-black text-[var(--color-text-secondary)]">
        <span>层级</span>
        <span>目录名称</span>
        <span>编号 / 状态</span>
      </div>

      {directory.map((topic1) => (
        <section key={topic1.id} className="border-b border-[var(--color-border)] last:border-b-0">
          <DirectoryRow
            level="一级"
            title={topic1.name}
            code={topic1.id}
            count={`${topic1.topic3Count} 个知识点`}
            strong
          />
          {topic1.children.map((topic2) => (
            <div key={topic2.id}>
              <DirectoryRow
                level="二级"
                title={topic2.name}
                code={topic2.id}
                count={`${topic2.children.length} 个知识点`}
                indent={18}
              />
              {topic2.children.map((topic3) => (
                <DirectoryRow
                  key={topic3.topic3_id}
                  level="三级"
                  title={topic3.topic3_name}
                  code={topic3.topic3_id}
                  status={topic3.status}
                  note={topic3.note}
                  sourceChapter={topic3.source_chapter}
                  indent={38}
                />
              ))}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

interface KnowledgeDirectoryTopic2 {
  id: string;
  name: string;
  children: KnowledgePointFlatItem[];
}

interface KnowledgeDirectoryTopic1 {
  id: string;
  name: string;
  children: KnowledgeDirectoryTopic2[];
  topic3Count: number;
}

function buildKnowledgeDirectory(items: KnowledgePointFlatItem[]): KnowledgeDirectoryTopic1[] {
  const topic1Map = new Map<string, KnowledgeDirectoryTopic1>();

  for (const item of items) {
    const topic1Id = item.topic1_id || 'uncategorized-topic1';
    const topic2Id = item.topic2_id || 'uncategorized-topic2';
    let topic1 = topic1Map.get(topic1Id);
    if (!topic1) {
      topic1 = {
        id: topic1Id,
        name: item.topic1_name || topic1Id,
        children: [],
        topic3Count: 0,
      };
      topic1Map.set(topic1Id, topic1);
    }

    let topic2 = topic1.children.find((node) => node.id === topic2Id);
    if (!topic2) {
      topic2 = {
        id: topic2Id,
        name: item.topic2_name || topic2Id,
        children: [],
      };
      topic1.children.push(topic2);
    }

    topic2.children.push(item);
    topic1.topic3Count += 1;
  }

  return Array.from(topic1Map.values());
}

function DirectoryRow({
  level,
  title,
  code,
  count,
  status,
  note,
  sourceChapter,
  indent = 0,
  strong = false,
}: {
  level: '一级' | '二级' | '三级';
  title: string;
  code: string;
  count?: string;
  status?: string;
  note?: string | null;
  sourceChapter?: string | null;
  indent?: number;
  strong?: boolean;
}) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)_120px] gap-4 border-b border-[var(--color-border)] px-4 py-2.5 text-sm last:border-b-0">
      <div className="flex items-start gap-2">
        <span className={`mt-0.5 rounded px-1.5 py-0.5 text-[11px] font-bold ${
          level === '一级'
            ? 'bg-[var(--color-accent-light)] text-[var(--color-accent-dark)]'
            : level === '二级'
              ? 'bg-[var(--color-bg-hover)] text-[var(--color-text-secondary)]'
              : 'bg-white text-[var(--color-text-muted)] ring-1 ring-[var(--color-border)]'
        }`}>
          {level}
        </span>
      </div>
      <div className="min-w-0" style={{ paddingLeft: indent }}>
        <div className={`truncate ${strong ? 'font-black text-[var(--color-text-main)]' : 'font-semibold text-[var(--color-text)]'}`}>
          {title}
        </div>
        {note && (
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-muted)]">
            <LatexRenderer text={note} inline />
          </div>
        )}
        {sourceChapter && (
          <div className="mt-1 text-xs text-[var(--color-text-subtle)]">{sourceChapter}</div>
        )}
      </div>
      <div className="min-w-0 text-right text-xs leading-5 text-[var(--color-text-muted)]">
        <div className="truncate font-mono">{code}</div>
        <div>{count || status || ''}</div>
      </div>
    </div>
  );
}
