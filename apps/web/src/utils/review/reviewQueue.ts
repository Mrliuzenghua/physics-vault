import {
  analyzeQuestionQuality,
  findDuplicateQuestionIds,
  type QuestionQualityCode,
  type QuestionQualityRuleConfig,
} from '../../services/questionQuality.ts';
import type { CachedQuestionQuality, ReviewPageResult } from '../../services/review/reviewCache';
import type { ReviewQuestionDraft } from '../../types';
import { findNextMatchingIndex } from '../reviewQueueNavigation.ts';

export type QueueKey = 'risk' | 'missing_answer' | 'missing_options' | 'image_issue' | 'ai_failed_page' | 'pending' | 'modified' | 'confirmed' | 'discarded' | 'all';

export interface RiskItem {
  kind: QuestionQualityCode;
  severity: 'danger' | 'warning';
  message: string;
}

export interface ReviewQueueCounts {
  total: number;
  risk: number;
  missingAnswer: number;
  missingOptions: number;
  imageIssue: number;
  failedPage: number;
  pending: number;
  modified: number;
  confirmed: number;
  discarded: number;
}

export function getRiskItems(
  draft: ReviewQuestionDraft,
  duplicateIds: ReadonlySet<string> = new Set(),
  config: QuestionQualityRuleConfig = {},
): RiskItem[] {
  return analyzeQuestionQuality(draft, {
    questionId: draft.question_id,
    duplicateIds,
    requireKnowledge: true,
    requireSource: true,
    config,
  }).map((issue) => ({
    kind: issue.code,
    severity: issue.severity === 'danger' ? 'danger' : 'warning',
    message: issue.message,
  }));
}

export function buildQualityReport(
  drafts: ReviewQuestionDraft[],
  duplicateIds: ReadonlySet<string>,
  config: QuestionQualityRuleConfig,
): CachedQuestionQuality[] {
  return drafts.map((draft) => ({
    question_id: draft.question_id,
    issues: analyzeQuestionQuality(draft, {
      questionId: draft.question_id,
      duplicateIds,
      requireKnowledge: true,
      requireSource: true,
      config,
    }),
  }));
}

export function buildReviewQueueCounts(
  drafts: ReviewQuestionDraft[],
  duplicateIds: ReadonlySet<string>,
  config: QuestionQualityRuleConfig,
  failedPageCount: number,
): ReviewQueueCounts {
  const counts: ReviewQueueCounts = {
    total: drafts.length,
    risk: 0,
    missingAnswer: 0,
    missingOptions: 0,
    imageIssue: 0,
    failedPage: failedPageCount,
    pending: 0,
    modified: 0,
    confirmed: 0,
    discarded: 0,
  };
  for (const draft of drafts) {
    counts[draft.status] += 1;
    const risks = getRiskItems(draft, duplicateIds, config);
    if (risks.length > 0) counts.risk += 1;
    if (risks.some((risk) => risk.kind === 'missing_answer')) counts.missingAnswer += 1;
    if (risks.some((risk) => risk.kind === 'missing_options')) counts.missingOptions += 1;
    if (risks.some((risk) => risk.kind === 'image_issue')) counts.imageIssue += 1;
  }
  return counts;
}

export function filterReviewDrafts(
  drafts: ReviewQuestionDraft[],
  queue: QueueKey,
  query: string,
  duplicateIds: ReadonlySet<string>,
  config: QuestionQualityRuleConfig,
  failedPages: ReviewPageResult[],
): Array<{ draft: ReviewQuestionDraft; index: number }> {
  const failedPageNumbers = new Set(failedPages.map((page) => page.page_no).filter((page): page is number => typeof page === 'number'));
  const keyword = query.trim().toLowerCase();
  return drafts
    .map((draft, index) => ({ draft, index }))
    .filter(({ draft, index }) => {
      const matchesSelectedQueue = queue === 'ai_failed_page'
        ? typeof draft.source_page === 'number' && failedPageNumbers.has(draft.source_page)
        : matchesQueue(draft, queue, duplicateIds, config);
      if (!matchesSelectedQueue) return false;
      if (!keyword) return true;
      return [String(index + 1), draft.title, draft.answer, draft.knowledge_point, draft.tags.join(' ')]
        .join(' ')
        .toLowerCase()
        .includes(keyword);
    });
}

export function findNextRiskIndex(
  drafts: ReviewQuestionDraft[],
  currentIndex: number,
  duplicateIds: ReadonlySet<string>,
  config: QuestionQualityRuleConfig,
): number | null {
  return findNextMatchingIndex(
    drafts,
    currentIndex,
    (draft) => draft.status !== 'discarded' && getRiskItems(draft, duplicateIds, config).length > 0,
  );
}

export function findDuplicateReviewQuestionIds(drafts: ReviewQuestionDraft[]): Set<string> {
  return findDuplicateQuestionIds(drafts, (draft) => draft.question_id);
}

function matchesQueue(
  draft: ReviewQuestionDraft,
  queue: Exclude<QueueKey, 'ai_failed_page'>,
  duplicateIds: ReadonlySet<string>,
  config: QuestionQualityRuleConfig,
): boolean {
  if (queue === 'all') return true;
  if (queue === 'pending' || queue === 'modified' || queue === 'confirmed' || queue === 'discarded') return draft.status === queue;
  const risks = getRiskItems(draft, duplicateIds, config);
  if (queue === 'risk') return risks.length > 0;
  if (queue === 'missing_answer') return risks.some((risk) => risk.kind === 'missing_answer');
  if (queue === 'missing_options') return risks.some((risk) => risk.kind === 'missing_options');
  return risks.some((risk) => risk.kind === 'image_issue');
}
