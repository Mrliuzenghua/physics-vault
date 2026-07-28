/**
 * 课堂 PPT 数据结构
 *
 * 层级: SlideDeck → SlidePage → SlideSection → SlideItem
 *
 * 数据层与渲染层职责分离：
 * - 本文件定义"PPT 页面输入数据模型"，供渲染组件消费
 * - 未来可从知识点缓存、模板系统、题库题目生成 slide 数据
 * - 不直接耦合数据库表结构
 */

// ── SlideItem（最小内容单元）─────────────────────────────────────

export interface SlideItem {
  /** 正文文本 */
  text: string;
  /** 唯一标识（兼容旧组件） */
  id?: string;
  /** 前置标签，例如 "方法" "公式" "易错" */
  label?: string;
  /** 高亮强调 */
  highlight?: boolean;
  /** @deprecated 请使用 highlight */
  emphasis?: boolean;
  /** 图标 emoji 或 codepoint */
  icon?: string;
  /** 关联公式（LaTeX 源码） */
  formula?: string;
  /** 图片路径 */
  imagePath?: string;
  /** 图片替代文本 */
  imageAlt?: string;
  /** 子条目（用于嵌套列表） */
  children?: SlideItem[];
}

// ── SlideSection（页面内容区块）─────────────────────────────────

export type SlideSectionType =
  | 'summary'
  | 'method'
  | 'warning'
  | 'example'
  | 'formula'
  | 'figure'
  | 'question'
  | 'analysis';

export interface SlideSection {
  id: string;
  type: SlideSectionType;
  /** 区块标题 */
  title: string;
  /** 区块内容条目 */
  items: SlideItem[];
  /** 补充说明（渲染为脚注或小字） */
  note?: string;
  /** 列数：1 = 单列, 2 = 双列 */
  columns?: 1 | 2;
}

// ── SlidePage（单页幻灯片）───────────────────────────────────────

export type SlidePageType =
  | 'knowledge_summary'
  | 'method_summary'
  | 'example_intro'
  | 'exercise_transition'
  | 'question_explain'
  | 'warning_summary';

export type SlideLayout =
  | 'single_column'
  | 'two_column'
  | 'three_card'
  | 'hero_with_sidebar'
  | 'grid_2x2';

export interface SlidePage {
  id: string;
  /** 页面类型 */
  pageType: SlidePageType;
  /** 页面主标题 */
  title: string;
  /** 副标题 */
  subtitle?: string;
  /** 页面标签（渲染为标题旁的 chip） */
  badge?: string;
  /** 布局模式 */
  layout: SlideLayout;
  /** 内容区块列表 */
  sections: SlideSection[];
  /** 页脚文字 */
  footer?: string;
}

// ── SlideDeck（整套课件）─────────────────────────────────────────

export interface SlideDeck {
  id: string;
  /** 课件主标题 */
  title: string;
  /** 课件副标题（学科 / 阶段 / 班型） */
  subtitle: string;
  /** 主题色标识（供渲染层选用配色方案） */
  theme: 'physics' | 'chemistry' | 'math' | 'general';
  /** 页面列表 */
  pages: SlidePage[];
}

// ── SlideDeck Builder Types ───────────────────────────────────────

export type SlideDeckTemplate = 'teach_practice_teach' | 'teach_then_practice' | 'practice_only';

export const SLIDE_DECK_TEMPLATE_LABELS: Record<SlideDeckTemplate, string> = {
  teach_practice_teach: '讲-练-讲（知识→习题→总结）',
  teach_then_practice: '先讲后练（知识页→习题页）',
  practice_only: '纯练（仅习题页）',
};

export interface SlideDeckBuilderInput {
  template: SlideDeckTemplate;
  title: string;
  subtitle?: string;
  knowledgePages: SlidePage[];
  questionPages: import('../types').Question[];
}
