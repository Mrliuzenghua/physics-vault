import type {
  ComposeItem,
  HandoutHeaderFooterConfig,
  HandoutItem,
  HandoutStyleConfig,
  LessonKnowledgeCard,
  LessonPackage,
  SavedLessonPackageSummary,
  Question,
} from '../types';
import type { SlideDeck, SlideDeckTemplate, SlidePage } from '../types/slides';

const LESSON_PACKAGE_KEY = 'physics-vault.current-lesson-package';
const LESSON_PACKAGE_LIBRARY_KEY = 'physics-vault.lesson-package-library';

function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function safeParse<T>(value: string | null, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

export function buildKnowledgeCards(questions: Question[]): LessonKnowledgeCard[] {
  const map = new Map<string, LessonKnowledgeCard>();

  for (const question of questions) {
    const names = [
      ...(question.knowledge_points || [])
        .map((point) => point.topic3_name || point.topic2_name || point.topic1_name)
        .filter(Boolean),
      ...(question.knowledge_point?.trim() ? [question.knowledge_point.trim()] : []),
    ];

    for (const rawName of names) {
      const name = rawName.trim();
      if (!name) continue;

      const existing = map.get(name);
      if (existing) {
        if (!existing.relatedQuestionIds.includes(question.question_id)) {
          existing.relatedQuestionIds.push(question.question_id);
        }
        continue;
      }

      map.set(name, {
        id: makeId('kp'),
        title: name,
        summary: `围绕“${name}”组织课堂引入、题目训练与方法归纳。`,
        points: [
          `先识别这一知识点对应的物理情境和核心变量。`,
          `再提炼图像、公式和常见设问，形成稳定的解题入口。`,
          `最后把相关题目串联成“知识点 + 例题 + 训练”的流式学案。`,
        ],
        relatedQuestionIds: [question.question_id],
      });
    }
  }

  return Array.from(map.values());
}

export function createLessonPackage(params: {
  id?: string;
  title?: string;
  subtitle?: string;
  source?: LessonPackage['source'];
  composeItems: ComposeItem[];
  headerFooter?: HandoutHeaderFooterConfig;
  styleConfig?: HandoutStyleConfig;
  slideTemplate?: SlideDeckTemplate;
}): LessonPackage {
  const {
    id,
    title = '未命名教学包',
    subtitle = '题目与知识点混合编排',
    source = 'compose',
    composeItems,
    headerFooter,
    styleConfig,
    slideTemplate,
  } = params;

  const questions = composeItems
    .filter((item): item is Extract<ComposeItem, { type: 'question' }> => item.type === 'question')
    .map((item) => item.question)
    .filter(Boolean) as Question[];

  const knowledgeCards = buildKnowledgeCards(questions);
  const selectedKnowledgeCards = new Map<string, LessonKnowledgeCard>();
  const textBlocks: LessonPackage['textBlocks'] = [];
  const nodes: LessonPackage['nodes'] = [];
  const knowledgeCardMap = new Map(knowledgeCards.map((card) => [card.id, card]));

  for (const item of composeItems) {
    if (item.type === 'separator') {
      nodes.push({ type: 'page_break', id: item.id, title: item.title });
      continue;
    }
    if (item.type === 'question') {
      nodes.push({ type: 'question', id: item.id, questionId: item.questionId });
      continue;
    }
    if (item.type === 'knowledge') {
      const card =
        knowledgeCardMap.get(item.knowledgeId) || {
          id: item.knowledgeId,
          title: item.title,
          summary: item.summary,
          points: item.points,
          relatedQuestionIds: [],
        };
      selectedKnowledgeCards.set(card.id, card);
      nodes.push({ type: 'knowledge', id: item.id, knowledgeId: card.id });
      continue;
    }
    textBlocks.push({
      id: item.id,
      title: item.title,
      content: item.content,
      blockKind: item.blockKind,
      style: item.style,
    });
    nodes.push({ type: 'text', id: item.id, textBlockId: item.id });
  }

  const now = new Date().toISOString();

  return {
    id: id || makeId('lesson'),
    title,
    subtitle,
    source,
    questions,
    knowledgeCards: Array.from(selectedKnowledgeCards.values()),
    textBlocks,
    nodes,
    headerFooter,
    styleConfig,
    slideTemplate,
    createdAt: now,
    updatedAt: now,
  };
}

export function saveCurrentLessonPackage(pkg: LessonPackage): void {
  localStorage.setItem(LESSON_PACKAGE_KEY, JSON.stringify(pkg));
}

export function loadCurrentLessonPackage(): LessonPackage | null {
  return safeParse<LessonPackage | null>(localStorage.getItem(LESSON_PACKAGE_KEY), null);
}

function saveLessonPackageLibrary(packages: LessonPackage[]): void {
  localStorage.setItem(LESSON_PACKAGE_LIBRARY_KEY, JSON.stringify(packages));
}

export function listSavedLessonPackages(): SavedLessonPackageSummary[] {
  const packages = safeParse<LessonPackage[]>(localStorage.getItem(LESSON_PACKAGE_LIBRARY_KEY), []);
  return packages
    .slice()
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .map((pkg) => ({
      id: pkg.id,
      title: pkg.title,
      subtitle: pkg.subtitle,
      updatedAt: pkg.updatedAt,
      questionCount: pkg.questions.length,
      knowledgeCount: pkg.knowledgeCards.length,
      nodeCount: pkg.nodes.length,
    }));
}

export function loadSavedLessonPackage(id: string): LessonPackage | null {
  const packages = safeParse<LessonPackage[]>(localStorage.getItem(LESSON_PACKAGE_LIBRARY_KEY), []);
  return packages.find((pkg) => pkg.id === id) || null;
}

export function saveLessonPackageToLibrary(pkg: LessonPackage): void {
  const packages = safeParse<LessonPackage[]>(localStorage.getItem(LESSON_PACKAGE_LIBRARY_KEY), []);
  const nextPkg = { ...pkg, updatedAt: new Date().toISOString() };
  const existingIndex = packages.findIndex((item) => item.id === pkg.id);
  if (existingIndex >= 0) {
    packages[existingIndex] = nextPkg;
  } else {
    packages.unshift(nextPkg);
  }
  saveLessonPackageLibrary(packages);
  saveCurrentLessonPackage(nextPkg);
}

export function deleteSavedLessonPackage(id: string): void {
  const packages = safeParse<LessonPackage[]>(localStorage.getItem(LESSON_PACKAGE_LIBRARY_KEY), []);
  saveLessonPackageLibrary(packages.filter((pkg) => pkg.id !== id));
}

export function buildHandoutItemsFromLessonPackage(pkg: LessonPackage): HandoutItem[] {
  const knowledgeMap = new Map(pkg.knowledgeCards.map((card) => [card.id, card]));
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));

  return pkg.nodes.reduce<HandoutItem[]>((items, node) => {
    if (node.type === 'page_break') {
      items.push({ type: 'page_break', title: node.title });
      return items;
    }
    if (node.type === 'knowledge') {
      const card = knowledgeMap.get(node.knowledgeId);
      if (card) {
        items.push({
          type: 'knowledge',
          title: card.title,
          summary: card.summary,
          points: card.points,
        });
      }
      return items;
    }
    if (node.type === 'text') {
      const textBlock = textMap.get(node.textBlockId);
      if (textBlock) {
        items.push({
          type: 'text',
          title: textBlock.title,
          content: textBlock.content,
          blockKind: textBlock.blockKind,
          style: textBlock.style,
        });
      }
      return items;
    }
    const question = questionMap.get(node.questionId);
    if (question) {
      items.push({ type: 'question', question });
    }
    return items;
  }, []);
}

