-- Migration 011: Audit traceability (tenant attribution + before/after state).
-- verify: audit_logs
--
-- Phase 10 (Audit, Compliance & Traceability). Additive only; migration 008
-- is untouched and existing audit records are preserved:
--
--   * company_id     : tenant attribution. The system is multi-company; audit
--                      records must be scoped to the affected company so
--                      cross-tenant review is impossible. NULL for events
--                      with no tenancy (unauthenticated security events,
--                      application-wide settings).
--   * actor_type     : 'user' (an authenticated human) or 'system' (a
--                      background / recovery / maintenance action with no
--                      human actor). Avoids fake user ids.
--   * before_state   : compact structured snapshot of the resource before
--                      the change (whitelisted fields only).
--   * after_state    : compact structured snapshot after the change.
--   * Index + FK     : company scoping is queryable; companies(id) is the
--                      authoritative owner table. DELETE SET NULL preserves
--                      audit history if a tenant is later removed.
--
-- No column carries secrets: password hashes, tokens and credentials are
-- never written here (enforced by the audit module's redaction layer).

ALTER TABLE `audit_logs`
    ADD COLUMN `company_id`   BIGINT UNSIGNED DEFAULT NULL AFTER `actor_id`,
    ADD COLUMN `actor_type`   VARCHAR(20)     NOT NULL DEFAULT 'user' AFTER `role`,
    ADD COLUMN `before_state` JSON            DEFAULT NULL AFTER `metadata`,
    ADD COLUMN `after_state`  JSON            DEFAULT NULL AFTER `before_state`,
    ADD KEY `idx_audit_logs_company` (`company_id`),
    ADD CONSTRAINT `fk_audit_logs_company`
        FOREIGN KEY (`company_id`) REFERENCES `companies` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE;