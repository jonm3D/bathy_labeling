declare module "plotly.js-dist-min" {
  const Plotly: {
    react: (root: HTMLElement, data: unknown[], layout: Record<string, unknown>, config?: Record<string, unknown>) => Promise<void>;
    relayout: (root: HTMLElement, update: Record<string, unknown>) => Promise<void>;
    restyle: (root: HTMLElement, update: Record<string, unknown>, traceIndices?: number[]) => Promise<void>;
    purge: (root: HTMLElement) => void;
  };
  export default Plotly;
}
