import Plotly from "plotly.js-dist-min";
import type { DemSamplePayload, LabelRow, SegmentPayload } from "./types.js";
import { manualSeedRowsForPlot } from "./plotRows.js";
import { buildProfilePlotConfig, PROFILE_DEFAULT_DRAGMODE } from "./profileControls.js";
import { profileDataRevision } from "./profileRevision.js";
import { plotlyClearSelectionUpdate, plotlySelectionVisibilityStyle } from "./profileSelection.js";
import { profilePointColor } from "./profileColors.js";
import { demSampleRevision, profileDemTracePoints } from "./demTrace.js";

export interface ProfileSettings {
  pointSize: number;
  pointOpacity: number;
  showClassifications: boolean;
  showDem: boolean;
}

export type SelectionHandler = (rows: Set<number>) => void;
export type ProfileRelayoutHandler = (update: Record<string, unknown>) => void;

const RANGE_BY_CONTAINER = new WeakMap<HTMLElement, { segmentId: string; ranges: AxisRanges }>();
const RELAYOUT_EVENTS = ["plotly_relayout", "plotly_relayouting"] as const;
const PLOT_TEXT_COLOR = "#172033";
const PLOT_PAPER_COLOR = "#f6f8fb";
const PLOT_BACKGROUND_COLOR = "#ffffff";
const PLOT_GRID_COLOR = "rgba(15, 23, 42, 0.1)";
const PLOT_ZERO_LINE_COLOR = "rgba(15, 23, 42, 0.18)";
const PLOT_SELECTION_COLOR = "#172033";
const PLOT_DEM_COLOR = "#334155";
const PLOT_MANUAL_SEED_COLOR = "#4f46e5";
const PLOT_SEGMENT_FILL_COLOR = "rgba(37, 99, 235, 0.08)";

