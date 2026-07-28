const DISPLAY_MATH_RE = /\$\$([^\n]*?)\$\$/g;
const MIXED_MATH_RE = /(?<!\$)\$([^\n$]{1,140}?)\$\$(?!\$)|(?<!\$)\$\$([^\n$]{1,140}?)\$(?!\$)/g;
const BLOCK_HINTS = ['\\begin', '\\end', '\\\\', '\\tag', '\\left.', '\\right.'];

export function normalizeShortInlineDisplayMath(text: string): string {
  if (!text || !text.includes('$$')) return text;
  return text
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map(normalizeMathLine)
    .join('\n');
}

function normalizeMathLine(line: string): string {
  return line
    .replace(DISPLAY_MATH_RE, (full, formula: string) => {
      const trimmed = formula.trim();
      if (!shouldDowngrade(line, full, trimmed)) return full;
      return `$${trimmed}$`;
    })
    .replace(MIXED_MATH_RE, (full, leftFormula: string | undefined, rightFormula: string | undefined) => {
      const formula = (leftFormula ?? rightFormula ?? '').trim();
      if (!shouldDowngrade(line, full, formula)) return full;
      return `$${formula}$`;
    });
}

function shouldDowngrade(line: string, full: string, formula: string): boolean {
  if (!formula) return false;
  if (line.trim() === full) return false;
  if (formula.length > 140) return false;
  if (BLOCK_HINTS.some((hint) => formula.includes(hint))) return false;
  return true;
}
