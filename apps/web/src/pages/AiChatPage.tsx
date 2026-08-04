import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ClipboardCheck, PanelRightOpen, Paperclip, RotateCcw, Search, Send, Sparkles, Square, X } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import {
  addToBasket,
  fetchAgentConfig,
  streamQuestionPickerAgent,
  submitAiGeneratedReview,
} from '../services/api';
import LatexRenderer from '../components/render/LatexRenderer';
import { useBasket } from '../hooks/useBasket';
import { AI_CONTEXT_CACHE_STORAGE_KEY, readAiContextCache } from '../utils/aiContextCache';
import { useComposeWorkbenchStore } from '../stores/useComposeWorkbenchStore';
import {
  applyComposeCommandsToWorkbench,
  describeComposeCommand,
  parseComposeCommandsFromText,
  stripComposeCommandsFromText,
  type ComposeCommand,
} from '../services/composeCommands';
import type {
  AgentAction,
  AgentTraceStep,
  AiAssistantQuestionContext,
  AiChatMessage,
  ComposeItem,
  QuestionPickerAgentResponse,
} from '../types';

const DEFAULT_QUICK_PROMPTS = [
  '找一道万有引力课堂例题',
  '按牛顿第二定律组一组基础到提高题',
  '闭合电路欧姆定律，给我讲课顺序',
  '选 6 道题做 20 分钟小测',
];

const QUICK_PROMPTS_BY_PAGE: Record<string, string[]> = {
  '/compose': [
    '按由易到难重排，先给我变更预览',
    '为每组题插入简洁的知识目录',
    '补齐这套卷缺少的题型',
    '统一检查并优化题图排版',
  ],
  '/browse': [
    '按当前筛选结果精选 6 道题',
    '找同知识点不同难度的题',
    '检查题篮是否重复或失衡',
    '找一道适合导入课堂的例题',
  ],
  '/review': [
    '检查当前校对任务的公式和缺失字段',
    '列出最需人工复核的题目',
    '检查题干、选项和答案是否自洽',
    '整理本批题的校对摘要',
  ],
};

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选',
  multi_choice: '多选',
  fill: '填空',
  experiment: '实验',
  calculation: '计算',
};

const COMPOSE_QUALITY_PROMPT = '请对当前试卷做一次整卷质量检查。按严重程度检查题型与分值比例、知识点覆盖、难度曲线、预计用时、重复内容、答案和解析完整性、公式渲染以及题图与题干是否匹配。先给出带题号的问题清单和改进建议，不要直接修改试卷。';

interface ComposeSelectionAction {
  label: string;
  prompt: string;
}

const CONVERSATIONS_STORAGE_KEY = 'physics_vault.agent_chat.v4.conversations';
const ACTIVE_CONVERSATION_STORAGE_KEY = 'physics_vault.agent_chat.v4.active';
const OLD_CHAT_MESSAGES_STORAGE_KEY = 'physics_vault.agent_chat.v2.messages';
const OLD_CHAT_TURNS_STORAGE_KEY = 'physics_vault.agent_chat.v2.turns';
const OLD_AGENT_SESSION_STORAGE_KEY = 'physics_vault.agent_chat.v2.session_id';
const CONTEXT_CACHE_STORAGE_KEY = AI_CONTEXT_CACHE_STORAGE_KEY;
const CONVERSATION_COUNT = 3;
const REVIEW_CACHE_PREFIX = 'physics_vault_review_cache.';
const LESSON_PACKAGE_KEY = 'physics-vault.current-lesson-package';

interface LessonPackageSnapshot {
  nodeCount: number;
  questionCount: number;
  knowledgeCount: number;
  title: string;
}

function readLessonPackageSnapshot(): LessonPackageSnapshot {
  try {
    const pkg = JSON.parse(window.localStorage.getItem(LESSON_PACKAGE_KEY) || 'null');
    return {
      nodeCount: Array.isArray(pkg?.nodes) ? pkg.nodes.length : 0,
      questionCount: Array.isArray(pkg?.questions) ? pkg.questions.length : 0,
      knowledgeCount: Array.isArray(pkg?.knowledgeCards) ? pkg.knowledgeCards.length : 0,
      title: String(pkg?.title || ''),
    };
  } catch {
    return { nodeCount: 0, questionCount: 0, knowledgeCount: 0, title: '' };
  }
}

function quickPromptsForPage(pathname: string): string[] {
  if (pathname.startsWith('/review')) return QUICK_PROMPTS_BY_PAGE['/review'];
  return QUICK_PROMPTS_BY_PAGE[pathname] || DEFAULT_QUICK_PROMPTS;
}

