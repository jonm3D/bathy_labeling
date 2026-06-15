export type FinalLabel = "surface" | "bathy" | "land" | "noise" | "ambiguous";
export type LabelSource = "manual" | "auto";
export type SegmentStatus = "unlabeled" | "draft" | "complete" | "stale" | "conflict";

export interface LabelRow {
  source_row: number;
  label: FinalLabel;
  label_source: LabelSource;
}

export interface SegmentSummary {
  segment_id: string;
  inventory_version: string;
  segment_config_version: string;
  stable_source_file_id: string;
  source_relative_path: string;
  source_label: string | null;
  file_name: string;
  beam: string;
  x_atc_start_m: number;
  x_atc_end_m: number;
  context_x_atc_start_m: number;
  context_x_atc_end_m: number;
  photon_count: number;
  day_night: "day" | "night";
  beam_strength: "strong" | "weak";
  status: SegmentStatus;
}

export interface PhotonTable {
  source_row: number[];
  index_ph: number[];
  lat: number[];
  lon: number[];
  x_atc_m: number[];
  ortho_h_m: number[];
  surface_h_m: number[];
  night_flag: number[];
  atl24_class_ph: Array<number | null>;
}

export interface SegmentPayload {
  segment: SegmentSummary;
  assigned: PhotonTable;
  context: PhotonTable;
}

export interface SegmentListPayload {
  count: number;
  segments: SegmentSummary[];
}

export interface LabelPayload {
  status: SegmentStatus;
  rows: LabelRow[];
  metadata: Record<string, unknown>;
}

export interface ProposalPayload {
  rows: LabelRow[];
  metadata: Record<string, unknown>;
}

export interface ManifestPayload {
  mode?: "reprocess" | string;
  configured?: boolean;
  input_dir?: string | null;
  output_dir?: string | null;
  suggested_output_dir?: string | null;
  source_count?: number;
  segment_count?: number;
}

export interface ReprocessSource {
  source_relative_path: string;
  file_name: string;
  source_label: string | null;
  beams: string[];
}

export interface ReprocessSourceListPayload {
  count: number;
  sources: ReprocessSource[];
}

export interface ReprocessBeamSummary {
  source_relative_path: string;
  file_name: string;
  beam: string;
  photon_count: number;
  day_night: "day" | "night";
  beam_strength: "strong" | "weak";
  x_atc_start_m: number;
  x_atc_end_m: number;
}

export interface ReprocessBeamPayload {
  source: ReprocessSource;
  beam: ReprocessBeamSummary;
  photons: PhotonTable;
  labels: LabelRow[];
}

export interface ReprocessSavePayload {
  source: string;
  output_path: string;
  written_beams: string[];
}
