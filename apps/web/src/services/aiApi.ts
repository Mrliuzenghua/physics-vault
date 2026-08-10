import type {
  AgentConfig,
  AgentConfigResponse,
  AgentStreamEvent,
  AgentTestResponse,
  AiAssistantResponse,
  AiChatMessage,
  AiChatTestResponse,
  McpConfig,
  McpConnectionTestResponse,
  McpRuntimeStatus,
  Question,
  QuestionPickerAgentResponse,
} from '../types';
import { request, requestResponse } from './apiClient.ts';

export async function fetchMcpStatus(): Promise<McpRuntimeStatus> { return request('/api/mcp/status'); }

export async function fetchMcpRuntimeConfig(): Promise<{
  vl: McpConfig['vl']; llm: McpConfig['llm']; vl_configured: boolean; llm_configured: boolean;
}> { return request('/api/mcp/config'); }

export async function testMcpConnection(target: 'vl' | 'llm'): Promise<McpConnectionTestResponse> {
  return request('/api/mcp/test-connection', { method: 'POST', body: JSON.stringify({ target }) });
}

export async function sendAiChatTest(messages: AiChatMessage[], temperature = 0.7): Promise<AiChatTestResponse> {
  return request('/api/mcp/chat-test', { method: 'POST', body: JSON.stringify({ messages, temperature }) });
}

export async function refineQuestionFormat(question: Question): Promise<Partial<Question>> {
  const result = await request<{ ok: boolean; data: Partial<Question> }>('/api/mcp/refine-question-format', {
    method: 'POST', body: JSON.stringify({ question }),
  });
  return result.data;
}

export async function completeQuestionAnalysis(question: Question): Promise<string> {
  const difficulty = Number(question.difficulty);
  const result = await request<{ ok: boolean; data: { analysis_text?: string; analysis?: string } }>('/api/mcp/generate-analysis', {
    method: 'POST',
    body: JSON.stringify({
      question: {
        question_id: question.question_id, question_type: question.question_type || 'calculation', title: question.title || '',
        options: question.options || [], answer: question.answer || '', analysis: question.analysis || '',
        figures: (question.figures || []).map((figure) => ({ fig_uuid: figure.fig_uuid, local_path: figure.local_path })),
        difficulty: Number.isInteger(difficulty) && difficulty >= 1 && difficulty <= 5 ? difficulty : null,
        knowledge_point: question.knowledge_point || null, tags: question.tags || [], source: question.source || null,
      }, style: 'exam_standard', include_extension: false,
    }),
  });
  const analysis = String(result.data.analysis_text || result.data.analysis || '').trim();
  if (!analysis) throw new Error('DeepSeek 没有返回可用解析，请检查题干、答案和模型配置。');
  return analysis;
}

export async function sendAiAssistantChat(messages: AiChatMessage[], options?: { query?: string; contextLimit?: number; temperature?: number }): Promise<AiAssistantResponse> {
  return request('/api/ai/assistant/chat', {
    method: 'POST',
    body: JSON.stringify({ messages, query: options?.query, context_limit: options?.contextLimit ?? 8, temperature: options?.temperature ?? 0.35 }),
  });
}

export async function fetchAgentConfig(): Promise<AgentConfigResponse> { return request('/api/agents/config'); }
export async function saveAgentConfig(config: AgentConfig): Promise<AgentConfigResponse> {
  return request('/api/agents/config', { method: 'POST', body: JSON.stringify(config) });
}
export async function testClaudeCodeAgent(): Promise<AgentTestResponse> { return request('/api/agents/test-claude-code', { method: 'POST' }); }

type QuestionPickerOptions = { query?: string; contextLimit?: number; contextQuestionIds?: string[]; sessionId?: string; resumeSession?: boolean };

function questionPickerBody(messages: AiChatMessage[], options: QuestionPickerOptions) {
  return {
    messages, query: options.query, context_limit: options.contextLimit ?? 12,
    context_question_ids: options.contextQuestionIds ?? [], session_id: options.sessionId, resume_session: options.resumeSession ?? false,
  };
}

export async function runQuestionPickerAgent(messages: AiChatMessage[], options: QuestionPickerOptions = {}): Promise<QuestionPickerAgentResponse> {
  return request('/api/agents/question-picker', { method: 'POST', body: JSON.stringify(questionPickerBody(messages, options)) });
}

export async function streamQuestionPickerAgent(
  messages: AiChatMessage[],
  options: QuestionPickerOptions & { signal?: AbortSignal; onEvent: (event: AgentStreamEvent) => void },
): Promise<void> {
  const res = await requestResponse('/api/agents/question-picker/stream', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: options.signal,
    body: JSON.stringify(questionPickerBody(messages, options)),
  });
  if (!res.body) throw new Error('浏览器没有返回可读取的智能体事件流');
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed) options.onEvent(JSON.parse(trimmed) as AgentStreamEvent);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) options.onEvent(JSON.parse(buffer.trim()) as AgentStreamEvent);
}
