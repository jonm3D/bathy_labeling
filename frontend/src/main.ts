import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

import {
  acceptProposal,
  createDefaultLabels,
  labelSelectionWithMode,
  labelsForAppMode,
  toggleLabelMode,
} from "./labelState.js";
import { createMap } from "./mapView.js";
import { clearProfile, renderProfile, type ProfileSettings } from "./profilePlot.js";
import {
  configureReprocessSession,
  fetchLabels,
  fetchManifest,
  fetchReprocessBeam,
  fetchReprocessSources,
  fetchSegment,
  fetchSegments,
  requestProposal,
  requestReprocessProposal,
  resetReprocessBeam,
  saveLabels,
  saveReprocessSource,
} from "./api.js";
import type {
  FinalLabel,
  LabelRow,
  ManifestPayload,
  ReprocessBeamPayload,
  ReprocessSource,
  SegmentPayload,
  SegmentSummary,
} from "./types.js";

type AppMode = "reprocess" | "training";

const setupPanel = requireElement("setup-panel");
const inputDir = requireInput("input-dir");
const outputDir = requireInput("output-dir");
const loadSessionButton = requireButton("load-session");
const fileHeading = requireElement("file-heading");
const beamHeading = requireElement("beam-heading");
const fileList = requireElement("file-list");
const beamList = requireElement("beam-list");
const segmentCount = requireElement("segment-count");
const activeSegment = requireElement("active-segment");
const statusElement = requireElement("status");
const profile = requireElement("profile");
const mapContainer = requireElement("map");
const classButtons = requireElement("class-buttons");
const runProposal = requireButton("run-proposal");
const showClassificationsButton = requireButton("show-classifications");
const resetAtl24 = requireButton("reset-atl24");
const saveLabelsButton = requireButton("save-labels");
const clearSelectionButton = requireButton("clear-selection");
const pointSize = requireInput("point-size");
const pointOpacity = requireInput("point-opacity");
let classModeButtons: HTMLButtonElement[] = [];

const mapView = createMap(mapContainer);

let appMode: AppMode = "reprocess";
let segments: SegmentSummary[] = [];
let reprocessSources: ReprocessSource[] = [];
let currentPayload: SegmentPayload | null = null;
let currentLabels: LabelRow[] = [];
let selectedRows = new Set<number>();
let activeLabel: FinalLabel | null = null;
let settings: ProfileSettings = readSettings();
let currentSegmentId: string | null = null;
let currentSource: string | null = null;
let currentBeam: string | null = null;
let selectedReprocessSource: string | null = null;
const reprocessLabelCache = new Map<string, LabelRow[]>();

configureLabelButtonsForMode("reprocess");
updateShowClassificationsButton();
void boot();

loadSessionButton.addEventListener("click", () => {
  void configureAndLoadReprocessSession();
});

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
  if (activeLabel && selectedRows.size > 0) {
    void applyLabelToSelectedRows(activeLabel);
    return;
  }
  setStatus(activeLabel ? `${formatLabel(activeLabel)} mode` : "Label mode off");
});

runProposal.addEventListener("click", async () => {
  if (!currentPayload) {
    return;
  }
  if (appMode === "reprocess") {
    await runReprocessProposal();
  } else {
    await runTrainingProposal();
  }
});

resetAtl24.addEventListener("click", async () => {
  if (appMode !== "reprocess" || !currentSource || !currentBeam) {
    return;
  }
  const reset = await resetReprocessBeam(currentSource, currentBeam);
  currentLabels = reset.rows;
  selectedRows = new Set();
  cacheCurrentReprocessLabels();
  setStatus("Reset to ATL24");
  await rerender();
});

saveLabelsButton.addEventListener("click", async () => {
  if (!currentPayload) {
    return;
  }
  if (appMode === "reprocess") {
    await saveCurrentReprocessSource();
  } else {
    await saveCurrentTrainingSegment();
  }
});

clearSelectionButton.addEventListener("click", () => {
  void clearCurrentSelection();
});

showClassificationsButton.addEventListener("click", () => {
  settings = {
    ...settings,
    showClassifications: !settings.showClassifications,
  };
  updateShowClassificationsButton();
  setStatus(settings.showClassifications ? "Classifications shown" : "Grey points");
  void rerender();
});

for (const input of [pointSize, pointOpacity]) {
  input.addEventListener("input", () => {
    settings = readSettings();
    void rerender();
  });
}

async function boot(): Promise<void> {
  setStatus("Loading");
  const manifest = await fetchManifest();
  if (manifest.mode === "reprocess") {
    await initializeReprocessMode(manifest);
  } else {
    await initializeTrainingMode();
  }
}

