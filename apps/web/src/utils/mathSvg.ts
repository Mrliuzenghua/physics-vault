let rendererPromise: Promise<(latex: string, display: boolean) => string> | null = null;

function toBase64(value: string): string {
  return window.btoa(unescape(encodeURIComponent(value)));
}

/** Renders a LaTeX fragment into a self-contained SVG data URI for Office exports. */
async function getRenderer(): Promise<(latex: string, display: boolean) => string> {
  if (!rendererPromise) {
    rendererPromise = Promise.all([
      import('mathjax-full/js/mathjax.js'),
      import('mathjax-full/js/input/tex.js'),
      import('mathjax-full/js/output/svg.js'),
      import('mathjax-full/js/adaptors/liteAdaptor.js'),
      import('mathjax-full/js/handlers/html.js'),
    ]).then(([{ mathjax }, { TeX }, { SVG }, { liteAdaptor }, { RegisterHTMLHandler }]) => {
      const adaptor = liteAdaptor();
      RegisterHTMLHandler(adaptor);
      const tex = new TeX({ packages: ['base', 'ams'] });
      const svg = new SVG({ fontCache: 'none' });
      const document = mathjax.document('', { InputJax: tex, OutputJax: svg });
      return (latex: string, display: boolean) => adaptor.outerHTML(document.convert(latex, { display }));
    });
  }
  return rendererPromise;
}

export async function latexToSvgDataUri(latex: string, display = false): Promise<string | null> {
  const source = String(latex || '').trim();
  if (!source) return null;
  try {
    const render = await getRenderer();
    const markup = render(source, display);
    return `data:image/svg+xml;base64,${toBase64(markup)}`;
  } catch {
    return null;
  }
}

export function extractLatexFragments(value: string, limit = 3): string[] {
  const matches = String(value || '').matchAll(/\$\$?([\s\S]*?)\$\$?|\\\[([\s\S]*?)\\\]/g);
  const unique = new Set<string>();
  for (const match of matches) {
    const fragment = (match[1] || match[2] || '').trim();
    if (fragment) unique.add(fragment);
    if (unique.size >= limit) break;
  }
  return [...unique];
}
