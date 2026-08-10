import { useEffect, useRef, useState } from 'react';
import { Bot, CheckCircle2, LoaderCircle, RefreshCw, Send, Settings2, Sparkles, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import LatexRenderer from '../render/LatexRenderer';
import { fetchAgentConfig, streamQuestionPickerAgent } from '../../services/aiApi';
import type { AgentAction, AiChatMessage, QuestionPickerAgentResponse } from '../../types';

interface Props {
  draftId: string;
  title: string;
  questionIds: string[];
  onBeforeSend: () => Promise<void>;
  onWorkbenchChanged: () => Promise<void>;
  onAddQuestionIds: (questionIds: string[]) => Promise<void>;
  onInsertText: (title: string, content: string) => void;
  onInsertPageBreak: () => void;
  onSetOutputProfile: (profile: 'student' | 'teacher') => void;
  onSetFigureScale: (scale: number) => void;
  onClose: () => void;
}

interface PendingChange {
  id: string;
  label: string;
  detail: string;
  apply: () => void | Promise<void>;
}

const QUICK_PROMPTS = [
  '按当前进度补齐一套 45 分钟测试',
  '检查题型、难度和知识点分布',
  '按题型分节并优化题序',
  '查找类似题替换当前最难的一题',
];

function createSessionId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `compose-agent-${Date.now()}`;
}