function compactText(value: unknown, maxLength = 90): string {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

function composeItemLabel(item: ComposeItem, index: number): string {
  if (item.type === 'question') {
    return `第 ${index + 1} 项 · ${TYPE_LABELS[item.question?.question_type || ''] || '题目'} · ${compactText(item.question?.title || item.questionId, 30)}`;
  }
  if (item.type === 'knowledge') return `第 ${index + 1} 项 · 知识目录 · ${compactText(item.title, 30)}`;
  if (item.type === 'text') return `第 ${index + 1} 项 · 文本 · ${compactText(item.title, 30)}`;
  return `第 ${index + 1} 项 · 分页`;
}

function composeSelectionActions(item: ComposeItem, index: number): ComposeSelectionAction[] {
  const position = `当前选中的第 ${index + 1} 项`;
  if (item.type === 'question') {
    const target = `${position}（题目 ID：${item.questionId}）`;
    const actions: ComposeSelectionAction[] = [
      {
        label: '检查内容',
        prompt: `请只检查${target}。核对题干、选项、答案、解析、知识点和公式是否自洽，先列问题，不要修改。`,
      },
      {
        label: '优化表达',
        prompt: `请只优化${target}的题干和选项表达，不改变考点与正确答案。先列出修改清单并给出可确认的变更预览。`,
      },
      {
        label: '补全解析',
        prompt: `请只为${target}补全或改进解析，给出清晰步骤、关键公式和易错点。先给变更预览。`,
      },
      {
        label: '调整难度',
        prompt: `请结合整卷结构调整${target}的难度，保持原考点，说明调整理由并先给变更预览。`,
      },
    ];
    if ((item.question?.figures || []).length > 0) {
      actions.push({
        label: '优化题图',
        prompt: `请只检查${target}的题图与题干是否匹配，并优化题图尺寸、对齐和图注。先给变更预览。`,
      });
    }
    return actions;
  }
  if (item.type === 'knowledge') {
    const target = `${position}（知识目录 ID：${item.id}，标题：${item.title}）`;
    return [
      { label: '精简内容', prompt: `请精简${target}，保留核心概念、规律和解题步骤，先给变更预览。` },
      { label: '补充要点', prompt: `请检查${target}缺少的关键知识和易错点，补齐后先给变更预览。` },
      { label: '优化结构', prompt: `请把${target}整理为更适合课堂阅读的顺序，先给变更预览。` },
    ];
  }
  if (item.type === 'text') {
    const target = `${position}（文本 ID：${item.id}，标题：${item.title}）`;
    return [
      { label: '润色文本', prompt: `请润色${target}，保持含义准确、语言简洁，先给变更预览。` },
      { label: '检查公式', prompt: `请只检查${target}中的公式语法、单位和符号，列出问题并给出可确认的修正。` },
      { label: '改为课堂说明', prompt: `请将${target}改写为简洁的课堂说明，先给变更预览。` },
    ];
  }
  return [];
}

function hasSuspiciousFormulaMarkers(value: string): boolean {
  const text = value.replace(/\\\$/g, '');
  const dollarCount = (text.match(/\$/g) || []).length;
  return dollarCount % 2 !== 0
    || (text.match(/\\\(/g) || []).length !== (text.match(/\\\)/g) || []).length
    || (text.match(/\\\[/g) || []).length !== (text.match(/\\\]/g) || []).length;
}

function composeQualityDetails(items: ComposeItem[]): string[] {
  const questions = items.flatMap((item) => item.type === 'question' && item.question ? [item.question] : []);
  const typeCounts = questions.reduce<Record<string, number>>((result, question) => {
    const label = TYPE_LABELS[question.question_type] || question.question_type;
    result[label] = (result[label] || 0) + 1;
    return result;
  }, {});
  const missingAnswers = questions.filter((question) => !String(question.answer || '').trim()).length;
  const missingAnalyses = questions.filter((question) => !String(question.analysis || '').trim()).length;
  const formulaWarnings = questions.filter((question) => hasSuspiciousFormulaMarkers([
    question.title,
    ...(question.options || []).map((option) => option.content),
    question.answer,
    question.analysis,
  ].join('\n'))).length;
  const normalizedTitles = questions.map((question) => question.title.replace(/\s+/g, '').trim()).filter(Boolean);
  const duplicateTitles = normalizedTitles.length - new Set(normalizedTitles).size;
  const difficultyValues = questions.map((question) => Number(question.difficulty)).filter(Number.isFinite);
  const averageDifficulty = difficultyValues.length
    ? (difficultyValues.reduce((sum, value) => sum + value, 0) / difficultyValues.length).toFixed(2)
    : '未设置';
  const totalScore = questions.map((question) => Number(question.score)).filter(Number.isFinite).reduce((sum, value) => sum + value, 0);
  return [
    `整卷质量摘要：已读取 ${questions.length} 道完整题目；题型分布 ${Object.entries(typeCounts).map(([type, count]) => `${type}${count}`).join('、') || '暂无'}。`,
    `完整性：缺答案 ${missingAnswers} 道，缺解析 ${missingAnalyses} 道，疑似公式标记异常 ${formulaWarnings} 道，重复题干 ${duplicateTitles} 道。`,
    `难度均值：${averageDifficulty}${totalScore > 0 ? `；当前题目总分 ${totalScore}` : '；题目分值尚未完整设置'}。`,
  ];
}

function composeWorkbenchDetails(
  items: ComposeItem[],
  selectedIndex: number,
  revision: number,
  savedRevision: number,
): string[] {
  const packageSnapshot = readLessonPackageSnapshot();
  const selected = selectedIndex >= 0 ? items[selectedIndex] : null;
  const counts = items.reduce<Record<string, number>>((result, item) => {
    result[item.type] = (result[item.type] || 0) + 1;
    return result;
  }, {});
  const orderedItems = items.slice(0, 40).map((item, index) => {
    if (item.type === 'question') {
      const question = item.question;
      return `${index + 1}. 题目 ${item.questionId}｜${TYPE_LABELS[question?.question_type || ''] || '类型未知'}｜难度 ${question?.difficulty ?? '未设置'}｜${compactText(question?.knowledge_point || '知识点未设置', 28)}｜${compactText(question?.title || '未命名', 72)}｜答案 ${compactText(question?.answer || '未填写', 20)}｜解析${question?.analysis?.trim() ? '已填写' : '缺失'}｜题图 ${question?.figures?.length || 0}`;
    }
    if (item.type === 'knowledge') return `${index + 1}. 知识卡 ${item.id}：${item.title}`;
    if (item.type === 'text') return `${index + 1}. 文本 ${item.id}：${item.title}`;
    return `${index + 1}. 分页 ${item.id}`;
  });
  const details = [
    `组卷工作台实时内容：${items.length} 个节点（题目 ${counts.question || 0}、知识卡 ${counts.knowledge || 0}、文本 ${counts.text || 0}、分页 ${counts.separator || 0}）。`,
    `当前选中：${selected ? `${selectedIndex + 1}. ${selected.type === 'question' ? selected.questionId : selected.title}` : '无'}。`,
    `文档状态：${revision === savedRevision ? '已保存' : '有未保存变更'}，修订 ${revision}。`,
    '当前顺序：',
    ...(orderedItems.length ? orderedItems : ['（空试卷）']),
    ...composeQualityDetails(items),
  ];
  if (selected?.type === 'question' && selected.question) {
    details.push(
      `当前选中题目完整信息：题干=${compactText(selected.question.title, 600)}`,
      `选项=${(selected.question.options || []).map((option) => `${option.opt}.${compactText(option.content, 180)}`).join('；') || '无'}`,
      `答案=${compactText(selected.question.answer, 200)}；解析=${compactText(selected.question.analysis, 800)}`,
      `知识点=${compactText(selected.question.knowledge_point, 120)}；难度=${selected.question.difficulty}；题图=${(selected.question.figures || []).map((figure) => `${figure.fig_uuid}(${figure.display_scale || 100}%,${figure.display_align || 'center'},${figure.caption || '无图注'})`).join('；') || '无'}`,
    );
  } else if (selected?.type === 'knowledge') {
    details.push(`当前选中知识目录完整信息：标题=${selected.title}；摘要=${compactText(selected.summary, 600)}；要点=${selected.points.map((point) => compactText(point, 220)).join('；')}`);
  } else if (selected?.type === 'text') {
    details.push(`当前选中文本完整信息：标题=${selected.title}；正文=${compactText(selected.content, 900)}`);
  }
  if (packageSnapshot.nodeCount > items.length) {
    details.unshift(
      `当前教学包缓存更完整：${packageSnapshot.nodeCount} 个编排节点，${packageSnapshot.questionCount} 道题，${packageSnapshot.knowledgeCount} 个知识目录。`,
      '当实时状态与教学包缓存数量不一致时，先用 MCP 回读当前组卷草稿，不要仅依赖下方节点列表。',
    );
  }
  return details;
}

const PAGE_CONTEXTS: Array<{
  match: (pathname: string) => boolean;
  title: string;
  intent: string;
  guidance: string;
}> = [
  {
    match: (pathname) => pathname === '/' || pathname === '/dashboard',
    title: '平台总览',
    intent: '查看题库、导入、组卷、校对等模块入口和整体状态。',
    guidance: '回答时先判断老师是在做全局规划还是想跳转到某个工作区。',
  },
  {
    match: (pathname) => pathname === '/browse',
    title: '题库浏览',
    intent: '检索正式题库、筛选题目、打回校对、加入题篮。',
    guidance: '如果用户说“这页/当前题库/这些筛选结果”，应围绕正式题库检索和题篮动作回答。',
  },
  {
    match: (pathname) => pathname === '/import',
    title: '导入识别',
    intent: '把文档、图片或批量文本解析成待校对草稿。',
    guidance: '如果用户问“这批材料/导入结果/送入校对”，应围绕导入流水线和校对任务回答。',
  },
  {
    match: (pathname) => pathname === '/review',
    title: '校对中心队列',
    intent: '查看所有可打开的校对任务，进入具体任务后逐题校对。',
    guidance: '如果用户问“校对中心有什么”，应先读取校对任务列表和 review_queue，而不是查正式题库。',
  },
  {
    match: (pathname) => pathname === '/compose',
    title: '组卷工作台',
    intent: '整理题篮、调整题序、插入知识目录和文本块，生成教学包。',
    guidance: '如果用户说“当前组卷/这套题/讲义结构”，应结合题篮和当前教学包回答。',
  },
  {
    match: (pathname) => pathname === '/handout',
    title: '讲义预览',
    intent: '预览并调整当前教学包生成的讲义。',
    guidance: '如果用户问排版、讲义顺序或内容缺失，应围绕当前教学包回答。',
  },
  {
    match: (pathname) => pathname === '/slides',
    title: '课件预览',
    intent: '预览当前教学包生成的课件。',
    guidance: '如果用户问课件页、讲课节奏或转成 PPT，应围绕当前教学包回答。',
  },
  {
    match: (pathname) => pathname === '/classroom',
    title: '课堂授课',
    intent: '以课堂展示方式使用当前教学包。',
    guidance: '如果用户问课堂节奏、互动提问或板书顺序，应围绕授课流程回答。',
  },
  {
    match: (pathname) => pathname === '/templates',
    title: '模板管理',
    intent: '管理讲义、课件或教学包模板。',
    guidance: '如果用户问模板，应先区分是保存当前模板还是套用已有模板。',
  },
  {
    match: (pathname) => pathname === '/assets-manager',
    title: '素材管理',
    intent: '管理题图、导入图片和素材引用。',
    guidance: '如果用户问图片、素材、未被引用，应围绕素材库和题目引用关系回答。',
  },
  {
    match: (pathname) => pathname === '/collections',
    title: '目录管理',
    intent: '管理知识目录、集合和分类口径。',
    guidance: '如果用户问知识点或目录，应优先围绕知识目录，而不是把知识点当普通标签。',
  },
  {
    match: (pathname) => pathname === '/task-logs',
    title: '任务日志',
    intent: '查看后端处理任务、导入任务和失败记录。',
    guidance: '如果用户问卡在哪里、失败在哪里，应围绕任务日志和最近错误定位。',
  },
  {
    match: (pathname) => pathname === '/settings',
    title: '系统设置',
    intent: '配置本地路径、数据库和基础选项。',
    guidance: '如果用户问配置，应区分前端设置、后端配置和本地文件路径。',
  },
  {
    match: (pathname) => pathname === '/settings/mcp',
    title: 'MCP 配置',
    intent: '配置 AI、MCP 网关、Claude Code 和模型连接。',
    guidance: '如果用户问 MCP 能力或连接，应围绕 MCP 状态、工具权限和 Claude Code 配置回答。',
  },
];

const DEFAULT_MESSAGES: AiChatMessage[] = [
  {
    role: 'assistant',
    content: '我在。说一个知识点、题型或课堂目标，我会先检索题库，再让本地 Claude Code 给出可执行的选题建议。',
  },
];

type SideTab = 'activity' | 'terminal' | 'context';

interface AgentSessionState {
  id: string;
  shouldResume: boolean;
}

interface AgentConversationTurn {
  id: string;
  sessionId: string;
  userContent: string;
  reply: string;
  queryUsed: string;
  agentName: string;
  agentUsed: boolean;
  selectedQuestions: AiAssistantQuestionContext[];
  actions: AgentAction[];
  warnings: string[];
  trace: AgentTraceStep[];
  terminalLines: string[];
  rawAgentText?: string | null;
  createdAt: string;
}

interface AgentConversation {
  id: string;
  title: string;
  messages: AiChatMessage[];
  turns: AgentConversationTurn[];
  agentSession: AgentSessionState;
  draft: string;
  query: string;
  markedDocument: string | null;
  contextQuestions: AiAssistantQuestionContext[];
  actions: AgentAction[];
  sending: boolean;
  error: string | null;
  lastAgent: string | null;
  aiUsed: boolean;
  warnings: string[];
  liveTrace: AgentTraceStep[];
  liveTerminal: string[];
  reviewingMessageIndex: number | null;
  reviewingArtifactId: string | null;
  lastFailedPrompt: string | null;
  appliedComposeMessageIndexes: number[];
}

interface AiArtifact {
  id: string;
  type: 'question' | 'knowledge' | 'analysis' | 'variant';
  title: string;
  content: string;
  summary: string;
}

function createAgentSessionId(): string {
  return crypto.randomUUID();
}

function createConversation(index: number, seed?: Partial<AgentConversation>): AgentConversation {
  return {
    id: seed?.id || `conversation_${crypto.randomUUID()}`,
    title: seed?.title || `对话 ${index + 1}`,
    messages: seed?.messages?.length ? seed.messages : DEFAULT_MESSAGES,
    turns: seed?.turns || [],
    agentSession: seed?.agentSession || { id: createAgentSessionId(), shouldResume: false },
    draft: seed?.draft || '',
    query: seed?.query || '',
    markedDocument: seed?.markedDocument || null,
    contextQuestions: seed?.contextQuestions || [],
    actions: seed?.actions || [],
    sending: false,
    error: null,
    lastAgent: seed?.lastAgent || null,
    aiUsed: seed?.aiUsed || false,
    warnings: [],
    liveTrace: seed?.liveTrace || [],
    liveTerminal: seed?.liveTerminal || [],
    reviewingMessageIndex: null,
    reviewingArtifactId: null,
    lastFailedPrompt: seed?.lastFailedPrompt || null,
    appliedComposeMessageIndexes: seed?.appliedComposeMessageIndexes || [],
  };
}

function readStoredConversations(): AgentConversation[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(CONVERSATIONS_STORAGE_KEY) || 'null');
    if (Array.isArray(parsed) && parsed.length > 0) {
      return Array.from({ length: CONVERSATION_COUNT }, (_, index) =>
        createConversation(index, parsed[index]),
      );
    }
  } catch {
    // Fall through to migration from the previous single-chat cache.
  }

  const legacyMessages = readLegacyMessages();
  const legacyTurns = readLegacyTurns();
  const legacySession = readLegacySession();
  return Array.from({ length: CONVERSATION_COUNT }, (_, index) =>
    createConversation(
      index,
      index === 0
        ? {
            messages: legacyMessages,
            turns: legacyTurns,
            agentSession: legacySession,
            title: '主对话',
          }
        : undefined,
    ),
  );
}

