import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

import {
  acceptProposal,
  createDefaultLabels,
  labelSelectionWithMode,
  labelsForAppMode,
  toggleLabelMode,
} from "./labelState.js";
import {
  computeMapSyncView,
  extractPlotlyXRange,
  getSegmentDistanceRange,
  type DistanceRange,
} from "./mapSync.js";
import { createMap, type MapCameraState } from "./mapView.js";
import {
  clearProfile,
  getProfileXRange,
  renderProfile,
  setProfileXRange,
  type ProfileSettings,
} from "./profilePlot.js";
import { labelColorForClass } from "./profileColors.js";
import {
  labelOriginStatusText,
  reprocessBeamStatusClass,
  reprocessBeamStatusText,
  reprocessFileStatusClass,
  reprocessFileStatusText,
} from "./reprocessStatus.js";
import {
  configureReprocessSession,
  fetchLabels,
  fetchManifest,
  requestReprocessDemSample,
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
import { reprocessSaveStatusText } from "./saveStatus.js";
import { createPayloadSwitchGuard } from "./syncState.js";
import {
  addRecentPath,
  defaultOutputDir,
  datasetSummaryText,
  emptyBeamSelectionDetail,
  evaluateDatasetDraft,
  labelHistoryCanRedo,
  labelHistoryCanUndo,
  labelHistoryRedo,
  labelHistorySnapshot,
  labelHistoryUndo,
  pushLabelHistory,
  labelDisplayName,
  shortcutActionForKey,
  selectionDetailText,
  type LabelHistory,
  type SaveState,
} from "./workflowUi.js";
import type {
  DemSamplePayload,
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
const demPath = requireInput("dem-path");
const demPathLabel = requireElement("dem-path-label");
const datasetStatus = requireElement("dataset-status");
const datasetFields = requireElement("dataset-fields");
const datasetSummary = requireElement("dataset-summary");
const datasetSummaryTextElement = requireElement("dataset-summary-text");
const loadSessionButton = requireButton("load-session");
const editDatasetButton = requireButton("edit-dataset");
const chooseInputDirButton = requireButton("choose-input-dir");
const suggestOutputDirButton = requireButton("suggest-output-dir");
const chooseDemPathButton = requireButton("choose-dem-path");
const inputDirError = requireElement("input-dir-error");
const outputDirError = requireElement("output-dir-error");
const demPathError = requireElement("dem-path-error");
const inputDirRecents = requireDataList("input-dir-recents");
const outputDirRecents = requireDataList("output-dir-recents");
const demPathRecents = requireDataList("dem-path-recents");
const fileHeading = requireElement("file-heading");
const beamHeading = requireElement("beam-heading");
const fileList = requireElement("file-list");
const beamList = requireElement("beam-list");
const segmentCount = requireElement("segment-count");
const activeSegment = requireElement("active-segment");
const selectionDetail = requireElement("selection-detail");
const statusElement = requireElement("status");
const profile = requireElement("profile");
const mapContainer = requireElement("map");
const classButtons = requireElement("class-buttons");
const emptyWorkflow = requireElement("empty-workflow");
const labelingControls = requireElement("labeling-controls");
const actionControls = requireElement("action-controls");
const runProposal = requireButton("run-proposal");
const showClassificationsToggle = requireInput("show-classifications");
const showClassificationsControl = requireElement("show-classifications-control");
const showDemToggle = requireInput("show-dem");
const showDemControl = requireElement("show-dem-control");
const resetAtl24 = requireButton("reset-atl24");
const saveLabelsButton = requireButton("save-labels");
const undoLabelsButton = requireButton("undo-labels");
const redoLabelsButton = requireButton("redo-labels");
const clearSelectionButton = requireButton("clear-selection");
const syncWithMapButton = requireButton("sync-with-map");
const pointSize = requireInput("point-size");
const pointOpacity = requireInput("point-opacity");
let classModeButtons: HTMLButtonElement[] = [];

const mapView = createMap(mapContainer);
const payloadSwitchGuard = createPayloadSwitchGuard();

let appMode: AppMode = "reprocess";
let segments: SegmentSummary[] = [];
let reprocessSources: ReprocessSource[] = [];
let currentPayload: SegmentPayload | null = null;
let currentLabels: LabelRow[] = [];
let selectedRows = new Set<number>();
let activeLabel: FinalLabel | null = null;
let settings: ProfileSettings = readSettings();
let currentDemSample: DemSamplePayload | null = null;
let currentDemKey: string | null = null;
let currentSegmentId: string | null = null;
let currentSource: string | null = null;
let currentBeam: string | null = null;
let selectedReprocessSource: string | null = null;
let fullProfileRange: DistanceRange | null = null;
let currentProfileRange: DistanceRange | null = null;
let restoreCameraState: MapCameraState | null = null;
let removeMapCameraListener: (() => void) | null = null;
let ignoreNextMapCameraChange = false;
let ignoreProfileRelayout = false;
const reprocessLabelCache = new Map<string, LabelRow[]>();
let outputPathWasEdited = false;
let datasetEditing = true;
let datasetLoading = false;
let labelHistory: LabelHistory = labelHistorySnapshot([]);
const labelBaselines = new Map<string, LabelRow[]>();
const dirtySelections = new Set<string>();

type RecentPathKind = "input" | "output" | "dem";

const RECENT_PATH_STORAGE_KEYS: Record<RecentPathKind, string> = {
  input: "bathy-labeler.recentInputPaths",
  output: "bathy-labeler.recentOutputPaths",
  dem: "bathy-labeler.recentDemPaths",
};

configureLabelButtonsForMode("reprocess");
renderRecentPathOptions();
updateDatasetControls();
showEmptySelection("No beam selected");
updateSelectionControls();
updateShowClassificationsButton();
updateShowDemButton();
updateSyncWithMapButton();
void boot().catch(handleBootError);

loadSessionButton.addEventListener("click", () => {
  void configureAndLoadReprocessSession();
});

editDatasetButton.addEventListener("click", () => {
  setDatasetEditing(true);
  updateDatasetControls();
});

inputDir.addEventListener("input", () => {
  if (!outputPathWasEdited || !outputDir.value.trim()) {
    outputDir.value = defaultOutputDir(inputDir.value);
  }
  updateDatasetControls();
});

outputDir.addEventListener("input", () => {
  outputPathWasEdited = true;
  updateDatasetControls();
});

demPath.addEventListener("input", () => {
  updateDatasetControls();
  if (!demPath.value.trim()) {
    settings = { ...settings, showDem: false };
  }
  updateShowDemButton();
});

chooseInputDirButton.addEventListener("click", () => {
  if (promptForPath("ATL24 input folder", inputDir)) {
    if (!outputPathWasEdited || !outputDir.value.trim()) {
      outputDir.value = defaultOutputDir(inputDir.value);
    }
    updateDatasetControls();
  }
});

suggestOutputDirButton.addEventListener("click", () => {
  outputDir.value = defaultOutputDir(inputDir.value);
  outputPathWasEdited = false;
  updateDatasetControls();
});

chooseDemPathButton.addEventListener("click", () => {
  if (promptForPath("DEM GeoTIFF", demPath)) {
    handleDemPathChanged();
  }
});

document.addEventListener("keydown", (event) => {
  void handleKeyboardShortcut(event);
});

classButtons.addEventListener("click", (event) => {
  const target = event.target instanceof HTMLElement ? event.target.closest<HTMLButtonElement>("button[data-label]") : null;
  if (!(target instanceof HTMLButtonElement)) {
    return;
  }
  const label = target.dataset.label;
  if (!isFinalLabel(label)) {
    return;
  }
  void setActiveLabelMode(label);
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
  if (!window.confirm("Reset this beam to the original ATL24 labels?")) {
    return;
  }
  const reset = await resetReprocessBeam(currentSource, currentBeam);
  recordLabelHistory(reset.rows);
  currentLabels = reset.rows;
  selectedRows = new Set();
  cacheCurrentReprocessLabels();
  updateDirtyStateForCurrentSelection();
  setStatus("Reset to ATL24");
  await rerender();
});

saveLabelsButton.addEventListener("click", async () => {
  await saveCurrentLabels();
});

clearSelectionButton.addEventListener("click", () => {
  void clearCurrentSelection();
});

undoLabelsButton.addEventListener("click", () => {
  void undoLabelChange();
});

redoLabelsButton.addEventListener("click", () => {
  void redoLabelChange();
});

syncWithMapButton.addEventListener("click", () => {
  const enabled = !isMapSyncEnabled();
  setMapSyncEnabled(enabled);
  if (enabled) {
    enableMapSync();
    setStatus(currentPayload ? "Map sync on" : "Map sync ready");
  } else {
    disableMapSync();
    setStatus("Map sync off");
  }
});

showClassificationsToggle.addEventListener("change", () => {
  settings = {
    ...settings,
    showClassifications: showClassificationsToggle.checked,
  };
  updateShowClassificationsButton();
  setStatus(settings.showClassifications ? "Class colors on" : "Grey points");
  void rerender();
});

showDemToggle.addEventListener("change", () => {
  if (showDemToggle.disabled) {
    return;
  }
  settings = {
    ...settings,
    showDem: showDemToggle.checked,
  };
  updateShowDemButton();
  if (settings.showDem) {
    void loadDemAndRerender();
  } else {
    setStatus("DEM hidden");
    void rerender();
  }
});

demPath.addEventListener("change", () => {
  handleDemPathChanged();
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

function handleBootError(error: unknown): void {
  segmentCount.textContent = "Dataset";
  showEmptySelection("No beam selected");
  fileList.replaceChildren();
  beamList.replaceChildren();
  setDatasetEditing(true);
  const message = `Backend unavailable: ${formatErrorMessage(error)}`;
  setDatasetStatus(message);
  setStatus(message);
}

async function initializeReprocessMode(manifest: ManifestPayload): Promise<void> {
  appMode = "reprocess";
  setupPanel.hidden = false;
  demPathLabel.hidden = false;
  showDemControl.hidden = false;
  showClassificationsControl.hidden = false;
  fileHeading.textContent = "Files";
  beamHeading.textContent = "Beams";
  configureLabelButtonsForMode("reprocess");
  runProposal.textContent = "Suggest from seeds";
  resetAtl24.hidden = false;
  saveLabelsButton.textContent = "Save cleaned H5";
  inputDir.value = manifest.input_dir ?? "";
  outputDir.value = manifest.output_dir ?? manifest.suggested_output_dir ?? defaultOutputDir(inputDir.value);
  outputPathWasEdited = Boolean(manifest.output_dir) && outputDir.value !== defaultOutputDir(inputDir.value);
  setDatasetEditing(!manifest.configured);
  updateDatasetControls();
  if (manifest.configured) {
    if (!manifest.output_dir && inputDir.value && outputDir.value) {
      await configureReprocessSession(inputDir.value, outputDir.value);
    }
    await loadReprocessSources();
  } else {
    segmentCount.textContent = "Dataset";
    showEmptySelection("No beam selected");
    fileList.replaceChildren();
    beamList.replaceChildren();
    setStatus("");
    updateSelectionControls();
  }
}

async function configureAndLoadReprocessSession(): Promise<void> {
  const draft = evaluateDatasetDraft(inputDir.value, outputDir.value, demPath.value);
  if (!draft.canLoad) {
    setDatasetStatus(draft.message);
    setStatus(draft.message);
    return;
  }
  inputDir.value = draft.inputPath;
  outputDir.value = draft.outputPath;
  demPath.value = draft.demPath;
  datasetLoading = true;
  updateDatasetControls();
  setStatus("Loading ATL24 folder");
  let failureMessage: string | null = null;
  try {
    await configureReprocessSession(draft.inputPath, draft.outputPath);
    rememberCurrentPaths();
    setDatasetEditing(false);
    reprocessLabelCache.clear();
    labelBaselines.clear();
    dirtySelections.clear();
    currentPayload = null;
    setActiveProfileRange(null);
    currentLabels = [];
    selectedRows = new Set();
    currentDemSample = null;
    currentDemKey = null;
    updateSelectionControls();
    updateShowDemButton();
    selectedReprocessSource = null;
    await loadReprocessSources();
  } catch (error) {
    failureMessage = `Load failed: ${formatErrorMessage(error)}`;
    setDatasetEditing(true);
  } finally {
    datasetLoading = false;
    updateDatasetControls();
  }
  if (failureMessage) {
    setDatasetStatus(failureMessage);
    setStatus(failureMessage);
  }
}

async function loadReprocessSources(): Promise<void> {
  const payload = await fetchReprocessSources();
  reprocessSources = payload.sources;
  segmentCount.textContent = `${payload.count.toLocaleString()} files`;
  setDatasetStatus("Loaded");
  const first = reprocessSources[0];
  selectedReprocessSource = first?.source_relative_path ?? null;
  renderReprocessSourceList();
  if (first?.beams[0]) {
    await selectReprocessBeam(first.source_relative_path, first.beams[0]);
  } else {
    clearProfile(profile);
    setActiveProfileRange(null);
    updateSelectionControls();
    updateShowDemButton();
    showEmptySelection("No beam selected");
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
  button.classList.add(reprocessFileStatusClass(source.status));
  button.dataset.source = source.source_relative_path;
  button.innerHTML = `<span>${source.file_name}</span><small>${reprocessFileStatusText(source)} · ${source.source_relative_path}</small>`;
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
  const status = source.beam_statuses[beam] ?? "unclassified";
  button.classList.add(reprocessBeamStatusClass(status));
  button.dataset.source = source.source_relative_path;
  button.dataset.beam = beam;
  button.innerHTML = `<span>${beam}</span><small>${reprocessBeamStatusText(status)} · ${source.file_name}</small>`;
  button.addEventListener("click", () => {
    void selectReprocessBeam(source.source_relative_path, beam);
  });
  return button;
}

async function selectReprocessBeam(source: string, beam: string): Promise<void> {
  const switchToken = beginPayloadSwitch();
  setStatus("Loading beam");
  try {
    selectedReprocessSource = source;
    renderReprocessBeamList(source);
    updateReprocessSelectionButtons();
    const payload = await fetchReprocessBeam(source, beam);
    if (!payloadSwitchGuard.isCurrent(switchToken)) {
      return;
    }
    currentSource = source;
    currentBeam = beam;
    currentSegmentId = null;
    currentPayload = segmentPayloadFromBeam(payload);
    setActiveProfileRange(currentPayload);
    currentLabels = cloneLabels(reprocessLabelCache.get(cacheKey(source, beam)) ?? payload.labels);
    const selectionKey = currentSelectionKey();
    if (selectionKey && !labelBaselines.has(selectionKey)) {
      labelBaselines.set(selectionKey, cloneLabels(payload.labels));
    }
    labelHistory = labelHistorySnapshot(currentLabels);
    updateDirtyStateForCurrentSelection();
    selectedRows = new Set();
    currentDemSample = null;
    currentDemKey = null;
    mapView.setSegment(currentPayload, { fit: !isMapSyncEnabled() });
    activeSegment.textContent = `${payload.beam.file_name} ${beam}`;
    updateActiveSelectionDetail();
    updateReprocessSelectionButtons();
    updateShowDemButton();
    const demStatus = settings.showDem ? await loadDemForCurrentBeam() : null;
    if (!payloadSwitchGuard.isCurrent(switchToken)) {
      return;
    }
    await rerender();
    if (!payloadSwitchGuard.isCurrent(switchToken)) {
      return;
    }
    syncMapToProfile(true);
    setStatus(demStatus ?? `${labelOriginStatusText(payload.label_origin)} · ${payload.beam.photon_count.toLocaleString()} photons`);
  } finally {
    finishPayloadSwitch(switchToken);
  }
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
  setStatus("Building label suggestion");
  const seeds = currentLabels.filter((row) => row.label_source === "manual");
  const proposal = await requestReprocessProposal(currentSource, currentBeam, seeds);
  const nextLabels = acceptProposal(currentLabels, proposal.rows);
  recordLabelHistory(nextLabels);
  currentLabels = nextLabels;
  selectedRows = new Set();
  cacheCurrentReprocessLabels();
  updateDirtyStateForCurrentSelection();
  setStatus(`Suggestion ready: ${countLabels(currentLabels)}`);
  await rerender();
}

async function saveCurrentReprocessSource(): Promise<void> {
  if (!currentSource || !currentBeam) {
    return;
  }
  cacheCurrentReprocessLabels();
  setStatus("Saving H5");
  const saved = await saveReprocessSource(currentSource, beamLabelsForSource(currentSource));
  applyReprocessSourceStatus(saved.source_status);
  markReprocessSourceSaved(currentSource);
  setStatus(reprocessSaveStatusText(saved));
  await rerender();
}

function applyReprocessSourceStatus(source: ReprocessSource): void {
  reprocessSources = reprocessSources.map((candidate) =>
    candidate.source_relative_path === source.source_relative_path ? source : candidate,
  );
  selectedReprocessSource = source.source_relative_path;
  renderReprocessSourceList();
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
  demPathLabel.hidden = true;
  showDemControl.hidden = true;
  settings = { ...settings, showDem: false };
  updateShowDemButton();
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
    setActiveProfileRange(null);
    updateSelectionControls();
    showEmptySelection("No segment selected");
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
  const switchToken = beginPayloadSwitch();
  setStatus("Loading segment");
  try {
    const payload = await fetchSegment(segmentId);
    const labels = await fetchLabels(segmentId);
    if (!payloadSwitchGuard.isCurrent(switchToken)) {
      return;
    }
    currentPayload = payload;
    setActiveProfileRange(currentPayload);
    currentLabels =
      labels.status === "complete"
        ? labels.rows
        : createDefaultLabels(currentPayload.assigned.source_row, "noise");
    currentSegmentId = segmentId;
    currentSource = null;
    currentBeam = null;
    const selectionKey = currentSelectionKey();
    if (selectionKey) {
      labelBaselines.set(selectionKey, cloneLabels(currentLabels));
    }
    labelHistory = labelHistorySnapshot(currentLabels);
    updateDirtyStateForCurrentSelection();
    selectedRows = new Set();
    activeSegment.textContent = `${currentPayload.segment.file_name} ${currentPayload.segment.beam} · ${formatKm(currentPayload.segment.x_atc_start_m)}-${formatKm(currentPayload.segment.x_atc_end_m)} km`;
    updateActiveSelectionDetail();
    mapView.setSegment(currentPayload, { fit: !isMapSyncEnabled() });
    updateSegmentSelectionButtons();
    await rerender();
    if (!payloadSwitchGuard.isCurrent(switchToken)) {
      return;
    }
    syncMapToProfile(true);
    setStatus(`${currentPayload.assigned.source_row.length.toLocaleString()} assigned photons`);
  } finally {
    finishPayloadSwitch(switchToken);
  }
}

async function runTrainingProposal(): Promise<void> {
  if (!currentPayload) {
    return;
  }
  setStatus("Running proposal");
  const seeds = currentLabels.filter((row) => row.label_source === "manual");
  const proposal = await requestProposal(currentPayload.segment.segment_id, seeds);
  const nextLabels = acceptProposal(currentLabels, proposal.rows);
  recordLabelHistory(nextLabels);
  currentLabels = nextLabels;
  selectedRows = new Set();
  updateDirtyStateForCurrentSelection();
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
  markCurrentSelectionSaved();
  setStatus("Saved");
  await loadSegments(currentSegmentId);
}

async function rerender(): Promise<void> {
  updateSelectionControls();
  updateShowDemButton();
  updateActiveSelectionDetail();
  if (!currentPayload) {
    return;
  }
  await renderProfile(profile, currentPayload, currentLabels, selectedRows, settings, activeDemSample(), (rows) => {
    void handleProfileSelection(rows);
  }, handleProfileRelayout);
  currentProfileRange = getProfileXRange(profile) ?? currentProfileRange ?? fullProfileRange;
}

async function loadDemAndRerender(): Promise<void> {
  const message = await loadDemForCurrentBeam();
  await rerender();
  if (message) {
    setStatus(message);
  }
}

async function loadDemForCurrentBeam(): Promise<string | null> {
  updateShowDemButton();
  const key = currentDemCacheKey();
  if (!settings.showDem || !currentSource || !currentBeam || !key) {
    return null;
  }
  if (currentDemKey === key && currentDemSample) {
    return `DEM sampled: ${currentDemSample.dem.valid_count.toLocaleString()}/${currentDemSample.dem.sample_count.toLocaleString()}`;
  }
  setStatus("Sampling DEM");
  try {
    currentDemSample = await requestReprocessDemSample(currentSource, currentBeam, demPath.value.trim());
    currentDemKey = key;
    return `DEM sampled: ${currentDemSample.dem.valid_count.toLocaleString()}/${currentDemSample.dem.sample_count.toLocaleString()}`;
  } catch (error) {
    currentDemSample = null;
    currentDemKey = null;
    return `DEM unavailable: ${errorMessage(error)}`;
  }
}

function activeDemSample(): DemSamplePayload | null {
  return settings.showDem && currentDemKey === currentDemCacheKey() ? currentDemSample : null;
}

function currentDemCacheKey(): string | null {
  const path = demPath.value.trim();
  return currentSource && currentBeam && path ? `${currentSource}\u0000${currentBeam}\u0000${path}` : null;
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
  const nextLabels = labelSelectionWithMode(currentLabels, selectedRows, label);
  recordLabelHistory(nextLabels);
  currentLabels = nextLabels;
  if (appMode === "reprocess") {
    cacheCurrentReprocessLabels();
  }
  updateDirtyStateForCurrentSelection();
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

function setActiveProfileRange(payload: SegmentPayload | null): void {
  fullProfileRange = payload ? getSegmentDistanceRange(payload) : null;
  currentProfileRange = fullProfileRange;
}

function beginPayloadSwitch(): number {
  const token = payloadSwitchGuard.begin();
  ignoreProfileRelayout = true;
  ignoreNextMapCameraChange = true;
  return token;
}

function finishPayloadSwitch(token: number): void {
  if (!payloadSwitchGuard.isCurrent(token)) {
    return;
  }
  payloadSwitchGuard.finish(token);
  window.setTimeout(() => {
    if (!payloadSwitchGuard.isSwitching()) {
      ignoreProfileRelayout = false;
    }
  }, 0);
}

function syncMapToProfile(animated: boolean): void {
  if (!isMapSyncEnabled() || !currentPayload) {
    return;
  }

  const syncView = computeMapSyncView(currentPayload, currentProfileRange ?? fullProfileRange);
  if (!syncView) {
    return;
  }

  currentProfileRange = syncView.rangeKm;
  ignoreNextMapCameraChange = true;
  mapView.syncToSegmentRange(syncView, animated);
  window.setTimeout(
    () => {
      ignoreNextMapCameraChange = false;
    },
    animated ? 900 : 0,
  );
}

function handleProfileRelayout(update: Record<string, unknown>): void {
  if (payloadSwitchGuard.isSwitching() || ignoreProfileRelayout) {
    return;
  }
  const nextRange = extractPlotlyXRange(update, fullProfileRange);
  if (nextRange === null) {
    return;
  }
  currentProfileRange = nextRange;
  syncMapToProfile(false);
}

async function syncProfileToMapView(): Promise<void> {
  if (!isMapSyncEnabled() || !currentPayload) {
    return;
  }

  if (payloadSwitchGuard.isSwitching()) {
    return;
  }

  if (ignoreNextMapCameraChange) {
    ignoreNextMapCameraChange = false;
    return;
  }

  const nextRange = mapView.getVisibleSegmentRange(currentPayload);
  if (nextRange === null || rangesAreClose(nextRange, currentProfileRange)) {
    return;
  }

  currentProfileRange = nextRange;
  ignoreProfileRelayout = true;
  try {
    await setProfileXRange(profile, nextRange);
  } finally {
    window.setTimeout(() => {
      ignoreProfileRelayout = false;
    }, 0);
  }
}

function rangesAreClose(left: DistanceRange, right: DistanceRange | null): boolean {
  if (right === null) {
    return false;
  }
  return Math.abs(left[0] - right[0]) < 0.001 && Math.abs(left[1] - right[1]) < 0.001;
}

function enableMapSync(): void {
  if (restoreCameraState === null) {
    restoreCameraState = mapView.getCameraState();
  }
  if (removeMapCameraListener === null) {
    removeMapCameraListener = mapView.onCameraChange(() => {
      void syncProfileToMapView();
    });
  }
  syncMapToProfile(true);
}

function disableMapSync(): void {
  removeMapCameraListener?.();
  removeMapCameraListener = null;
  ignoreNextMapCameraChange = false;
  ignoreProfileRelayout = false;

  if (restoreCameraState !== null) {
    mapView.restoreCameraState(restoreCameraState, true);
    restoreCameraState = null;
  }
}

function isMapSyncEnabled(): boolean {
  return syncWithMapButton.getAttribute("aria-pressed") === "true";
}

function setMapSyncEnabled(enabled: boolean): void {
  syncWithMapButton.setAttribute("aria-pressed", String(enabled));
  syncWithMapButton.classList.toggle("is-active", enabled);
}

function updateSyncWithMapButton(): void {
  syncWithMapButton.disabled = false;
  setMapSyncEnabled(isMapSyncEnabled());
}

function setDatasetEditing(editing: boolean): void {
  datasetEditing = editing;
  updateDatasetControls();
  updateSelectionControls();
}

async function setActiveLabelMode(label: FinalLabel): Promise<void> {
  if (!currentPayload) {
    return;
  }
  activeLabel = toggleLabelMode(activeLabel, label);
  updateClassModeButtons();
  if (activeLabel && selectedRows.size > 0) {
    await applyLabelToSelectedRows(activeLabel);
    return;
  }
  setStatus(activeLabel ? `${formatLabel(activeLabel)} mode` : "Label mode off");
}

async function handleKeyboardShortcut(event: KeyboardEvent): Promise<void> {
  const targetTagName = event.target instanceof HTMLElement ? event.target.tagName.toLowerCase() : undefined;
  const action = shortcutActionForKey({
    key: event.key,
    metaKey: event.metaKey,
    ctrlKey: event.ctrlKey,
    shiftKey: event.shiftKey,
    targetTagName,
  });
  if (action === null) {
    return;
  }
  if (action === "save") {
    if (!saveLabelsButton.disabled) {
      event.preventDefault();
      await saveCurrentLabels();
    }
    return;
  }
  if (action === "undo") {
    if (!undoLabelsButton.disabled) {
      event.preventDefault();
      await undoLabelChange();
    }
    return;
  }
  if (action === "redo") {
    if (!redoLabelsButton.disabled) {
      event.preventDefault();
      await redoLabelChange();
    }
    return;
  }
  if (!currentPayload) {
    return;
  }
  event.preventDefault();
  if (action === "escape") {
    if (selectedRows.size > 0) {
      await clearCurrentSelection();
      return;
    }
    activeLabel = null;
    updateClassModeButtons();
    setStatus("Label mode off");
    return;
  }
  if (action === "label_surface") {
    await setActiveLabelMode("surface");
  } else if (action === "label_bathy") {
    await setActiveLabelMode("bathy");
  } else if (action === "label_erase") {
    await setActiveLabelMode("no_label");
  }
}

async function saveCurrentLabels(): Promise<void> {
  if (!currentPayload) {
    return;
  }
  if (appMode === "reprocess") {
    await saveCurrentReprocessSource();
  } else {
    await saveCurrentTrainingSegment();
  }
}

function recordLabelHistory(nextLabels: LabelRow[]): void {
  labelHistory = pushLabelHistory(labelHistory, currentLabels, nextLabels);
}

async function undoLabelChange(): Promise<void> {
  const undone = labelHistoryUndo(labelHistory, currentLabels);
  labelHistory = undone.history;
  currentLabels = undone.labels;
  selectedRows = new Set();
  if (appMode === "reprocess") {
    cacheCurrentReprocessLabels();
  }
  updateDirtyStateForCurrentSelection();
  setStatus("Undid label change");
  await rerender();
}

async function redoLabelChange(): Promise<void> {
  const redone = labelHistoryRedo(labelHistory, currentLabels);
  labelHistory = redone.history;
  currentLabels = redone.labels;
  selectedRows = new Set();
  if (appMode === "reprocess") {
    cacheCurrentReprocessLabels();
  }
  updateDirtyStateForCurrentSelection();
  setStatus("Redid label change");
  await rerender();
}

function updateSelectionControls(): void {
  const hasPayload = currentPayload !== null;
  const saveable = hasSaveableChanges();
  emptyWorkflow.hidden = hasPayload;
  labelingControls.hidden = !hasPayload;
  actionControls.hidden = !hasPayload;
  clearSelectionButton.disabled = selectedRows.size === 0;
  runProposal.disabled = !hasPayload;
  saveLabelsButton.disabled = !hasPayload || !saveable;
  saveLabelsButton.classList.toggle("is-primary", hasPayload && saveable && !datasetEditing);
  undoLabelsButton.disabled = !hasPayload || !labelHistoryCanUndo(labelHistory);
  redoLabelsButton.disabled = !hasPayload || !labelHistoryCanRedo(labelHistory);
  resetAtl24.disabled = appMode !== "reprocess" || !currentSource || !currentBeam;
  showClassificationsToggle.disabled = !hasPayload;
  pointSize.disabled = !hasPayload;
  pointOpacity.disabled = !hasPayload;
  for (const button of classModeButtons) {
    button.disabled = !hasPayload;
  }
}

function updateDatasetControls(): void {
  const draft = evaluateDatasetDraft(inputDir.value, outputDir.value, demPath.value);
  datasetFields.hidden = !datasetEditing;
  datasetSummary.hidden = datasetEditing || !draft.inputPath;
  datasetSummaryTextElement.textContent = datasetSummaryText(draft.inputPath, draft.outputPath, draft.demPath);
  loadSessionButton.disabled = datasetLoading || !draft.canLoad;
  loadSessionButton.textContent = datasetLoading ? "Loading..." : "Load dataset";
  loadSessionButton.classList.toggle("is-primary", datasetEditing);
  editDatasetButton.disabled = datasetLoading;
  chooseInputDirButton.disabled = datasetLoading;
  suggestOutputDirButton.disabled = datasetLoading || !draft.suggestedOutputPath;
  chooseDemPathButton.disabled = datasetLoading;
  updatePathError(inputDir, inputDirError, draft.fieldErrors.input);
  updatePathError(outputDir, outputDirError, draft.fieldErrors.output);
  updatePathError(demPath, demPathError, draft.fieldErrors.dem);
  setDatasetStatus(datasetEditing ? draft.message : "Loaded");
}

function setDatasetStatus(message: string): void {
  datasetStatus.textContent = message;
}

function formatErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function updatePathError(input: HTMLInputElement, errorElement: HTMLElement, message: string | undefined): void {
  input.setAttribute("aria-invalid", message ? "true" : "false");
  errorElement.textContent = message ?? "";
  errorElement.hidden = !message || !datasetEditing;
}

function promptForPath(label: string, input: HTMLInputElement): boolean {
  const nextPath = window.prompt(label, input.value.trim());
  if (nextPath === null) {
    return false;
  }
  input.value = nextPath.trim();
  return true;
}

function handleDemPathChanged(): void {
  currentDemSample = null;
  currentDemKey = null;
  updateDatasetControls();
  if (!demPath.value.trim()) {
    settings = { ...settings, showDem: false };
  }
  updateShowDemButton();
  if (settings.showDem) {
    void loadDemAndRerender();
  } else {
    void rerender();
  }
}

function rememberCurrentPaths(): void {
  rememberRecentPath("input", inputDir.value);
  rememberRecentPath("output", outputDir.value);
  rememberRecentPath("dem", demPath.value);
  renderRecentPathOptions();
}

function rememberRecentPath(kind: RecentPathKind, path: string): void {
  const recentPaths = addRecentPath(loadRecentPaths(kind), path);
  try {
    window.localStorage.setItem(RECENT_PATH_STORAGE_KEYS[kind], JSON.stringify(recentPaths));
  } catch {
    return;
  }
}

function loadRecentPaths(kind: RecentPathKind): string[] {
  try {
    const stored = window.localStorage.getItem(RECENT_PATH_STORAGE_KEYS[kind]);
    if (!stored) {
      return [];
    }
    const parsed: unknown = JSON.parse(stored);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function renderRecentPathOptions(): void {
  renderDataList(inputDirRecents, loadRecentPaths("input"));
  renderDataList(outputDirRecents, loadRecentPaths("output"));
  renderDataList(demPathRecents, loadRecentPaths("dem"));
}

function renderDataList(dataList: HTMLDataListElement, paths: string[]): void {
  dataList.replaceChildren(
    ...paths.map((path) => {
      const option = document.createElement("option");
      option.value = path;
      return option;
    }),
  );
}

function showEmptySelection(message: string): void {
  activeSegment.textContent = message;
  selectionDetail.textContent = emptyBeamSelectionDetail();
}

function updateActiveSelectionDetail(): void {
  if (!currentPayload) {
    selectionDetail.textContent = emptyBeamSelectionDetail();
    return;
  }
  selectionDetail.textContent = selectionDetailText(
    currentPayload.assigned.source_row.length,
    currentLabels,
    selectionSaveState(),
  );
}

function currentSelectionKey(): string | null {
  if (appMode === "reprocess") {
    return currentSource && currentBeam ? cacheKey(currentSource, currentBeam) : null;
  }
  return currentSegmentId ? `training\u0000${currentSegmentId}` : null;
}

function selectionSaveState(): SaveState {
  if (!currentPayload) {
    return "neutral";
  }
  return isCurrentSelectionDirty() ? "dirty" : "saved";
}

function isCurrentSelectionDirty(): boolean {
  const key = currentSelectionKey();
  return key ? dirtySelections.has(key) : false;
}

function hasSaveableChanges(): boolean {
  if (appMode !== "reprocess") {
    return isCurrentSelectionDirty();
  }
  if (!currentSource) {
    return false;
  }
  return Array.from(dirtySelections).some((key) => key.split("\u0000")[0] === currentSource);
}

function updateDirtyStateForCurrentSelection(): void {
  const key = currentSelectionKey();
  if (!key) {
    return;
  }
  const baseline = labelBaselines.get(key);
  if (!baseline || labelsEqual(baseline, currentLabels)) {
    dirtySelections.delete(key);
  } else {
    dirtySelections.add(key);
  }
}

function markCurrentSelectionSaved(): void {
  const key = currentSelectionKey();
  if (!key) {
    return;
  }
  labelBaselines.set(key, cloneLabels(currentLabels));
  dirtySelections.delete(key);
  labelHistory = labelHistorySnapshot(currentLabels);
}

function markReprocessSourceSaved(source: string): void {
  for (const [key, labels] of reprocessLabelCache.entries()) {
    const [cachedSource] = key.split("\u0000");
    if (cachedSource === source) {
      labelBaselines.set(key, cloneLabels(labels));
      dirtySelections.delete(key);
    }
  }
  markCurrentSelectionSaved();
}

function labelsEqual(left: LabelRow[], right: LabelRow[]): boolean {
  return (
    left.length === right.length &&
    left.every((row, index) => {
      const candidate = right[index];
      return (
        candidate !== undefined &&
        row.source_row === candidate.source_row &&
        row.label === candidate.label &&
        row.label_source === candidate.label_source
      );
    })
  );
}

function updateShowClassificationsButton(): void {
  showClassificationsToggle.checked = settings.showClassifications;
}

function updateShowDemButton(): void {
  const canShowDem = appMode === "reprocess" && Boolean(currentSource && currentBeam && demPath.value.trim());
  if (!canShowDem && settings.showDem) {
    settings = { ...settings, showDem: false };
  }
  showDemToggle.disabled = !canShowDem;
  showDemToggle.checked = settings.showDem;
}

function readSettings(): ProfileSettings {
  return {
    pointSize: Number.parseFloat(pointSize.value),
    pointOpacity: Number.parseFloat(pointOpacity.value),
    showClassifications: showClassificationsToggle.checked,
    showDem: showDemToggle.checked,
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
    button.disabled = currentPayload === null;
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
  button.className = "label-mode-button";
  button.style.setProperty("--label-swatch", labelColorForClass(option.label));
  const swatch = document.createElement("span");
  swatch.className = "label-swatch";
  swatch.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.textContent = option.text;
  button.replaceChildren(swatch, text);
  button.title = labelShortcutTitle(option.label);
  return button;
}

function labelShortcutTitle(label: FinalLabel): string {
  if (label === "surface") {
    return "Surface (1)";
  }
  if (label === "bathy") {
    return "Bathy (2)";
  }
  if (label === "no_label") {
    return "Erase (3)";
  }
  return labelDisplayName(label);
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

function cacheKey(source: string, beam: string): string {
  return `${source}\u0000${beam}`;
}

function cloneLabels(labels: LabelRow[]): LabelRow[] {
  return labels.map((row) => ({ ...row }));
}

function formatLabel(label: FinalLabel): string {
  return labelDisplayName(label);
}

function formatKm(meters: number): string {
  return (meters / 1000).toFixed(1);
}

function setStatus(message: string): void {
  statusElement.textContent = message;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
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

function requireDataList(id: string): HTMLDataListElement {
  const element = requireElement(id);
  if (!(element instanceof HTMLDataListElement)) {
    throw new Error(`Element is not a datalist: ${id}`);
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
