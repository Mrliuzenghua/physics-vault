import type { Question } from '../types';
import type { SlideDeck, SlideDeckBuilderInput, SlidePage } from '../types/slides';

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multi_choice: '多选题',
  fill: '填空题',
  experiment: '实验题',
  calculation: '计算题',
};

function questionToSlide(question: Question, index: number): SlidePage {
  return {
    id: `q-${question.question_id}`,
    pageType: 'question_explain',
    title: `第 ${index + 1} 题`,
    subtitle: question.knowledge_point || undefined,
    badge: TYPE_LABELS[question.question_type] || question.question_type,
    layout: 'single_column',
    sections: [],
    footer: question.source || undefined,
  };
}

export function buildSlideDeck(input: SlideDeckBuilderInput): SlideDeck {
  const { template, title, subtitle, knowledgePages, questionPages } = input;
  const questionSlides = questionPages.map((question, index) => questionToSlide(question, index));
  const pages: SlidePage[] = [];

  switch (template) {
    case 'teach_practice_teach':
      pages.push(...knowledgePages.slice(0, Math.ceil(knowledgePages.length / 2)));
      pages.push(...questionSlides);
      pages.push(...knowledgePages.slice(Math.ceil(knowledgePages.length / 2)));
      break;
    case 'teach_then_practice':
      pages.push(...knowledgePages);
      pages.push(...questionSlides);
      break;
    case 'practice_only':
      pages.push(...questionSlides);
      break;
  }

  return {
    id: `deck-${Date.now()}`,
    title,
    subtitle: subtitle || `${questionPages.length} 道题 · ${knowledgePages.length} 个知识点页面`,
    theme: 'physics',
    pages,
  };
}
