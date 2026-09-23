-- Migration 000: Foundation schema bootstrap.
-- verify: companies, users, roles, user_roles
--
-- Phase 12 audit finding: the migration catalog was not bootstrappable from
-- an empty database. The Phase 1 foundation (companies, users, roles,
-- user_roles) was created by hand before migrations were tracked, so a fresh
-- ``deploy/migrate.sh`` run failed at migration 002 with
-- ``ERROR 1824 FAILED to open the referenced table 'companies'`` because the
-- FK target tables never existed. This migration makes the catalog
-- self-contained: run it first (``000``) so every later reference resolves.
--
-- The four tables below are byte-compatible with how they were provisioned
-- in Phase 1 minus nothing: only the *base* columns are created. Migration
-- 006 appends the companies/users preference columns and migration 011 appends
-- the audit traceability columns, exactly as they were added in production
-- history. Counter start values (AUTO_INCREMENT) are intentionally not
-- pinned: a fresh database starts at 1.
--
-- ``CREATE TABLE IF NOT EXISTS`` keeps this idempotent for databases that
-- were already provisioned by hand (the guarded rename in 008 and the
-- ``--record-existing`` seeding path expect exactly that behaviour).

CREATE TABLE IF NOT EXISTS `companies` (
    `id`                        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `name`                      VARCHAR(255)    NOT NULL,
    `tax_registration_number`   VARCHAR(50)     DEFAULT NULL,
    `email`                     VARCHAR(255)    DEFAULT NULL,
    `phone`                     VARCHAR(50)     DEFAULT NULL,
    `address`                   TEXT            DEFAULT NULL,
    `is_active`                 TINYINT(1)      NOT NULL DEFAULT 1,
    `created_at`                DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`                DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_companies_tax_registration_number` (`tax_registration_number`),
    KEY `idx_companies_name` (`name`),
    KEY `idx_companies_active` (`is_active`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users` (
    `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `company_id`    BIGINT UNSIGNED DEFAULT NULL,
    `username`      VARCHAR(100)    NOT NULL,
    `email`         VARCHAR(255)    NOT NULL,
    `password_hash` VARCHAR(255)    NOT NULL,
    `first_name`    VARCHAR(100)    DEFAULT NULL,
    `last_name`     VARCHAR(100)    DEFAULT NULL,
    `is_active`     TINYINT(1)      NOT NULL DEFAULT 1,
    `last_login_at` DATETIME        DEFAULT NULL,
    `created_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_users_username` (`username`),
    UNIQUE KEY `uq_users_email` (`email`),
    KEY `idx_users_company` (`company_id`),
    CONSTRAINT `fk_users_company`
        FOREIGN KEY (`company_id`) REFERENCES `companies` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `roles` (
    `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `name`        VARCHAR(100)    NOT NULL,
    `description` VARCHAR(255)    DEFAULT NULL,
    `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_roles_name` (`name`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `user_roles` (
    `user_id`     BIGINT UNSIGNED NOT NULL,
    `role_id`     BIGINT UNSIGNED NOT NULL,
    `assigned_at` DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`, `role_id`),
    KEY `fk_user_roles_role` (`role_id`),
    CONSTRAINT `fk_user_roles_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_user_roles_role`
        FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;