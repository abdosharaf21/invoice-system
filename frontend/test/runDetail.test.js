import { describe, it } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { deliveryCounts } from "../assets/js/pages/runDetail.js";

describe("email delivery counts", () => {
  it("counts each delivery status", () => {
    const deliveries = [
      { status: "sent" },
      { status: "sent" },
      { status: "failed" },
      { status: "no_email" },
      { status: "no_email" },
      { status: "invalid" },
      { status: "skipped" },
    ];
    assert.deepEqual(deliveryCounts(deliveries), {
      pending: 0, sent: 2, failed: 1, skipped: 1, no_email: 2, invalid: 1,
    });
  });

  it("treats missing status as pending", () => {
    assert.deepEqual(deliveryCounts([{ recipient_email: "a@example.com" }]), {
      pending: 1, sent: 0, failed: 0, skipped: 0, no_email: 0, invalid: 0,
    });
  });

  it("returns an all-zero grid for no deliveries", () => {
    assert.deepEqual(deliveryCounts([]), {
      pending: 0, sent: 0, failed: 0, skipped: 0, no_email: 0, invalid: 0,
    });
    assert.deepEqual(deliveryCounts(null), {
      pending: 0, sent: 0, failed: 0, skipped: 0, no_email: 0, invalid: 0,
    });
  });
});