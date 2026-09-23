-- Migration 004: Reconciliation error detail columns.
-- verify: reconciliation_errors
--
-- Phase 4 (reconciliation engine) needs field-level comparison results to be
-- both machine-readable and human-readable. The Phase 2 schema only stored a
-- generic error_type + message on reconciliation_errors, which is not enough
-- to tell a user exactly which field differs and by how much.
--
-- This migration adds nullable detail columns. All are optional so existing
-- error rows and callers keep working unchanged.

ALTER TABLE `reconciliation_errors`
    ADD COLUMN `field`              VARCHAR(100)   DEFAULT NULL AFTER `entity_id`,
    ADD COLUMN `accounting_value`   VARCHAR(255)   DEFAULT NULL AFTER `field`,
    ADD COLUMN `tax_authority_value` VARCHAR(255)  DEFAULT NULL AFTER `accounting_value`,
    ADD COLUMN `difference`         DECIMAL(15, 2) DEFAULT NULL AFTER `tax_authority_value`;