function readLegacyMessages(): AiChatMessage[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(OLD_CHAT_MESSAGES_STORAGE_KEY) || 'null');
    if (!Array.isArray(parsed) || parsed.length === 0) return DEFAULT_MESSAGES;
    return parsed.filter(
      (item) =>
        item &&
        typeof item.content === 'string' &&
        ['system', 'user', 'assistant'].includes(item.role),
    );
  } catch {
    return DEFAULT_MESSAGES;
  }
}

function readLegacyTurns(): AgentConversationTurn[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(OLD_CHAT_TURNS_STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function readLegacySession(): AgentSessionState {
  try {
    const stored = localStorage.getItem(OLD_AGENT_SESSION_STORAGE_KEY);
    if (stored) return { id: stored, shouldResume: true };
  } catch {
    // A fresh session still works if storage is unavailable.
  }
  return { id: createAgentSessionId(), shouldResume: false };
}

function readContextCache(): AiAssistantQuestionContext[] {
  return readAiContextCache();
}

function buildPageContextMessage(
  pathname: string,
  search: string,
  basketCount: number,
  liveComposeDetails: string[] = [],
): AiChatMessage {
  const reviewMatch = pathname.match(/^\/review\/([^/]+)/);
  if (!reviewMatch) {
    const page = PAGE_CONTEXTS.find((item) => item.match(pathname));
    const details = [
      `当前页面：${page?.title || '未知页面'} ${pathname}${search || ''}`,
      `页面用途：${page?.intent || '当前路由暂未登记具体用途。'}`,
      `回答提示：${page?.guidance || '先根据当前页面判断用户说的“这里、当前、这批、这套”指什么，不确定时要说明不确定。'}`,
    ];

    if (pathname === '/browse') {
      details.push(...buildBrowsePageDetails(search, basketCount));
    } else if (['/compose', '/handout', '/slides', '/classroom'].includes(pathname)) {
      details.push(...buildLessonPackageDetails(basketCount));
      if (pathname === '/compose') {
        details.push(...liveComposeDetails);
        details.push('当用户要求修改当前组卷文档时，请先说明修改方案，并在回复末尾输出一个 JSON 代码块：{"composeCommands":[...] }。可用命令类型为 insert_text、insert_knowledge、insert_page_break、remove_node、duplicate_node、move_node、move_node_after、update_question、update_text、update_knowledge、update_figure、set_all_figures。update_figure 可设置 displayScale、displayAlign、caption；set_all_figures 可统一图片尺寸和对齐。题图比例使用 25 到 100 的整数。所有命令会先展示变更清单，由用户确认后执行；不要输出 JavaScript。');
      }
    } else if (pathname === '/review') {
      details.push('如果用户问“当前校对任务”，当前只是队列页，没有打开具体 task_id；应先列出可打开任务。');
    } else if (pathname === '/assets-manager') {
      details.push('如果用户问“未被引用图片”，应查看素材引用关系或调用相关后端接口，不要只看文件名猜。');
    } else if (pathname === '/collections') {
      details.push('知识点应以知识目录为准；标签只做横向检索，不要把两者混为一谈。');
    }

    return {
      role: 'system',
      content: details.join('\n'),
    };
  }

  const taskId = decodeURIComponent(reviewMatch[1] || '').trim();
  if (!taskId) {
    return {
      role: 'system',
      content: `当前页面：校对中心任务页 ${pathname}，但 URL 里没有读到有效 task_id。`,
    };
  }

  const details = [
    `当前页面：校对中心任务页 /review/${taskId}`,
    `当前校对任务 task_id：${taskId}`,
    '如果用户问“校对中心的题目、当前待校对题、清洗这批题”，应优先读取这个 task_id 对应的任务内容。',
    '不要仅凭 list_review_tasks 的全局列表结果判断当前任务为空；当前任务已经在页面打开。',
    `建议优先调用 get_review_task("${taskId}")，必要时再用 list_review_tasks 或 list_review_queue 交叉检查。`,
  ];

  const cache = readReviewPageCache(taskId);
  if (cache) {
    details.push(...cache);
  }

  return {
    role: 'system',
    content: details.join('\n'),
  };
}

function buildBrowsePageDetails(search: string, basketCount: number): string[] {
  const params = new URLSearchParams(search);
  const entries = Array.from(params.entries()).filter(([, value]) => value);
  return [
    `当前题篮数量：${basketCount} 道。`,
    entries.length
      ? `当前 URL 筛选参数：${entries.map(([key, value]) => `${key}=${value}`).join('，')}`
      : '当前 URL 没有显式筛选参数；若用户说“当前筛选结果”，需要通过题库检索状态或重新询问确认。',
    '如果用户问“这些题/当前题库页”，优先使用正式题库检索工具；如果问“打回/回炉”，再用校对相关工具。',
  ];
}

function buildLessonPackageDetails(basketCount: number): string[] {
  const details = [`当前题篮数量：${basketCount} 道。`];
  try {
    const pkg = JSON.parse(localStorage.getItem(LESSON_PACKAGE_KEY) || 'null');
    if (!pkg || typeof pkg !== 'object') {
      details.push('当前没有读到本地教学包缓存。');
      return details;
    }
    const questions = Array.isArray(pkg.questions) ? pkg.questions : [];
    const knowledgeCards = Array.isArray(pkg.knowledgeCards) ? pkg.knowledgeCards : [];
    const nodes = Array.isArray(pkg.nodes) ? pkg.nodes : [];
    details.push(
      `当前教学包：${String(pkg.title || '未命名教学包')}`,
      `教学包内容：${questions.length} 道题，${knowledgeCards.length} 个知识目录块，${nodes.length} 个编排节点。`,
    );
  } catch {
    details.push('当前教学包缓存读取失败。');
  }
  return details;
}

function readReviewPageCache(taskId: string): string[] | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(`${REVIEW_CACHE_PREFIX}${taskId}`) || 'null');
    if (!parsed || parsed.taskId !== taskId || !Array.isArray(parsed.drafts)) return null;
    const drafts = parsed.drafts as Array<Record<string, unknown>>;
    const currentIndex = Number(parsed.currentIndex || 0);
    const current = drafts[Math.min(Math.max(currentIndex, 0), Math.max(drafts.length - 1, 0))];
    const statusCounts = drafts.reduce<Record<string, number>>((acc, draft) => {
      const status = String(draft.status || 'pending');
      acc[status] = (acc[status] || 0) + 1;
      return acc;
    }, {});
    const riskCount = drafts.filter((draft) => {
      const knowledge = String(draft.knowledge_point || draft.knowledge_points || '').trim();
      const title = String(draft.title || '').trim();
      const answer = String(draft.answer || '').trim();
      return !knowledge || !title || !answer;
    }).length;
    const details = [
      `页面本地校对缓存：共有 ${drafts.length} 道草稿题，当前第 ${Math.min(currentIndex + 1, drafts.length)} 题。`,
      `状态分布：${Object.entries(statusCounts).map(([key, value]) => `${key} ${value}`).join('，') || '无'}`,
      `疑似需补齐基础字段的草稿：${riskCount} 道。`,
    ];
    if (current) {
      details.push(
        `当前题摘要：${String(current.question_id || current.id || '')} ${String(current.title || '').slice(0, 120)}`,
        `当前题状态：${String(current.status || 'pending')}；知识点：${String(current.knowledge_point || current.knowledge_points || '未标注')}`,
      );
    }
    return details;
  } catch {
    return null;
  }
}

function mergeQuestionContexts(
  first: AiAssistantQuestionContext[],
  second: AiAssistantQuestionContext[],
): AiAssistantQuestionContext[] {
  const merged: AiAssistantQuestionContext[] = [];
  const seen = new Set<string>();
  for (const item of [...first, ...second]) {
    if (!item.question_id || seen.has(item.question_id)) continue;
    seen.add(item.question_id);
    merged.push(item);
  }
  return merged;
}

