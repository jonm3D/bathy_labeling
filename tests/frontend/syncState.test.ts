import assert from "node:assert/strict";
import test from "node:test";

import { createPayloadSwitchGuard } from "../../frontend/src/syncState.js";

test("payload switch guard marks older switches stale", () => {
  const guard = createPayloadSwitchGuard();

  const first = guard.begin();
  const second = guard.begin();

  assert.equal(guard.isCurrent(first), false);
  assert.equal(guard.isCurrent(second), true);
  assert.equal(guard.isSwitching(), true);
});

test("payload switch guard only clears the active switch", () => {
  const guard = createPayloadSwitchGuard();

  const first = guard.begin();
  const second = guard.begin();
  guard.finish(first);

  assert.equal(guard.isSwitching(), true);
  assert.equal(guard.isCurrent(second), true);

  guard.finish(second);

  assert.equal(guard.isSwitching(), false);
});
