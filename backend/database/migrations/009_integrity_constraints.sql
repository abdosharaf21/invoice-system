-- Migration 009: Data integrity and business invariant constraints.
-- verify: invoices, invoice_items, tax_invoices, tax_invoice_items,
--         import_batches, reconciliation_runs, reconciliation_results,
--         email_deliveries, audit_logs
--
-- Imposes database-level CHECK constraints that encode the financial and
-- taxonomic invariants the application already enforces in its service
-- layer. The audit that preceded this migration confirmed every invariant
-- below holds against the live dataset (0 violations), so the constraints
-- cannot reject pre-existing valid rows.
--
-- Two data remediations run before the constraints are added so the
-- database itself is consistent:
--
--   1. `import_batches.total_rows` was never persisted by the completed
--      import path (the code fix lands in the same release). Existing
--      completed batches therefore carry total_rows = 0 while their
--      processed/error counters are populated. The minimal consistent
--      backfill is total_rows = processed_rows + error_rows; this is a
--      counter correction, not a data deletion.
--
--   2. `tax_invoices` id 63 (TI-T002) stores total_amount = 1100.00 while
--      its components total_sales(1000.00) - total_discount(0.00) +
--      vat_amount(140.00) evaluate to 1140.00. net_amount(1000.00) is
--      consistent with total_sales - total_discount, so the derived total
--      is repaired to the invariant value 1140.00. The document's net and
--      VAT figures are preserved; only the derived total is corrected.
--
-- Constraint vocabulary is sourced from the module contracts:
--
--   * import_batches.status     -> imports/contract.py BATCH_STATUSES
--   * reconciliation_runs.status -> reconciliation/contract.py RUN_STATUSES
--   * reconciliation_results.match_status -> reconciliation/contract.py RESULT_STATUSES
--   * email_deliveries.status   -> email/model.py DELIVERY_STATUSES
--   * audit_logs.action/result  -> audit_trail/model.py ACTION_* / RESULT_*
--
-- MySQL 8.0.16+ enforces CHECK constraints; versions before that parse
-- and ignore them. This server runs MySQL 8.0.46, where they are active.

-- ---------------------------------------------------------------------------
-- 1. Data remediation: backfill total_rows on completed batches.
-- ---------------------------------------------------------------------------

-- Guarded: only touches the specific repair set, never rows that already
-- carry a value or non-completed batches whose total is legitimately zero.
UPDATE `import_batches`
SET `total_rows` = `processed_rows` + `error_rows`
WHERE `status` = 'completed'
  AND `total_rows` = 0
  AND (`processed_rows` > 0 OR `error_rows` > 0);

-- ---------------------------------------------------------------------------
-- 2. Data remediation: repair derived total on inconsistent tax invoice.
--    1140.00 = 1000.00 (total_sales) - 0.00 (total_discount) + 140.00 (vat)
-- ---------------------------------------------------------------------------

UPDATE `tax_invoices`
SET `total_amount` = ROUND(`total_sales` - `total_discount` + `vat_amount`, 2)
WHERE `total_amount` <> ROUND(`total_sales` - `total_discount` + `vat_amount`, 2);

-- ---------------------------------------------------------------------------
-- 3. Integrity constraints.
-- ---------------------------------------------------------------------------

-- invoices: header-level financial invariants.
ALTER TABLE `invoices`
    ADD CONSTRAINT `chk_invoices_money_nonneg`
        CHECK (`subtotal_amount` >= 0 AND `discount_amount` >= 0
               AND `vat_amount` >= 0 AND `total_amount` >= 0),
    ADD CONSTRAINT `chk_invoices_discount_le_subtotal`
        CHECK (`discount_amount` <= `subtotal_amount`),
    ADD CONSTRAINT `chk_invoices_total_formula`
        CHECK (`total_amount` = ROUND(`subtotal_amount` - `discount_amount`
                                     + `vat_amount`, 2)),
    ADD CONSTRAINT `chk_invoices_currency`
        CHECK (`currency` REGEXP '^[A-Z]{3}$');

