-- Migration 005: Widen reconciliation match statuses.
-- verify: reconciliation_results
--
-- The Phase 2 schema stored reconciliation_results.match_status as
-- VARCHAR(20). The reconciliation engine's status vocabulary includes
-- 'missing_in_tax_authority' (23 chars) and 'extra_in_tax_authority'
-- (22 chars), so the column is widened to 32 characters to fit the full
-- status set.

ALTER TABLE `reconciliation_results`
    MODIFY COLUMN `match_status` VARCHAR(32) NOT NULL;