"""Reconciliation service: orchestrates reconciliation runs end to end.

The service owns the run lifecycle:

1. create the run row as ``pending``,
2. mark it ``running`` with a start time,
3. load the company's accounting invoices and tax authority invoices for the
   target period,
4. run the pure reconciliation engine,
5. persist results, errors and the ``completed`` status in a single
   transaction,
6. on a fatal database/system error, mark the run ``failed`` and re-raise.

Individual invoice mismatches are expected outcomes, not errors. The run is
never reported successful unless every result row was persisted atomically.
"""

import logging
import math
from decimal import Decimal
from typing import List, Optional

from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation import export as report_export
from backend.modules.reconciliation.engine import (
    ReconcileOutcome,
    is_valid_period,
    normalize_period,
    reconcile,
)
from backend.modules.reconciliation.model import (
    ReconciliationRun,
)

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Coordinates reconciliation runs for a company and period."""

    def __init__(
        self,
        recon_repo,
        invoice_repo,
        tax_repo,
        user_repo=None,
    ) -> None:
        self._recon_repo = recon_repo
        self._invoice_repo = invoice_repo
        self._tax_repo = tax_repo
        self._user_repo = user_repo

    def company_for_user(self, user_id: int) -> Optional[int]:
        """Resolve the company id a user belongs to, if any."""
        if self._user_repo is None:
            return None
        user = self._user_repo.get_by_id(user_id)
        if user is None:
            return None
        return user.company_id

    def start_run(
        self,
        company_id: int,
        period: str,
        money_tolerance: Optional[Decimal] = None,
    ) -> tuple:
        """Run a full reconciliation for a company and 'YYYY-MM' period.

        Args:
            company_id: Owning company id.
            period: Billing period as 'YYYY-MM'.
            money_tolerance: Optional tolerance for money comparisons.

        Returns:
            ``(run, summary_counts)`` where the run is the persisted,
            completed run and summary_counts is a per-status breakdown.

        Raises:
            ValueError: if the period is malformed.
        """
        normalized = normalize_period(period)
        if not is_valid_period(normalized):
            raise ValueError(
                f"Invalid period '{period}'. Expected a 'YYYY-MM' period."
            )

        run = self._recon_repo.create_run(ReconciliationRun(
            company_id=company_id,
            period=normalized,
            status=c.RUN_PENDING,
        ))
        self._recon_repo.start_run(run.id)

        try:
            account_invoices = self._invoice_repo.list_by_company_and_period(
                company_id, normalized
            )
            tax_invoices = self._tax_repo.list_by_company_and_period(
                company_id, normalized
            )
            outcome = reconcile(
                account_invoices,
                tax_invoices,
                money_tolerance=money_tolerance,
            )
        except Exception:
            logger.exception("Reconciliation run %s failed", run.id)
            self._mark_failed(run.id)
            raise

        counts = self._counts(outcome)
        try:
            self._recon_repo.finish_run_transaction(
                run.id,
                outcome.results,
                outcome.errors,
                invoice_count=len(account_invoices),
                tax_invoice_count=len(tax_invoices),
                matched_count=counts[c.MATCHED],
                unmatched_count=counts[c.MISMATCHED]
                + counts[c.MISSING_IN_TAX_AUTHORITY]
                + counts[c.EXTRA_IN_TAX_AUTHORITY]
                + counts[c.INVALID],
                error_count=len(outcome.errors),
            )
        except Exception:
            logger.exception(
                "Failed to persist outcomes for reconciliation run %s", run.id
            )
            self._mark_failed(run.id)
            raise

        persisted = self._recon_repo.get_run_by_id(run.id)
        return persisted, counts

    def get_run(self, run_id: int, company_id: int) -> Optional[ReconciliationRun]:
        """Fetch a run by id, scoped to a company."""
        run = self._recon_repo.get_run_by_id(run_id)
        if run is None or run.company_id != company_id:
            return None
        return run

    def list_runs(
        self, company_id: int, limit: int = 50, offset: int = 0
    ) -> List[ReconciliationRun]:
        """List a company's runs, newest first."""
        return self._recon_repo.list_runs_by_company(
            company_id, limit=limit, offset=offset
        )

    def get_summary(self, run_id: int) -> dict:
        """Per-status result counts for a run, zero-filled."""
        raw = self._recon_repo.get_results_summary(run_id)
        return {status: int(raw.get(status, 0)) for status in c.RESULT_STATUSES}

    def get_results(self, run_id: int, company_id: int) -> Optional[List[dict]]:
        """Fetch a run's results (enriched), scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        return self._recon_repo.get_results_with_details(run_id)

    def get_errors(self, run_id: int, company_id: int):
        """Fetch a run's errors, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        return self._recon_repo.list_errors(run_id)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def get_report_summary(self, run_id: int, company_id: int) -> Optional[dict]:
        """Structured summary of a run, scoped to a company.

        Counts come from the persisted run's result rows (SQL aggregation)
        and the persisted error table — reconciliation is never re-run to
        produce the summary.
        """
        run = self.get_run(run_id, company_id)
        if run is None:
            return None
        statuses = self._recon_repo.get_results_summary(run_id)
        counts = {status: int(statuses.get(status, 0)) for status in c.RESULT_STATUSES}
        total = sum(counts.values())
        return {
            "run": run.to_dict(),
            "summary": {
                **counts,
                "total_results": total,
                "unmatched": total - counts[c.MATCHED],
                "errors": self._recon_repo.count_errors(run_id),
            },
        }

    def paginate_results(
        self,
        run_id: int,
        company_id: int,
        page: int,
        page_size: int,
        filters: Optional[dict] = None,
    ) -> Optional[dict]:
        """Paginated, filtered results for a run, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        query_filters = filters or {}
        total = self._recon_repo.count_results(run_id, query_filters)
        offset = (page - 1) * page_size
        items = self._recon_repo.list_results_report(
            run_id, limit=page_size, offset=offset, filters=query_filters
        )
        return self._envelope(items, total, page, page_size)

    def paginate_errors(
        self,
        run_id: int,
        company_id: int,
        page: int,
        page_size: int,
        filters: Optional[dict] = None,
    ) -> Optional[dict]:
        """Paginated, filtered errors for a run, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        query_filters = filters or {}
        total = self._recon_repo.count_errors(run_id, query_filters)
        offset = (page - 1) * page_size
        items = self._recon_repo.list_errors_report(
            run_id, limit=page_size, offset=offset, filters=query_filters
        )
        return self._envelope(items, total, page, page_size)

    def export_results(
        self,
        run_id: int,
        company_id: int,
        fmt: str,
        filters: Optional[dict] = None,
    ) -> Optional[tuple]:
        """Export a run's results (filtered) as csv/xlsx, scoped to a company.

        Returns ``(filename, mimetype, payload)`` or None when the run is not
        accessible. The full filtered dataset is streamed from the repository
        in batches.
        """
        if self.get_run(run_id, company_id) is None:
            return None
        rows = self._recon_repo.iter_results_report(run_id, filters or {})
        payload, mimetype, extension = report_export.build_file("results", rows, fmt)
        return f"reconciliation_results_{run_id}.{extension}", mimetype, payload

    def export_errors(
        self,
        run_id: int,
        company_id: int,
        fmt: str,
        filters: Optional[dict] = None,
    ) -> Optional[tuple]:
        """Export a run's errors (filtered) as csv/xlsx, scoped to a company."""
        if self.get_run(run_id, company_id) is None:
            return None
        rows = self._recon_repo.iter_errors_report(run_id, filters or {})
        payload, mimetype, extension = report_export.build_file("errors", rows, fmt)
        return f"reconciliation_errors_{run_id}.{extension}", mimetype, payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _envelope(items: list, total: int, page: int, page_size: int) -> dict:
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _counts(outcome: ReconcileOutcome) -> dict:
        counts = {status: 0 for status in c.RESULT_STATUSES}
        for result in outcome.results:
            if result.match_status in counts:
                counts[result.match_status] += 1
        return counts

    def _mark_failed(self, run_id: int) -> None:
        try:
            self._recon_repo.fail_run(run_id)
        except Exception:
            logger.exception("Failed to mark run %s as failed", run_id)