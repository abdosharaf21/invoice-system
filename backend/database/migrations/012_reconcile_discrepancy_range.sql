-- Phase 15: correct the reconciliation discrepancy CHECK constraint.
--
-- `009_integrity_constraints.sql` introduced
-- `chk_reconciliation_results_discrepancy_nonneg` requiring
-- `discrepancy_amount >= 0`. The reconciliation engine intentionally stores
-- a *signed* discrepancy (accounting total minus tax-authority total), so a
-- row whose tax authority overstates the accounting amount is legitimately
-- negative. The frontend report panel renders exactly these values with
-- `neg`/`pos` styling, and the engine unit suite asserts signed values.
--
-- The `>= 0` check therefore rejects valid business outcomes and aborts the
-- entire reconciliation run (HTTP 500) whenever the tax authority line
-- exceeds the accounting line. This migration replaces the one-sided check
-- with a symmetric magnitude bound that preserves the signed semantics while
-- still guarding the column against absurd values.

ALTER TABLE `reconciliation_results`
    DROP CHECK `chk_reconciliation_results_discrepancy_nonneg`,
    ADD CONSTRAINT `chk_reconciliation_results_discrepancy_range`
        CHECK (`discrepancy_amount` BETWEEN -999999999999.99 AND 999999999999.99);

-- verify: reconciliation_results