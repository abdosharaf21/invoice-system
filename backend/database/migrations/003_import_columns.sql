-- Migration 003: Import-targeted column additions.
--
-- Phase 3 (Accounting File Import) requires a few schema extensions:
--
--   1. `invoices.uuid` - upstream accounting files identify invoices by a
--      UUID. It is the preferred *(and strongest)* duplicate-detection key
--      for imported invoices, so we persist it. It is nullable because
--      pre-existing / manually created invoices have no UUID, and unique so
--      UUID collisions across imports are impossible.
--
--   2. `import_batches.source_type` - distinguishes where a batch came from:
--      'manual' (future UI entry) vs 'file' (this phase). Files also need to
--      record which format produced the rows.
--
--   3. `import_batch_errors.field` and `import_batch_errors.error_code` -
--      row errors carry a structured payload (row, field, error code,
--      message, raw row). `row_number` + `error_message` already exist, but
--      the structured field/code columns are required by the Phase 3 spec
--      so the fix-up tooling and the API can render actionable errors.

ALTER TABLE `invoices`
    ADD COLUMN `uuid` CHAR(36) DEFAULT NULL AFTER `id`,
    ADD UNIQUE KEY `uq_invoices_uuid` (`uuid`);

ALTER TABLE `import_batches`
    ADD COLUMN `source_type` VARCHAR(20) NOT NULL DEFAULT 'manual' AFTER `file_type`;

ALTER TABLE `import_batch_errors`
    ADD COLUMN `field` VARCHAR(100) DEFAULT NULL AFTER `row_number`,
    ADD COLUMN `error_code` VARCHAR(50) DEFAULT NULL AFTER `field`;