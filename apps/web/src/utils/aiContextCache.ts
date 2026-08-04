import type { AiAssistantQuestionContext, Question } from '../types';

export const AI_CONTEXT_CACHE_STORAGE_KEY = 'physics_vault.agent_chat.v2.context_cache';

export function readAiContextCache(): AiAssistantQuestionContext[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(AI_CONTEXT_CACHE_STORAGE_KEY) || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => item && typeof item.question_id === 'string');
  } catch {
    return [];
  }
}

export function writeAiContextCache(items: AiAssistantQuestionContext[]): void {
  localStorage.setItem(AI_CONTEXT_CACHE_STORAGE_KEY, JSON.stringify(dedupeContexts(items).slice(0, 30)));
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