export async function renderProfile(
  container: HTMLElement,
  payload: SegmentPayload,
  labels: LabelRow[],
  selectedRows: Set<number>,
  settings: ProfileSettings,
  demSample: DemSamplePayload | null,
  onSelect: SelectionHandler,
  onRelayout?: ProfileRelayoutHandler,
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
  const demTrace = settings.showDem && demSample ? profileDemTracePoints(demSample) : null;

  const traces = [
    {
      type: "scattergl",
      mode: "markers",
      name: "Context",
      ...plotlySelectionVisibilityStyle(1),
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
      ...plotlySelectionVisibilityStyle(settings.pointOpacity),
      x: assignedRows.map((row) => payload.assigned.x_atc_m[row.index] / 1000),
      y: assignedRows.map((row) => payload.assigned.ortho_h_m[row.index]),
      customdata: assignedRows.map((row) => row.sourceRow),
      marker: {
        color: assignedRows.map((row) =>
          profilePointColor(labelByRow.get(row.sourceRow)?.label ?? "no_label", settings.showClassifications),
        ),
        size: settings.pointSize,
        opacity: settings.pointOpacity,
      },
      hovertemplate: "x %{x:.3f} km<br>h %{y:.2f} m<br>row %{customdata}<extra></extra>",
    },
    ...(demTrace
      ? [
          {
            type: "scattergl",
            mode: "lines+markers",
            name: "DEM",
            ...plotlySelectionVisibilityStyle(0.95),
            x: demTrace.xKm,
            y: demTrace.hM,
            marker: {
              color: PLOT_DEM_COLOR,
              size: 3,
              opacity: 0.9,
            },
            line: {
              color: PLOT_DEM_COLOR,
              width: 1,
            },
            hovertemplate: "x %{x:.3f} km<br>DEM %{y:.2f} m<extra>DEM</extra>",
          },
        ]
      : []),
    {
      type: "scattergl",
      mode: "markers",
      name: "Selected",
      ...plotlySelectionVisibilityStyle(0.92),
      x: selected.map((row) => payload.assigned.x_atc_m[row.index] / 1000),
      y: selected.map((row) => payload.assigned.ortho_h_m[row.index]),
      customdata: selected.map((row) => row.sourceRow),
      marker: {
        color: "rgba(255, 255, 255, 0.95)",
        size: settings.pointSize + 4,
        opacity: 0.92,
        symbol: "circle-open",
        line: { width: 2, color: PLOT_SELECTION_COLOR },
      },
      hovertemplate: "selected row %{customdata}<extra></extra>",
    },
    {
      type: "scattergl",
      mode: "markers",
      name: "Manual seeds",
      ...plotlySelectionVisibilityStyle(0.95),
      x: manualSeeds.map((row) => payload.assigned.x_atc_m[row.index] / 1000),
      y: manualSeeds.map((row) => payload.assigned.ortho_h_m[row.index]),
      customdata: manualSeeds.map((row) => row.sourceRow),
      marker: {
        color: "rgba(255, 255, 255, 0)",
        size: settings.pointSize + 6,
        opacity: 0.95,
        symbol: "circle-open",
        line: { width: 2, color: PLOT_MANUAL_SEED_COLOR },
      },
      hovertemplate: "manual seed row %{customdata}<extra></extra>",
    },
  ];

  await Plotly.react(
    container,
    traces,
    {
      margin: { l: 56, r: 18, t: 20, b: 42 },
      paper_bgcolor: PLOT_PAPER_COLOR,
      plot_bgcolor: PLOT_BACKGROUND_COLOR,
      font: { color: PLOT_TEXT_COLOR },
      dragmode: PROFILE_DEFAULT_DRAGMODE,
      showlegend: false,
      xaxis: {
        title: { text: "x_atc (km)" },
        gridcolor: PLOT_GRID_COLOR,
        range: fixedRanges.x,
        zeroline: false,
      },
      yaxis: {
        title: { text: "ortho_h (m)" },
        gridcolor: PLOT_GRID_COLOR,
        range: fixedRanges.y,
        zerolinecolor: PLOT_ZERO_LINE_COLOR,
      },
      uirevision: payload.segment.segment_id,
      datarevision: profileDataRevision(labels, selectedRows, {
        ...settings,
        demRevision: demSampleRevision(settings.showDem ? demSample : null),
      }),
      shapes: [
        {
          type: "rect",
          xref: "x",
          yref: "paper",
          x0: payload.segment.x_atc_start_m / 1000,
          x1: payload.segment.x_atc_end_m / 1000,
          y0: 0,
          y1: 1,
          fillcolor: PLOT_SEGMENT_FILL_COLOR,
          line: { width: 0 },
          layer: "below",
        },
      ],
    },
    buildProfilePlotConfig(() => {
      resetProfileRanges(container, payload.segment.segment_id, initialRanges);
    }),
  );
  await Plotly.restyle(
    container,
    plotlyClearSelectionUpdate(traces.length),
    traces.map((_, index) => index),
  );

  container.dataset.segmentId = payload.segment.segment_id;
  RANGE_BY_CONTAINER.set(container, { segmentId: payload.segment.segment_id, ranges: fixedRanges });
  attachRangeHandler(container, payload.segment.segment_id, fixedRanges, onRelayout);
  attachSelectionHandlers(container, onSelect);
}

export function clearProfile(container: HTMLElement): void {
  Plotly.purge(container);
}

export async function setProfileXRange(container: HTMLElement, range: [number, number]): Promise<void> {
  await Plotly.relayout(container, { "xaxis.range": range });
}

export function getProfileXRange(container: HTMLElement): [number, number] | null {
  return readCurrentRanges(container)?.x ?? null;
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

function attachRangeHandler(
  container: HTMLElement,
  segmentId: string,
  fallbackRanges: AxisRanges,
  onRelayout?: ProfileRelayoutHandler,
): void {
  const plot = container as HTMLElement & {
    removeAllListeners?: (eventName: string) => void;
    on?: (eventName: string, handler: (event: PlotRelayoutEvent) => void) => void;
  };
  for (const eventName of RELAYOUT_EVENTS) {
    plot.removeAllListeners?.(eventName);
  }
  const handleRelayout = (event: PlotRelayoutEvent) => {
    const stored = RANGE_BY_CONTAINER.get(container);
    const base = stored?.segmentId === segmentId ? stored.ranges : fallbackRanges;
    const ranges = rangesFromRelayout(event, base);
    if (ranges) {
      RANGE_BY_CONTAINER.set(container, { segmentId, ranges });
    }
    onRelayout?.(event);
  };
  for (const eventName of RELAYOUT_EVENTS) {
    plot.on?.(eventName, handleRelayout);
  }
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
