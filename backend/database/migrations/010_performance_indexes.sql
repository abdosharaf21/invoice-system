-- Migration 010: Performance indexes for Phase 8 hot read paths.
-- verify: tax_invoices
--
-- Indexes touched: tax_invoices, import_batches, reconciliation_runs,
-- email_deliveries.
--
-- The Phase 8 performance audit measured every hot query against a
-- structurally identical copy of the live schema. EXPLAIN showed three
-- gaps worth fixing and two index duplicates worth removing:
--
--   1. tax_invoices are loaded per period with
--      `WHERE company_id = ? AND issue_datetime LIKE 'YYYY-MM%'`; no index
--      led with (company_id, issue_datetime), so MySQL ran a FULL TABLE SCAN
--      (EXPLAIN type=ALL) for every reconciliation run. The new composite
--      index turns the period load into a range access on the company's
--      rows.
--
--   2. import_batches and reconciliation_runs are listed newest-first within
--      a company (`ORDER BY created_at DESC, id DESC`); the old plan ran a
--      per-company filesort on every page. The new composites make the
--      ordering index-driven (backward index scan), so the cost no longer
--      grows with a company's history size.
--
--   3. idx_tax_invoices_company is a leftmost-prefix duplicate of
--      uq_tax_invoices_company_internal (company_id, ...) and of the new
--      composite above; idx_email_deliveries_run is a leftmost-prefix
--      duplicate of uq_email_deliveries_run_recipient (run_id, ...). Both
--      drops are metadata-only and cannot change any query plan, but remove
--      redundant index maintenance and storage.
--
-- All statements are additive/housekeeping: no table data is altered, no
-- constraint (including the FK guarantee that the refreshed indexes' prefix
-- columns already satisfy) is removed.

-- 1. Period loads of tax authority invoices (fix the full-table scan).
ALTER TABLE `tax_invoices`
    ADD INDEX `idx_tax_invoices_company_issue_datetime`
        (`company_id`, `issue_datetime`);

-- 2. Newest-first company lists for batches and reconciliation runs.
ALTER TABLE `import_batches`
    ADD INDEX `idx_import_batches_company_created`
        (`company_id`, `created_at`, `id`);

ALTER TABLE `reconciliation_runs`
    ADD INDEX `idx_reconciliation_runs_company_created`
        (`company_id`, `created_at`, `id`);

-- 3. Drop redundant leftmost-prefix duplicates (covered by the composites
--    and the existing unique indexes above).
ALTER TABLE `tax_invoices`
    DROP INDEX `idx_tax_invoices_company`;

ALTER TABLE `email_deliveries`
    DROP INDEX `idx_email_deliveries_run`;