async function initializeReprocessMode(manifest: ManifestPayload): Promise<void> {
  appMode = "reprocess";
  setupPanel.hidden = false;
  fileHeading.textContent = "Files";
  beamHeading.textContent = "Beams";
  configureLabelButtonsForMode("reprocess");
  runProposal.textContent = "Run Smart Labeler";
  resetAtl24.hidden = false;
  saveLabelsButton.textContent = "Save H5";
  inputDir.value = manifest.input_dir ?? "";
  outputDir.value = manifest.output_dir ?? manifest.suggested_output_dir ?? defaultOutputDir(inputDir.value);
  if (manifest.configured) {
    if (!manifest.output_dir && inputDir.value && outputDir.value) {
      await configureReprocessSession(inputDir.value, outputDir.value);
    }
    await loadReprocessSources();
  } else {
    segmentCount.textContent = "Choose folders";
    activeSegment.textContent = "No beam selected";
    fileList.replaceChildren();
    beamList.replaceChildren();
    setStatus("");
  }
}

async function configureAndLoadReprocessSession(): Promise<void> {
  const inputValue = inputDir.value.trim();
  if (!inputValue) {
    setStatus("Input folder required");
    return;
  }
  if (!outputDir.value.trim()) {
    outputDir.value = defaultOutputDir(inputValue);
  }
  setStatus("Loading ATL24 folder");
  await configureReprocessSession(inputValue, outputDir.value.trim());
  reprocessLabelCache.clear();
  currentPayload = null;
  currentLabels = [];
  selectedRows = new Set();
  updateSelectionControls();
  selectedReprocessSource = null;
  await loadReprocessSources();
}

async function loadReprocessSources(): Promise<void> {
  const payload = await fetchReprocessSources();
  reprocessSources = payload.sources;
  segmentCount.textContent = `${payload.count.toLocaleString()} files`;
  const first = reprocessSources[0];
  selectedReprocessSource = first?.source_relative_path ?? null;
  renderReprocessSourceList();
  if (first?.beams[0]) {
    await selectReprocessBeam(first.source_relative_path, first.beams[0]);
  } else {
    clearProfile(profile);
    updateSelectionControls();
    activeSegment.textContent = "No beam selected";
    setStatus("No ATL24 beams found");
  }
}

function renderReprocessSourceList(): void {
  fileList.replaceChildren(...reprocessSources.map(reprocessFileButton));
  renderReprocessBeamList(selectedReprocessSource);
  updateReprocessSelectionButtons();
}

function renderReprocessBeamList(sourceRelativePath: string | null): void {
  const source = reprocessSources.find((candidate) => candidate.source_relative_path === sourceRelativePath);
  if (!source) {
    beamList.replaceChildren();
    return;
  }
  beamList.replaceChildren(...source.beams.map((beam) => reprocessBeamButton(source, beam)));
  updateReprocessSelectionButtons();
}

function reprocessFileButton(source: ReprocessSource): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "segment-button";
  button.dataset.source = source.source_relative_path;
  button.innerHTML = `<span>${source.file_name}</span><small>${source.beams.length.toLocaleString()} beams · ${source.source_relative_path}</small>`;
  button.addEventListener("click", () => {
    selectedReprocessSource = source.source_relative_path;
    renderReprocessBeamList(source.source_relative_path);
    updateReprocessSelectionButtons();
    if (source.beams[0]) {
      void selectReprocessBeam(source.source_relative_path, source.beams[0]);
    }
  });
  return button;
}

function reprocessBeamButton(source: ReprocessSource, beam: string): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "segment-button";
  button.dataset.source = source.source_relative_path;
  button.dataset.beam = beam;
  button.innerHTML = `<span>${beam}</span><small>${source.file_name}</small>`;
  button.addEventListener("click", () => {
    void selectReprocessBeam(source.source_relative_path, beam);
  });
  return button;
}

async function selectReprocessBeam(source: string, beam: string): Promise<void> {
  setStatus("Loading beam");
  selectedReprocessSource = source;
  renderReprocessBeamList(source);
  updateReprocessSelectionButtons();
  const payload = await fetchReprocessBeam(source, beam);
  currentSource = source;
  currentBeam = beam;
  currentSegmentId = null;
  currentPayload = segmentPayloadFromBeam(payload);
  currentLabels = cloneLabels(reprocessLabelCache.get(cacheKey(source, beam)) ?? payload.labels);
  selectedRows = new Set();
  mapView.setSegment(currentPayload);
  activeSegment.textContent = `${payload.beam.file_name} ${beam} · full track`;
  updateReprocessSelectionButtons();
  await rerender();
  setStatus(`${payload.beam.photon_count.toLocaleString()} photons`);
}

