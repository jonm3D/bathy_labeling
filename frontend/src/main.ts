import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

import {
  acceptProposal,
  createDefaultLabels,
  importAtl24Classifications,
  labelSelectionWithMode,
  toggleLabelMode,
} from "./labelState.js";
import { createMap } from "./mapView.js";
import { clearProfile, renderProfile, type ProfileSettings } from "./profilePlot.js";
import { fetchLabels, fetchSegment, fetchSegments, requestProposal, saveLabels } from "./api.js";
import type { FinalLabel, LabelRow, SegmentPayload, SegmentSummary } from "./types.js";

const openList = requireElement("segments-open");
const completeList = requireElement("segments-complete");
const segmentCount = requireElement("segment-count");
const activeSegment = requireElement("active-segment");
const statusElement = requireElement("status");
const profile = requireElement("profile");
const mapContainer = requireElement("map");
const classButtons = requireElement("class-buttons");
const runProposal = requireButton("run-proposal");
const importAtl24 = requireButton("import-atl24");
const acceptProposalButton = requireButton("accept-proposal");
const saveLabelsButton = requireButton("save-labels");
const pointSize = requireInput("point-size");
const pointOpacity = requireInput("point-opacity");
const classModeButtons = Array.from(classButtons.querySelectorAll<HTMLButtonElement>("button[data-label]"));

const mapView = createMap(mapContainer);

let segments: SegmentSummary[] = [];
let currentPayload: SegmentPayload | null = null;
let currentLabels: LabelRow[] = [];
let proposalRows: LabelRow[] = [];
let selectedRows = new Set<number>();
let activeLabel: FinalLabel | null = null;
let settings: ProfileSettings = readSettings();

updateClassModeButtons();
void loadSegments();

classButtons.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement)) {
    return;
  }
  const label = target.dataset.label;
  if (!isFinalLabel(label)) {
    return;
  }
  activeLabel = toggleLabelMode(activeLabel, label);
  updateClassModeButtons();
  setStatus(activeLabel ? `${formatLabel(activeLabel)} mode` : "Label mode off");
});

runProposal.addEventListener("click", async () => {
  if (!currentPayload) {
    return;
  }
  setStatus("Running proposal");
  const seeds = currentLabels.filter((row) => row.label_source === "manual");
  const proposal = await requestProposal(currentPayload.segment.segment_id, seeds);
  proposalRows = proposal.rows;
  currentLabels = acceptProposal(currentLabels, proposal.rows);
  setStatus(`Proposal ready: ${countLabels(proposal.rows)}`);
  await rerender();
});

importAtl24.addEventListener("click", async () => {
  if (!currentPayload) {
    return;
  }
  currentLabels = importAtl24Classifications(currentLabels, currentPayload.assigned.atl24_class_ph);
  proposalRows = [];
  setStatus(`Imported ATL24: ${countLabels(currentLabels)}`);
  await rerender();
});

acceptProposalButton.addEventListener("click", async () => {
  if (proposalRows.length === 0) {
    return;
  }
  currentLabels = acceptProposal(currentLabels, proposalRows);
  setStatus(`Proposal accepted: ${countLabels(currentLabels)}`);
  await rerender();
});

saveLabelsButton.addEventListener("click", async () => {
  if (!currentPayload) {
    return;
  }
  setStatus("Saving");
  const saved = await saveLabels(currentPayload.segment.segment_id, currentLabels);
  currentLabels = saved.rows;
  proposalRows = [];
  setStatus("Saved");
  await loadSegments(currentPayload.segment.segment_id);
});

for (const input of [pointSize, pointOpacity]) {
  input.addEventListener("input", () => {
    settings = readSettings();
    void rerender();
  });
}

async function loadSegments(selectSegmentId?: string): Promise<void> {
  setStatus("Loading segments");
  const payload = await fetchSegments();
  segments = payload.segments;
  segmentCount.textContent = `${payload.count.toLocaleString()} segments`;
  renderSegmentLists();
  const nextSegmentId = selectSegmentId ?? segments[0]?.segment_id;
  if (nextSegmentId) {
    await selectSegment(nextSegmentId);
  } else {
    clearProfile(profile);
    activeSegment.textContent = "No segment selected";
  }
  setStatus("");
}

