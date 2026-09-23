-- Migration 002: E-Invoice domain tables.
-- verify: reconciliation_runs
--
-- Adds the Phase 2 domain schema on top of the reconciled foundation:
--   * import tracking  -> import_batches, import_batch_errors
--   * accounting side  -> invoices, invoice_items
--   * tax authority    -> tax_invoices, tax_invoice_items
--   * reconciliation   -> reconciliation_runs, reconciliation_results,
--                         reconciliation_errors
--
-- The accounting side (invoices) is the source of truth for what was
-- issued/received. The tax authority side (tax_invoices) mirrors the
-- E-Invoice documents exchanged with the tax authority and is kept
-- separate by design. Reconciliation joins the two.
--
-- All money amounts are DECIMAL(15,2). All foreign keys cascade from their
-- parent rows so cleanup stays predictable.

-- ---------------------------------------------------------------------------
-- 1. Import / batch tracking
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `import_batches` (
    `id`             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `company_id`     BIGINT UNSIGNED NOT NULL,
    `filename`       VARCHAR(255)    NOT NULL,
    `file_type`      VARCHAR(20)     NOT NULL DEFAULT 'csv',
    `status`         VARCHAR(20)     NOT NULL DEFAULT 'uploaded',
    `total_rows`     INT UNSIGNED    NOT NULL DEFAULT 0,
    `processed_rows` INT UNSIGNED    NOT NULL DEFAULT 0,
    `error_rows`     INT UNSIGNED    NOT NULL DEFAULT 0,
    `uploaded_by`    BIGINT UNSIGNED DEFAULT NULL,
    `started_at`     DATETIME        DEFAULT NULL,
    `finished_at`    DATETIME        DEFAULT NULL,
    `created_at`     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_import_batches_company` (`company_id`),
    KEY `idx_import_batches_status` (`status`),
    KEY `idx_import_batches_uploaded_by` (`uploaded_by`),
    CONSTRAINT `fk_import_batches_company`
        FOREIGN KEY (`company_id`) REFERENCES `companies` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_import_batches_uploaded_by`
        FOREIGN KEY (`uploaded_by`) REFERENCES `users` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `import_batch_errors` (
    `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `batch_id`    BIGINT UNSIGNED NOT NULL,
    `row_number`  INT UNSIGNED    NOT NULL,
    `error_message` TEXT          NOT NULL,
    `raw_data`    TEXT            DEFAULT NULL,
    `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_import_batch_errors_batch` (`batch_id`),
    CONSTRAINT `fk_import_batch_errors_batch`
        FOREIGN KEY (`batch_id`) REFERENCES `import_batches` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 2. Accounting invoices (the books)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `invoices` (
    `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `company_id`         BIGINT UNSIGNED NOT NULL,
    `import_batch_id`    BIGINT UNSIGNED DEFAULT NULL,
    `invoice_number`     VARCHAR(50)     NOT NULL,
    `invoice_type`       VARCHAR(20)     NOT NULL DEFAULT 'sales',
    `invoice_date`       DATE            NOT NULL,
    `due_date`           DATE            DEFAULT NULL,
    `currency`           VARCHAR(3)      NOT NULL DEFAULT 'EGP',
    `counterparty_name`  VARCHAR(255)    NOT NULL,
    `counterparty_tax_id`VARCHAR(50)     DEFAULT NULL,
    `subtotal_amount`    DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `discount_amount`    DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `vat_amount`         DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `total_amount`       DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `status`             VARCHAR(20)     NOT NULL DEFAULT 'draft',
    `created_at`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_invoices_company_number` (`company_id`, `invoice_number`),
    KEY `idx_invoices_company_date` (`company_id`, `invoice_date`),
    KEY `idx_invoices_status` (`status`),
    KEY `idx_invoices_import_batch` (`import_batch_id`),
    CONSTRAINT `fk_invoices_company`
        FOREIGN KEY (`company_id`) REFERENCES `companies` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_invoices_import_batch`
        FOREIGN KEY (`import_batch_id`) REFERENCES `import_batches` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `invoice_items` (
    `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `invoice_id`      BIGINT UNSIGNED NOT NULL,
    `description`     VARCHAR(255)    NOT NULL,
    `quantity`        DECIMAL(15, 4)  NOT NULL DEFAULT 1.0000,
    `unit_price`      DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `discount_amount` DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `vat_rate`        DECIMAL(5, 2)   NOT NULL DEFAULT 0.00,
    `vat_amount`      DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `line_total`      DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_invoice_items_invoice` (`invoice_id`),
    CONSTRAINT `fk_invoice_items_invoice`
        FOREIGN KEY (`invoice_id`) REFERENCES `invoices` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 3. Tax authority invoices (E-Invoice documents)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `tax_invoices` (
    `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `company_id`         BIGINT UNSIGNED NOT NULL,
    `account_invoice_id` BIGINT UNSIGNED DEFAULT NULL,
    `import_batch_id`    BIGINT UNSIGNED DEFAULT NULL,
    `uuid`               CHAR(36)        DEFAULT NULL,
    `internal_id`        VARCHAR(50)     DEFAULT NULL,
    `document_type`      VARCHAR(20)     NOT NULL DEFAULT 'invoice',
    `issue_datetime`     DATETIME        NOT NULL,
    `currency`           VARCHAR(3)      NOT NULL DEFAULT 'EGP',
    `exchange_rate`      DECIMAL(12, 6)  NOT NULL DEFAULT 1.000000,
    `seller_name`        VARCHAR(255)    NOT NULL,
    `seller_tax_id`      VARCHAR(50)     DEFAULT NULL,
    `buyer_name`         VARCHAR(255)    DEFAULT NULL,
    `buyer_tax_id`       VARCHAR(50)     DEFAULT NULL,
    `total_sales`        DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `total_discount`     DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `net_amount`         DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `vat_amount`         DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `other_charges`      DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `total_amount`       DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `submission_status`  VARCHAR(20)     NOT NULL DEFAULT 'draft',
    `submission_errors`  TEXT            DEFAULT NULL,
    `created_at`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_tax_invoices_uuid` (`uuid`),
    UNIQUE KEY `uq_tax_invoices_company_internal` (`company_id`, `internal_id`),
    KEY `idx_tax_invoices_company` (`company_id`),
    KEY `idx_tax_invoices_account_invoice` (`account_invoice_id`),
    KEY `idx_tax_invoices_submission_status` (`submission_status`),
    KEY `idx_tax_invoices_import_batch` (`import_batch_id`),
    CONSTRAINT `fk_tax_invoices_company`
        FOREIGN KEY (`company_id`) REFERENCES `companies` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_tax_invoices_account_invoice`
        FOREIGN KEY (`account_invoice_id`) REFERENCES `invoices` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT `fk_tax_invoices_import_batch`
        FOREIGN KEY (`import_batch_id`) REFERENCES `import_batches` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `tax_invoice_items` (
    `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `tax_invoice_id`  BIGINT UNSIGNED NOT NULL,
    `description`     VARCHAR(255)    NOT NULL,
    `item_type`       VARCHAR(20)     NOT NULL DEFAULT 'composite',
    `quantity`        DECIMAL(15, 4)  NOT NULL DEFAULT 1.0000,
    `unit_value`      DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `vat_rate`        DECIMAL(5, 2)   NOT NULL DEFAULT 0.00,
    `vat_amount`      DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `discount_amount` DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `total_amount`    DECIMAL(15, 2)  NOT NULL DEFAULT 0.00,
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_tax_invoice_items_invoice` (`tax_invoice_id`),
    CONSTRAINT `fk_tax_invoice_items_invoice`
        FOREIGN KEY (`tax_invoice_id`) REFERENCES `tax_invoices` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 4. Reconciliation
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `reconciliation_runs` (
    `id`               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `company_id`       BIGINT UNSIGNED NOT NULL,
    `period`           VARCHAR(20)     NOT NULL,
    `status`           VARCHAR(20)     NOT NULL DEFAULT 'pending',
    `invoice_count`    INT UNSIGNED    NOT NULL DEFAULT 0,
    `tax_invoice_count` INT UNSIGNED   NOT NULL DEFAULT 0,
    `matched_count`    INT UNSIGNED    NOT NULL DEFAULT 0,
    `unmatched_count`  INT UNSIGNED    NOT NULL DEFAULT 0,
    `error_count`      INT UNSIGNED    NOT NULL DEFAULT 0,
    `started_at`       DATETIME        DEFAULT NULL,
    `finished_at`      DATETIME        DEFAULT NULL,
    `created_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_reconciliation_runs_company` (`company_id`),
    KEY `idx_reconciliation_runs_period` (`period`),
    KEY `idx_reconciliation_runs_status` (`status`),
    CONSTRAINT `fk_reconciliation_runs_company`
        FOREIGN KEY (`company_id`) REFERENCES `companies` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `reconciliation_results` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `run_id`            BIGINT UNSIGNED NOT NULL,
    `account_invoice_id` BIGINT UNSIGNED DEFAULT NULL,
    `tax_invoice_id`    BIGINT UNSIGNED DEFAULT NULL,
    `match_status`      VARCHAR(20)     NOT NULL,
    `discrepancy_amount` DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    `notes`             TEXT            DEFAULT NULL,
    `created_at`        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_reconciliation_results_run_account` (`run_id`, `account_invoice_id`),
    UNIQUE KEY `uq_reconciliation_results_run_tax` (`run_id`, `tax_invoice_id`),
    KEY `idx_reconciliation_results_match_status` (`match_status`),
    CONSTRAINT `fk_reconciliation_results_run`
        FOREIGN KEY (`run_id`) REFERENCES `reconciliation_runs` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT `fk_reconciliation_results_account_invoice`
        FOREIGN KEY (`account_invoice_id`) REFERENCES `invoices` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT `fk_reconciliation_results_tax_invoice`
        FOREIGN KEY (`tax_invoice_id`) REFERENCES `tax_invoices` (`id`)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `reconciliation_errors` (
    `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `run_id`      BIGINT UNSIGNED NOT NULL,
    `source_type` VARCHAR(20)     NOT NULL,
    `entity_id`   BIGINT UNSIGNED DEFAULT NULL,
    `error_type`  VARCHAR(50)     NOT NULL,
    `message`     TEXT            NOT NULL,
    `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_reconciliation_errors_run` (`run_id`),
    CONSTRAINT `fk_reconciliation_errors_run`
        FOREIGN KEY (`run_id`) REFERENCES `reconciliation_runs` (`id`)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;