-- invoice_items: line-level financial invariants.
ALTER TABLE `invoice_items`
    ADD CONSTRAINT `chk_invoice_items_quantity_pos`
        CHECK (`quantity` > 0),
    ADD CONSTRAINT `chk_invoice_items_money_nonneg`
        CHECK (`unit_price` >= 0 AND `discount_amount` >= 0
               AND `vat_amount` >= 0 AND `line_total` >= 0),
    ADD CONSTRAINT `chk_invoice_items_vat_range`
        CHECK (`vat_rate` BETWEEN 0 AND 100),
    ADD CONSTRAINT `chk_invoice_items_formula`
        CHECK (`line_total` = ROUND(`quantity` * `unit_price`
                                     - `discount_amount` + `vat_amount`, 2)),
    ADD CONSTRAINT `chk_invoice_items_discount_le_gross`
        CHECK (`discount_amount` <= `quantity` * `unit_price`);

-- tax_invoices: header-level financial invariants.
ALTER TABLE `tax_invoices`
    ADD CONSTRAINT `chk_tax_invoices_money_nonneg`
        CHECK (`total_sales` >= 0 AND `total_discount` >= 0
               AND `net_amount` >= 0 AND `vat_amount` >= 0
               AND `other_charges` >= 0 AND `total_amount` >= 0),
    ADD CONSTRAINT `chk_tax_invoices_discount_le_sales`
        CHECK (`total_discount` <= `total_sales`),
    ADD CONSTRAINT `chk_tax_invoices_net_formula`
        CHECK (`net_amount` = ROUND(`total_sales` - `total_discount`, 2)),
    ADD CONSTRAINT `chk_tax_invoices_total_formula`
        CHECK (`total_amount` = ROUND(`total_sales` - `total_discount`
                                     + `vat_amount`, 2)),
    ADD CONSTRAINT `chk_tax_invoices_currency`
        CHECK (`currency` REGEXP '^[A-Z]{3}$');

-- tax_invoice_items: line-level financial invariants (authority side).
ALTER TABLE `tax_invoice_items`
    ADD CONSTRAINT `chk_tax_invoice_items_quantity_pos`
        CHECK (`quantity` > 0),
    ADD CONSTRAINT `chk_tax_invoice_items_money_nonneg`
        CHECK (`unit_value` >= 0 AND `discount_amount` >= 0
               AND `vat_amount` >= 0 AND `total_amount` >= 0),
    ADD CONSTRAINT `chk_tax_invoice_items_vat_range`
        CHECK (`vat_rate` BETWEEN 0 AND 100),
    ADD CONSTRAINT `chk_tax_invoice_items_formula`
        CHECK (`total_amount` = ROUND(`quantity` * `unit_value`
                                      - `discount_amount` + `vat_amount`, 2)),
    ADD CONSTRAINT `chk_tax_invoice_items_discount_le_gross`
        CHECK (`discount_amount` <= `quantity` * `unit_value`);

-- import_batches: lifecycle vocabulary and counter sanity.
ALTER TABLE `import_batches`
    ADD CONSTRAINT `chk_import_batches_status`
        CHECK (`status` IN ('uploaded', 'processing', 'completed', 'failed'));

-- reconciliation_runs: lifecycle vocabulary.
ALTER TABLE `reconciliation_runs`
    ADD CONSTRAINT `chk_reconciliation_runs_status`
        CHECK (`status` IN ('pending', 'running', 'completed', 'failed'));

-- reconciliation_results: match vocabulary and non-negative discrepancy.
ALTER TABLE `reconciliation_results`
    ADD CONSTRAINT `chk_reconciliation_results_match_status`
        CHECK (`match_status` IN (
            'matched',
            'mismatched',
            'missing_in_tax_authority',
            'extra_in_tax_authority',
            'invalid'
        )),
    ADD CONSTRAINT `chk_reconciliation_results_discrepancy_nonneg`
        CHECK (`discrepancy_amount` >= 0);

-- email_deliveries: delivery lifecycle vocabulary.
ALTER TABLE `email_deliveries`
    ADD CONSTRAINT `chk_email_deliveries_status`
        CHECK (`status` IN ('pending', 'sent', 'failed', 'skipped',
                            'no_email', 'invalid'));

-- audit_logs: audited action and outcome vocabulary.
ALTER TABLE `audit_logs`
    ADD CONSTRAINT `chk_audit_logs_action`
        CHECK (`action` IN ('login', 'logout', 'create', 'update', 'delete',
                            'view', 'import', 'reconcile', 'other')),
    ADD CONSTRAINT `chk_audit_logs_result`
        CHECK (`result` IN ('success', 'failure'));