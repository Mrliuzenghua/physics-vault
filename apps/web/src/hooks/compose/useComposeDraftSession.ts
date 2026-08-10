import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { fetchLatestPaperDraft, fetchPaperDraft } from '../../services/api';
import { fetchQuestion, fetchQuestionsByIds } from '../../services/questionApi';
import { buildComposeItemsFromPaperDraft, getQuestionSnapshot } from '../../utils/composeDraft';
import type { BasketItem, ComposeItem, ComposeQuestionItem, PaperDraft, Question, TemplateMaterialPackage } from '../../types';

const CURRENT_COMPOSE_DRAFT_STORAGE_KEY = 'physics-vault.compose.current-draft-id';
const DEFAULT_SUBTITLE = '知识点、文本说明与试题自由拼接';

type DraftSaveState = 'idle' | 'saving' | 'saved' | 'error';

interface UseComposeDraftSessionOptions {
  basketItems: BasketItem[];
  composeItems: ComposeItem[];
  documentRevision: number;
  incomingPackage?: TemplateMaterialPackage;
  loadComposeItems: (items: ComposeItem[], selectedIndex?: number) => void;
  savedRevision: number;
  setLessonSubtitle: Dispatch<SetStateAction<string>>;
  setLessonTitle: Dispatch<SetStateAction<string>>;
  startNewDraft: boolean;
  updateComposeItems: (updater: (items: ComposeItem[]) => ComposeItem[]) => void;
}

function buildComposeItemsFromQuestions(questions: Question[]): ComposeItem[] {
  return questions.map((question) => ({
    type: 'question',
    id: question.question_id,
    questionId: question.question_id,
    question,
  }));
}

