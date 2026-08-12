import type { AiAssistantQuestionContext, Question } from '../types';
import { readJsonStorage, writeJsonStorage } from '../services/safeStorage.ts';

export const AI_CONTEXT_CACHE_STORAGE_KEY = 'physics_vault.agent_chat.v2.context_cache';

export function readAiContextCache(): AiAssistantQuestionContext[] {
  const parsed = readJsonStorage<unknown>(AI_CONTEXT_CACHE_STORAGE_KEY, []);
  if (!Array.isArray(parsed)) return [];
  return parsed.filter((item): item is AiAssistantQuestionContext => (
    item !== null && typeof item === 'object' && typeof item.question_id === 'string'
  ));
}

export function writeAiContextCache(items: AiAssistantQuestionContext[]): void {
  writeJsonStorage(AI_CONTEXT_CACHE_STORAGE_KEY, dedupeContexts(items).slice(0, 30));
}

export function addQuestionsToAiContext(questions: Question[]): AiAssistantQuestionContext[] {
  const next = dedupeContexts([...readAiContextCache(), ...questions.map(questionToAiContext)]).slice(0, 30);
  writeAiContextCache(next);
  return next;
}

export function questionToAiContext(question: Question): AiAssistantQuestionContext {
  const knowledgeNames = (question.knowledge_points || [])
    .map((item) => item.topic3_name || item.topic2_name || item.topic1_name)
    .filter(Boolean);
  const knowledgePoint = question.knowledge_point || knowledgeNames[0] || question.topic3 || question.topic2 || null;
  return {
    question_id: question.question_id,
    title: question.title || '',
    question_type: question.question_type || null,
    difficulty: question.difficulty !== undefined && question.difficulty !== null ? String(question.difficulty) : null,
    knowledge_point: knowledgePoint,
    source: question.source || question.primary_paper_id || question.origin_file || null,
    answer: question.answer || null,
    analysis: question.analysis || null,
    tags: [...new Set([...(question.tags || []), ...knowledgeNames])],
  };
}

function dedupeContexts(items: AiAssistantQuestionContext[]): AiAssistantQuestionContext[] {
  const result: AiAssistantQuestionContext[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    if (!item.question_id || seen.has(item.question_id)) continue;
    seen.add(item.question_id);
    result.push(item);
  }
  return result;
}
