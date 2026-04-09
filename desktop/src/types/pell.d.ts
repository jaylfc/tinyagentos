declare module "pell" {
  export function init(config: {
    element: HTMLElement;
    onChange: (html: string) => void;
    actions: string[];
  }): { content: HTMLElement };
}
