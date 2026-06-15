export interface PlotlySelectionVisibilityStyle {
  selectedpoints: null;
  selected: { marker: { opacity: number } };
  unselected: { marker: { opacity: number } };
}

export function plotlySelectionVisibilityStyle(markerOpacity: number): PlotlySelectionVisibilityStyle {
  return {
    selectedpoints: null,
    selected: { marker: { opacity: markerOpacity } },
    unselected: { marker: { opacity: markerOpacity } },
  };
}

export function plotlyClearSelectionUpdate(traceCount: number): { selectedpoints: null[] } {
  return {
    selectedpoints: Array.from({ length: traceCount }, () => null),
  };
}
