declare module 'viewerjs' {
  interface ViewerOptions {
    navbar?: boolean;
    toolbar?: boolean;
    title?: boolean;
  }

  export default class Viewer {
    constructor(element: Element, options?: ViewerOptions);
    destroy(): void;
  }
}

declare module 'docx-preview' {
  export function renderAsync(
    data: ArrayBuffer | Blob,
    container: HTMLElement,
    styleContainer?: HTMLElement,
    options?: Record<string, unknown>,
  ): Promise<unknown>;
}

declare module '*.mjs?url' {
  const source: string;
  export default source;
}
