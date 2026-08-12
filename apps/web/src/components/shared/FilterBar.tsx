import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Search, SlidersHorizontal, X } from 'lucide-react';

import type { FilterFacets, SearchFilters } from '../../types';

interface Props {
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
  facets?: FilterFacets;
}

const MODULES = ['力学', '电磁学', '热学', '光学', '原子物理', '实验'];
const TYPES = [
  { value: 'single_choice', label: '单选' },
  { value: 'multi_choice', label: '多选' },
  { value: 'fill', label: '填空' },
  { value: 'experiment', label: '实验' },
  { value: 'calculation', label: '计算' },
];
const DIFFICULTIES = [
  { value: '1', label: '★☆☆☆☆' },
  { value: '2', label: '★★☆☆☆' },
  { value: '3', label: '★★★☆☆' },
  { value: '4', label: '★★★★☆' },
  { value: '5', label: '★★★★★' },
];
const SEARCH_MODES = [
  { value: 'browse', label: '浏览' },
  { value: 'strict', label: '精确' },
  { value: 'hybrid', label: '混合' },
  { value: 'similar', label: '相似' },
];

const INTERNAL_FACET_VALUES = new Set(['demo', 'standard']);

export default function FilterBar({ filters, onChange, facets }: Props) {
  const [keyword, setKeyword] = useState(filters.query || '');
  const [advancedOpen, setAdvancedOpen] = useState(false);

  useEffect(() => {
    setKeyword(filters.query || '');
  }, [filters.query]);

  const update = useCallback(
    (patch: Partial<SearchFilters>) => {
      onChange({ ...filters, offset: 0, ...patch });
    },
    [filters, onChange],
  );

  const handleSearch = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter') {
      update({
        query: keyword || undefined,
        search_mode: keyword.trim() ? (filters.search_mode === 'browse' ? 'hybrid' : filters.search_mode) : 'browse',
      });
    }
  };

  const submitSearch = () => {
    update({
      query: keyword || undefined,
      search_mode: keyword.trim() ? (filters.search_mode === 'browse' ? 'hybrid' : filters.search_mode) : 'browse',
    });
  };

  const clearAll = () => {
    setKeyword('');
    onChange({ limit: filters.limit || 20, offset: 0, search_mode: 'browse' });
  };

  const hasAdvancedFilters = Boolean(
    filters.year || filters.region || filters.exam_type || filters.module || filters.question_type || filters.difficulty || filters.status,
  );
  const activeFilterCount = [
    filters.query,
    filters.year,
    filters.region,
    filters.exam_type,
    filters.module,
    filters.question_type,
    filters.difficulty,
    filters.status,
    filters.topic1_id,
    filters.topic2_id,
    filters.topic3_id,
  ].filter(Boolean).length;
  const years = Array.from(new Set([
    ...(facets?.years || []),
    ...(filters.year ? [filters.year] : []),
  ])).sort((left, right) => right - left);
  const regions = (facets?.regions || []).filter(
    (value) => !INTERNAL_FACET_VALUES.has(value.trim().toLowerCase()),
  );
  const examTypes = (facets?.exam_types || []).filter(
    (value) => !INTERNAL_FACET_VALUES.has(value.trim().toLowerCase()),
  );
  const clearAdvanced = () => update({
    year: undefined,
    region: undefined,
    exam_type: undefined,
    module: undefined,
    question_type: undefined,
    difficulty: undefined,
    status: undefined,
  });
  const showAdvanced = advancedOpen || hasAdvancedFilters;

  return (
    <div className="space-y-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2 lg:flex-nowrap">
        <div className="flex shrink-0 overflow-hidden rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)]">
          {SEARCH_MODES.map((mode) => (
            <button
              type="button"
              key={mode.value}
              onClick={() => update({ search_mode: mode.value as SearchFilters['search_mode'] })}
              className={`h-9 cursor-pointer border-none px-3 text-xs font-bold transition-colors ${
                (filters.search_mode || 'browse') === mode.value
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'bg-[var(--color-bg-card)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
              }`}
            >
              {mode.label}
            </button>
          ))}
        </div>

        <div className="flex min-w-[260px] flex-1 overflow-hidden rounded-md border border-[var(--color-border)] bg-white focus-within:border-[var(--color-accent)] focus-within:ring-2 focus-within:ring-[var(--color-accent-light)]">
          <Search size={16} className="ml-3 mt-2.5 shrink-0 text-[var(--color-text-muted)]" />
          <input
            type="text"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onKeyDown={handleSearch}
            placeholder="搜索题干、题号、来源或知识点"
            className="h-9 min-w-0 flex-1 border-0 bg-transparent px-2 text-sm text-[var(--color-text-main)] outline-none"
          />
          <button
            type="button"
            onClick={submitSearch}
            className="h-9 shrink-0 border-l border-[var(--color-border)] px-4 text-xs font-bold text-[var(--color-accent)] hover:bg-[var(--color-accent-light)]"
          >
            搜索
          </button>
        </div>

        <button
          type="button"
          onClick={() => setAdvancedOpen((value) => !value)}
          aria-expanded={showAdvanced}
          className={`flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-3 text-xs font-semibold transition-colors ${
            showAdvanced
              ? 'border-[var(--color-accent)] bg-[var(--color-accent-light)] text-[var(--color-accent)]'
              : 'border-[var(--color-border)] bg-white text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]'
          }`}
        >
          <SlidersHorizontal size={15} />
          筛选{activeFilterCount > 0 ? ` ${activeFilterCount}` : ''}
        </button>

        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={clearAll}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
            aria-label="清空筛选"
            title="清空筛选"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {showAdvanced && <div className="flex flex-wrap items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3 py-2">
        <span className="mr-1 text-xs font-semibold text-[var(--color-text-muted)]">高级筛选</span>
        <select
          value={filters.year || ''}
          onChange={(event) => update({ year: event.target.value ? Number(event.target.value) : undefined })}
          className="h-8 rounded-md border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)]"
        >
          <option value="">年份{facets ? `（${years.length}）` : '（加载中）'}</option>
          {years.map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>

        <select
          value={filters.region || ''}
          onChange={(event) => update({ region: event.target.value || undefined })}
          disabled={!facets}
          className="h-8 rounded-md border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)] disabled:opacity-60"
        >
          <option value="">地区</option>
          {regions.map((region) => (
            <option key={region} value={region}>{region}</option>
          ))}
        </select>

        <select
          value={filters.exam_type || ''}
          onChange={(event) => update({ exam_type: event.target.value || undefined })}
          disabled={!facets}
          className="h-8 rounded-md border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)] disabled:opacity-60"
        >
          <option value="">考试类型</option>
          {examTypes.map((examType) => (
            <option key={examType} value={examType}>{examType}</option>
          ))}
        </select>

        <select
          value={filters.module || ''}
          onChange={(event) => update({ module: event.target.value || undefined })}
          className="h-8 rounded-md border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)]"
        >
          <option value="">模块</option>
          {MODULES.map((module) => (
            <option key={module} value={module}>
              {module}
            </option>
          ))}
        </select>

        <select
          value={filters.question_type || ''}
          onChange={(event) => update({ question_type: event.target.value || undefined })}
          className="h-8 rounded-md border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)]"
        >
          <option value="">题型</option>
          {TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>

        <select
          value={filters.difficulty || ''}
          onChange={(event) => update({ difficulty: event.target.value || undefined })}
          className="h-8 rounded-md border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)]"
        >
          <option value="">难度</option>
          {DIFFICULTIES.map((difficulty) => (
            <option key={difficulty.value} value={difficulty.value}>
              {difficulty.label}
            </option>
          ))}
        </select>

        <select
          value={filters.status || ''}
          onChange={(event) => update({ status: event.target.value || undefined })}
          className="h-8 rounded-md border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)]"
        >
          <option value="">状态</option>
          <option value="已审核">已审核</option>
          <option value="待审核">待审核</option>
          <option value="已确认">已确认</option>
          <option value="待校验">待校验</option>
        </select>

        {hasAdvancedFilters && (
          <button
            type="button"
            onClick={clearAdvanced}
            className="h-8 cursor-pointer rounded-md px-2 text-xs font-bold text-[var(--color-danger)] hover:bg-[var(--color-danger-soft)]"
          >
            重置高级筛选
          </button>
        )}
      </div>}
    </div>
  );
}
