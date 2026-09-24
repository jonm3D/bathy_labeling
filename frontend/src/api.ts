import type {
  LabelRow,
  DemSamplePayload,
  ManifestPayload,
  ProposalPayload,
  ReprocessBeamPayload,
  ReprocessSavePayload,
  ReprocessSourceListPayload,
  ReviewSourceListPayload,
  ReviewSavePayload,
  ReviewTrackPayload,
} from "./types.js";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({ detail: response.statusText }))) as { detail?: unknown };
    throw new Error(String(body.detail ?? response.statusText));
  }
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new Error(
      `Expected JSON from ${url}; received ${contentType || "unknown content type"}. Is the backend server running?`,
    );
  }
  return response.json() as Promise<T>;
}

export function buildReprocessBeamUrl(source: string, beam: string): string {
  const params = new URLSearchParams({ source, beam });
  return `/reprocess/beam?${params.toString()}`;
}

export function buildReviewTrackUrl(source: string, track: string): string {
  const params = new URLSearchParams({ source, track });
  return `/review/track?${params.toString()}`;
}

export function fetchManifest(): Promise<ManifestPayload> {
  return fetchJson<ManifestPayload>("/manifest");
}

export function configureReprocessSession(inputDir: string, outputDir: string): Promise<ManifestPayload> {
  return fetchJson<ManifestPayload>("/reprocess/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input_dir: inputDir, output_dir: outputDir }),
  });
}

export function fetchReprocessSources(): Promise<ReprocessSourceListPayload> {
  return fetchJson<ReprocessSourceListPayload>("/reprocess/sources");
}

export function fetchReprocessBeam(source: string, beam: string): Promise<ReprocessBeamPayload> {
  return fetchJson<ReprocessBeamPayload>(buildReprocessBeamUrl(source, beam));
}

export function fetchReviewSources(): Promise<ReviewSourceListPayload> {
  return fetchJson<ReviewSourceListPayload>("/review/sources");
}

export function fetchReviewTrack(source: string, track: string): Promise<ReviewTrackPayload> {
  return fetchJson<ReviewTrackPayload>(buildReviewTrackUrl(source, track));
}

export function saveReviewTrack(source: string, track: string, labels: LabelRow[]): Promise<ReviewSavePayload> {
  return fetchJson<ReviewSavePayload>("/review/track/labels", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, track, labels }),
  });
}

export function requestReprocessProposal(source: string, beam: string, seeds: LabelRow[]): Promise<ProposalPayload> {
  return fetchJson<ProposalPayload>("/reprocess/proposal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, beam, seeds }),
  });
}

export function resetReprocessBeam(source: string, beam: string): Promise<ProposalPayload> {
  return fetchJson<ProposalPayload>("/reprocess/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, beam }),
  });
}

export function requestReprocessDemSample(source: string, beam: string, demPath: string): Promise<DemSamplePayload> {
  return fetchJson<DemSamplePayload>("/reprocess/dem-sample", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, beam, dem_path: demPath }),
  });
}

export function saveReprocessSource(
  source: string,
  beamLabels: Record<string, LabelRow[]>,
): Promise<ReprocessSavePayload> {
  return fetchJson<ReprocessSavePayload>("/reprocess/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, beam_labels: beamLabels }),
  });
}
