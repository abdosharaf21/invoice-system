-- Migration 007: Taxpayer notification email support.
-- verify: email_deliveries
--
-- Phase 7 (rebuilt) emails reconciliation summaries to the run's
-- *taxpayers/counterparties*, resolved from the imported accounting data —
-- not to internal users. Two changes are required:
--
--   1. `invoices.counterparty_email` - the counterparty's notification
--      address, captured from imported accounting files and stored on the
--      accounting invoice (the source of truth). It is optional because
--      pre-existing / manually created invoices may lack it; such taxpayers
--      are recorded as "no email" on delivery tracking instead of failing.
--
--   2. `email_deliveries` - tracks every per-taxpayer notification attempt
--      made for a reconciliation run: pending/sent/failed/skipped/no_email/
--      invalid states, the request correlation id, attempt timestamps and a
--      failure reason. One row exists per (run, recipient), so a taxpayer is
--      never emailed twice for the same run unless an operator explicitly
--      resends.
--
-- The new invoices column is appended AFTER `updated_at` (mirroring the
-- convention in migration 006) so the existing positional `SELECT *` row
-- mapping in InvoiceRepository keeps working unchanged.

ALTER TABLE `invoices`
    ADD COLUMN `counterparty_email` VARCHAR(255) DEFAULT NULL AFTER `updated_at`;

CREATE TABLE IF NOT EXISTS `email_deliveries` (
    `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `company_id`      BIGINT UNSIGNED NOT NULL,
    `run_id`          BIGINT UNSIGNED NOT NULL,
    `recipient_email` VARCHAR(255)    DEFAULT NULL,
    `taxpayer_name`   VARCHAR(255)    DEFAULT NULL,
    `taxpayer_tax_id` VARCHAR(50)     DEFAULT NULL,
    `invoice_count`   INT UNSIGNED    NOT NULL DEFAULT 0,
    `subject`         VARCHAR(255)    NOT NULL DEFAULT '',
    `status`          VARCHAR(20)     NOT NULL DEFAULT 'pending',
    `failure_reason`  VARCHAR(255)    DEFAULT NULL,
    `request_id`      VARCHAR(128)    DEFAULT NULL,
    `attempted_at`    DATETIME        DEFAULT NULL,
    `sent_at`         DATETIME        DEFAULT NULL,
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_email_deliveries_run_recipient` (`run_id`, `recipient_email`),
    KEY `idx_email_deliveries_company` (`company_id`),
    KEY `idx_email_deliveries_run` (`run_id`),
    KEY `idx_email_deliveries_status` (`status`),
    KEY `idx_email_deliveries_recipient` (`recipient_email`),
    CONSTRAINT `fk_email_deliveries_company`
        FOREIGN KEY (`company_id`) REFERENCES `companies` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_email_deliveries_run`
        FOREIGN KEY (`run_id`) REFERENCES `reconciliation_runs` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;