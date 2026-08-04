import { Node } from '@tiptap/core';
import { ReactNodeViewRenderer } from '@tiptap/react';
import QuestionFigureView from './QuestionFigureView';
import QuestionFormulaView from './QuestionFormulaView';

export const QuestionFigureNode = Node.create({
  name: 'questionFigure',
  group: 'inline',
  inline: true,
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      figureId: {
        default: '',
        parseHTML: (element) => element.getAttribute('data-question-figure') || '',
        renderHTML: (attributes) => ({ 'data-question-figure': attributes.figureId }),
      },
      src: {
        default: '',
        parseHTML: (element) => element.getAttribute('data-question-figure-src') || '',
        renderHTML: (attributes) => ({ 'data-question-figure-src': attributes.src }),
      },
      displayScale: {
        default: 60,
        parseHTML: (element) => Number(element.getAttribute('data-question-figure-scale') || 60),
        renderHTML: (attributes) => ({ 'data-question-figure-scale': attributes.displayScale }),
      },
      displayAlign: {
        default: 'center',
        parseHTML: (element) => element.getAttribute('data-question-figure-align') || 'center',
        renderHTML: (attributes) => ({ 'data-question-figure-align': attributes.displayAlign }),
      },
      label: { default: '题图' },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-question-figure]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      {
        ...HTMLAttributes,
        'data-question-figure': HTMLAttributes.figureId,
        class: 'pv-tiptap-figure-node',
      },
      `图 ${HTMLAttributes.figureId || ''}`,
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(QuestionFigureView);
  },
});

export const QuestionFormulaNode = Node.create({
  name: 'questionFormula',
  group: 'inline',
  inline: true,
  atom: true,

  addAttributes() {
    return {
      latex: {
        default: '',
        parseHTML: (element) => element.getAttribute('data-question-formula') || '',
        renderHTML: (attributes) => ({ 'data-question-formula': attributes.latex }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-question-formula]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      {
        ...HTMLAttributes,
        'data-question-formula': HTMLAttributes.latex,
        class: 'pv-tiptap-formula-node',
      },
      `$${HTMLAttributes.latex || '公式'}$`,
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(QuestionFormulaView);
  },
});

export const QUESTION_EDITOR_NODES = [QuestionFigureNode, QuestionFormulaNode];

export function figureNode(figureId: string, src = '', displayScale = 60, displayAlign: 'left' | 'center' | 'right' = 'center') {
  return { type: 'questionFigure', attrs: { figureId, src, displayScale, displayAlign, label: '题图' } };
}

export function formulaNode(latex = '...') {
  return { type: 'questionFormula', attrs: { latex } };
}
