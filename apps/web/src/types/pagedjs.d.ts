declare module 'pagedjs' {
  export class Previewer {
    preview(source: Node | string, stylesheets?: string[], renderTo?: Element): Promise<unknown>;
  }
}