function renderSegmentLists(): void {
  const open = segments.filter((segment) => segment.status !== "complete");
  const complete = segments.filter((segment) => segment.status === "complete");
  openList.replaceChildren(...open.map(segmentButton));
  completeList.replaceChildren(...complete.map(segmentButton));
}

function segmentButton(segment: SegmentSummary): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "segment-button";
  button.dataset.segmentId = segment.segment_id;
  button.innerHTML = `<span>${segment.file_name} ${segment.beam}</span><small>${formatKm(segment.x_atc_start_m)}-${formatKm(segment.x_atc_end_m)} km · ${segment.status}</small>`;
  button.addEventListener("click", () => {
    void selectSegment(segment.segment_id);
  });
  return button;
}

async function selectSegment(segmentId: string): Promise<void> {
  setStatus("Loading segment");
  currentPayload = await fetchSegment(segmentId);
  const labels = await fetchLabels(segmentId);
  currentLabels =
    labels.status === "complete"
      ? labels.rows
      : createDefaultLabels(currentPayload.assigned.source_row);
  proposalRows = [];
  selectedRows = new Set();
  activeSegment.textContent = `${currentPayload.segment.file_name} ${currentPayload.segment.beam} · ${formatKm(currentPayload.segment.x_atc_start_m)}-${formatKm(currentPayload.segment.x_atc_end_m)} km`;
  mapView.setSegment(currentPayload);
  await rerender();
  setStatus(`${currentPayload.assigned.source_row.length.toLocaleString()} assigned photons`);
}

async function rerender(): Promise<void> {
  if (!currentPayload) {
    return;
  }
  await renderProfile(profile, currentPayload, currentLabels, selectedRows, settings, (rows) => {
    void handleProfileSelection(rows);
  });
}

async function handleProfileSelection(rows: Set<number>): Promise<void> {
  selectedRows = rows;
  if (activeLabel && rows.size > 0) {
    currentLabels = labelSelectionWithMode(currentLabels, rows, activeLabel);
    proposalRows = [];
    setStatus(`Set ${rows.size.toLocaleString()} ${formatLabel(activeLabel).toLowerCase()} photons`);
  }
  await rerender();
}

function readSettings(): ProfileSettings {
  return {
    pointSize: Number.parseFloat(pointSize.value),
    pointOpacity: Number.parseFloat(pointOpacity.value),
  };
}

function countLabels(labels: LabelRow[]): string {
  const counts = new Map<FinalLabel, number>();
  for (const row of labels) {
    counts.set(row.label, (counts.get(row.label) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([label, count]) => `${label} ${count}`)
    .join(", ");
}

function updateClassModeButtons(): void {
  for (const button of classModeButtons) {
    const label = button.dataset.label;
    const isActive = label === activeLabel;
    button.setAttribute("aria-pressed", String(isActive));
    button.classList.toggle("is-active", isActive);
  }
}

function formatLabel(label: FinalLabel): string {
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function formatKm(meters: number): string {
  return (meters / 1000).toFixed(1);
}

function setStatus(message: string): void {
  statusElement.textContent = message;
}

function requireElement(id: string): HTMLElement {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing element: ${id}`);
  }
  return element;
}

function requireButton(id: string): HTMLButtonElement {
  const element = requireElement(id);
  if (!(element instanceof HTMLButtonElement)) {
    throw new Error(`Element is not a button: ${id}`);
  }
  return element;
}

function requireInput(id: string): HTMLInputElement {
  const element = requireElement(id);
  if (!(element instanceof HTMLInputElement)) {
    throw new Error(`Element is not an input: ${id}`);
  }
  return element;
}

function isFinalLabel(value: string | undefined): value is FinalLabel {
  return value === "surface" || value === "bathy" || value === "land" || value === "noise" || value === "ambiguous";
}