export default function ComposeAiPanel({
  draftId,
  title,
  questionIds,
  onBeforeSend,
  onWorkbenchChanged,
  onAddQuestionIds,
  onInsertText,
  onInsertPageBreak,
  onSetOutputProfile,
  onSetFigureScale,
  onClose,
}: Props) {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<AiChatMessage[]>([
    {
      role: 'assistant',
      content: '我已经连到当前试卷。你可以直接说“补 5 道电磁感应题”、“按难度重排”或“检查这套卷”。',
    },
  ]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [agentAvailable, setAgentAvailable] = useState<boolean | null>(null);
  const [statusText, setStatusText] = useState('正在读取 MCP 状态');
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [pendingChanges, setPendingChanges] = useState<PendingChange[]>([]);
  const sessionId = useRef(createSessionId());
  const shouldResume = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const parseLocalCommand = (content: string): PendingChange[] => {
    const normalized = content.trim();
    const changes: PendingChange[] = [];
    const textMatch = normalized.match(/^(?:插入|添加)(?:文本|说明|知识点)[:：]\s*([^\n]+)(?:\n([\s\S]+))?$/);
    if (textMatch) {
      const titleText = textMatch[1].trim();
      const bodyText = (textMatch[2] || titleText).trim();
      changes.push({ id: `text-${Date.now()}`, label: '插入文本块', detail: titleText, apply: () => onInsertText(titleText, bodyText) });
    }
    if (/^(?:插入|添加)(?:分页|分节)$/.test(normalized)) {
      changes.push({ id: `break-${Date.now()}`, label: '插入分页', detail: '在当前选中位置插入分页节点', apply: onInsertPageBreak });
    }
    if (/(?:教师版|教师答案|显示答案)/.test(normalized)) {
      changes.push({ id: `profile-teacher-${Date.now()}`, label: '切换教师版', detail: '显示答案和解析', apply: () => onSetOutputProfile('teacher') });
    } else if (/(?:学生版|隐藏答案|不显示答案)/.test(normalized)) {
      changes.push({ id: `profile-student-${Date.now()}`, label: '切换学生版', detail: '隐藏答案和解析', apply: () => onSetOutputProfile('student') });
    }
    const scaleMatch = normalized.match(/(?:全部|所有).*(?:题图|图片).*(\d{2,3})\s*%/);
    if (scaleMatch) {
      const scale = Math.max(25, Math.min(100, Number(scaleMatch[1])));
      changes.push({ id: `scale-${Date.now()}`, label: '统一题图尺寸', detail: `调整为 ${scale}%`, apply: () => onSetFigureScale(scale) });
    }
    return changes;
  };

  useEffect(() => {
    let active = true;
    void fetchAgentConfig()
      .then((result) => {
        if (!active) return;
        setAgentAvailable(result.available && result.config.enabled);
        setStatusText(result.available && result.config.enabled ? 'MCP 已连接' : result.message || 'AI 协作未启用');
      })
      .catch((reason) => {
        if (!active) return;
        setAgentAvailable(false);
        setStatusText(reason instanceof Error ? reason.message : 'MCP 状态读取失败');
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, statusText]);

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      await onWorkbenchChanged();
      setStatusText('已同步 AI 修改');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '同步失败');
    } finally {
      setSyncing(false);
    }
  };

  const handleSend = async (preset?: string) => {
    const content = (preset ?? draft).trim();
    if (!content || sending) return;

    const userMessage: AiChatMessage = { role: 'user', content };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setDraft('');
    setSending(true);
    setError(null);
    setActions([]);

    const localChanges = parseLocalCommand(content);
    if (localChanges.length > 0) {
      setPendingChanges(localChanges);
      setMessages((current) => [...current, { role: 'assistant', content: '已识别为工作台变更，请确认后应用。' }]);
      setStatusText('等待确认变更');
      setSending(false);
      return;
    }
    setStatusText('先同步当前试卷');

    try {
      await onBeforeSend();
      const finalResponse: { current: QuestionPickerAgentResponse | null } = { current: null };
      const systemMessage: AiChatMessage = {
        role: 'system',
        content: [
          '当前页面是组卷工作台，你是试卷编排协作者。',
          `当前草稿 id：${draftId}`,
          `试卷标题：${title || '未命名试卷'}`,
          `当前题目：${questionIds.length} 道，question_id：${questionIds.join(', ') || '无'}`,
          '需要查题、加题、插入分节、重排或读取草稿时，优先使用 physics_vault MCP 组卷工具。',
          '如果操作需要确认，先 dry_run 给出预览；用户在后续消息确认后再执行。',
          '所有修改只写入组卷草稿，不修改正式题库。',
        ].join('\n'),
      };

      await streamQuestionPickerAgent(
        [...messages.slice(-17), systemMessage, userMessage],
        {
          contextLimit: 16,
          contextQuestionIds: questionIds,
          sessionId: sessionId.current,
          resumeSession: shouldResume.current,
          onEvent: (event) => {
            if (event.type === 'trace' && event.step) setStatusText(event.step.detail || event.step.title);
            if (event.type === 'terminal' && event.message) setStatusText(event.message);
            if ((event.type === 'warning' || event.type === 'error') && event.message) setStatusText(event.message);
            if (event.type === 'response' && event.response) finalResponse.current = event.response;
          },
        },
      );

      if (!finalResponse.current) throw new Error('AI 没有返回最终结果');
      const result = finalResponse.current;
      sessionId.current = result.session_id || sessionId.current;
      shouldResume.current = result.agent_used;
      setMessages((current) => [...current, { role: 'assistant', content: result.reply || '处理完成' }]);
      setActions(result.actions || []);
      setStatusText(result.agent_used ? '已通过 MCP 完成本轮处理' : '本轮未调用 MCP');
      await onWorkbenchChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'AI 处理失败');
      setStatusText('MCP 协作中断');
    } finally {
      setSending(false);
    }
  };

  const applyPendingChanges = async () => {
    setSyncing(true);
    try {
      for (const change of pendingChanges) await change.apply();
      setPendingChanges([]);
      await onWorkbenchChanged();
      setStatusText('已应用 AI 变更');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '应用变更失败');
    } finally {
      setSyncing(false);
    }
  };

  const handleAction = async (action: AgentAction) => {
    if (!action.question_ids.length) return;
    setSyncing(true);
    try {
      await onAddQuestionIds(action.question_ids);
      setActions((current) => current.filter((item) => item.action_id !== action.action_id));
      setStatusText(`已加入 ${action.question_ids.length} 道题`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '题目加入失败');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <aside className="flex w-[360px] shrink-0 flex-col border-l border-[#d7e0eb] bg-white">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-[#e1e7ef] px-3.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[#eaf3ff] text-[#2567b8]">
          <Sparkles size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold text-[#172033]">AI 协作</div>
          <div className="flex items-center gap-1.5 text-[10px] text-[#718096]">
            <span className={`h-1.5 w-1.5 rounded-full ${agentAvailable ? 'bg-[#22a06b]' : agentAvailable === false ? 'bg-[#d14343]' : 'bg-[#94a3b8]'}`} />
            <span className="truncate">{statusText}</span>
          </div>
        </div>
        <button type="button" onClick={() => navigate('/settings/mcp')} className="rounded p-1.5 text-[#718096] hover:bg-[#f1f5f9] hover:text-[#172033]" title="MCP 设置">
          <Settings2 size={15} />
        </button>
        <button type="button" onClick={onClose} className="rounded p-1.5 text-[#718096] hover:bg-[#f1f5f9] hover:text-[#172033]" title="收起 AI">
          <X size={16} />
        </button>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-[#f7f9fc] p-3">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`flex gap-2 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {message.role === 'assistant' && <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white text-[#2567b8] shadow-sm"><Bot size={14} /></span>}
            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-[12px] leading-5 shadow-sm ${message.role === 'user' ? 'bg-[#2567b8] text-white' : 'border border-[#e1e7ef] bg-white text-[#263244]'}`}>
              <LatexRenderer text={message.content} />
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex items-center gap-2 rounded-md border border-[#d8e6f5] bg-white px-3 py-2 text-[11px] text-[#52657a]">
            <LoaderCircle size={14} className="animate-spin text-[#2567b8]" />
            <span className="min-w-0 truncate">{statusText}</span>
          </div>
        )}

        {actions.length > 0 && (
          <div className="space-y-1.5 rounded-md border border-[#cfe1f5] bg-[#f4f9ff] p-2.5">
            <div className="text-[10px] font-semibold text-[#52657a]">AI 建议的可执行操作</div>
            {actions.map((action) => (
              <button key={action.action_id} type="button" onClick={() => void handleAction(action)} disabled={syncing} className="flex w-full items-center gap-2 rounded border border-[#cfe1f5] bg-white px-2.5 py-2 text-left text-[11px] font-semibold text-[#1f5fb8] hover:border-[#7aaee3] disabled:opacity-50">
                <CheckCircle2 size={14} />
                <span className="min-w-0 flex-1">{action.label}</span>
                <span>{action.question_ids.length} 题</span>
              </button>
            ))}
          </div>
        )}

        {pendingChanges.length > 0 && (
          <div className="space-y-2 rounded-md border border-[#f0d49a] bg-[#fffaf0] p-2.5">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-semibold text-[#8a5b00]">变更预览</div>
              <span className="text-[10px] text-[#a87919]">{pendingChanges.length} 项待确认</span>
            </div>
            {pendingChanges.map((change) => (
              <div key={change.id} className="rounded border border-[#f0d49a] bg-white px-2.5 py-2">
                <div className="text-[11px] font-semibold text-[#263244]">{change.label}</div>
                <div className="mt-0.5 text-[10px] text-[#718096]">{change.detail}</div>
              </div>
            ))}
            <div className="flex gap-1.5">
              <button type="button" onClick={() => void applyPendingChanges()} disabled={syncing} className="flex-1 rounded bg-[#2567b8] px-2 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50">应用变更</button>
              <button type="button" onClick={() => setPendingChanges([])} disabled={syncing} className="rounded border border-[#d4deea] bg-white px-2.5 py-1.5 text-[11px] text-[#52657a]">取消</button>
            </div>
          </div>
        )}

        {error && <div className="rounded-md border border-[#f2caca] bg-[#fff5f5] px-3 py-2 text-[11px] leading-5 text-[#b42318]">{error}</div>}
      </div>

      <div className="shrink-0 border-t border-[#e1e7ef] bg-white p-3">
        <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
          {QUICK_PROMPTS.map((prompt) => (
            <button key={prompt} type="button" onClick={() => void handleSend(prompt)} disabled={sending} className="shrink-0 rounded-full border border-[#d8e2ee] bg-white px-2.5 py-1 text-[10px] text-[#52657a] hover:border-[#7aaee3] hover:text-[#1f5fb8] disabled:opacity-50">
              {prompt}
            </button>
          ))}
        </div>
        <div className="rounded-md border border-[#cfd9e6] bg-white p-2 shadow-[0_4px_16px_rgba(15,23,42,0.06)] focus-within:border-[#5294d8]">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            placeholder="说出组卷目标或直接下达修改指令…"
            rows={3}
            className="w-full resize-none bg-transparent text-xs leading-5 text-[#172033] outline-none placeholder:text-[#9aa8b8]"
          />
          <div className="mt-1 flex items-center justify-between">
            <button type="button" onClick={() => void handleSync()} disabled={syncing || sending} className="flex items-center gap-1 rounded px-1.5 py-1 text-[10px] text-[#718096] hover:bg-[#f1f5f9] hover:text-[#172033] disabled:opacity-50" title="从草稿重新同步">
              <RefreshCw size={12} className={syncing ? 'animate-spin' : ''} />
              同步
            </button>
            <button type="button" onClick={() => void handleSend()} disabled={!draft.trim() || sending} className="flex h-7 items-center gap-1.5 rounded-md bg-[#2567b8] px-2.5 text-[11px] font-semibold text-white hover:bg-[#1f5a9f] disabled:cursor-not-allowed disabled:opacity-45">
              {sending ? <LoaderCircle size={13} className="animate-spin" /> : <Send size={13} />}
              发送
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
