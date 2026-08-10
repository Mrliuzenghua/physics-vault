import type { QuestionQualityCode, QuestionQualityRuleConfig, QuestionQualitySeverity } from '../questionQuality';
import type { ImportMediaAsset, KnowledgeReviewDraft, ReviewQuestionDraft } from '../../types';

const REVIEW_CACHE_PREFIX = 'physics_vault_review_cache.';
const REVIEW_CACHE_VERSION = 1;
const REVIEW_QUALITY_CONFIG_KEY = 'physics_vault_review_quality_config.v1';

export interface ReviewPageResult {
  page_no?: number;
  status?: string;
  page_image_path?: string;
  error?: string;
  question_count?: number;
  image_width?: number | null;
  image_height?: number | null;
  regions?: Array<{
    region_id?: string | null;
    question_id?: string | null;
    bbox?: [number, number, number, number] | null;
  }>;
}

export interface ReviewTaskMeta {
  batchId?: string;
  warnings: string[];
  pageResults: ReviewPageResult[];
  mediaAssets: ImportMediaAsset[];
}

export interface CachedQuestionQuality {
  question_id: string;
  issues: Array<{
    code: QuestionQualityCode;
    severity: QuestionQualitySeverity;
    field: string;
    message: string;
  }>;
}

export interface CachedReviewState<Queue extends string = string> {
  version: 1;
  taskId: string;
  savedAt: string;
  drafts: ReviewQuestionDraft[];
  qualityReport?: CachedQuestionQuality[];
  knowledgeDrafts?: KnowledgeReviewDraft[];
  taskMeta: ReviewTaskMeta;
  currentIndex: number;
  queue: Queue;
}

function getStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function reviewCacheKey(taskId: string): string {
  return `${REVIEW_CACHE_PREFIX}${taskId}`;
}

export function readReviewCache<Queue extends string = string>(taskId: string): CachedReviewState<Queue> | null {
  try {
    const raw = getStorage()?.getItem(reviewCacheKey(taskId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedReviewState<Queue>;
    if (parsed.version !== REVIEW_CACHE_VERSION || parsed.taskId !== taskId || !Array.isArray(parsed.drafts)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeReviewCache<Queue extends string>(
  taskId: string,
  state: Omit<CachedReviewState<Queue>, 'version' | 'taskId' | 'savedAt'>,
): void {
  try {
    getStorage()?.setItem(reviewCacheKey(taskId), JSON.stringify({
      version: REVIEW_CACHE_VERSION,
      taskId,
      savedAt: new Date().toISOString(),
      ...state,
    }));
  } catch {
    // Ignore storage quota or privacy-mode failures; the page still works.
  }
}

export function clearReviewCache(taskId: string): void {
  try {
    getStorage()?.removeItem(reviewCacheKey(taskId));
  } catch {
    // Ignore localStorage failures.
  }
}

export function mergeMediaAssets(...groups: ImportMediaAsset[][]): ImportMediaAsset[] {
  const merged = new Map<string, ImportMediaAsset>();
  groups.flat().forEach((asset) => {
    const key = asset.relative_path || asset.image_id || asset.filename;
    if (key && !merged.has(key)) merged.set(key, asset);
  });
  return [...merged.values()];
}

export function mediaAssetsFromDrafts(drafts: ReviewQuestionDraft[]): ImportMediaAsset[] {
  return mergeMediaAssets(drafts.flatMap((draft) => draft.figures.map((figure) => ({
    image_id: figure.fig_uuid,
    filename: figure.local_path.split(/[\\/]/).pop() || figure.fig_uuid,
    relative_path: figure.local_path,
    absolute_path: '',
    size: 0,
  }))));
}

export function mergeTaskMeta(
  preferred: ReviewTaskMeta | null | undefined,
  fallback: ReviewTaskMeta,
  drafts: ReviewQuestionDraft[],
): ReviewTaskMeta {
  return {
    batchId: preferred?.batchId || fallback.batchId,
    warnings: Array.isArray(preferred?.warnings) ? preferred.warnings : fallback.warnings,
    pageResults: Array.isArray(preferred?.pageResults) ? preferred.pageResults : fallback.pageResults,
    mediaAssets: mergeMediaAssets(
      preferred?.mediaAssets ?? [],
      fallback.mediaAssets,
      mediaAssetsFromDrafts(drafts),
    ),
  };
}

export function readQualityConfig(): QuestionQualityRuleConfig {
  try {
    const raw = getStorage()?.getItem(REVIEW_QUALITY_CONFIG_KEY);
    return raw ? JSON.parse(raw) as QuestionQualityRuleConfig : {};
  } catch {
    return {};
  }
}

export function writeQualityConfig(config: QuestionQualityRuleConfig): void {
  try {
    getStorage()?.setItem(REVIEW_QUALITY_CONFIG_KEY, JSON.stringify(config));
  } catch {
    // Keep the in-memory configuration when browser storage is unavailable.
  }
}
