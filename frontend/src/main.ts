import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

import {
  acceptProposal,
  dirtyBeamLabelsForSource,
  LABEL_OPTIONS,
  labelSelectionWithMode,
  toggleLabelMode,
  type LabelModeOption,
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
  fetchManifest,
  requestReprocessDemSample,
  fetchReprocessBeam,
  fetchReprocessSources,
  fetchReviewSources,
  fetchReviewTrack,
  requestReprocessProposal,
  resetReprocessBeam,
  saveReprocessSource,
  saveReviewTrack,
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
  ReviewSource,
  ReviewTrackPayload,
  SegmentPayload,
} from "./types.js";

type AppMode = "reprocess" | "review";

const appHeading = requireElement("app-heading");
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
const labelingHeading = requireElement("labeling-heading");
const actionControls = requireElement("action-controls");
const runProposal = requireButton("run-proposal");
const showClassificationsToggle = requireInput("show-classifications");
const showClassificationsControl = requireElement("show-classifications-control");
const showClassificationsLabel = requireElement("show-classifications-label");
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
let reprocessSources: ReprocessSource[] = [];
let reviewSources: ReviewSource[] = [];
let currentPayload: SegmentPayload | null = null;
let currentLabels: LabelRow[] = [];
let selectedRows = new Set<number>();
let activeLabel: FinalLabel | null = null;
let settings: ProfileSettings = readSettings();
let currentDemSample: DemSamplePayload | null = null;
let currentDemKey: string | null = null;
let currentSource: string | null = null;
let currentBeam: string | null = null;
let selectedReprocessSource: string | null = null;
let fullProfileRange: DistanceRange | null = null;
let currentProfileRange: DistanceRange | null = null;
let profileXReversed = false;
let restoreCameraState: MapCameraState | null = null;
let removeMapCameraListener: (() => void) | null = null;
let ignoreNextMapCameraChange = false;
let ignoreMapCameraChangeToken = 0;
let ignoreProfileRelayout = false;
const reprocessLabelCache = new Map<string, LabelRow[]>();
let outputPathWasEdited = false;
let datasetEditing = true;
let datasetLoading = false;
let saveInProgress = false;
let labelHistory: LabelHistory = labelHistorySnapshot([]);
const labelBaselines = new Map<string, LabelRow[]>();
const dirtySelections = new Set<string>();

type RecentPathKind = "input" | "output" | "dem";

const RECENT_PATH_STORAGE_KEYS: Record<RecentPathKind, string> = {
  input: "bathy-labeler.recentInputPaths",
  output: "bathy-labeler.recentOutputPaths",
  dem: "bathy-labeler.recentDemPaths",
};

configureLabelButtons();
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
  }
});