function segmentPayloadFromBeam(payload: ReprocessBeamPayload): SegmentPayload {
  return {
    segment: {
      segment_id: `${payload.beam.source_relative_path}::${payload.beam.beam}`,
      inventory_version: "reprocess-full-beam-v1",
      segment_config_version: "full-track",
      stable_source_file_id: payload.beam.source_relative_path,
      source_relative_path: payload.beam.source_relative_path,
      source_label: payload.source.source_label,
      file_name: payload.beam.file_name,
      beam: payload.beam.beam,
      x_atc_start_m: payload.beam.x_atc_start_m,
      x_atc_end_m: payload.beam.x_atc_end_m,
      context_x_atc_start_m: payload.beam.x_atc_start_m,
      context_x_atc_end_m: payload.beam.x_atc_end_m,
      photon_count: payload.beam.photon_count,
      day_night: payload.beam.day_night,
      beam_strength: payload.beam.beam_strength,
      status: "unlabeled",
    },
    assigned: payload.photons,
    context: payload.photons,
  };
}

async function runReprocessProposal(): Promise<void> {
  if (!currentSource || !currentBeam) {
    return;
  }
  setStatus("Running smart labeler");
  const seeds = currentLabels.filter((row) => row.label_source === "manual");
  const proposal = await requestReprocessProposal(currentSource, currentBeam, seeds);
  currentLabels = acceptProposal(currentLabels, proposal.rows);
  selectedRows = new Set();
  cacheCurrentReprocessLabels();
  setStatus(`Smart labeler ready: ${countLabels(currentLabels)}`);
  await rerender();
}

async function saveCurrentReprocessSource(): Promise<void> {
  if (!currentSource || !currentBeam) {
    return;
  }
  cacheCurrentReprocessLabels();
  setStatus("Saving H5");
  const saved = await saveReprocessSource(currentSource, beamLabelsForSource(currentSource));
  setStatus(`Saved ${saved.output_path}`);
}

function cacheCurrentReprocessLabels(): void {
  if (currentSource && currentBeam) {
    reprocessLabelCache.set(cacheKey(currentSource, currentBeam), cloneLabels(currentLabels));
  }
}

function beamLabelsForSource(source: string): Record<string, LabelRow[]> {
  const labelsByBeam: Record<string, LabelRow[]> = {};
  for (const [key, labels] of reprocessLabelCache.entries()) {
    const [cachedSource, cachedBeam] = key.split("\u0000");
    if (cachedSource === source && cachedBeam) {
      labelsByBeam[cachedBeam] = cloneLabels(labels);
    }
  }
  return labelsByBeam;
}

async function initializeTrainingMode(): Promise<void> {
  appMode = "training";
  setupPanel.hidden = true;
  fileHeading.textContent = "To Label";
  beamHeading.textContent = "Labeled";
  configureLabelButtonsForMode("training");
  runProposal.textContent = "Run Proposal";
  resetAtl24.hidden = true;
  saveLabelsButton.textContent = "Done";
  await loadSegments();
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
    updateSelectionControls();
    activeSegment.textContent = "No segment selected";
  }
  setStatus("");
}

function renderSegmentLists(): void {
  const open = segments.filter((segment) => segment.status !== "complete");
  const complete = segments.filter((segment) => segment.status === "complete");
  fileList.replaceChildren(...open.map(segmentButton));
  beamList.replaceChildren(...complete.map(segmentButton));
}

function segmentButton(segment: SegmentSummary): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "segment-button";
  button.dataset.segmentId = segment.segment_id;
  button.innerHTML = `<span>${segment.file_name} ${segment.beam}</span><small>${formatKm(segment.x_atc_start_m)}-${formatKm(segment.x_atc_end_m)} km · ${segment.status}</small>`;
  button.classList.toggle("is-selected", segment.segment_id === currentSegmentId);
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
      : createDefaultLabels(currentPayload.assigned.source_row, "noise");
  currentSegmentId = segmentId;
  currentSource = null;
  currentBeam = null;
  selectedRows = new Set();
  activeSegment.textContent = `${currentPayload.segment.file_name} ${currentPayload.segment.beam} · ${formatKm(currentPayload.segment.x_atc_start_m)}-${formatKm(currentPayload.segment.x_atc_end_m)} km`;
  mapView.setSegment(currentPayload);
  updateSegmentSelectionButtons();
  await rerender();
  setStatus(`${currentPayload.assigned.source_row.length.toLocaleString()} assigned photons`);
}

