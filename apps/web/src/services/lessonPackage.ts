import type {
  ComposeItem,
  HandoutHeaderFooterConfig,
  HandoutItem,
  HandoutStyleConfig,
  LessonKnowledgeCard,
  LessonPackage,
  SavedLessonPackageSummary,
  LessonFolder,
  Question,
} from '../types';
import type { SlideDeck, SlideDeckTemplate, SlidePage } from '../types/slides';
import { parseLessonPackage, parseLessonPackageList } from './lessonPackageSchema.ts';
import { readJsonStorage, writeJsonStorage } from './safeStorage.ts';

const LESSON_PACKAGE_KEY = 'physics-vault.current-lesson-package';
const LESSON_PACKAGE_LIBRARY_KEY = 'physics-vault.lesson-package-library';
const LESSON_FOLDER_LIBRARY_KEY = 'physics-vault.lesson-folder-library';

function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function teachingPointsForKnowledge(name: string): string[] {
  return [
    `概念与条件：明确“${name}”对应的研究对象、物理过程、适用条件和核心物理量。`,
    '规律与表达：写出关键关系式，结合图像、实验现象或能量变化解释物理意义。',
    '解题路径：先识别模型，再列关系式与边界条件，最后检查方向、单位与数量级。',
    '常见误区：警惕条件变化、正负号、临界状态，以及过程量与状态量的混淆。',
  ];
}

function stableKnowledgeId(name: string): string {
  let hash = 2166136261;
  for (let index = 0; index < name.length; index += 1) {
    hash ^= name.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `kp-${(hash >>> 0).toString(36)}`;
}

function cleanQuestionText(value?: string | null): string {
  return String(value || '')
    .replace(/!\[fig:[^\]]+\]/g, '')
    .replace(/\$\$?/g, '')
    .replace(/\\(?:text|mathrm)\{([^{}]*)\}/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractFormulaCues(questions: Question[]): string[] {
  const formulas: string[] = [];
  const seen = new Set<string>();
  for (const question of questions) {
    const source = `${question.title || question.stem_text || ''}\n${question.analysis || ''}`
      .replace(/!\[fig:[^\]]+\]/g, ' ');
    for (const match of source.matchAll(/\$\$?([^$]{2,80})\$\$?/g)) {
      const formula = match[1].trim();
      if (!formula || /[\u4e00-\u9fff]{4,}/.test(formula) || seen.has(formula)) continue;
      seen.add(formula);
      formulas.push(`$${formula}$`);
      if (formulas.length >= 3) return formulas;
    }
  }
  return formulas;
}

function enrichedTeachingPoints(name: string, questions: Question[]): string[] {
  const baselinePoints = teachingPointsForKnowledge(name);
  const formulaCues = extractFormulaCues(questions);
  const hasFigure = questions.some((question) => (question.figures || []).length > 0);
  const sampleStem = cleanQuestionText(questions[0]?.title || questions[0]?.stem_text);
  const context = sampleStem
    ? `典型情境可从“${sampleStem.slice(0, 72)}${sampleStem.length > 72 ? '…' : ''}”切入。`
    : '从题目关键词、装置状态和过程阶段识别模型。';

  return [
    baselinePoints[0] || `概念定位：说明“${name}”研究的对象、过程与核心物理量，区分已知量、待求量和约束条件。`,
    `规律表达：${formulaCues.length > 0 ? `关联式包括 ${formulaCues.join('、')}，使用时逐一核对成立条件。` : '从定义式、决定式和过程规律三个层次整理关系式，并说明各物理量的方向与单位。'}`,
    `情境识别：${context}`,
    hasFigure
      ? '图像与实验：先读坐标、斜率、面积、截距和装置连接关系，再把图像信息翻译成物理量与方程。'
      : '模型建构：画出过程草图或受力图，统一正方向和参考系，再建立分阶段关系。',
    '解题流程：审题标注条件 → 建立模型 → 列出关系式 → 联立求解 → 检查单位、方向、数量级和特殊值。',
    baselinePoints[3] || '易错提醒：不要忽略适用条件、初末状态、正负号、矢量方向，以及平均量与瞬时量的区别。',
    `课堂自检：能否用一句话解释“${name}”的核心规律，并说明条件改变后结论如何变化。`,
  ];
}

export function buildKnowledgeCardContent(title: string, questions: Question[] = []) {
  return {
    summary: `围绕“${title}”组织概念、规律、模型、图像与易错点，形成“讲解—示例—训练—复盘”的完整学习链。`,
    points: enrichedTeachingPoints(title, questions),
  };
}

export function buildKnowledgeCards(questions: Question[]): LessonKnowledgeCard[] {
  const map = new Map<string, LessonKnowledgeCard>();

  for (const question of questions) {
    const structuredNames = (question.knowledge_points || [])
      .map((point) => point.topic3_name || point.topic2_name || point.topic1_name)
      .filter(Boolean);
    const names = structuredNames.length > 0
      ? structuredNames
      : question.knowledge_point?.split(/[\n,，;；/]+/).map((item) => item.trim()).filter(Boolean) || [];

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
        id: stableKnowledgeId(name),
        title: name,
        summary: `围绕知识目录“${name}”组织课堂引入、题目训练与方法归纳。`,
        points: [
          `先定位这一目录节点对应的物理情境和核心变量。`,
          `再提炼图像、公式和常见设问，形成稳定的解题入口。`,
          `最后把相关题目串联成“目录节点 + 例题 + 训练”的流式学案。`,
        ],
        relatedQuestionIds: [question.question_id],
      });
    }
  }

  const questionMap = new Map(questions.map((question) => [question.question_id, question]));
  return Array.from(map.values()).map((card) => {
    const relatedQuestions = card.relatedQuestionIds
      .map((questionId) => questionMap.get(questionId))
      .filter((question): question is Question => Boolean(question));
    const content = buildKnowledgeCardContent(card.title, relatedQuestions);
    return {
      ...card,
      summary: relatedQuestions.length > 0
        ? `${content.summary.replace('，形成', `，关联 ${relatedQuestions.length} 道题形成`)}`
        : content.summary,
      points: content.points,
    };
  });
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
      // A compose knowledge item is an editable teaching object.  The generated
      // card only contributes its relation metadata; title, rich summary and
      // points must always come from the workbench, otherwise the preview would
      // silently replace an editor change with the automatically generated copy.
      const generatedCard = knowledgeCardMap.get(item.knowledgeId);
      const card: LessonKnowledgeCard = {
        id: item.knowledgeId,
        title: item.title,
        summary: item.summary,
        points: item.points,
        relatedQuestionIds: generatedCard?.relatedQuestionIds || [],
      };
      selectedKnowledgeCards.set(card.id, card);
      nodes.push({ type: 'knowledge', id: item.id, knowledgeId: card.id });
      continue;
    }
    textBlocks.push({
      id: item.id,
      title: item.title,
      content: item.content,
      document: item.document,
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
  writeJsonStorage(LESSON_PACKAGE_KEY, pkg);
}

export function loadCurrentLessonPackage(): LessonPackage | null {
  return parseLessonPackage(readJsonStorage<unknown>(LESSON_PACKAGE_KEY, null));
}

function saveLessonPackageLibrary(packages: LessonPackage[]): void {
  writeJsonStorage(LESSON_PACKAGE_LIBRARY_KEY, packages);
}

export function listSavedLessonPackages(): SavedLessonPackageSummary[] {
  const packages = parseLessonPackageLibrary();
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
      folderId: pkg.folderId || null,
    }));
}