function isUserFacingWarning(message: string): boolean {
  return !message.includes('输出已自动整理');
}

function extractAiArtifacts(text: string): AiArtifact[] {
  const source = text.trim();
  if (source.length < 80) return [];
  if (isOperationalAssistantReply(source)) return [];

  const jsonArtifacts = extractJsonArtifacts(source);
  if (jsonArtifacts.length > 0) return jsonArtifacts.slice(0, 6);

  const sectionArtifacts = splitStructuredSections(source);
  if (sectionArtifacts.length > 0) return sectionArtifacts.slice(0, 6);

  const type = inferArtifactType(source);
  if (!type) return [];
  return [
    {
      id: artifactId(type, source, 0),
      type,
      title: inferArtifactTitle(source, type, 0),
      content: source,
      summary: summarizeArtifact(source),
    },
  ];
}

function extractJsonArtifacts(source: string): AiArtifact[] {
  const blocks: string[] = [];
  for (const match of source.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)) {
    blocks.push(match[1].trim());
  }
  if (source.trimStart().startsWith('[') || source.trimStart().startsWith('{')) {
    blocks.push(source);
  }

  const artifacts: AiArtifact[] = [];
  for (const block of blocks) {
    try {
      const parsed = JSON.parse(block);
      const items = Array.isArray(parsed) ? parsed : [parsed];
      items.forEach((item, index) => {
        if (!item || typeof item !== 'object') return;
        const content = JSON.stringify(item, null, 2);
        const type = inferArtifactType(content);
        if (!type) return;
        const title =
          String((item as Record<string, unknown>).title || (item as Record<string, unknown>).name || '').trim() ||
          inferArtifactTitle(content, type, index);
        artifacts.push({
          id: artifactId(type, content, index),
          type,
          title,
          content,
          summary: summarizeArtifact(content),
        });
      });
    } catch {
      // Non-JSON code blocks are kept as normal chat text.
    }
  }
  return dedupeArtifacts(artifacts);
}

