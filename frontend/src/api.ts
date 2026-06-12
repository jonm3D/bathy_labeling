import type { LabelPayload, LabelRow, ProposalPayload, SegmentListPayload, SegmentPayload } from "./types.js";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({ detail: response.statusText }))) as { detail?: unknown };
    throw new Error(String(body.detail ?? response.statusText));
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
