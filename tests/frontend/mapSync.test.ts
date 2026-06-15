import assert from "node:assert/strict";
import test from "node:test";

import {
  clampDistanceRangeToFullRange,
  computeMapSyncView,
  computeVisibleDistanceRangeFromScreen,
  extractPlotlyXRange,
  getSegmentDistanceRange,
} from "../../frontend/src/mapSync.js";
import type { PhotonTable, SegmentPayload } from "../../frontend/src/types.js";

function samplePayload(overrides: Partial<SegmentPayload> = {}): SegmentPayload {
  const context = photonTable({
    x_atc_m: [0, 10_000, 20_000],
    lon: [144, 145, 146],
    lat: [13, 13, 13],
  });
  const payload: SegmentPayload = {
    segment: {
      segment_id: "segment-1",
      inventory_version: "inventory-v1",
      segment_config_version: "segment-v1",
      stable_source_file_id: "ATL24_sample.h5",
      source_relative_path: "ATL24_sample.h5",
      source_label: null,
      file_name: "ATL24_sample.h5",
      beam: "gt1r",
      x_atc_start_m: 0,
      x_atc_end_m: 20_000,
      context_x_atc_start_m: 0,
      context_x_atc_end_m: 20_000,
      photon_count: 3,
      day_night: "day",
      beam_strength: "strong",
      status: "unlabeled",
    },
    assigned: context,
    context,
  };
  return { ...payload, ...overrides };
}

function photonTable(overrides: Pick<PhotonTable, "x_atc_m" | "lon" | "lat">): PhotonTable {
  const count = overrides.x_atc_m.length;
  return {
    source_row: Array.from({ length: count }, (_, index) => index),
    index_ph: Array.from({ length: count }, (_, index) => index + 10),
    ortho_h_m: Array.from({ length: count }, (_, index) => index),
    surface_h_m: Array.from({ length: count }, () => 0),
    night_flag: Array.from({ length: count }, () => 0),
    atl24_class_ph: Array.from({ length: count }, () => null),
    ...overrides,
  };
}

function assertClose(actual: number, expected: number, epsilon = 1e-6): void {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} was not within ${epsilon} of ${expected}`);
}

test("getSegmentDistanceRange returns the context x_atc extent in kilometers", () => {
  assert.deepEqual(getSegmentDistanceRange(samplePayload()), [0, 20]);
});

test("clampDistanceRangeToFullRange keeps sync ranges inside real track distances", () => {
  assert.deepEqual(clampDistanceRangeToFullRange([-100, 120], [0, 20]), [0, 20]);
  assert.deepEqual(clampDistanceRangeToFullRange([-100, -90], [0, 20]), [0, 0.2]);
  const rightEdge = clampDistanceRangeToFullRange([90, 100], [0, 20]);
  assertClose(rightEdge[0], 19.8);
  assertClose(rightEdge[1], 20);
});

test("computeMapSyncView sorts profile ranges and interpolates endpoints", () => {
  const view = computeMapSyncView(samplePayload(), [15, 5]);

  assert.ok(view);
  assert.deepEqual(view.rangeKm, [5, 15]);
  assertClose(view.start[0], 144.5);
  assertClose(view.start[1], 13);
  assertClose(view.end[0], 145.5);
  assertClose(view.end[1], 13);
  assertClose(view.center[0], 145);
  assertClose(view.center[1], 13);
  assertClose(view.bearing, 0, 0.02);
});

test("computeMapSyncView expands very small profile ranges", () => {
  const view = computeMapSyncView(samplePayload(), [10, 10.01]);

  assert.ok(view);
  assertClose((view.rangeKm[0] + view.rangeKm[1]) / 2, 10.005);
  assertClose(view.rangeKm[1] - view.rangeKm[0], 0.2);
});

test("computeMapSyncView clamps out-of-data profile ranges to real track endpoints", () => {
  const view = computeMapSyncView(samplePayload(), [-100, 120]);

  assert.ok(view);
  assert.deepEqual(view.rangeKm, [0, 20]);
  assertClose(view.start[0], 144);
  assertClose(view.end[0], 146);
  assertClose(view.center[0], 145);
});

test("computeMapSyncView returns null for unusable payloads", () => {
  const singlePointContext = photonTable({
    x_atc_m: [0],
    lon: [144],
    lat: [13],
  });

  assert.equal(computeMapSyncView(samplePayload({ context: singlePointContext }), [0, 1]), null);
});

test("extractPlotlyXRange reads range changes and autorange resets", () => {
  assert.deepEqual(extractPlotlyXRange({ "xaxis.range[0]": 3, "xaxis.range[1]": 8 }, [0, 20]), [3, 8]);
  assert.deepEqual(extractPlotlyXRange({ "xaxis.range": [2, 12] }, [0, 20]), [2, 12]);
  assert.deepEqual(extractPlotlyXRange({ "xaxis.autorange": true }, [0, 20]), [0, 20]);
  assert.equal(extractPlotlyXRange({ "yaxis.range[0]": -4 }, [0, 20]), null);
});

test("computeVisibleDistanceRangeFromScreen clips projected track segments to the viewport", () => {
  const range = computeVisibleDistanceRangeFromScreen(
    [
      { distanceKm: 0, x: -10, y: 50 },
      { distanceKm: 20, x: 110, y: 50 },
    ],
    { left: 0, top: 0, right: 100, bottom: 100 },
  );

  assert.ok(range);
  assertClose(range[0], 1.6666667);
  assertClose(range[1], 18.3333333);
});

test("computeVisibleDistanceRangeFromScreen extrapolates when the viewport extends beyond endpoints", () => {
  const range = computeVisibleDistanceRangeFromScreen(
    [
      { distanceKm: 0, x: 20, y: 50 },
      { distanceKm: 20, x: 80, y: 50 },
    ],
    { left: 0, top: 0, right: 100, bottom: 100 },
  );

  assert.ok(range);
  assertClose(range[0], -6.6666667);
  assertClose(range[1], 26.6666667);
});

test("computeVisibleDistanceRangeFromScreen returns null when the track misses the viewport", () => {
  assert.equal(
    computeVisibleDistanceRangeFromScreen(
      [
        { distanceKm: 0, x: -20, y: -20 },
        { distanceKm: 20, x: 120, y: -20 },
      ],
      { left: 0, top: 0, right: 100, bottom: 100 },
    ),
    null,
  );
});