resetAtl24.addEventListener("click", async () => {
  if (appMode !== "reprocess" || !currentSource || !currentBeam) {
    return;
  }
  if (!window.confirm("Reset this beam to the original ATL24 labels?")) {
    return;
  }
  const source = currentSource;
  const beam = currentBeam;
  const labelsBeforeRequest = cloneLabels(currentLabels);
  const reset = await resetReprocessBeam(source, beam);
  if (
    currentSource !== source ||
    currentBeam !== beam ||
    !labelsEqual(currentLabels, labelsBeforeRequest)
  ) {
    return;
  }
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
  setStatus(
    settings.showClassifications ? "Class colors on" : "Grey points",
  );
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
  if (manifest.mode === "review") {
    await initializeReviewMode(manifest);
  } else {
    await initializeReprocessMode(manifest);
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

async function initializeReviewMode(manifest: ManifestPayload): Promise<void> {
  appMode = "review";
  document.title = "ICESat-2 AOI Labeler";
  appHeading.textContent = document.title;
  setupPanel.hidden = true;
  demPathLabel.hidden = true;
  showDemControl.hidden = true;
  showClassificationsControl.hidden = false;
  showClassificationsLabel.textContent = "Class colors";
  classButtons.hidden = false;
  labelingHeading.textContent = "Labeling";
  runProposal.hidden = true;
  resetAtl24.hidden = true;
  saveLabelsButton.textContent = "Save GeoPackage";
  emptyWorkflow.textContent = "Select a site and track to classify";
  fileHeading.textContent = "Sites";
  beamHeading.textContent = "Tracks";
  settings = { ...settings, showClassifications: true, showDem: false };
  showClassificationsToggle.checked = true;
  await loadReviewSources(manifest.context_margin_m ?? 1000);
}

async function loadReviewSources(contextMarginM: number): Promise<void> {
  const payload = await fetchReviewSources();
  reviewSources = payload.sources;
  segmentCount.textContent = `${payload.count.toLocaleString()} sites · ${formatKm(contextMarginM)} km context · ↑/↓ sites · ←/→ tracks`;
  const first = reviewSources.find((source) => source.beams.length > 0) ?? reviewSources[0];
  selectedReprocessSource = first?.source_relative_path ?? null;
  renderReviewSourceList();
  if (first?.beams[0]) {
    await selectReviewTrack(first.source_relative_path, first.beams[0]);
  } else {
    showEmptyReviewSite(first?.file_name ?? "No sites configured");
  }
}

function renderReviewSourceList(): void {
  fileList.replaceChildren(...reviewSources.map(reviewSourceButton));
  renderReviewTrackList(selectedReprocessSource);
  updateReviewSelectionButtons();
}

function renderReviewTrackList(sourceId: string | null): void {
  const source = reviewSources.find((candidate) => candidate.source_relative_path === sourceId);
  if (!source) {
    beamList.replaceChildren();
    return;
  }
  const elements: HTMLElement[] = [];
  if (source.review_note) {
    const note = document.createElement("p");
    note.className = "review-note";
    note.textContent = source.review_note;
    note.title = source.review_note;
    elements.push(note);
  }
  elements.push(...source.beams.map((track) => reviewTrackButton(source, track)));
  beamList.replaceChildren(...elements);
}

function reviewSourceButton(source: ReviewSource): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "segment-button";
  button.dataset.source = source.source_relative_path;
  const dirtyCount = source.beams.filter((track) =>
    dirtySelections.has(cacheKey(source.source_relative_path, track)),
  ).length;
  const dirtyText = dirtyCount > 0 ? ` · ${dirtyCount.toLocaleString()} unsaved` : "";
  button.innerHTML = `<span>${source.file_name}</span><small>${source.beam_count.toLocaleString()} tracks · ${source.aoi_photon_count.toLocaleString()} photons · ${source.annotated_track_count.toLocaleString()} saved${dirtyText}</small>`;
  button.addEventListener("click", () => {
    selectedReprocessSource = source.source_relative_path;
    renderReviewTrackList(source.source_relative_path);
    updateReviewSelectionButtons();
    if (source.beams[0]) {
      void selectReviewTrack(source.source_relative_path, source.beams[0]);
    } else {
      showEmptyReviewSite(source.file_name);
    }
  });
  return button;
}

function reviewTrackButton(source: ReviewSource, track: string): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "segment-button";
  button.dataset.source = source.source_relative_path;
  button.dataset.beam = track;
  const photonCount = source.track_photon_counts[track] ?? 0;
  const closestDistance = source.track_closest_distances_m[track];
  const distanceText = closestDistance == null ? "distance unavailable" : `${closestDistance.toFixed(1)} m closest`;
  const dirty = dirtySelections.has(cacheKey(source.source_relative_path, track));
  const priorityIndex = source.priority_tracks.indexOf(track);
  const priorityText = priorityIndex >= 0 ? `Review pick ${priorityIndex + 1} · ` : "";
  const reviewNote = source.track_notes[track];
  const status = dirty
    ? "unsaved"
    : source.track_statuses[track] === "annotated"
      ? "saved"
      : "unlabeled";
  button.innerHTML = `<span>${formatTrackKey(track)}</span><small>${priorityText}${distanceText} · ${photonCount.toLocaleString()} AOI photons · ${status}</small>`;
  if (reviewNote) {
    const note = document.createElement("small");
    note.className = "track-review-note";
    note.textContent = reviewNote;
    button.append(note);
  }
  button.addEventListener("click", () => {
    void selectReviewTrack(source.source_relative_path, track);
  });
  return button;
}

async function selectReviewTrack(source: string, track: string): Promise<void> {
  const switchToken = beginPayloadSwitch();
  setStatus("Loading track");
  try {
    selectedReprocessSource = source;
    renderReviewTrackList(source);
    updateReviewSelectionButtons();
    const payload = await fetchReviewTrack(source, track);
    if (!payloadSwitchGuard.isCurrent(switchToken)) {
      return;
    }
    currentSource = source;
    currentBeam = track;
    currentPayload = segmentPayloadFromReviewTrack(payload);
    setActiveProfileRange(currentPayload);
    currentLabels = cloneLabels(
      reprocessLabelCache.get(cacheKey(source, track)) ?? payload.labels,
    );
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
    activeSegment.textContent = `${payload.source.file_name} · RGT ${payload.beam.rgt}, cycle ${payload.beam.cycle}, spot ${payload.beam.spot}`;
    const trackIndex = payload.source.beams.indexOf(track);
    const closestDistance = payload.source.track_closest_distances_m[track];
    const distanceText = closestDistance == null ? "" : ` · ${closestDistance.toFixed(1)} m closest`;
    const reviewNote = payload.source.track_notes[track];
    const noteText = reviewNote ? ` · ${reviewNote}` : "";
    selectionDetail.textContent = `Track ${trackIndex + 1} of ${payload.source.beams.length}${distanceText} · ${payload.beam.photon_count.toLocaleString()} AOI photons · ${payload.beam.context_photon_count.toLocaleString()} with context${noteText}`;
    selectionDetail.title = reviewNote ?? "";
    updateReviewSelectionButtons();
    updateSelectionControls();
    await rerender();
    if (!payloadSwitchGuard.isCurrent(switchToken)) {
      return;
    }
    syncMapToProfile(true);
    setStatus(
      payload.label_origin === "manual_output"
        ? "Saved classifications loaded"
        : payload.source.product === "atl24"
          ? "ATL24 labels loaded"
          : "Raw ATL03 photons loaded",
    );
  } finally {
    finishPayloadSwitch(switchToken);
  }
}

async function saveCurrentReviewTrack(): Promise<void> {
  if (!currentSource || !currentBeam) {
    return;
  }
  const source = currentSource;
  const track = currentBeam;
  const labels = cloneLabels(currentLabels);
  setStatus("Saving GeoPackage");
  const saved = await saveReviewTrack(source, track, labels);
  if (currentSource !== source || currentBeam !== track) {
    return;
  }
  currentLabels = cloneLabels(saved.labels);
  reprocessLabelCache.set(cacheKey(source, track), cloneLabels(saved.labels));
  markCurrentSelectionSaved();
  reviewSources = reviewSources.map((candidate) =>
    candidate.source_relative_path === source ? saved.source_status : candidate,
  );
  renderReviewSourceList();
  setStatus("GeoPackage saved");
  await rerender();
}

function segmentPayloadFromReviewTrack(payload: ReviewTrackPayload): SegmentPayload {
  return {
    segment: {
      segment_id: `${payload.beam.source_relative_path}::${payload.beam.beam}`,
      inventory_version: `sliderule-${payload.source.product}-geoparquet-v1`,
      segment_config_version: "aoi-plus-context",
      stable_source_file_id: payload.beam.source_relative_path,
      source_relative_path: payload.beam.source_relative_path,
      source_label: payload.source.source_label,
      file_name: payload.beam.file_name,
      beam: payload.beam.beam,
      x_atc_start_m: payload.beam.x_atc_start_m,
      x_atc_end_m: payload.beam.x_atc_end_m,
      context_x_atc_start_m: payload.beam.context_x_atc_start_m,
      context_x_atc_end_m: payload.beam.context_x_atc_end_m,
      photon_count: payload.beam.photon_count,
      day_night: payload.beam.day_night,
      beam_strength: payload.beam.beam_strength,
      status: "unlabeled",
    },
    assigned: payload.assigned,
    context: payload.context,
    aoi_geometry: payload.aoi_geometry,
    site_marker: payload.site_marker,
    height_axis_label: payload.source.height_axis_label,
  };
}

function showEmptyReviewSite(siteName: string): void {
  currentPayload = null;
  currentSource = selectedReprocessSource;
  currentBeam = null;
  currentLabels = [];
  selectedRows = new Set();
  clearProfile(profile);
  mapView.clearSegment();
  setActiveProfileRange(null);
  activeSegment.textContent = siteName;
  emptyWorkflow.textContent = "No profile available for this AOI";
  selectionDetail.textContent = "No tracks intersect this AOI";
  setStatus("0 AOI photons");
  updateSelectionControls();
}

function updateReviewSelectionButtons(): void {
  for (const button of fileList.querySelectorAll<HTMLButtonElement>("button[data-source]")) {
    button.classList.toggle("is-selected", button.dataset.source === selectedReprocessSource);
  }
  for (const button of beamList.querySelectorAll<HTMLButtonElement>("button[data-beam]")) {
    button.classList.toggle(
      "is-selected",
      button.dataset.source === currentSource && button.dataset.beam === currentBeam,
    );
  }
}

async function navigateReview(action: "previous_site" | "next_site" | "previous_track" | "next_track"): Promise<void> {
  if (appMode !== "review" || reviewSources.length === 0 || payloadSwitchGuard.isSwitching()) {
    return;
  }
  const sourceId = currentSource ?? selectedReprocessSource ?? reviewSources[0].source_relative_path;
  const sourceIndex = Math.max(
    0,
    reviewSources.findIndex((source) => source.source_relative_path === sourceId),
  );

  if (action === "previous_site" || action === "next_site") {
    const offset = action === "previous_site" ? -1 : 1;
    const nextSource = reviewSources[(sourceIndex + offset + reviewSources.length) % reviewSources.length];
    selectedReprocessSource = nextSource.source_relative_path;
    renderReviewTrackList(nextSource.source_relative_path);
    updateReviewSelectionButtons();
    if (nextSource.beams[0]) {
      await selectReviewTrack(nextSource.source_relative_path, nextSource.beams[0]);
    } else {
      showEmptyReviewSite(nextSource.file_name);
    }
    return;
  }

  const source = reviewSources[sourceIndex];
  if (source.beams.length === 0) {
    return;
  }
  const trackIndex = Math.max(0, source.beams.indexOf(currentBeam ?? source.beams[0]));
  const offset = action === "previous_track" ? -1 : 1;
  const nextTrack = source.beams[(trackIndex + offset + source.beams.length) % source.beams.length];
  await selectReviewTrack(source.source_relative_path, nextTrack);
}

function formatTrackKey(track: string): string {
  const match = /^rgt_(\d+)_cycle_(\d+)_spot_(\d+)$/.exec(track);
  if (!match) {
    return track;
  }
  return `RGT ${Number(match[1])} · cycle ${Number(match[2])} · spot ${Number(match[3])}`;
}

async function initializeReprocessMode(manifest: ManifestPayload): Promise<void> {
  appMode = "reprocess";
  showClassificationsLabel.textContent = "Class colors";
  document.title = "ATL24 Bathymetry Cleaner";
  appHeading.textContent = "ATL24 Bathymetry Cleaner";
  setupPanel.hidden = false;
  demPathLabel.hidden = false;
  showDemControl.hidden = false;
  showClassificationsControl.hidden = false;
  classButtons.hidden = false;
  labelingHeading.textContent = "Labeling";
  fileHeading.textContent = "Files";
  beamHeading.textContent = "Beams";
  runProposal.hidden = false;
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
  if (saveInProgress) {
    return;
  }
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
  const source = currentSource;
  const beam = currentBeam;
  setStatus("Building label suggestion");
  const labelsBeforeRequest = cloneLabels(currentLabels);
  const seeds = currentLabels.filter((row) => row.label_source === "manual");
  const proposal = await requestReprocessProposal(source, beam, seeds);
  if (
    currentSource !== source ||
    currentBeam !== beam ||
    !labelsEqual(currentLabels, labelsBeforeRequest)
  ) {
    return;
  }
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
  const source = currentSource;
  cacheCurrentReprocessLabels();
  const labelsByBeam = dirtyBeamLabelsForSource(source, reprocessLabelCache, dirtySelections);
  setStatus("Saving H5");
  const saved = await saveReprocessSource(source, labelsByBeam);
  applyReprocessSourceStatus(saved.source_status);
  markReprocessSourceSaved(source, labelsByBeam);
  if (currentSource === source) {
    setStatus(reprocessSaveStatusText(saved));
    await rerender();
  }
}

function applyReprocessSourceStatus(source: ReprocessSource): void {
  reprocessSources = reprocessSources.map((candidate) =>
    candidate.source_relative_path === source.source_relative_path ? source : candidate,
  );
  renderReprocessSourceList();
}

function cacheCurrentReprocessLabels(): void {
  if (currentSource && currentBeam) {
    reprocessLabelCache.set(cacheKey(currentSource, currentBeam), cloneLabels(currentLabels));
  }
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
  const renderedRange = getProfileXRange(profile);
  currentProfileRange = renderedRange
    ? normalizeDistanceRange(renderedRange)
    : currentProfileRange ?? fullProfileRange;
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
  const source = currentSource;
  const beam = currentBeam;
  const path = demPath.value.trim();
  setStatus("Sampling DEM");
  try {
    const sample = await requestReprocessDemSample(source, beam, path);
    if (currentDemCacheKey() !== key) {
      return null;
    }
    currentDemSample = sample;
    currentDemKey = key;
    return `DEM sampled: ${currentDemSample.dem.valid_count.toLocaleString()}/${currentDemSample.dem.sample_count.toLocaleString()}`;
  } catch (error) {
    if (currentDemCacheKey() !== key) {
      return null;
    }
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
  if (appMode === "reprocess" || appMode === "review") {
    cacheCurrentReprocessLabels();
  }
  updateDirtyStateForCurrentSelection();
  if (appMode === "review") {
    renderReviewSourceList();
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

function setActiveProfileRange(payload: SegmentPayload | null): void {
  fullProfileRange = payload ? getSegmentDistanceRange(payload) : null;
  currentProfileRange = fullProfileRange;
  profileXReversed = false;
}

function beginPayloadSwitch(): number {
  const token = payloadSwitchGuard.begin();
  ignoreProfileRelayout = true;
  suppressProgrammaticMapCameraChange(true);
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
  updateProfileXOrientation(syncView.profileReversed);
  suppressProgrammaticMapCameraChange(animated);
  mapView.syncToSegmentRange(syncView, animated);
}

function updateProfileXOrientation(nextReversed: boolean): void {
  if (profileXReversed === nextReversed) {
    return;
  }
  profileXReversed = nextReversed;
  if (currentProfileRange) {
    void setProfileXRangeIgnoringRelayout(currentProfileRange);
  }
}

function suppressProgrammaticMapCameraChange(animated: boolean): void {
  const token = ignoreMapCameraChangeToken + 1;
  ignoreMapCameraChangeToken = token;
  ignoreNextMapCameraChange = true;
  window.setTimeout(
    () => {
      if (ignoreMapCameraChangeToken === token) {
        ignoreNextMapCameraChange = false;
      }
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
  currentProfileRange = normalizeDistanceRange(nextRange);
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
    ignoreMapCameraChangeToken += 1;
    ignoreNextMapCameraChange = false;
    return;
  }

  const nextRange = mapView.getVisibleSegmentRange(currentPayload);
  if (nextRange === null || rangesAreClose(nextRange, currentProfileRange)) {
    return;
  }

  currentProfileRange = normalizeDistanceRange(nextRange);
  await setProfileXRangeIgnoringRelayout(currentProfileRange);
}

async function setProfileXRangeIgnoringRelayout(range: DistanceRange): Promise<void> {
  ignoreProfileRelayout = true;
  try {
    await setProfileXRange(profile, getProfileDisplayRange(range));
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
  const normalizedLeft = normalizeDistanceRange(left);
  const normalizedRight = normalizeDistanceRange(right);
  return (
    Math.abs(normalizedLeft[0] - normalizedRight[0]) < 0.001 &&
    Math.abs(normalizedLeft[1] - normalizedRight[1]) < 0.001
  );
}

function normalizeDistanceRange(range: DistanceRange): DistanceRange {
  return range[0] <= range[1] ? range : [range[1], range[0]];
}

function getProfileDisplayRange(range: DistanceRange): DistanceRange {
  const normalized = normalizeDistanceRange(range);
  return profileXReversed ? [normalized[1], normalized[0]] : normalized;
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
  ignoreMapCameraChangeToken += 1;
  ignoreProfileRelayout = false;

  if (profileXReversed && currentProfileRange) {
    profileXReversed = false;
    void setProfileXRangeIgnoringRelayout(currentProfileRange);
  }

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
  if (
    action === "previous_site" ||
    action === "next_site" ||
    action === "previous_track" ||
    action === "next_track"
  ) {
    if (appMode === "review") {
      event.preventDefault();
      await navigateReview(action);
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
  if (
    !currentPayload ||
    saveInProgress ||
    datasetLoading ||
    (appMode === "reprocess" && datasetEditing)
  ) {
    return;
  }
  saveInProgress = true;
  updateDatasetControls();
  try {
    if (appMode === "reprocess") {
      await saveCurrentReprocessSource();
    } else {
      await saveCurrentReviewTrack();
    }
  } catch (error) {
    setStatus(`Save failed: ${errorMessage(error)}`);
  } finally {
    saveInProgress = false;
    updateDatasetControls();
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
  if (appMode === "reprocess" || appMode === "review") {
    cacheCurrentReprocessLabels();
  }
  updateDirtyStateForCurrentSelection();
  if (appMode === "review") {
    renderReviewSourceList();
  }
  setStatus("Undid label change");
  await rerender();
}

async function redoLabelChange(): Promise<void> {
  const redone = labelHistoryRedo(labelHistory, currentLabels);
  labelHistory = redone.history;
  currentLabels = redone.labels;
  selectedRows = new Set();
  if (appMode === "reprocess" || appMode === "review") {
    cacheCurrentReprocessLabels();
  }
  updateDirtyStateForCurrentSelection();
  if (appMode === "review") {
    renderReviewSourceList();
  }
  setStatus("Redid label change");
  await rerender();
}

function updateSelectionControls(): void {
  const hasPayload = currentPayload !== null;
  const saveable = hasSaveableChanges();
  const datasetBlocksSave = appMode === "reprocess" && datasetEditing;
  emptyWorkflow.hidden = hasPayload;
  labelingControls.hidden = !hasPayload;
  actionControls.hidden = !hasPayload;
  clearSelectionButton.disabled = selectedRows.size === 0;
  runProposal.disabled = !hasPayload || appMode === "review";
  saveLabelsButton.disabled =
    !hasPayload || !saveable || saveInProgress || datasetLoading || datasetBlocksSave;
  saveLabelsButton.textContent = saveInProgress
    ? "Saving..."
    : appMode === "reprocess"
      ? "Save cleaned H5"
      : "Save GeoPackage";
  saveLabelsButton.classList.toggle(
    "is-primary",
    hasPayload && saveable && !saveInProgress && !datasetLoading && !datasetBlocksSave,
  );
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
  const busy = datasetLoading || saveInProgress;
  datasetFields.hidden = !datasetEditing;
  datasetSummary.hidden = datasetEditing || !draft.inputPath;
  datasetSummaryTextElement.textContent = datasetSummaryText(draft.inputPath, draft.outputPath, draft.demPath);
  loadSessionButton.disabled = busy || !draft.canLoad;
  loadSessionButton.textContent = datasetLoading ? "Loading..." : "Load dataset";
  loadSessionButton.classList.toggle("is-primary", datasetEditing);
  editDatasetButton.disabled = busy;
  chooseInputDirButton.disabled = busy;
  suggestOutputDirButton.disabled = busy || !draft.suggestedOutputPath;
  chooseDemPathButton.disabled = busy;
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
  if (appMode === "review") {
    const saveState = isCurrentSelectionDirty() ? " · unsaved changes" : "";
    selectionDetail.textContent = `${currentPayload.assigned.source_row.length.toLocaleString()} AOI photons · ${currentPayload.context.source_row.length.toLocaleString()} with context${saveState}`;
    return;
  }
  selectionDetail.textContent = selectionDetailText(
    currentPayload.assigned.source_row.length,
    currentLabels,
    selectionSaveState(),
  );
}

function currentSelectionKey(): string | null {
  return currentSource && currentBeam ? cacheKey(currentSource, currentBeam) : null;
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
  if (appMode === "review") {
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

function markReprocessSourceSaved(source: string, savedLabelsByBeam: Record<string, LabelRow[]>): void {
  for (const [beam, savedLabels] of Object.entries(savedLabelsByBeam)) {
    const key = cacheKey(source, beam);
    labelBaselines.set(key, cloneLabels(savedLabels));
    const cachedLabels = reprocessLabelCache.get(key);
    if (cachedLabels && labelsEqual(cachedLabels, savedLabels)) {
      dirtySelections.delete(key);
    } else {
      dirtySelections.add(key);
    }
  }
  if (currentSource === source && currentBeam) {
    const savedLabels = savedLabelsByBeam[currentBeam];
    if (savedLabels && labelsEqual(currentLabels, savedLabels)) {
      labelHistory = labelHistorySnapshot(currentLabels);
    }
  }
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

function configureLabelButtons(): void {
  classButtons.replaceChildren(...LABEL_OPTIONS.map(labelModeButton));
  classModeButtons = Array.from(classButtons.querySelectorAll<HTMLButtonElement>("button[data-label]"));
  updateClassModeButtons();
}

function labelModeButton(option: LabelModeOption): HTMLButtonElement {
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
