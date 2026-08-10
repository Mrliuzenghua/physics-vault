import type {
  ComposeItem,
  ComposeTextItem,
  PaperDraft,
  Question,
} from '../types';

/**
 * Project question instances are stored in paper-draft payloads as complete
 * snapshots. Legacy drafts may not have a snapshot and are handled by the
 * caller's question-bank fallback.
 */
export function getQuestionSnapshot(payload: Record<string, unknown> = {}): Question | undefined {
  const snapshot = payload.question_snapshot;
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return undefined;
  const question = snapshot as Partial<Question>;
  return typeof question.question_id === 'string' && question.question_id.trim()
    ? snapshot as Question
    : undefined;
}

export function buildComposeItemsFromPaperDraft(draft: PaperDraft, questions: Question[]): ComposeItem[] {
  const questionMap = new Map(questions.map((question) => [question.question_id, question]));
  return draft.items.map((item) => {
    const payload = item.payload || {};
    if (item.type === 'question') {
      const snapshot = getQuestionSnapshot(payload);
      const questionId = snapshot?.question_id || item.question_id || item.id;
      return {
        type: 'question',
        id: item.id,
        questionId,
        // Prefer the project snapshot. The question-bank lookup is retained
        // only for legacy drafts created before snapshots were persisted.
        question: snapshot || questionMap.get(questionId),
      };
    }
    if (item.type === 'knowledge') {
      return {
        type: 'knowledge',
        id: item.id,
        knowledgeId: String(payload.topic3_id || payload.id || item.id),
        title: String(payload.title || item.title || '知识点'),
        content: String(payload.content || ''),
        summary: String(payload.summary || payload.content || ''),
        points: Array.isArray(payload.points) ? payload.points.map(String) : [],
      };
    }
    if (item.type === 'text') {
      return {
        type: 'text',
        id: item.id,
        title: String(payload.title || item.title || '教学说明'),
        content: String(payload.content || ''),
        document: payload.document as Record<string, unknown> | undefined,
        blockKind: payload.blockKind as ComposeTextItem['blockKind'],
        style: payload.style as ComposeTextItem['style'],
      };
    }
    return { type: 'separator', id: item.id, title: item.title || '分页' };
  });
}
