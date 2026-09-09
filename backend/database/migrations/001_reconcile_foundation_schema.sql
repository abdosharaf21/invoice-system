-- Migration 001: Reconcile the foundation schema.
--
-- Reconciles the Phase 1 foundation schema with the code that relies on it.
--
-- 1. The AuthRepository persists revoked JWT ids (jti) in a
--    `refresh_token_blocklist` table, but that table was never created.
--    Without it, /api/auth/logout and /api/auth/refresh crash against a
--    real database. This migration creates it.
--
-- 2. No changes are required for `companies`, `users`, `roles`,
--    `user_roles` and `audit_logs`; the users/companies/roles schema is
--    already the target design. The Python user model/repository layer is
--    updated in code to match this schema (see the Phase 2 code changes).

CREATE TABLE IF NOT EXISTS `refresh_token_blocklist` (
    `id`           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `jti`          VARCHAR(64)     NOT NULL,
    `token_type`   VARCHAR(16)     NOT NULL DEFAULT 'access',
    `expires_at`   DATETIME        NOT NULL,
    `created_at`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_refresh_token_blocklist_jti` (`jti`),
    KEY `idx_refresh_token_blocklist_expires` (`expires_at`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;