function splitStructuredSections(source: string): AiArtifact[] {
  const matches = Array.from(
    source.matchAll(
      /(^|\n)(#{2,4}\s*)?((?:题目|试题|变式|知识点|解析)(?:\s*[一二三四五六七八九十\d]+)?)[：:、.\s]/g,
    ),
  );
  if (matches.length < 2) return [];

  const artifacts: AiArtifact[] = [];
  matches.forEach((match, index) => {
    const start = (match.index || 0) + match[1].length;
    const end = index + 1 < matches.length ? matches[index + 1].index || source.length : source.length;
    const content = source.slice(start, end).trim();
    const type = inferArtifactType(content);
    if (!type || content.length < 60) return;
    artifacts.push({
      id: artifactId(type, content, index),
      type,
      title: inferArtifactTitle(content, type, index),
      content,
      summary: summarizeArtifact(content),
    });
  });
  return dedupeArtifacts(artifacts);
}

function inferArtifactType(text: string): AiArtifact['type'] | null {
  const normalized = text.toLowerCase();
  const hasQuestionShape =
    /题干|答案|解析|选项|难度|q_type|question_body|answer|analysis/.test(normalized) &&
    /题|question|选项|答案|解析/.test(normalized);
  if (hasQuestionShape) return /变式|拓展|variant/.test(normalized) ? 'variant' : 'question';
  if (/定义|核心公式|易错点|key_summary|definition|formula|error_prone/.test(normalized)) return 'knowledge';
  if (/解析|解法|思路|易错点|analysis/.test(normalized) && normalized.length > 120) return 'analysis';
  return null;
}

function isOperationalAssistantReply(text: string): boolean {
  const normalized = text.toLowerCase();
  const operationalSignals = [
    'claude code',
    '调用失败',
    '没跑完',
    '当前任务',
    '当前页面',
    '校对中心',
    'list_review',
    'get_review_task',
    'review_queue',
    'task_id',
    'trace',
    '能读',
    '不是空的',
    'demo',
  ];
  return operationalSignals.some((signal) => normalized.includes(signal.toLowerCase()));
}

function inferArtifactTitle(text: string, type: AiArtifact['type'], index: number): string {
  const firstLine = text
    .split('\n')
    .map((line) => line.replace(/^#+\s*/, '').trim())
    .find(Boolean);
  if (firstLine && firstLine.length <= 40) return firstLine;
  return `${artifactTypeLabel(type)} ${index + 1}`;
}

function summarizeArtifact(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/[#>*_\-`]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180);
}

function artifactTypeLabel(type: AiArtifact['type']): string {
  const labels: Record<AiArtifact['type'], string> = {
    question: '试题',
    knowledge: '知识点',
    analysis: '解析',
    variant: '变式',
  };
  return labels[type];
}

function artifactId(type: AiArtifact['type'], content: string, index: number): string {
  let hash = 0;
  for (let i = 0; i < content.length; i += 1) {
    hash = (hash * 31 + content.charCodeAt(i)) >>> 0;
  }
  return `${type}_${index}_${hash.toString(16)}`;
}

function dedupeArtifacts(artifacts: AiArtifact[]): AiArtifact[] {
  const seen = new Set<string>();
  return artifacts.filter((artifact) => {
    const key = `${artifact.type}:${artifact.content}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export default function AiChatPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const basket = useBasket();
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const documentRef = useRef<HTMLInputElement | null>(null);
  const abortControllersRef = useRef(new Map<string, AbortController>());
  const [conversations, setConversations] = useState<AgentConversation[]>(() => readStoredConversations());
  const [activeConversationId, setActiveConversationId] = useState(() => {
    try {
      return localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY) || '';
    } catch {
      return '';
    }
  });
  const [contextCache, setContextCache] = useState<AiAssistantQuestionContext[]>(() => readContextCache());
  const [agentAvailable, setAgentAvailable] = useState(false);
  const [agentMessage, setAgentMessage] = useState('');
  const [sideTab, setSideTab] = useState<SideTab>('activity');
  const [sidePanelOpen, setSidePanelOpen] = useState(false);
  const [lessonPackageSnapshot, setLessonPackageSnapshot] = useState(readLessonPackageSnapshot);
  const composeItems = useComposeWorkbenchStore((state) => state.items);
  const composeSelectedIndex = useComposeWorkbenchStore((state) => state.selectedIndex);
  const composeRevision = useComposeWorkbenchStore((state) => state.revision);
  const composeSavedRevision = useComposeWorkbenchStore((state) => state.savedRevision);
  const canUndoCompose = useComposeWorkbenchStore((state) => state.past.length > 0);
  const undoCompose = useComposeWorkbenchStore((state) => state.undo);

  const activeConversation = useMemo(
    () => conversations.find((item) => item.id === activeConversationId) || conversations[0],
    [activeConversationId, conversations],
  );
  const latestTurn = activeConversation?.turns[0] ?? null;
  const visibleTrace = activeConversation?.sending ? activeConversation.liveTrace : latestTurn?.trace ?? [];
  const visibleTerminal = activeConversation?.sending
    ? activeConversation.liveTerminal
    : latestTurn?.terminalLines ?? [];
  const visibleContextQuestions = mergeQuestionContexts(contextCache, activeConversation?.contextQuestions || []);
  const cachedQuestionIds = contextCache.map((question) => question.question_id);
  const basketIds = new Set(basket.items.map((item) => item.question_id));
  const pageContext = PAGE_CONTEXTS.find((item) => item.match(location.pathname));
  const quickPrompts = quickPromptsForPage(location.pathname);
  const liveComposeDetails = location.pathname === '/compose'
    ? composeWorkbenchDetails(composeItems, composeSelectedIndex, composeRevision, composeSavedRevision)
    : [];
  const visibleComposeCount = Math.max(composeItems.length, lessonPackageSnapshot.nodeCount);
  const selectedComposeItem = composeSelectedIndex >= 0 ? composeItems[composeSelectedIndex] : null;
  const selectionActions = selectedComposeItem
    ? composeSelectionActions(selectedComposeItem, composeSelectedIndex)
    : [];

  useEffect(() => {
    if (!activeConversationId && conversations[0]) {
      setActiveConversationId(conversations[0].id);
    }
  }, [activeConversationId, conversations]);

  useEffect(() => {
    const serializable = conversations.map((conversation) => ({
      ...conversation,
      sending: false,
      error: null,
      warnings: conversation.warnings.slice(-3),
      liveTrace: conversation.liveTrace.slice(-20),
      liveTerminal: conversation.liveTerminal.slice(-200),
      reviewingMessageIndex: null,
      reviewingArtifactId: null,
      messages: conversation.messages.slice(-50),
      turns: conversation.turns.slice(0, 24),
    }));
    localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(serializable));
  }, [conversations]);

  useEffect(() => {
    if (activeConversationId) {
      localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, activeConversationId);
    }
  }, [activeConversationId]);

  useEffect(() => {
    if (location.pathname !== '/compose') return;
    const refresh = () => {
      const next = readLessonPackageSnapshot();
      setLessonPackageSnapshot((current) => (
        current.nodeCount === next.nodeCount
        && current.questionCount === next.questionCount
        && current.knowledgeCount === next.knowledgeCount
        && current.title === next.title
          ? current
          : next
      ));
    };
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => window.clearInterval(timer);
  }, [location.pathname]);

  useEffect(() => {
    localStorage.setItem(CONTEXT_CACHE_STORAGE_KEY, JSON.stringify(contextCache.slice(0, 30)));
  }, [contextCache]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ block: 'end' });
  }, [
    activeConversation?.id,
    activeConversation?.messages.length,
    activeConversation?.sending,
    activeConversation?.liveTrace.length,
    activeConversation?.liveTerminal.length,
  ]);

  useEffect(() => {
    let mounted = true;
    fetchAgentConfig()
      .then((result) => {
        if (!mounted) return;
        setAgentAvailable(result.available && result.config.enabled);
        setAgentMessage(result.message);
      })
      .catch((err) => {
        if (!mounted) return;
        setAgentAvailable(false);
        setAgentMessage(err instanceof Error ? err.message : '智能体状态读取失败');
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => () => {
    abortControllersRef.current.forEach((controller) => controller.abort());
    abortControllersRef.current.clear();
  }, []);

  const updateConversation = (
    conversationId: string,
    updater: (conversation: AgentConversation) => AgentConversation,
  ) => {
    setConversations((prev) =>
      prev.map((conversation) => (conversation.id === conversationId ? updater(conversation) : conversation)),
    );
  };

  const setConversationWarning = (conversationId: string, message: string) => {
    updateConversation(conversationId, (conversation) => ({ ...conversation, warnings: [message] }));
  };

  const handleSend = async (conversationId: string, preset?: string) => {
    const conversation = conversations.find((item) => item.id === conversationId);
    if (!conversation || conversation.sending) return;
    const content = (preset ?? conversation.draft).trim();
    if (!content) return;

    const userMessage: AiChatMessage = { role: 'user', content };
    const nextMessages: AiChatMessage[] = [...conversation.messages, userMessage];
    const pageContextMessage = buildPageContextMessage(
      location.pathname,
      location.search,
      basket.items.length,
      liveComposeDetails,
    );
    if (conversation.markedDocument) {
      pageContextMessage.content += `\n当前标记文档：${conversation.markedDocument}`;
    }
    const agentMessages: AiChatMessage[] = [
      ...conversation.messages.slice(-28),
      pageContextMessage,
      userMessage,
    ];
    const traceBuffer: AgentTraceStep[] = [];
    const terminalBuffer: string[] = [];
    const warningBuffer: string[] = [];
    const finalResponseRef: { current: QuestionPickerAgentResponse | null } = { current: null };
    const controller = new AbortController();
    abortControllersRef.current.set(conversationId, controller);

    updateConversation(conversationId, (item) => ({
      ...item,
      messages: nextMessages,
      draft: '',
      sending: true,
      error: null,
      warnings: [],
      liveTrace: [],
      liveTerminal: [],
      lastFailedPrompt: null,
    }));
    setSideTab('activity');

    try {
      await streamQuestionPickerAgent(agentMessages, {
        query: conversation.query.trim() || undefined,
        contextLimit: 12,
        contextQuestionIds: cachedQuestionIds,
        sessionId: conversation.agentSession.id,
        resumeSession: conversation.agentSession.shouldResume,
        signal: controller.signal,
        onEvent: (event) => {
          if (event.type === 'trace' && event.step) {
            traceBuffer.push(event.step);
            updateConversation(conversationId, (item) => ({ ...item, liveTrace: [...traceBuffer] }));
          }
          if (event.type === 'terminal' && event.message) {
            terminalBuffer.push(event.message);
            updateConversation(conversationId, (item) => ({ ...item, liveTerminal: [...terminalBuffer] }));
          }
          if ((event.type === 'warning' || event.type === 'error') && event.message) {
            warningBuffer.push(event.message);
            updateConversation(conversationId, (item) => ({
              ...item,
              warnings: warningBuffer.filter(isUserFacingWarning),
            }));
          }
          if (event.type === 'response' && event.response) {
            finalResponseRef.current = event.response;
          }
        },
      });

      if (!finalResponseRef.current) {
        throw new Error('智能体没有返回最终结果');
      }

      const result = finalResponseRef.current;
      const reply = result.reply || '(没有返回内容)';
      const terminalLines = terminalBuffer.length
        ? terminalBuffer
        : result.raw_agent_text
          ? result.raw_agent_text.split('\n').filter(Boolean)
          : [];
      const turn: AgentConversationTurn = {
        id: `turn_${Date.now()}`,
        sessionId: result.session_id || conversation.agentSession.id,
        userContent: content,
        reply,
        queryUsed: result.query_used,
        agentName: result.agent_name,
        agentUsed: result.agent_used,
        selectedQuestions: result.selected_questions || [],
        actions: result.actions || [],
        warnings: result.warnings || warningBuffer,
        trace: result.trace?.length ? result.trace : traceBuffer,
        terminalLines,
        rawAgentText: result.raw_agent_text || null,
        createdAt: new Date().toISOString(),
      };

      updateConversation(conversationId, (item) => ({
        ...item,
        messages: [...nextMessages, { role: 'assistant', content: reply }],
        turns: [turn, ...item.turns].slice(0, 24),
        contextQuestions: result.selected_questions || [],
        actions: result.actions || [],
        lastAgent: result.agent_name,
        aiUsed: result.agent_used,
        agentSession: result.agent_used
          ? {
              id: result.session_id || item.agentSession.id,
              shouldResume: true,
            }
          : item.agentSession,
        warnings: (result.warnings || warningBuffer).filter(isUserFacingWarning),
        liveTrace: turn.trace,
        liveTerminal: turn.terminalLines,
        query: !item.query.trim() && result.query_used ? result.query_used : item.query,
      }));
      setContextCache((prev) => mergeQuestionContexts(prev, result.selected_questions || []).slice(0, 30));
    } catch (err) {
      const stopped = err instanceof Error && err.name === 'AbortError';
      updateConversation(conversationId, (item) => ({
        ...item,
        error: stopped ? null : err instanceof Error ? err.message : '发送失败',
        warnings: stopped ? ['已停止本轮任务，对话内容已保留。'] : item.warnings,
        lastFailedPrompt: stopped ? null : content,
      }));
    } finally {
      abortControllersRef.current.delete(conversationId);
      updateConversation(conversationId, (item) => ({ ...item, sending: false }));
      if (window.location.pathname === '/ai-chat') {
        inputRef.current?.focus();
      }
    }
  };

  const stopConversation = (conversationId: string) => {
    abortControllersRef.current.get(conversationId)?.abort();
  };

  const clearConversation = (conversationId: string) => {
    updateConversation(conversationId, (item) => ({
      ...createConversation(conversations.findIndex((conversation) => conversation.id === conversationId), {
        id: item.id,
        title: item.title,
      }),
    }));
  };

  const runAction = (action: AgentAction, conversationId: string) => {
    if (action.type === 'add_to_basket') {
      action.question_ids.forEach(addToBasket);
      setConversationWarning(conversationId, `已加入题篮：${action.question_ids.length} 道题`);
      return;
    }
    if (action.type === 'open_questions' && action.question_ids[0]) {
      navigate(`/question/${encodeURIComponent(action.question_ids[0])}`);
      return;
    }
    if (action.type === 'create_paper_draft') {
      action.question_ids.forEach(addToBasket);
      navigate('/compose');
    }
  };

  const runComposeCommands = (commands: ComposeCommand[], conversationId: string, messageIndex: number) => {
    const conversation = conversations.find((item) => item.id === conversationId);
    if (conversation?.appliedComposeMessageIndexes.includes(messageIndex)) return;
    const applied = applyComposeCommandsToWorkbench(commands);
    if (applied > 0) {
      updateConversation(conversationId, (item) => ({
        ...item,
        appliedComposeMessageIndexes: [...new Set([...item.appliedComposeMessageIndexes, messageIndex])],
      }));
    }
    setConversationWarning(
      conversationId,
      applied > 0 ? `已应用 ${applied} 项文档修改，可随时撤销` : '没有可应用的文档修改',
    );
  };

  const undoComposeCommands = (conversationId: string, messageIndex: number) => {
    undoCompose();
    updateConversation(conversationId, (item) => ({
      ...item,
      appliedComposeMessageIndexes: item.appliedComposeMessageIndexes.filter((index) => index !== messageIndex),
    }));
    setConversationWarning(conversationId, '已撤销这次 AI 文档修改');
  };

  const sendMessageToReview = async (
    conversationId: string,
    message: AiChatMessage,
    index: number,
  ) => {
    const conversation = conversations.find((item) => item.id === conversationId);
    if (!conversation || conversation.reviewingMessageIndex !== null) return;
    updateConversation(conversationId, (item) => ({ ...item, reviewingMessageIndex: index, error: null }));
    try {
      const chatContext = conversation.messages
        .slice(Math.max(0, index - 6), index + 1)
        .map((item) => `${item.role === 'user' ? '用户' : 'AI'}：${item.content}`)
        .join('\n\n');
      const result = await submitAiGeneratedReview({
        source_text: message.content,
        source: `AI 题库助手 · ${conversation.title}`,
        chat_context: chatContext,
        session_id: conversation.agentSession.id,
      });
      setConversationWarning(conversationId, `已送入审核：${result.question_count} 道题`);
      navigate(`/review/${result.task_id}`);
    } catch (err) {
      updateConversation(conversationId, (item) => ({
        ...item,
        error: err instanceof Error ? err.message : '送入审核失败',
      }));
    } finally {
      updateConversation(conversationId, (item) => ({ ...item, reviewingMessageIndex: null }));
    }
  };

  const sendArtifactToReview = async (
    conversationId: string,
    artifact: AiArtifact,
    message: AiChatMessage,
    index: number,
  ) => {
    const conversation = conversations.find((item) => item.id === conversationId);
    if (!conversation || conversation.reviewingArtifactId !== null) return;
    updateConversation(conversationId, (item) => ({ ...item, reviewingArtifactId: artifact.id, error: null }));
    try {
      const chatContext = conversation.messages
        .slice(Math.max(0, index - 6), index + 1)
        .map((item) => `${item.role === 'user' ? '用户' : 'AI'}：${item.content}`)
        .join('\n\n');
      const result = await submitAiGeneratedReview({
        source_text: artifact.content,
        source: `AI 题库助手 · ${conversation.title} · ${artifact.title}`,
        chat_context: `${chatContext}\n\n送审产物：${artifact.title}\n\n原始回复：${message.content}`,
        session_id: conversation.agentSession.id,
      });
      setConversationWarning(conversationId, `已送入审核：${result.question_count} 道题`);
      navigate(`/review/${result.task_id}`);
    } catch (err) {
      updateConversation(conversationId, (item) => ({
        ...item,
        error: err instanceof Error ? err.message : '送入审核失败',
      }));
    } finally {
      updateConversation(conversationId, (item) => ({ ...item, reviewingArtifactId: null }));
    }
  };

  if (!activeConversation) {
    return null;
  }

  return (
    <div className="relative flex h-full min-h-0 overflow-hidden bg-slate-50 text-slate-900">
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[56px] shrink-0 items-center justify-between border-b border-slate-200 bg-white/95 px-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-sm font-black text-slate-900">AI 助手</h1>
              <StatusDot ok={agentAvailable} />
              <span className="truncate text-xs text-slate-500">
                {agentAvailable ? 'Claude Code 已连接' : agentMessage || '未连接'}
              </span>
              {pageContext && <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">{pageContext.title}</span>}
            </div>
            <div className="mt-2 flex items-center gap-2">
              {conversations.map((conversation, index) => (
                <ConversationTab
                  key={conversation.id}
                  active={conversation.id === activeConversation.id}
                  title={conversation.title}
                  index={index}
                  sending={conversation.sending}
                  onClick={() => setActiveConversationId(conversation.id)}
                />
              ))}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() => setSidePanelOpen(true)}
              className="flex h-8 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              title="查看执行详情和上下文"
            >
              <PanelRightOpen size={13} />
              详情
            </button>
            <button
              type="button"
              onClick={() => clearConversation(activeConversation.id)}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              title="重置当前对话"
              aria-label="重置当前对话"
            >
              <RotateCcw size={13} />
            </button>
          </div>
        </header>

        <section className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 py-3">
          <div className="mx-auto flex w-full min-w-0 max-w-[920px] flex-col gap-4">
            {activeConversation.messages.map((message, index) => {
              const isUser = message.role === 'user';
              const isLatestAssistant = !isUser && index === activeConversation.messages.length - 1 && !activeConversation.sending;
              return (
                <MessageBlock
                  key={`${activeConversation.id}-${message.role}-${index}`}
                  message={message}
                  isLatestAssistant={isLatestAssistant}
                  actions={isLatestAssistant ? activeConversation.actions : []}
                  onRunAction={(action) => runAction(action, activeConversation.id)}
                  onRunComposeCommands={(commands) => runComposeCommands(commands, activeConversation.id, index)}
                  onUndoCompose={() => undoComposeCommands(activeConversation.id, index)}
                  composeApplied={activeConversation.appliedComposeMessageIndexes.includes(index)}
                  canUndoCompose={canUndoCompose}
                  canSendToReview={!isUser && index > 0}
                  sendingToReview={activeConversation.reviewingMessageIndex === index}
                  reviewingArtifactId={activeConversation.reviewingArtifactId}
                  onSendToReview={() => void sendMessageToReview(activeConversation.id, message, index)}
                  onSendArtifactToReview={(artifact) =>
                    void sendArtifactToReview(activeConversation.id, artifact, message, index)
                  }
                />
              );
            })}
            {activeConversation.sending && <RunningBlock trace={visibleTrace} onStop={() => stopConversation(activeConversation.id)} />}
            {activeConversation.warnings.length > 0 && (
              <InlineNotice>{activeConversation.warnings[activeConversation.warnings.length - 1]}</InlineNotice>
            )}
            {activeConversation.error && (
              <InlineNotice tone="error">
                <div className="flex items-center gap-2">
                  <span className="min-w-0 flex-1">{activeConversation.error}</span>
                  {activeConversation.lastFailedPrompt && (
                    <button type="button" onClick={() => void handleSend(activeConversation.id, activeConversation.lastFailedPrompt || undefined)} className="shrink-0 rounded border border-rose-200 bg-white px-2 py-1 font-semibold text-rose-700 hover:bg-rose-100">
                      重试
                    </button>
                  )}
                </div>
              </InlineNotice>
            )}
            <div ref={chatEndRef} />
          </div>
        </section>

        <footer className="shrink-0 border-t border-slate-200 bg-white px-3 py-2">
          <div className="mx-auto max-w-[920px]">
            {location.pathname === '/compose' && (
              <div className="mb-2">
                <div className="flex items-center gap-2 text-[10px] text-slate-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  <span>已读取当前试卷</span>
                  <span className="font-semibold text-slate-700">{visibleComposeCount} 个内容</span>
                  <span>·</span>
                  <span>{composeSelectedIndex >= 0 ? `当前选中第 ${composeSelectedIndex + 1} 项` : '未选中内容'}</span>
                  <span className="ml-auto">{composeRevision === composeSavedRevision ? '已同步' : '等待自动保存'}</span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 border-y border-slate-100 py-2">
                  <button
                    type="button"
                    onClick={() => void handleSend(activeConversation.id, COMPOSE_QUALITY_PROMPT)}
                    disabled={activeConversation.sending}
                    className="flex h-7 shrink-0 items-center gap-1.5 rounded-md bg-blue-600 px-2.5 text-[11px] font-black text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    <ClipboardCheck size={13} />整卷体检
                  </button>
                  {selectedComposeItem && (
                    <span className="max-w-[210px] shrink-0 truncate px-1 text-[11px] font-semibold text-slate-600" title={composeItemLabel(selectedComposeItem, composeSelectedIndex)}>
                      {composeItemLabel(selectedComposeItem, composeSelectedIndex)}
                    </span>
                  )}
                  {selectionActions.map((action) => (
                    <button
                      key={action.label}
                      type="button"
                      onClick={() => void handleSend(activeConversation.id, action.prompt)}
                      disabled={activeConversation.sending}
                      className="flex h-7 shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 text-[11px] font-semibold text-slate-600 hover:border-blue-500 hover:text-blue-700 disabled:opacity-50"
                    >
                      <Sparkles size={12} />{action.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="mb-2 flex flex-wrap gap-2 pb-1">
              {quickPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => void handleSend(activeConversation.id, prompt)}
                  disabled={activeConversation.sending}
                  className="h-8 shrink-0 rounded-full border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-600 hover:border-blue-500 hover:text-blue-700 disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
            <div className="rounded-xl border border-slate-300 bg-white p-2 shadow-[0_12px_30px_rgba(15,23,42,0.08)] focus-within:border-blue-500">
              <textarea
                ref={inputRef}
                value={activeConversation.draft}
                onChange={(event) =>
                  updateConversation(activeConversation.id, (item) => ({ ...item, draft: event.target.value }))
                }
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void handleSend(activeConversation.id);
                  }
                }}
                placeholder={location.pathname === '/compose' ? '直接说明怎样调整当前试卷…' : '输入任务，例如：帮我找一道有引力的题目'}
                className="max-h-[110px] min-h-[54px] w-full resize-none bg-transparent px-2 py-1.5 text-xs leading-5 text-slate-900 outline-none placeholder:text-slate-400"
              />
              {activeConversation.markedDocument && (
                <div className="mb-2 flex items-center gap-2 rounded-md bg-blue-50 px-2.5 py-1.5 text-[11px] text-blue-700">
                  <span className="min-w-0 flex-1 truncate">
                    已标记文档：{activeConversation.markedDocument}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      updateConversation(activeConversation.id, (item) => ({ ...item, markedDocument: null }))
                    }
                    className="shrink-0 font-semibold text-blue-600 hover:text-blue-800"
                  >
                    移除
                  </button>
                </div>
              )}
              <div className="flex items-center gap-2 border-t border-slate-100 px-2 pt-2">
                <input
                  ref={documentRef}
                  type="file"
                  accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.md"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    updateConversation(activeConversation.id, (item) => ({
                      ...item,
                      markedDocument: file.name,
                    }));
                    event.currentTarget.value = '';
                  }}
                />
                <div className="flex h-8 min-w-0 flex-1 items-center gap-1.5 rounded-md bg-slate-100 px-2 text-slate-400 focus-within:ring-1 focus-within:ring-blue-400">
                  <Search size={13} className="shrink-0" />
                  <input
                    value={activeConversation.query}
                    onChange={(event) =>
                      updateConversation(activeConversation.id, (item) => ({ ...item, query: event.target.value }))
                    }
                    placeholder="限定检索词（可选）"
                    className="min-w-0 flex-1 bg-transparent text-xs text-slate-700 outline-none placeholder:text-slate-400"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => documentRef.current?.click()}
                  className="h-8 shrink-0 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-600 hover:border-blue-500 hover:text-blue-700"
                >
                  <span className="flex items-center gap-1.5"><Paperclip size={13} />文档</span>
                </button>
                <button
                  type="button"
                  onClick={() => activeConversation.sending ? stopConversation(activeConversation.id) : void handleSend(activeConversation.id)}
                  disabled={!activeConversation.sending && !activeConversation.draft.trim()}
                  className={`flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-black text-white shadow-[0_8px_18px_rgba(37,99,235,0.22)] disabled:bg-slate-300 ${activeConversation.sending ? 'bg-slate-700 hover:bg-slate-800' : 'bg-blue-600 hover:bg-blue-700'}`}
                >
                  {activeConversation.sending ? <><Square size={12} fill="currentColor" />停止</> : <><Send size={13} />发送</>}
                </button>
              </div>
            </div>
          </div>
        </footer>
      </main>

      <aside className={`${sidePanelOpen ? 'flex' : 'hidden'} absolute inset-y-0 right-0 z-20 w-[260px] flex-col border-l border-slate-200 bg-white shadow-[-16px_0_36px_rgba(15,23,42,0.12)]`}>
        <div className="flex h-[46px] shrink-0 items-center gap-1 border-b border-slate-200 px-2">
          <SideTabButton active={sideTab === 'activity'} onClick={() => setSideTab('activity')}>过程</SideTabButton>
          <SideTabButton active={sideTab === 'terminal'} onClick={() => setSideTab('terminal')}>详情</SideTabButton>
          <SideTabButton active={sideTab === 'context'} onClick={() => setSideTab('context')}>上下文</SideTabButton>
          <button
            type="button"
            onClick={() => setSidePanelOpen(false)}
            className="ml-auto flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            aria-label="关闭详情面板"
            title="关闭详情面板"
          >
            <X size={14} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {sideTab === 'activity' && <ActivityPanel steps={visibleTrace} running={activeConversation.sending} />}
          {sideTab === 'terminal' && <TerminalPanel lines={visibleTerminal} running={activeConversation.sending} />}
          {sideTab === 'context' && (
            <ContextPanel
              questions={visibleContextQuestions}
              cachedIds={new Set(cachedQuestionIds)}
              basketIds={basketIds}
              onAddToBasket={(id) => {
                addToBasket(id);
                setConversationWarning(activeConversation.id, '已加入题篮：1 道题');
              }}
              onPin={(question) => {
                setContextCache((prev) => mergeQuestionContexts(prev, [question]).slice(0, 30));
                setConversationWarning(activeConversation.id, `已固定到上下文：${question.question_id}`);
              }}
              onUnpin={(id) => {
                setContextCache((prev) => prev.filter((question) => question.question_id !== id));
                setConversationWarning(activeConversation.id, `已从上下文移除：${id}`);
              }}
              onClearCache={() => {
                setContextCache([]);
                setConversationWarning(activeConversation.id, '已清空上下文缓存');
              }}
            />
          )}
        </div>
      </aside>
    </div>
  );
}

function ConversationTab({
  active,
  title,
  index,
  sending,
  onClick,
}: {
  active: boolean;
  title: string;
  index: number;
  sending: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-7 items-center gap-2 rounded-md px-2.5 text-[11px] font-black ${
        active ? 'bg-blue-600 text-white' : 'bg-blue-50 text-blue-700 hover:bg-blue-100'
      }`}
    >
      <span>{title || `对话 ${index + 1}`}</span>
      {sending && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />}
    </button>
  );
}

function MessageBlock({
  message,
  isLatestAssistant,
  actions,
  onRunAction,
  onRunComposeCommands,
  onUndoCompose,
  composeApplied,
  canUndoCompose,
  canSendToReview,
  sendingToReview,
  reviewingArtifactId,
  onSendToReview,
  onSendArtifactToReview,
}: {
  message: AiChatMessage;
  isLatestAssistant: boolean;
  actions: AgentAction[];
  onRunAction: (action: AgentAction) => void;
  onRunComposeCommands: (commands: ComposeCommand[]) => void;
  onUndoCompose: () => void;
  composeApplied: boolean;
  canUndoCompose: boolean;
  canSendToReview: boolean;
  sendingToReview: boolean;
  reviewingArtifactId: string | null;
  onSendToReview: () => void;
  onSendArtifactToReview: (artifact: AiArtifact) => void;
}) {
  const isUser = message.role === 'user';
  const artifacts = isUser ? [] : extractAiArtifacts(message.content);
  const composeCommands = isUser ? [] : parseComposeCommandsFromText(message.content);
  const visibleContent = composeCommands.length > 0 ? stripComposeCommandsFromText(message.content) : message.content;
  const [selectedCommandIndexes, setSelectedCommandIndexes] = useState<number[]>(() => composeCommands.map((_, index) => index));
  const selectedCommands = composeCommands.filter((_, index) => selectedCommandIndexes.includes(index));
  const allCommandsSelected = composeCommands.length > 0 && selectedCommands.length === composeCommands.length;
  const toggleCommand = (index: number) => {
    setSelectedCommandIndexes((current) => current.includes(index)
      ? current.filter((item) => item !== index)
      : [...current, index].sort((a, b) => a - b));
  };
  return (
    <article className={`flex min-w-0 gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && <Avatar label="AI" />}
      <div className={`min-w-0 ${isUser ? 'max-w-[76%]' : 'max-w-[82%]'}`}>
        <div
          className={`rounded-xl px-3 py-2 text-xs leading-6 ${
            isUser
              ? 'bg-blue-600 text-white shadow-[0_10px_24px_rgba(37,99,235,0.20)]'
              : 'border border-slate-200 bg-white text-slate-700 shadow-[0_10px_26px_rgba(15,23,42,0.06)]'
          }`}
        >
          <LatexRenderer text={visibleContent || '已生成可应用的文档修改。'} className="ai-chat-rich-text" />
        </div>
        {isLatestAssistant && actions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {actions.map((action) => (
              <button
                key={action.action_id}
                type="button"
                onClick={() => onRunAction(action)}
              className="h-7 rounded-full border border-blue-100 bg-blue-50 px-2.5 text-[11px] font-black text-blue-700 hover:border-blue-500 hover:bg-blue-100"
              >
                {action.label} · {action.question_ids.length} 题
              </button>
            ))}
          </div>
        )}
        {isLatestAssistant && composeCommands.length > 0 && (
          <div className={`mt-2 rounded-lg border p-2.5 text-[11px] text-slate-700 ${composeApplied ? 'border-emerald-200 bg-emerald-50' : 'border-blue-200 bg-blue-50'}`}>
            <div className="flex items-center justify-between gap-3">
              <div className={composeApplied ? 'font-black text-emerald-800' : 'font-black text-blue-800'}>
                {composeApplied ? `已应用 ${selectedCommands.length} 项修改` : '文档修改清单'}
              </div>
              <label className="flex shrink-0 cursor-pointer items-center gap-1.5 font-semibold text-slate-500">
                <input
                  type="checkbox"
                  checked={allCommandsSelected}
                  disabled={composeApplied}
                  onChange={(event) => setSelectedCommandIndexes(event.target.checked ? composeCommands.map((_, index) => index) : [])}
                  className="h-3.5 w-3.5 accent-blue-600"
                />
                全选
              </label>
            </div>
            <ul className="mt-2 space-y-1.5">
              {composeCommands.map((command, index) => (
                <li key={`${command.type}-${index}`}>
                  <label className={`flex items-start gap-2 rounded-md border px-2 py-1.5 ${selectedCommandIndexes.includes(index) ? 'border-blue-200 bg-white' : 'border-slate-200 bg-slate-50 text-slate-400'} ${composeApplied ? 'cursor-default' : 'cursor-pointer'}`}>
                    <input
                      type="checkbox"
                      checked={selectedCommandIndexes.includes(index)}
                      disabled={composeApplied}
                      onChange={() => toggleCommand(index)}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-blue-600"
                    />
                    <span className="min-w-0">{index + 1}. {describeComposeCommand(command)}</span>
                  </label>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => onRunComposeCommands(selectedCommands)}
                disabled={composeApplied || selectedCommands.length === 0}
                className="h-7 rounded-md bg-blue-600 px-3 font-black text-white hover:bg-blue-700 disabled:bg-emerald-600"
              >
                {composeApplied ? '已应用' : selectedCommands.length > 0 ? `应用选中（${selectedCommands.length}）` : '请选择修改'}
              </button>
              <button
                type="button"
                onClick={onUndoCompose}
                disabled={!composeApplied || !canUndoCompose}
                className="h-7 rounded-md border border-slate-200 bg-white px-3 font-black text-slate-600 disabled:opacity-40"
              >
                撤销
              </button>
            </div>
          </div>
        )}
        {artifacts.length > 0 && (
          <ArtifactCards
            artifacts={artifacts}
            reviewingArtifactId={reviewingArtifactId}
            onSendToReview={onSendArtifactToReview}
          />
        )}
        {canSendToReview && (
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSendToReview}
              disabled={sendingToReview}
              className="h-7 rounded-full border border-emerald-100 bg-emerald-50 px-2.5 text-[11px] font-black text-emerald-700 hover:border-emerald-500 hover:bg-emerald-100 disabled:cursor-wait disabled:opacity-60"
            >
              {sendingToReview ? '正在送审' : artifacts.length > 0 ? '整段送审' : '送入 AI 内容审核'}
            </button>
          </div>
        )}
      </div>
      {isUser && <Avatar label="你" tone="user" />}
    </article>
  );
}

function ArtifactCards({
  artifacts,
  reviewingArtifactId,
  onSendToReview,
}: {
  artifacts: AiArtifact[];
  reviewingArtifactId: string | null;
  onSendToReview: (artifact: AiArtifact) => void;
}) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => new Set());

  const toggleCollapsed = (artifactId: string) => {
    setCollapsedIds((current) => {
      const next = new Set(current);
      if (next.has(artifactId)) next.delete(artifactId);
      else next.add(artifactId);
      return next;
    });
  };

  return (
    <div className="mt-3 grid min-w-0 gap-2">
      {artifacts.map((artifact) => {
        const collapsed = collapsedIds.has(artifact.id);
        return (
        <div key={artifact.id} className="min-w-0 overflow-hidden rounded-lg border border-emerald-100 bg-emerald-50/70 p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-white px-2 py-1 text-[11px] font-black text-emerald-700 ring-1 ring-emerald-100">
                  {artifactTypeLabel(artifact.type)}
                </span>
                <div className="min-w-0 break-words text-xs font-black text-slate-800">{artifact.title}</div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => toggleCollapsed(artifact.id)}
                className="h-8 rounded-md border border-emerald-200 bg-white px-2.5 text-xs font-black text-emerald-700 hover:bg-emerald-100"
              >
                {collapsed ? '展开' : '收起'}
              </button>
              <button
                type="button"
                onClick={() => onSendToReview(artifact)}
                disabled={reviewingArtifactId === artifact.id}
                className="h-8 rounded-md bg-emerald-600 px-3 text-xs font-black text-white hover:bg-emerald-700 disabled:cursor-wait disabled:bg-emerald-300"
              >
                {reviewingArtifactId === artifact.id ? '送审中' : '送审'}
              </button>
            </div>
          </div>
          {collapsed ? (
            <div className="mt-2 line-clamp-2 break-words text-xs leading-5 text-slate-600">
              <LatexRenderer text={artifact.summary} inline />
            </div>
          ) : (
            <div className="ai-chat-rich-text mt-3 min-w-0 overflow-x-hidden break-words rounded-md border border-emerald-100 bg-white/80 p-3 text-xs leading-6 text-slate-700">
              <LatexRenderer text={artifact.content} />
            </div>
          )}
        </div>
        );
      })}
    </div>
  );
}

function RunningBlock({ trace, onStop }: { trace: AgentTraceStep[]; onStop: () => void }) {
  const current = trace[trace.length - 1];
  return (
    <article className="flex justify-start gap-3">
      <Avatar label="AI" />
      <div className="max-w-[82%] rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-[0_10px_26px_rgba(15,23,42,0.06)]">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <span className="h-2 w-2 animate-pulse rounded-full bg-blue-600" />
          <span className="min-w-0 flex-1">Claude Code 正在处理</span>
          <button type="button" onClick={onStop} className="flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 hover:bg-slate-50">
            <Square size={9} fill="currentColor" />停止
          </button>
        </div>
        <div className="mt-1 text-[11px] leading-5 text-slate-500">
          {current?.title ? `当前步骤：${current.title}` : '等待本地智能体响应...'}
        </div>
      </div>
    </article>
  );
}

function ActivityPanel({ steps, running }: { steps: AgentTraceStep[]; running: boolean }) {
  if (steps.length === 0) {
    return <EmptyHint text="发送任务后，这里会出现实时执行轨迹。" />;
  }
  return (
    <div className="space-y-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs font-black text-slate-900">执行轨迹</div>
        <span className="text-xs text-slate-500">{running ? '运行中' : `${steps.length} 步`}</span>
      </div>
      <PhaseStrip steps={steps} running={running} />
      <div className="space-y-1">
        {steps.map((step, index) => (
          <TraceRow
            key={`${step.title}-${index}`}
            step={step}
            index={index}
            active={running && index === steps.length - 1}
          />
        ))}
      </div>
    </div>
  );
}

function PhaseStrip({ steps, running }: { steps: AgentTraceStep[]; running: boolean }) {
  const phases = [
    { key: 'goal', label: '读需求', match: ['读取对话目标'] },
    { key: 'context', label: '上下文', match: ['复用对话缓存', '载入上下文缓存'] },
    { key: 'search', label: '查题库', match: ['检索数据库题目'] },
    { key: 'agent', label: 'Claude', match: ['启动 Claude Code'] },
    { key: 'result', label: '整理', match: ['解析结果', '整理输出'] },
  ];
  const activeStep = steps[steps.length - 1]?.title || '';
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="grid grid-cols-5 gap-2">
        {phases.map((phase) => {
          const matchedIndex = steps.findIndex((step) => phase.match.some((text) => step.title.includes(text)));
          const done = matchedIndex >= 0;
          const active = running && phase.match.some((text) => activeStep.includes(text));
          return (
            <div key={phase.key} className="min-w-0">
              <div
                className={`mx-auto h-2 rounded-full ${
                  active ? 'animate-pulse bg-blue-600' : done ? 'bg-emerald-500' : 'bg-slate-200'
                }`}
              />
              <div className={`mt-2 truncate text-center text-[11px] font-black ${done ? 'text-slate-700' : 'text-slate-400'}`}>
                {phase.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TraceRow({ step, index, active }: { step: AgentTraceStep; index: number; active: boolean }) {
  const color =
    step.status === 'error'
      ? 'bg-[#ef4444]'
      : step.status === 'warning'
        ? 'bg-[#f59e0b]'
        : active
          ? 'bg-[#2f75d6]'
          : 'bg-[#39a36b]';
  return (
    <div className="grid grid-cols-[22px_minmax(0,1fr)] gap-3">
      <div className="relative flex justify-center">
        {index > 0 && <span className="absolute -top-3 h-4 w-px bg-slate-200" />}
        <span className={`mt-1 h-2.5 w-2.5 rounded-full ${color} ${active ? 'animate-pulse' : ''}`} />
      </div>
      <div className="pb-4">
        <div className="text-xs font-black text-slate-700">{step.title}</div>
        <div className="mt-1 text-[11px] leading-4 text-slate-500">{step.detail}</div>
      </div>
    </div>
  );
}

function TerminalPanel({ lines, running }: { lines: string[]; running: boolean }) {
  if (lines.length === 0) {
    return <EmptyHint text={running ? '正在准备执行详情...' : '本轮没有更多执行详情。'} />;
  }
  return (
    <div className="flex h-full min-h-[420px] flex-col overflow-hidden rounded-lg border border-blue-200 bg-[#eff6ff]">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-blue-200 bg-[#dbeafe] px-3">
        <span className="text-xs font-semibold text-blue-800">执行详情</span>
        <span className="text-[11px] text-blue-600">{running ? '运行中' : `${lines.length} 条`}</span>
      </div>
      <pre className="min-h-0 flex-1 overflow-auto p-3 text-[11px] leading-5 whitespace-pre-wrap text-blue-950">
        {lines.join('\n')}
      </pre>
    </div>
  );
}

function ContextPanel({
  questions,
  cachedIds,
  basketIds,
  onAddToBasket,
  onPin,
  onUnpin,
  onClearCache,
}: {
  questions: AiAssistantQuestionContext[];
  cachedIds: Set<string>;
  basketIds: Set<string>;
  onAddToBasket: (id: string) => void;
  onPin: (question: AiAssistantQuestionContext) => void;
  onUnpin: (id: string) => void;
  onClearCache: () => void;
}) {
  if (questions.length === 0) {
    return <EmptyHint text="命中的题目会出现在这里。固定后会作为下一轮 Claude Code 的上下文。" />;
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-black text-slate-900">上下文缓存</div>
          <div className="mt-1 text-xs text-slate-500">
            已固定 {cachedIds.size} 道题，后续对话会优先参考。
          </div>
        </div>
        {cachedIds.size > 0 && (
          <button
            type="button"
            onClick={onClearCache}
            className="h-7 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-500 hover:bg-slate-50"
          >
            清空
          </button>
        )}
      </div>
      {questions.map((question) => (
        <div key={question.question_id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="truncate text-xs font-black text-blue-700">{question.question_id}</span>
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                onClick={() => onAddToBasket(question.question_id)}
                disabled={basketIds.has(question.question_id)}
                className="rounded-md bg-blue-50 px-2 py-1 text-[11px] font-black text-blue-700 disabled:bg-emerald-50 disabled:text-emerald-700"
              >
                {basketIds.has(question.question_id) ? '已入题篮' : '加入题篮'}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (cachedIds.has(question.question_id)) {
                    onUnpin(question.question_id);
                  } else {
                    onPin(question);
                  }
                }}
                className="rounded-md bg-white px-2 py-1 text-[11px] font-black text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100"
              >
                {cachedIds.has(question.question_id) ? '移除缓存' : '固定上下文'}
              </button>
            </div>
          </div>
          <LatexRenderer
            text={question.title || '无题干'}
            className="break-words text-xs leading-5 text-slate-700"
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {question.question_type && <Chip>{TYPE_LABELS[question.question_type] || question.question_type}</Chip>}
            {question.difficulty && <Chip>难度 {question.difficulty}</Chip>}
            {question.knowledge_point && <Chip>{question.knowledge_point}</Chip>}
          </div>
        </div>
      ))}
    </div>
  );
}

function SideTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`h-7 rounded-md px-2.5 text-[11px] font-black ${
        active ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-blue-50'
      }`}
    >
      {children}
    </button>
  );
}

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`h-2 w-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-slate-300'}`} />;
}

function Avatar({ label, tone }: { label: string; tone?: 'user' }) {
  return (
    <div
      className={`mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-black ${
        tone === 'user' ? 'bg-blue-100 text-blue-700' : 'bg-blue-600 text-white'
      }`}
    >
      {label}
    </div>
  );
}

function InlineNotice({ children, tone = 'warning' }: { children: ReactNode; tone?: 'warning' | 'error' }) {
  return (
    <div
      className={`mx-8 rounded-lg border px-3 py-2 text-[11px] leading-5 ${
        tone === 'error'
          ? 'border-rose-200 bg-rose-50 text-rose-700'
          : 'border-amber-200 bg-amber-50 text-amber-700'
      }`}
    >
      {children}
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-4 text-xs leading-5 text-slate-500">
      {text}
    </div>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-500">
      {children}
    </span>
  );
}
