import type { FinalLabel } from "./types.js";

export const GREY_POINT_COLOR = "#8d99ae";

const LABEL_COLORS: Record<FinalLabel, string> = {
  surface: "#4cc9f0",
  bathy: "#ef4444",
  no_label: GREY_POINT_COLOR,
  land: "#b08968",
  noise: GREY_POINT_COLOR,
  ambiguous: "#f4a261",
};

export function profilePointColor(label: FinalLabel, showClassifications: boolean): string {
  return showClassifications ? LABEL_COLORS[label] : GREY_POINT_COLOR;
}
