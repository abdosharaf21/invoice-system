import { test } from "node:test";
import assert from "node:assert/strict";

import { unwrapImportResult } from "../assets/js/utils/payload.js";

test("unwrapImportResult prefers the envelope batch (backend contract)", () => {
  const batch = { id: 7, status: "completed", processed_rows: 2, error_rows: 1 };
  const result = unwrapImportResult({ batch, errors: [{ row_number: 3 }] });
  assert.equal(result.id, 7);
  assert.equal(result.status, "completed");
});

test("unwrapImportResult falls back to a direct batch payload", () => {
  const batch = { id: 8, filename: "x.csv" };
  assert.equal(unwrapImportResult(batch), batch);
});

test("unwrapImportResult tolerates empty/undefined payloads", () => {
  assert.deepEqual(unwrapImportResult(undefined), {});
  assert.deepEqual(unwrapImportResult(null), {});
});