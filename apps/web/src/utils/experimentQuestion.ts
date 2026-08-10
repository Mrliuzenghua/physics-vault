import type { Option } from '../types';

/**
 * Experiment procedures occasionally arrive from OCR in the generic options
 * field. They are not selectable answers, so normalize them into stem text.
 */
export function experimentStepsToText(options: Option[]): string {
  return options
    .map((option, index) => String(option.content || '').trim() && `（${index + 1}）${String(option.content).trim()}`)
    .filter((step): step is string => Boolean(step))
    .join('\n\n');
}

export function mergeExperimentStepsIntoTitle(title: string, options: Option[]): string {
  const steps = experimentStepsToText(options);
  if (!steps) return title.trim();
  const trimmedTitle = title.trim();
  const hasStepHeading = /(?:主要)?实验步骤(?:如下)?[：:]?/.test(trimmedTitle);
  return [trimmedTitle, hasStepHeading ? '' : '实验步骤：', steps]
    .filter(Boolean)
    .join('\n\n');
}
