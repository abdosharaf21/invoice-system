/**
 * Email automation API client — consuming /api/email (status, diagnostics)
 * and the per-run delivery endpoints under /api/reconciliation.
 *
 * The /api/email endpoints are admin-only on the backend; non-admin callers
 * receive 403. The delivery endpoints require the admin, accountant or
 * manager role. Responses follow the standard { success, data } envelope
 * and the shared api client unwraps `data`, so these functions return the
 * payload object directly.
 */

import { api } from "../api/client.js";

/** Read-only email configuration status (admin only). */
export async function getEmailStatus() {
  return api.get("/api/email/status");
}

/** Send a single diagnostic test email to `recipient` (admin only). */
export async function sendTestEmail(recipient) {
  return api.post("/api/email/test", { to: recipient });
}

/** Per-taxpayer notification deliveries recorded for a run. */
export async function listRunEmailDeliveries(runId) {
  return api.get(`/api/reconciliation/runs/${runId}/email-deliveries`);
}

/** Explicitly resend one recorded delivery for a run. */
export async function resendEmailDelivery(runId, deliveryId) {
  return api.post(
    `/api/reconciliation/runs/${runId}/email-deliveries/${deliveryId}/resend`,
  );
}