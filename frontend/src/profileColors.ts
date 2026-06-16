import type { FinalLabel } from "./types.js";

export const GREY_POINT_COLOR = "#8d99ae";

export const CLASS_COLORS: Record<FinalLabel, string> = {
  surface: "#0072b2",
  bathy: "#d55e00",
  no_label: "#8b95a1",
  land: "#8f6b3f",
  noise: "#6b7280",
  ambiguous: "#7c3aed",
};

export function labelColorForClass(label: FinalLabel): string {
  return CLASS_COLORS[label];
}

export function profilePointColor(label: FinalLabel, showClassifications: boolean): string {
  return showClassifications ? labelColorForClass(label) : GREY_POINT_COLOR;
}
