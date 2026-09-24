export type FinalLabel = "surface" | "bathy" | "no_label";
export type LabelSource = "manual" | "auto";
export type ReprocessBeamStatus = "complete" | "unclassified" | "invalid";
export type ReprocessFileStatus = ReprocessBeamStatus | "partial";
export type ReprocessLabelOrigin = "manual_output" | "atl24_original" | "raw_unclassified";

export interface LabelRow {
  source_row: number;
  label: FinalLabel;
  label_source: LabelSource;
}

/** The along-track extent the profile highlights for one beam or track. */
export interface SegmentExtent {
  segment_id: string;
  x_atc_start_m: number;
  x_atc_end_m: number;
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
  segment: SegmentExtent;
  assigned: PhotonTable;
  context: PhotonTable;
  aoi_geometry?: GeoJsonPolygon | GeoJsonMultiPolygon;
  site_marker?: SiteMapMarker | null;
  height_axis_label?: string;
}

export interface SiteMapMarker {
  label: string;
  longitude: number;
  latitude: number;
}

export interface GeoJsonPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

export interface GeoJsonMultiPolygon {
  type: "MultiPolygon";
  coordinates: number[][][][];
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
  review_config?: string;
  context_margin_m?: number;
  source_product?: "atl24" | string;
}

export interface ReprocessSource {
  source_relative_path: string;
  file_name: string;
  source_label: string | null;
  beams: string[];
  status: ReprocessFileStatus;
  completed_beam_count: number;
  invalid_beam_count: number;
  beam_count: number;
  beam_statuses: Record<string, ReprocessBeamStatus>;
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
  label_origin: ReprocessLabelOrigin;
  manual_output_path: string | null;
}

export interface ReviewSource {
  source_relative_path: string;
  file_name: string;
  source_label: string;
  product: "atl24" | string;
  height_axis_label: string;
  review_note: string | null;
  priority_tracks: string[];
  track_notes: Record<string, string>;
  beams: string[];
  beam_count: number;
  aoi_photon_count: number;
  context_photon_count: number;
  track_photon_counts: Record<string, number>;
  track_closest_distances_m: Record<string, number | null>;
  track_statuses: Record<string, "annotated" | "unlabeled">;
  annotated_track_count: number;
}

export interface ReviewSourceListPayload {
  count: number;
  sources: ReviewSource[];
}

export interface ReviewTrackPayload {
  source: ReviewSource;
  beam: ReprocessBeamSummary & {
    rgt: number;
    cycle: number;
    spot: number;
    context_photon_count: number;
    context_x_atc_start_m: number;
    context_x_atc_end_m: number;
  };
  assigned: PhotonTable;
  context: PhotonTable;
  labels: LabelRow[];
  label_origin: ReprocessLabelOrigin;
  manual_output_path: string | null;
  aoi_geometry: GeoJsonPolygon | GeoJsonMultiPolygon;
  site_marker: SiteMapMarker | null;
}

export interface ReviewSavePayload {
  status: "saved";
  source: string;
  track: string;
  output_path: string;
  backup_path: string | null;
  labels: LabelRow[];
  source_status: ReviewSource;
}

export interface DemProfilePayload {
  dem_path: string;
  dem_name: string;
  crs: string;
  x_atc_m: number[];
  dem_h_m: Array<number | null>;
  sample_count: number;
  valid_count: number;
  sampling_method: "nearest" | string;
}

export interface DemSamplePayload {
  source: string;
  beam: string;
  dem: DemProfilePayload;
}

export interface ReprocessSavePayload {
  source: string;
  outputs: Array<{ beam: string; output_path: string }>;
  output_paths: string[];
  backups: Array<{ beam: string; backup_path: string }>;
  backup_paths: string[];
  written_beams: string[];
  source_status: ReprocessSource;
}
