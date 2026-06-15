import Plotly from "plotly.js-dist-min";
import type { FinalLabel, LabelRow, SegmentPayload } from "./types.js";
import { manualSeedRowsForPlot } from "./plotRows.js";
import { buildProfilePlotConfig } from "./profileControls.js";

export interface ProfileSettings {
  pointSize: number;
  pointOpacity: number;
}

export type SelectionHandler = (rows: Set<number>) => void;

const LABEL_COLORS: Record<FinalLabel, string> = {
  surface: "#4cc9f0",
  bathy: "#2a9d8f",
  no_label: "#8d99ae",
  land: "#b08968",
  noise: "#8d99ae",
  ambiguous: "#f4a261",
};

const RANGE_BY_CONTAINER = new WeakMap<HTMLElement, { segmentId: string; ranges: AxisRanges }>();

export async function renderProfile(
  container: HTMLElement,
  payload: SegmentPayload,
  labels: LabelRow[],
  selectedRows: Set<number>,
  settings: ProfileSettings,
  onSelect: SelectionHandler,
): Promise<void> {
  const labelByRow = new Map(labels.map((row) => [row.source_row, row]));
  const contextRows = payload.context.source_row.map((sourceRow, index) => ({ sourceRow, index }));
  const assignedRows = payload.assigned.source_row.map((sourceRow, index) => ({ sourceRow, index }));
  const selected = assignedRows.filter((row) => selectedRows.has(row.sourceRow));
  const manualSeeds = manualSeedRowsForPlot(labels, assignedRows);
  const sameSegment = container.dataset.segmentId === payload.segment.segment_id;
  const storedRangeState = RANGE_BY_CONTAINER.get(container);
  const storedRanges =
    sameSegment && storedRangeState?.segmentId === payload.segment.segment_id ? storedRangeState.ranges : null;
  const currentRanges = sameSegment ? readCurrentRanges(container) : null;
  const initialRanges = computeInitialRanges(payload);
  const fixedRanges = currentRanges ?? storedRanges ?? initialRanges;

  await Plotly.react(
    container,
    [
      {
        type: "scattergl",
        mode: "markers",
        name: "Context",
        x: contextRows.map((row) => payload.context.x_atc_m[row.index] / 1000),
        y: contextRows.map((row) => payload.context.ortho_h_m[row.index]),
        customdata: contextRows.map((row) => row.sourceRow),
        marker: {
          color: "rgba(88, 96, 110, 0.32)",
          size: Math.max(1, settings.pointSize - 1),
        },
        hovertemplate: "x %{x:.3f} km<br>h %{y:.2f} m<extra>context</extra>",
      },
      {
        type: "scattergl",
        mode: "markers",
        name: "Assigned",
        x: assignedRows.map((row) => payload.assigned.x_atc_m[row.index] / 1000),
        y: assignedRows.map((row) => payload.assigned.ortho_h_m[row.index]),
        customdata: assignedRows.map((row) => row.sourceRow),
        marker: {
          color: assignedRows.map((row) => LABEL_COLORS[labelByRow.get(row.sourceRow)?.label ?? "no_label"]),
          size: settings.pointSize,
          opacity: settings.pointOpacity,
        },
        hovertemplate: "x %{x:.3f} km<br>h %{y:.2f} m<br>row %{customdata}<extra></extra>",
      },
      {
        type: "scattergl",
        mode: "markers",
        name: "Selected",
        x: selected.map((row) => payload.assigned.x_atc_m[row.index] / 1000),
        y: selected.map((row) => payload.assigned.ortho_h_m[row.index]),
        customdata: selected.map((row) => row.sourceRow),
        marker: {
          color: "rgba(255, 255, 255, 0.95)",
          size: settings.pointSize + 4,
          opacity: 0.92,
          symbol: "circle-open",
          line: { width: 2, color: "#111827" },
        },
        hovertemplate: "selected row %{customdata}<extra></extra>",
      },
      {
        type: "scattergl",
        mode: "markers",
        name: "Manual seeds",
        x: manualSeeds.map((row) => payload.assigned.x_atc_m[row.index] / 1000),
        y: manualSeeds.map((row) => payload.assigned.ortho_h_m[row.index]),
        customdata: manualSeeds.map((row) => row.sourceRow),
        marker: {
          color: "rgba(255, 255, 255, 0)",
          size: settings.pointSize + 6,
          opacity: 0.95,
          symbol: "circle-open",
          line: { width: 2, color: "#f97316" },
        },
        hovertemplate: "manual seed row %{customdata}<extra></extra>",
      },
    ],
    {
      margin: { l: 56, r: 18, t: 20, b: 42 },
      paper_bgcolor: "#f8fafc",
      plot_bgcolor: "#ffffff",
      font: { color: "#172033" },
      dragmode: "lasso",
      showlegend: false,
      xaxis: {
        title: { text: "x_atc (km)" },
        gridcolor: "rgba(15, 23, 42, 0.1)",
        range: fixedRanges.x,
        zeroline: false,
      },
      yaxis: {
        title: { text: "ortho_h (m)" },
        gridcolor: "rgba(15, 23, 42, 0.1)",
        range: fixedRanges.y,
        zerolinecolor: "rgba(15, 23, 42, 0.18)",
      },
      uirevision: payload.segment.segment_id,
      shapes: [
        {
          type: "rect",
          xref: "x",
          yref: "paper",
          x0: payload.segment.x_atc_start_m / 1000,
          x1: payload.segment.x_atc_end_m / 1000,
          y0: 0,
          y1: 1,
          fillcolor: "rgba(42, 157, 143, 0.08)",
          line: { width: 0 },
          layer: "below",
        },
      ],
    },
    buildProfilePlotConfig(() => {
      resetProfileRanges(container, payload.segment.segment_id, initialRanges);
    }),
  );

  container.dataset.segmentId = payload.segment.segment_id;
  RANGE_BY_CONTAINER.set(container, { segmentId: payload.segment.segment_id, ranges: fixedRanges });
  attachRangeHandler(container, payload.segment.segment_id, fixedRanges);
  attachSelectionHandlers(container, onSelect);
}