async function runTrainingProposal(): Promise<void> {
  if (!currentPayload) {
    return;
  }
  setStatus("Running proposal");
  const seeds = currentLabels.filter((row) => row.label_source === "manual");
  const proposal = await requestProposal(currentPayload.segment.segment_id, seeds);
  currentLabels = acceptProposal(currentLabels, proposal.rows);
  selectedRows = new Set();
  setStatus(`Proposal ready: ${countLabels(currentLabels)}`);
  await rerender();
}

async function saveCurrentTrainingSegment(): Promise<void> {
  if (!currentSegmentId) {
    return;
  }
  setStatus("Saving");
  const saved = await saveLabels(currentSegmentId, currentLabels);
  currentLabels = saved.rows;
  setStatus("Saved");
  await loadSegments(currentSegmentId);
}

async function rerender(): Promise<void> {
  updateSelectionControls();
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
    await applyLabelToSelectedRows(activeLabel);
    return;
  }
  setStatus(rows.size > 0 ? `${rows.size.toLocaleString()} photons selected` : "Selection cleared");
  await rerender();
}

async function applyLabelToSelectedRows(label: FinalLabel): Promise<void> {
  if (selectedRows.size === 0) {
    return;
  }
  const selectedCount = selectedRows.size;
  currentLabels = labelSelectionWithMode(currentLabels, selectedRows, label);
  if (appMode === "reprocess") {
    cacheCurrentReprocessLabels();
  }
  selectedRows = new Set();
  setStatus(`Set ${selectedCount.toLocaleString()} ${formatLabel(label).toLowerCase()} photons`);
  await rerender();
}

async function clearCurrentSelection(): Promise<void> {
  if (selectedRows.size === 0) {
    return;
  }
  selectedRows = new Set();
  setStatus("Selection cleared");
  await rerender();
}

function updateSelectionControls(): void {
  clearSelectionButton.disabled = selectedRows.size === 0;
}

function updateShowClassificationsButton(): void {
  showClassificationsButton.setAttribute("aria-pressed", String(settings.showClassifications));
}

function readSettings(): ProfileSettings {
  return {
    pointSize: Number.parseFloat(pointSize.value),
    pointOpacity: Number.parseFloat(pointOpacity.value),
    showClassifications: showClassificationsButton.getAttribute("aria-pressed") !== "false",
  };
}

function countLabels(labels: LabelRow[]): string {
  const counts = new Map<FinalLabel, number>();
  for (const row of labels) {
    counts.set(row.label, (counts.get(row.label) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([label, count]) => `${formatLabel(label).toLowerCase()} ${count}`)
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

function configureLabelButtonsForMode(mode: AppMode): void {
  const options = labelsForAppMode(mode);
  if (activeLabel && !options.some((option) => option.label === activeLabel)) {
    activeLabel = null;
  }
  classButtons.replaceChildren(...options.map(labelModeButton));
  classModeButtons = Array.from(classButtons.querySelectorAll<HTMLButtonElement>("button[data-label]"));
  updateClassModeButtons();
}

function labelModeButton(option: { label: FinalLabel; text: string }): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.label = option.label;
  button.textContent = option.text;
  return button;
}

function updateReprocessSelectionButtons(): void {
  for (const button of fileList.querySelectorAll<HTMLButtonElement>(".segment-button[data-source]")) {
    button.classList.toggle("is-selected", button.dataset.source === selectedReprocessSource);
  }
  for (const button of beamList.querySelectorAll<HTMLButtonElement>(".segment-button[data-source][data-beam]")) {
    button.classList.toggle("is-selected", button.dataset.source === currentSource && button.dataset.beam === currentBeam);
  }
}

function updateSegmentSelectionButtons(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>(".segment-button[data-segment-id]")) {
    button.classList.toggle("is-selected", button.dataset.segmentId === currentSegmentId);
  }
}

function defaultOutputDir(inputPath: string): string {
  const trimmed = inputPath.trim().replace(/\/+$/, "");
  return trimmed ? `${trimmed}_labeled` : "";
}

function cacheKey(source: string, beam: string): string {
  return `${source}\u0000${beam}`;
}

function cloneLabels(labels: LabelRow[]): LabelRow[] {
  return labels.map((row) => ({ ...row }));
}

function formatLabel(label: FinalLabel): string {
  if (label === "no_label") {
    return "No label";
  }
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
  return (
    value === "surface" ||
    value === "bathy" ||
    value === "no_label" ||
    value === "land" ||
    value === "noise" ||
    value === "ambiguous"
  );
}