export function buildKnowledgeSlides(cards: LessonKnowledgeCard[]): SlidePage[] {
  return cards.map((card, index) => ({
    id: `knowledge-${card.id}`,
    pageType: 'knowledge_summary',
    title: card.title,
    subtitle: `关联题目 ${card.relatedQuestionIds.length} 道`,
    badge: index === 0 ? '知识点引入' : '关联知识点',
    layout: card.points.length > 4 ? 'two_column' : 'single_column',
    sections: [
      {
        id: `${card.id}-summary`,
        type: 'summary',
        title: '课堂要点',
        items: card.points.map((point, pointIndex) => ({
          id: `${card.id}-${pointIndex}`,
          text: point,
          emphasis: pointIndex === 0,
        })),
        note: card.summary,
      },
    ],
    footer: `关联题号：${card.relatedQuestionIds.join('、')}`,
  }));
}

export function buildSlideDeckFromLessonPackage(pkg: LessonPackage): SlideDeck {
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const knowledgeMap = new Map(
    buildKnowledgeSlides(pkg.knowledgeCards).map((slide) => [slide.id.replace('knowledge-', ''), slide]),
  );
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));
  const pages: SlidePage[] = [];

  pkg.nodes.forEach((node, index) => {
    if (node.type === 'page_break') {
      return;
    }
    if (node.type === 'knowledge') {
      const slide = knowledgeMap.get(node.knowledgeId);
      if (slide) {
        pages.push(slide);
      }
      return;
    }
    if (node.type === 'text') {
      const block = textMap.get(node.textBlockId);
      if (block) {
        pages.push({
          id: `text-${block.id}`,
          pageType: 'method_summary',
          title: block.title,
          subtitle: pkg.subtitle,
          badge: '文本卡片',
          layout: 'single_column',
          sections: [
            {
              id: `${block.id}-section`,
              type: 'summary',
              title: block.title,
              items: block.content
                .split('\n')
                .map((line) => line.trim())
                .filter(Boolean)
                .map((line, lineIndex) => ({
                  id: `${block.id}-${lineIndex}`,
                  text: line,
                  emphasis: lineIndex === 0,
                })),
              note: '来自组卷工作台插入的说明文本',
            },
          ],
          footer: `编排节点 ${index + 1}`,
        });
      }
      return;
    }

    const question = questionMap.get(node.questionId);
    if (question) {
      pages.push({
        id: `q-${question.question_id}`,
        pageType: 'question_explain',
        title: `题目 ${pages.filter((page) => page.pageType === 'question_explain').length + 1}`,
        subtitle: question.knowledge_point || pkg.subtitle,
        badge: question.question_type,
        layout: 'single_column',
        sections: [],
        footer: question.source || undefined,
      });
    }
  });

  return {
    id: `deck-${pkg.id}`,
    title: pkg.title,
    subtitle: pkg.subtitle,
    theme: 'physics',
    pages,
  };
}