export function useComposeDraftSession({
  basketItems,
  composeItems,
  documentRevision,
  incomingPackage,
  loadComposeItems,
  savedRevision,
  setLessonSubtitle,
  setLessonTitle,
  startNewDraft,
  updateComposeItems,
}: UseComposeDraftSessionOptions) {
  const queryClient = useQueryClient();
  const initialBasketItemsRef = useRef<BasketItem[]>(basketItems);
  const [draftId, setDraftId] = useState(() => (
    (!startNewDraft && typeof window !== 'undefined' ? window.localStorage.getItem(CURRENT_COMPOSE_DRAFT_STORAGE_KEY) : null)
      || `lesson-current-${Date.now()}`
  ));
  const draftIdRef = useRef(draftId);
  const [serverDraftUpdatedAt, setServerDraftUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [draftSaveState, setDraftSaveState] = useState<DraftSaveState>('idle');

  const recordSavedDraft = useCallback((draft: PaperDraft) => {
    draftIdRef.current = draft.id;
    setDraftId(draft.id);
    window.localStorage.setItem(CURRENT_COMPOSE_DRAFT_STORAGE_KEY, draft.id);
    setServerDraftUpdatedAt(draft.updated_at);
    queryClient.setQueryData(['paper-draft', 'latest'], draft);
  }, [queryClient]);

  const hydrateServerDraft = useCallback(async (draft: PaperDraft, supplementalBasketItems: BasketItem[] = []) => {
    const draftQuestionIds = draft.items
      .filter((item) => item.type === 'question' && item.question_id && !getQuestionSnapshot(item.payload || {}))
      .map((item) => item.question_id as string);
    const basketQuestionIds = supplementalBasketItems.map((item) => item.question_id);
    const questionIds = [...new Set([...draftQuestionIds, ...basketQuestionIds])];
    const questions = questionIds.length > 0 ? await fetchQuestionsByIds(questionIds) : [];
    const loaded = buildComposeItemsFromPaperDraft(draft, questions);
    const questionMap = new Map(questions.map((question) => [question.question_id, question]));
    const includedQuestionIds = new Set(
      loaded
        .filter((item): item is ComposeQuestionItem => item.type === 'question')
        .map((item) => item.questionId),
    );
    for (const basketItem of supplementalBasketItems) {
      if (includedQuestionIds.has(basketItem.question_id)) continue;
      loaded.push({
        type: 'question',
        id: basketItem.question_id,
        questionId: basketItem.question_id,
        question: questionMap.get(basketItem.question_id),
      });
      includedQuestionIds.add(basketItem.question_id);
    }
    recordSavedDraft(draft);
    setLessonTitle(draft.title);
    setLessonSubtitle(draft.subtitle || DEFAULT_SUBTITLE);
    loadComposeItems(loaded);
    setLoading(false);
    setDraftSaveState('saved');
  }, [loadComposeItems, recordSavedDraft, setLessonSubtitle, setLessonTitle]);

  const refreshDraft = useCallback(async (): Promise<boolean> => {
    const latest = await fetchLatestPaperDraft();
    if (
      latest
      && latest.id === draftIdRef.current
      && latest.updated_at !== serverDraftUpdatedAt
    ) {
      await hydrateServerDraft(latest);
      return true;
    }
    return false;
  }, [hydrateServerDraft, serverDraftUpdatedAt]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const initialBasketItems = initialBasketItemsRef.current;
      if (startNewDraft) {
        window.localStorage.removeItem(CURRENT_COMPOSE_DRAFT_STORAGE_KEY);
      }
      const storedDraftId = window.localStorage.getItem(CURRENT_COMPOSE_DRAFT_STORAGE_KEY);
      if (!startNewDraft && storedDraftId) {
        try {
          const storedDraft = await fetchPaperDraft(storedDraftId);
          if (storedDraft && storedDraft.items.length > 0) {
            if (!cancelled) await hydrateServerDraft(storedDraft, initialBasketItems);
            return;
          }
        } catch {
          // Continue with the basket or template when the remembered draft is unavailable.
        }
      }

      if (incomingPackage && incomingPackage.questions.length > 0) {
        if (!cancelled) {
          setLessonTitle(incomingPackage.name || '未命名试卷');
          loadComposeItems(buildComposeItemsFromQuestions(incomingPackage.questions));
          setLoading(false);
        }
        return;
      }

      if (initialBasketItems.length === 0) {
        try {
          const draft = await queryClient.fetchQuery({
            queryKey: ['paper-draft', 'latest'],
            queryFn: fetchLatestPaperDraft,
          });
          if (draft && draft.items.length > 0) {
            if (!cancelled) await hydrateServerDraft(draft);
            return;
          }
        } catch {
          // 工作台草稿不可用时，保持空白工作台，仍可从题篮开始组卷。
        }
        if (!cancelled) {
          loadComposeItems([]);
          setLoading(false);
        }
        return;
      }

      let loaded: ComposeItem[];
      try {
        const questionIds = initialBasketItems.map((item) => item.question_id);
        const questions = await queryClient.fetchQuery({
          queryKey: ['questions', 'batch', [...questionIds].sort()],
          queryFn: () => fetchQuestionsByIds(questionIds),
        });
        const questionMap = new Map(questions.map((question) => [question.question_id, question]));
        loaded = initialBasketItems.map((basketItem) => ({
          type: 'question',
          id: basketItem.question_id,
          questionId: basketItem.question_id,
          question: questionMap.get(basketItem.question_id),
        }));
      } catch {
        loaded = [];
        for (const basketItem of initialBasketItems) {
          try {
            const question = await queryClient.fetchQuery({
              queryKey: ['question', basketItem.question_id],
              queryFn: () => fetchQuestion(basketItem.question_id),
            });
            loaded.push({ type: 'question', id: basketItem.question_id, questionId: basketItem.question_id, question });
          } catch {
            loaded.push({ type: 'question', id: basketItem.question_id, questionId: basketItem.question_id });
          }
        }
      }

      if (!cancelled) {
        loadComposeItems(loaded);
        setLoading(false);
      }
    }

    void load();
    return () => { cancelled = true; };
  }, [hydrateServerDraft, incomingPackage, loadComposeItems, queryClient, setLessonTitle, startNewDraft]);

  useEffect(() => {
    if (loading || basketItems.length === 0) return undefined;
    const includedQuestionIds = new Set(
      composeItems
        .filter((item): item is ComposeQuestionItem => item.type === 'question')
        .map((item) => item.questionId),
    );
    const missingBasketItems = basketItems.filter((item) => !includedQuestionIds.has(item.question_id));
    if (missingBasketItems.length === 0) return undefined;

    let cancelled = false;
    void fetchQuestionsByIds(missingBasketItems.map((item) => item.question_id))
      .catch(() => [])
      .then((questions) => {
        if (cancelled) return;
        const questionMap = new Map(questions.map((question) => [question.question_id, question]));
        updateComposeItems((current) => {
          const currentQuestionIds = new Set(
            current
              .filter((item): item is ComposeQuestionItem => item.type === 'question')
              .map((item) => item.questionId),
          );
          const additions: ComposeQuestionItem[] = missingBasketItems
            .filter((item) => !currentQuestionIds.has(item.question_id))
            .map((item) => ({
              type: 'question',
              id: item.question_id,
              questionId: item.question_id,
              question: questionMap.get(item.question_id),
            }));
          return additions.length > 0 ? [...current, ...additions] : current;
        });
      });
    return () => { cancelled = true; };
  }, [basketItems, composeItems, loading, updateComposeItems]);

  useEffect(() => {
    if (loading || !serverDraftUpdatedAt) return undefined;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'hidden' || documentRevision !== savedRevision) return;
      void refreshDraft().catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [documentRevision, loading, refreshDraft, savedRevision, serverDraftUpdatedAt]);

  return {
    draftId,
    draftSaveState,
    hydrateServerDraft,
    loading,
    recordSavedDraft,
    refreshDraft,
    serverDraftUpdatedAt,
    setDraftSaveState,
  };
}
