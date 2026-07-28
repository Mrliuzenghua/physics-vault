import type React from 'react';
import { useCallback, useState } from 'react';

import type { SearchFilters } from '../../types';

interface Props {
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
  facets?: {
    years: number[];
    modules: string[];
    question_types: string[];
    difficulties: string[];
  };
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

export default function FilterBar({ filters, onChange, facets }: Props) {
  const [keyword, setKeyword] = useState(filters.query || '');

  const update = useCallback(
    (patch: Partial<SearchFilters>) => {
      onChange({ ...filters, offset: 0, ...patch });
    },
    [filters, onChange],
  );

  const handleSearch = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter') {
      update({ query: keyword || undefined });
    }
  };

  const clearAll = () => {
    setKeyword('');
    onChange({ limit: filters.limit || 20, offset: 0, search_mode: 'browse' });
  };

  const activeFilters = [
    filters.query && `关键词: ${filters.query}`,
    filters.year && `年份: ${filters.year}`,
    filters.module && `模块: ${filters.module}`,
    filters.question_type && `题型: ${filters.question_type}`,
    filters.difficulty && `难度: ${'★'.repeat(Number(filters.difficulty))}`,
    filters.topic1_id && `考点: ${filters.topic1_id}`,
    filters.status && `状态: ${filters.status}`,
  ].filter(Boolean);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-lg border" style={{ borderColor: 'var(--color-border)' }}>
          {SEARCH_MODES.map((mode) => (
            <button
              key={mode.value}
              onClick={() => update({ search_mode: mode.value as SearchFilters['search_mode'] })}
              className="cursor-pointer border-none px-2.5 py-1.5 text-xs font-medium transition-colors"
              style={{
                background:
                  (filters.search_mode || 'browse') === mode.value ? 'var(--color-accent)' : 'var(--color-bg-card)',
                color: (filters.search_mode || 'browse') === mode.value ? '#fff' : 'var(--color-text-secondary)',
              }}
            >
              {mode.label}
            </button>
          ))}
        </div>

        <input
          type="text"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onKeyDown={handleSearch}
          placeholder="输入关键词后回车或点击搜索"
          className="min-w-40 flex-1 rounded-lg border px-3 py-1.5 text-sm outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
          }}
        />

        <button
          onClick={() => update({ query: keyword || undefined })}
          className="cursor-pointer rounded-lg border-none px-3 py-1.5 text-xs font-medium text-white"
          style={{ background: 'var(--color-accent)' }}
        >
          搜索
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={filters.year || ''}
          onChange={(event) => update({ year: event.target.value ? Number(event.target.value) : undefined })}
          className="rounded border px-2 py-1.5 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
          }}
        >
          <option value="">年份</option>
          {(facets?.years || [2025, 2024, 2023, 2022, 2021, 2020]).map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>

        <select
          value={filters.module || ''}
          onChange={(event) => update({ module: event.target.value || undefined })}
          className="rounded border px-2 py-1.5 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
          }}
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
          className="rounded border px-2 py-1.5 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
          }}
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
          className="rounded border px-2 py-1.5 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
          }}
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
          className="rounded border px-2 py-1.5 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-card)',
            color: 'var(--color-text)',
          }}
        >
          <option value="">状态</option>
          <option value="已审核">已审核</option>
          <option value="待审核">待审核</option>
          <option value="已确认">已确认</option>
          <option value="待校验">待校验</option>
        </select>

        {activeFilters.length > 0 && (
          <button
            onClick={clearAll}
            className="cursor-pointer rounded border px-2 py-1.5 text-xs"
            style={{
              borderColor: 'var(--color-border)',
              color: 'var(--color-red)',
              background: 'var(--color-bg-card)',
            }}
          >
            清空筛选
          </button>
        )}
      </div>

      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {activeFilters.map((item, index) => (
            <span
              key={`${item}-${index}`}
              className="rounded-full px-2 py-0.5 text-xs"
              style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent-dark)' }}
            >
              {item}
            </span>
          ))}
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            ({activeFilters.length} 项筛选)
          </span>
        </div>
      )}
    </div>
  );
}
