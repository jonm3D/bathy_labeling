import type {
  LabelPayload,
  LabelRow,
  DemSamplePayload,
  ManifestPayload,
  ProposalPayload,
  ReprocessBeamPayload,
  ReprocessSavePayload,
  ReprocessSourceListPayload,
  SegmentListPayload,
  SegmentPayload,
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

export function buildSegmentUrl(segmentId: string): string {
  return `/segments/${encodeURIComponent(segmentId)}`;
}

export function buildLabelsUrl(segmentId: string): string {
  return `${buildSegmentUrl(segmentId)}/labels`;
}

export function buildProposalUrl(segmentId: string): string {
  return `${buildSegmentUrl(segmentId)}/proposal`;
}

export function buildReprocessBeamUrl(source: string, beam: string): string {
  const params = new URLSearchParams({ source, beam });
  return `/reprocess/beam?${params.toString()}`;
}

export function fetchManifest(): Promise<ManifestPayload> {
  return fetchJson<ManifestPayload>("/manifest");
}

export function fetchSegments(): Promise<SegmentListPayload> {
  return fetchJson<SegmentListPayload>("/segments");
}

export function fetchSegment(segmentId: string): Promise<SegmentPayload> {
  return fetchJson<SegmentPayload>(buildSegmentUrl(segmentId));
}

export function fetchLabels(segmentId: string): Promise<LabelPayload> {
  return fetchJson<LabelPayload>(buildLabelsUrl(segmentId));
}

export function requestProposal(segmentId: string, seeds: LabelRow[]): Promise<ProposalPayload> {
  return fetchJson<ProposalPayload>(buildProposalUrl(segmentId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seeds }),
  });
}

export function saveLabels(segmentId: string, labels: LabelRow[]): Promise<LabelPayload> {
  return fetchJson<LabelPayload>(buildLabelsUrl(segmentId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ labels }),
  });
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