export function clearProfile(container: HTMLElement): void {
  Plotly.purge(container);
}

function resetProfileRanges(container: HTMLElement, segmentId: string, ranges: AxisRanges): void {
  RANGE_BY_CONTAINER.set(container, { segmentId, ranges });
  void Plotly.relayout(container, {
    "xaxis.autorange": false,
    "xaxis.range": ranges.x,
    "yaxis.autorange": false,
    "yaxis.range": ranges.y,
  });
}

function attachSelectionHandlers(container: HTMLElement, onSelect: SelectionHandler): void {
  const plot = container as HTMLElement & {
    removeAllListeners?: (eventName: string) => void;
    on?: (eventName: string, handler: (event: PlotSelectionEvent) => void) => void;
  };
  for (const eventName of ["plotly_click", "plotly_selected"]) {
    plot.removeAllListeners?.(eventName);
  }
  plot.on?.("plotly_click", (event) => {
    onSelect(rowsFromEvent(event));
  });
  plot.on?.("plotly_selected", (event) => {
    onSelect(rowsFromEvent(event));
  });
}

function attachRangeHandler(container: HTMLElement, segmentId: string, fallbackRanges: AxisRanges): void {
  const plot = container as HTMLElement & {
    removeAllListeners?: (eventName: string) => void;
    on?: (eventName: string, handler: (event: PlotRelayoutEvent) => void) => void;
  };
  plot.removeAllListeners?.("plotly_relayout");
  plot.on?.("plotly_relayout", (event) => {
    const stored = RANGE_BY_CONTAINER.get(container);
    const base = stored?.segmentId === segmentId ? stored.ranges : fallbackRanges;
    const ranges = rangesFromRelayout(event, base);
    if (ranges) {
      RANGE_BY_CONTAINER.set(container, { segmentId, ranges });
    }
  });
}

interface PlotSelectionEvent {
  points?: Array<{ customdata?: unknown }>;
}

type PlotRelayoutEvent = Record<string, unknown>;

function rowsFromEvent(event: PlotSelectionEvent): Set<number> {
  const rows = new Set<number>();
  for (const point of event.points ?? []) {
    if (typeof point.customdata === "number") {
      rows.add(point.customdata);
    }
  }
  return rows;
}

interface AxisRanges {
  x: [number, number];
  y: [number, number];
}

function readCurrentRanges(container: HTMLElement): AxisRanges | null {
  const plot = container as HTMLElement & {
    _fullLayout?: {
      xaxis?: { range?: unknown };
      yaxis?: { range?: unknown };
    };
  };
  const x = readRange(plot._fullLayout?.xaxis?.range);
  const y = readRange(plot._fullLayout?.yaxis?.range);
  return x && y ? { x, y } : null;
}

function readRange(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length !== 2) {
    return null;
  }
  const start = Number(value[0]);
  const end = Number(value[1]);
  return Number.isFinite(start) && Number.isFinite(end) ? [start, end] : null;
}

function rangesFromRelayout(event: PlotRelayoutEvent, base: AxisRanges): AxisRanges | null {
  const x = readRelayoutRange(event, "xaxis") ?? base.x;
  const y = readRelayoutRange(event, "yaxis") ?? base.y;
  const changed = readRelayoutRange(event, "xaxis") !== null || readRelayoutRange(event, "yaxis") !== null;
  return changed ? { x, y } : null;
}

function readRelayoutRange(event: PlotRelayoutEvent, axisName: "xaxis" | "yaxis"): [number, number] | null {
  return readRange(event[`${axisName}.range`]) ?? readRange([event[`${axisName}.range[0]`], event[`${axisName}.range[1]`]]);
}

function computeInitialRanges(payload: SegmentPayload): AxisRanges {
  const xValues = payload.context.x_atc_m.map((value) => value / 1000);
  const yValues = payload.context.ortho_h_m;
  return {
    x: paddedRange(xValues, 0.05),
    y: paddedRange(yValues, 0.08),
  };
}

function paddedRange(values: number[], fraction: number): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const value of values) {
    if (Number.isFinite(value)) {
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [0, 1];
  }
  if (min === max) {
    const pad = Math.max(1, Math.abs(min) * fraction);
    return [min - pad, max + pad];
  }
  const pad = (max - min) * fraction;
  return [min - pad, max + pad];
}
