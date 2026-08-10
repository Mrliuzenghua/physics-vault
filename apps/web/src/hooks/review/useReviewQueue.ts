import { useCallback, useMemo, useState } from 'react';

import type { QuestionQualityRuleConfig } from '../../services/questionQuality';
import type { ReviewPageResult } from '../../services/review/reviewCache';
import type { ReviewQuestionDraft } from '../../types';
import {
  buildQualityReport,
  buildReviewQueueCounts,
  filterReviewDrafts,
  findDuplicateReviewQuestionIds,
  findNextRiskIndex,
  type QueueKey,
} from '../../utils/review/reviewQueue';

interface UseReviewQueueOptions {
  drafts: ReviewQuestionDraft[];
  pageResults: ReviewPageResult[];
  qualityConfig: QuestionQualityRuleConfig;
}

export function useReviewQueue({ drafts, pageResults, qualityConfig }: UseReviewQueueOptions) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [queue, setQueue] = useState<QueueKey>('risk');
  const [questionQuery, setQuestionQuery] = useState('');

  const currentDraft = drafts[currentIndex] ?? null;
  const currentPage = useMemo(() => {
    if (!currentDraft?.source_page) return null;
    return pageResults.find((page) => page.page_no === currentDraft.source_page) ?? null;
  }, [currentDraft, pageResults]);
  const failedPages = useMemo(() => pageResults.filter((page) => page.status === 'failed'), [pageResults]);
  const duplicateQuestionIds = useMemo(() => findDuplicateReviewQuestionIds(drafts), [drafts]);
  const qualityReport = useMemo(
    () => buildQualityReport(drafts, duplicateQuestionIds, qualityConfig),
    [drafts, duplicateQuestionIds, qualityConfig],
  );
  const counts = useMemo(
    () => buildReviewQueueCounts(drafts, duplicateQuestionIds, qualityConfig, failedPages.length),
    [drafts, duplicateQuestionIds, failedPages.length, qualityConfig],
  );
  const filteredDrafts = useMemo(
    () => filterReviewDrafts(drafts, queue, questionQuery, duplicateQuestionIds, qualityConfig, failedPages),
    [drafts, duplicateQuestionIds, failedPages, qualityConfig, questionQuery, queue],
  );
  const goPrevious = useCallback(() => setCurrentIndex((previous) => Math.max(0, previous - 1)), []);
  const goNext = useCallback(() => setCurrentIndex((previous) => Math.min(drafts.length - 1, previous + 1)), [drafts.length]);
  const goNextRisk = useCallback(() => {
    const nextIndex = findNextRiskIndex(drafts, currentIndex, duplicateQuestionIds, qualityConfig);
    if (nextIndex !== null) setCurrentIndex(nextIndex);
  }, [currentIndex, drafts, duplicateQuestionIds, qualityConfig]);

  return {
    counts,
    currentDraft,
    currentIndex,
    currentPage,
    duplicateQuestionIds,
    failedPages,
    filteredDrafts,
    goNext,
    goNextRisk,
    goPrevious,
    qualityReport,
    questionQuery,
    queue,
    setCurrentIndex,
    setQuestionQuery,
    setQueue,
  };
}