export function loadSavedLessonPackage(id: string): LessonPackage | null {
  const packages = parseLessonPackageLibrary();
  return packages.find((pkg) => pkg.id === id) || null;
}

export function saveLessonPackageToLibrary(pkg: LessonPackage): void {
  const packages = parseLessonPackageLibrary();
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

export function listLessonFolders(): LessonFolder[] {
  const value = readJsonStorage<unknown>(LESSON_FOLDER_LIBRARY_KEY, []);
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is LessonFolder => Boolean(
    item && typeof item === 'object'
    && typeof (item as LessonFolder).id === 'string'
    && typeof (item as LessonFolder).name === 'string',
  ));
}

function saveLessonFolders(folders: LessonFolder[]): void {
  writeJsonStorage(LESSON_FOLDER_LIBRARY_KEY, folders);
}

export function createLessonFolder(name: string): LessonFolder | null {
  const cleanName = name.trim();
  if (!cleanName) return null;
  const now = new Date().toISOString();
  const folder: LessonFolder = { id: makeId('folder'), name: cleanName, createdAt: now, updatedAt: now };
  saveLessonFolders([...listLessonFolders(), folder]);
  return folder;
}

export function renameLessonFolder(id: string, name: string): void {
  const cleanName = name.trim();
  if (!cleanName) return;
  const now = new Date().toISOString();
  saveLessonFolders(listLessonFolders().map((folder) => folder.id === id ? { ...folder, name: cleanName, updatedAt: now } : folder));
}

export function deleteLessonFolder(id: string): void {
  saveLessonFolders(listLessonFolders().filter((folder) => folder.id !== id));
  const packages = parseLessonPackageLibrary().map((pkg) => pkg.folderId === id ? { ...pkg, folderId: null } : pkg);
  saveLessonPackageLibrary(packages);
}

export function moveSavedLessonPackage(id: string, folderId: string | null): void {
  const packages = parseLessonPackageLibrary().map((pkg) => pkg.id === id ? { ...pkg, folderId, updatedAt: new Date().toISOString() } : pkg);
  saveLessonPackageLibrary(packages);
}

export function deleteSavedLessonPackage(id: string): void {
  const packages = parseLessonPackageLibrary();
  saveLessonPackageLibrary(packages.filter((pkg) => pkg.id !== id));
}

function parseLessonPackageLibrary(): LessonPackage[] {
  return parseLessonPackageList(readJsonStorage<unknown>(LESSON_PACKAGE_LIBRARY_KEY, []));
}

export function buildHandoutItemsFromLessonPackage(pkg: LessonPackage): HandoutItem[] {
  const knowledgeMap = new Map(pkg.knowledgeCards.map((card) => [card.id, card]));
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));

  return pkg.nodes.reduce<HandoutItem[]>((items, node) => {
    if (node.type === 'page_break') {
      items.push({ id: node.id, type: 'page_break', title: node.title });
      return items;
    }
    if (node.type === 'knowledge') {
      const card = knowledgeMap.get(node.knowledgeId);
      if (card) {
        items.push({
          id: node.id,
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
          id: node.id,
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
      items.push({ id: node.id, type: 'question', question });
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
    badge: index === 0 ? '知识目录' : '关联目录',
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
          badge: '文本节点',
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
