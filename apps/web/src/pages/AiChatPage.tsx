import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import {
  addToBasket,
  getMcpConfig,
  sendAiAssistantChat,
} from '../services/api';
import type {
  AiAssistantCompositionSuggestion,
  AiAssistantQuestionContext,
  AiChatMessage,
} from '../types';

const QUICK_PROMPTS = [
  '帮我组一份牛顿第二定律的课堂练习，难度由浅入深。',
  '从题库里找适合讲闭合电路欧姆定律的题，并说明讲课顺序。',
  '我想出一份 20 分钟小测，题型要覆盖选择题和计算题。',
  '帮我看看当前题库里哪些题适合作为课后作业。',
];

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选',
  multi_choice: '多选',
  fill: '填空',
  experiment: '实验',
  calculation: '计算',
};

export default function AiChatPage() {
  const llmConfig = useMemo(() => getMcpConfig().llm, []);
  const [messages, setMessages] = useState<AiChatMessage[]>([
    {
      role: 'assistant',
      content: '我是题库备课助手。你可以直接问我“帮我组一份力学基础练习”或“找几道闭合电路题作为课堂例题”，我会先查询数据库里的题目，再给出组卷建议。',
    },
  ]);
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [contextQuestions, setContextQuestions] = useState<AiAssistantQuestionContext[]>([]);
  const [suggestions, setSuggestions] = useState<AiAssistantCompositionSuggestion[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastModel, setLastModel] = useState<string | null>(null);
  const [aiUsed, setAiUsed] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);

  const handleSend = async (preset?: string) => {
    const content = (preset ?? draft).trim();
    if (!content || sending) return;

    const nextMessages: AiChatMessage[] = [...messages, { role: 'user', content }];
    setMessages(nextMessages);
    setDraft('');
    setSending(true);
    setError(null);
    setWarnings([]);

    try {
      const result = await sendAiAssistantChat(nextMessages, {
        query: query.trim() || undefined,
        contextLimit: 10,
      });
      setMessages([...nextMessages, { role: 'assistant', content: result.reply || '(没有返回内容)' }]);
      setContextQuestions(result.context_questions || []);
      setSuggestions(result.composition_suggestions || []);
      setLastModel(result.model);
      setAiUsed(result.ai_used);
      setWarnings(result.warnings || []);
      if (!query.trim() && result.query_used) {
        setQuery(result.query_used);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setSending(false);
    }
  };

  const clearMessages = () => {
    setMessages([
      {
        role: 'assistant',
        content: '会话已清空。你可以继续让我查询题库、解释题目或给出组卷方案。',
      },
    ]);
    setDraft('');
    setError(null);
    setWarnings([]);
    setContextQuestions([]);
    setSuggestions([]);
  };

  const addQuestions = (ids: string[]) => {
    ids.forEach(addToBasket);
  };

  return (
    <div className="h-full overflow-hidden bg-[#eef4fb] text-[#18243a]">
      <div className="grid h-full grid-cols-[minmax(0,1fr)_360px]">
        <main className="flex min-w-0 flex-col overflow-hidden">
          <section className="border-b border-[#dbe6f4] bg-white px-6 py-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="mb-1 text-xs font-semibold tracking-[0.22em] text-[#2c75d6]">AI DATABASE ASSISTANT</p>
                <h1 className="text-2xl font-black text-[#152238]">AI 题库备课助手</h1>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-[#687891]">
                  与 AI 对话时会自动查询数据库题目作为上下文，并返回可执行的组卷建议。
                </p>
              </div>
              <button
                onClick={clearMessages}
                className="rounded-xl border border-[#d8e2f0] bg-white px-4 py-2 text-sm font-semibold text-[#40506a]"
              >
                清空会话
              </button>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <InfoTile label="模型" value={llmConfig.model_name || '未配置'} />
              <InfoTile label="最近响应" value={lastModel || '还没有回复'} />
              <InfoTile label="模式" value={aiUsed ? 'AI + 题库上下文' : '题库规则建议'} />
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => void handleSend(prompt)}
                  disabled={sending}
                  className="rounded-full border border-[#d7e2f0] bg-[#f8fbff] px-3 py-1.5 text-xs font-medium text-[#40506a] disabled:opacity-60"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </section>

          <section className="flex min-h-0 flex-1 flex-col p-5">
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-2xl bg-white p-4 shadow-[0_18px_45px_rgba(25,48,84,0.08)]">
              {messages.map((message, index) => {
                const isUser = message.role === 'user';
                return (
                  <div key={`${message.role}-${index}`} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-3xl rounded-2xl px-4 py-3 text-sm leading-7 whitespace-pre-wrap ${
                        isUser ? 'bg-[#2673d9] text-white' : 'bg-[#f4f8fc] text-[#1f3148]'
                      }`}
                    >
                      {message.content}
                    </div>
                  </div>
                );
              })}

              {sending && (
                <div className="flex justify-start">
                  <div className="rounded-2xl bg-[#f4f8fc] px-4 py-3 text-sm text-[#5c6c84]">
                    正在查询题库并生成建议…
                  </div>
                </div>
              )}
            </div>

            <div className="mt-4 rounded-2xl bg-white p-4 shadow-[0_18px_45px_rgba(25,48,84,0.08)]">
              {error && (
                <div className="mb-3 rounded-xl border border-[#ffc9c9] bg-[#fff1f1] px-4 py-3 text-sm font-semibold text-[#d73535]">
                  {error}
                </div>
              )}
              {warnings.length > 0 && (
                <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-700">
                  {warnings.join('；')}
                </div>
              )}

              <div className="mb-3">
                <label className="mb-1 block text-xs font-semibold text-[#6f8098]">检索关键词，可留空让 AI 从问题中判断</label>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="例如：牛顿第二定律、闭合电路、机械能守恒"
                  className="h-10 w-full rounded-xl border border-[#d7e2f0] bg-[#fbfdff] px-3 text-sm text-[#18243a] outline-none focus:border-[#2d72d9]"
                />
              </div>

              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleSend();
                  }
                }}
                placeholder="告诉我你的组卷目标、知识点、难度、课时长度或学生情况..."
                className="min-h-[110px] w-full resize-none rounded-xl border border-[#d7e2f0] bg-[#fbfdff] px-4 py-3 text-sm leading-7 text-[#18243a] outline-none focus:border-[#2d72d9]"
              />

              <div className="mt-3 flex justify-end">
                <button
                  onClick={() => void handleSend()}
                  disabled={sending || !draft.trim()}
                  className="rounded-xl bg-[#172a49] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(23,42,73,0.18)] disabled:opacity-60"
                >
                  {sending ? '生成中…' : '查询题库并发送'}
                </button>
              </div>
            </div>
          </section>
        </main>

        <aside className="min-h-0 overflow-y-auto border-l border-[#dbe6f4] bg-white p-4">
          <PanelTitle title="数据库上下文" subtitle={`${contextQuestions.length} 道相关题`} />
          <div className="space-y-3">
            {contextQuestions.length === 0 ? (
              <EmptyHint text="发送问题后，这里会显示从数据库检索到的题目。" />
            ) : (
              contextQuestions.map((question) => (
                <QuestionContextCard key={question.question_id} question={question} onAdd={() => addQuestions([question.question_id])} />
              ))
            )}
          </div>

          <div className="mt-6">
            <PanelTitle title="组卷建议" subtitle={`${suggestions.length} 个方案`} />
            <div className="space-y-3">
              {suggestions.length === 0 ? (
                <EmptyHint text="AI 会根据检索题目生成组卷方案。" />
              ) : (
                suggestions.map((suggestion) => (
                  <SuggestionCard
                    key={suggestion.title}
                    suggestion={suggestion}
                    onAdd={() => addQuestions(suggestion.question_ids)}
                  />
                ))
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#dde6f3] bg-[#f7faff] px-4 py-3">
      <div className="text-xs font-semibold text-[#7a8aa3]">{label}</div>
      <div className="mt-1 truncate text-sm font-black text-[#3f506b]">{value}</div>
    </div>
  );
}

function PanelTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-3">
      <div className="text-sm font-black text-[#152238]">{title}</div>
      <div className="mt-0.5 text-xs text-[#7a8aa3]">{subtitle}</div>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[#d6e1ef] bg-[#f8fbff] px-4 py-5 text-sm leading-6 text-[#7a8aa3]">
      {text}
    </div>
  );
}

function QuestionContextCard({
  question,
  onAdd,
}: {
  question: AiAssistantQuestionContext;
  onAdd: () => void;
}) {
  return (
    <div className="rounded-xl border border-[#dbe6f4] bg-[#fbfdff] p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-full bg-[#edf4ff] px-2 py-1 text-xs font-bold text-[#2c75d6]">
          {question.question_id}
        </span>
        <button onClick={onAdd} className="text-xs font-semibold text-[#2c75d6]">
          加入题篮
        </button>
      </div>
      <div className="mt-2 line-clamp-3 text-sm leading-6 text-[#2d3d55]">{question.title || '无题干'}</div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {question.question_type && <Chip>{TYPE_LABELS[question.question_type] || question.question_type}</Chip>}
        {question.difficulty && <Chip>难度 {question.difficulty}</Chip>}
        {question.knowledge_point && <Chip>{question.knowledge_point}</Chip>}
      </div>
    </div>
  );
}

function SuggestionCard({
  suggestion,
  onAdd,
}: {
  suggestion: AiAssistantCompositionSuggestion;
  onAdd: () => void;
}) {
  return (
    <div className="rounded-xl border border-[#dbe6f4] bg-[#fbfdff] p-3">
      <div className="text-sm font-black text-[#152238]">{suggestion.title}</div>
      <p className="mt-2 text-xs leading-6 text-[#687891]">{suggestion.rationale}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Chip>{suggestion.question_ids.length} 题</Chip>
        <Chip>约 {suggestion.estimated_score} 分</Chip>
        {Object.entries(suggestion.difficulty_mix).map(([name, count]) => (
          <Chip key={name}>{name} {count}</Chip>
        ))}
      </div>
      <button onClick={onAdd} className="mt-3 w-full rounded-lg bg-[#2673d9] px-3 py-2 text-xs font-semibold text-white">
        将方案题目加入题篮
      </button>
    </div>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full bg-[#eef4fb] px-2 py-1 text-[11px] font-semibold text-[#60708a]">
      {children}
    </span>
  );
}
