-- Migration 008: Platform audit trail.
-- verify: audit_logs
--
-- Adds the `audit_logs` table that backs the audit_trail module: the
-- record_event / record_security_event helpers and the
-- GET /api/audit-trail/logs API.
--
-- Design (adapted from the POS audit trail, scoped to this single-tenant
-- invoice system):
--
--   * The event carries the acting user (actor_id/actor_email/role), the
--     action verb, the affected resource, the outcome, a free-form JSON
--     metadata payload, the request correlation id, and the client's IP
--     address and user agent where available.
--   * No organization/company column: this system has no multi-tenant
--     scope, so one global audit stream is the correct model.
--   * `metadata` is JSON so structured details can be filtered later
--     without schema churn. Audit records must never contain secrets
--     (passwords, tokens, uploaded file bodies) — the module enforces
--     this; the column is type-checked JSON for integrity.
--   * Indexes cover the common query paths: time range, actor, action,
--     resource, outcome and correlation id.
--
-- Note for live databases provisioned before migrations were tracked:
-- those environments contain a Phase-1 `audit_logs` table (created by
-- hand, referenced by no code, and shaped differently — description /
-- entity columns plus a company column that never used). This migration
-- deterministically renames that untracked table aside (preserving any
-- data in `audit_logs_legacy`) before creating the canonical table. On a
-- fresh database the rename is a guarded no-op.

SET @audit_008_legacy := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'audit_logs'
);
SET @audit_008_sql := IF(
    @audit_008_legacy = 1,
    'RENAME TABLE `audit_logs` TO `audit_logs_legacy`',
    'SELECT 1'
);
PREPARE audit_008_statement FROM @audit_008_sql;
EXECUTE audit_008_statement;
DEALLOCATE PREPARE audit_008_statement;

CREATE TABLE IF NOT EXISTS `audit_logs` (
    `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `actor_id`      BIGINT UNSIGNED DEFAULT NULL,
    `actor_email`   VARCHAR(255)    DEFAULT NULL,
    `role`          VARCHAR(50)     DEFAULT NULL,
    `action`        VARCHAR(50)     NOT NULL,
    `resource_type` VARCHAR(100)    NOT NULL,
    `resource_id`   VARCHAR(255)    DEFAULT NULL,
    `result`        VARCHAR(20)     NOT NULL DEFAULT 'success',
    `metadata`      JSON            DEFAULT NULL,
    `request_id`    VARCHAR(128)    DEFAULT NULL,
    `ip_address`    VARCHAR(45)     DEFAULT NULL,
    `user_agent`    VARCHAR(500)    DEFAULT NULL,
    `created_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_audit_logs_created_at` (`created_at`),
    KEY `idx_audit_logs_actor` (`actor_id`),
    KEY `idx_audit_logs_action` (`action`),
    KEY `idx_audit_logs_resource` (`resource_type`, `resource_id`),
    KEY `idx_audit_logs_result` (`result`),
    KEY `idx_audit_logs_request_id` (`request_id`),
    CONSTRAINT `fk_audit_logs_actor`
        FOREIGN KEY (`actor_id`) REFERENCES `users` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;