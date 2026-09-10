"""Service-level tests for the reconciliation report methods.

Uses a fake repository so the summary composition, pagination envelope math,
export passthrough and company scoping are tested without a database or HTTP.
"""

from datetime import datetime
from decimal import Decimal

from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.model import ReconciliationRun
from backend.modules.reconciliation.service import ReconciliationService

RUN = ReconciliationRun(
    id=7, company_id=1, period="2024-03", status=c.RUN_COMPLETED,
    invoice_count=6, tax_invoice_count=6,
    matched_count=1, unmatched_count=5, error_count=2,
    started_at=datetime(2024, 4, 1, 10, 0, 0),
    finished_at=datetime(2024, 4, 1, 10, 0, 5),
)


class FakeReconRepo:
    def __init__(self):
        self.run = RUN
        self.summary = {
            c.MATCHED: 1,
            c.MISMATCHED: 1,
            c.MISSING_IN_TAX_AUTHORITY: 1,
            c.EXTRA_IN_TAX_AUTHORITY: 1,
            c.INVALID: 1,
        }
        self.error_count = 2
        self.results = [
            {"id": i, "run_id": 7, "match_status": c.MATCHED}
            for i in range(1, 26)
        ]
        self.errors = [{"id": i, "run_id": 7, "error_type": c.E_TOTAL_AMOUNT_MISMATCH}
                       for i in range(1, 6)]
        self.list_results_filters = None
        self.count_results_filters = None

    def get_run_by_id(self, run_id):
        if run_id == self.run.id:
            return self.run
        return ReconciliationRun(id=run_id, company_id=99, period="2024-01")

    def get_results_summary(self, run_id):
        return dict(self.summary)

    def count_errors(self, run_id, filters=None):
        return len(self.errors)

    def count_results(self, run_id, filters=None):
        self.count_results_filters = filters
        return len(self.results)

    def list_results_report(self, run_id, limit, offset, filters=None):
        self.list_results_filters = filters
        return self.results[offset:offset + limit]

    def list_errors_report(self, run_id, limit, offset, filters=None):
        return self.errors[offset:offset + limit]

    def iter_results_report(self, run_id, filters=None, batch_size=500):
        yield from self.results

    def iter_errors_report(self, run_id, filters=None, batch_size=500):
        yield from self.errors


def make_service(repo=None):
    repo = repo or FakeReconRepo()
    return ReconciliationService(repo, None, None, None)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_get_report_summary_composes_run_and_counts():
    repo = FakeReconRepo()
    repo.errors = [{"id": 1, "run_id": 7}, {"id": 2, "run_id": 7}]
    service = make_service(repo)
    result = service.get_report_summary(7, 1)

    assert result["run"]["id"] == 7
    assert result["run"]["company_id"] == 1
    assert result["run"]["status"] == c.RUN_COMPLETED
    assert result["summary"][c.MATCHED] == 1
    assert result["summary"][c.MISMATCHED] == 1
    assert result["summary"][c.MISSING_IN_TAX_AUTHORITY] == 1
    assert result["summary"][c.EXTRA_IN_TAX_AUTHORITY] == 1
    assert result["summary"][c.INVALID] == 1
    assert result["summary"]["total_results"] == 5
    assert result["summary"]["unmatched"] == 4
    assert result["summary"]["errors"] == 2


def test_get_report_summary_empty_run_zero_filled():
    repo = FakeReconRepo()
    repo.summary = {}
    repo.errors = []
    service = make_service(repo)
    result = service.get_report_summary(7, 1)

    summary = result["summary"]
    assert summary[c.MATCHED] == 0
    assert summary[c.MISMATCHED] == 0
    assert summary["total_results"] == 0
    assert summary["unmatched"] == 0
    assert summary["errors"] == 0


def test_get_report_summary_all_matched():
    repo = FakeReconRepo()
    repo.summary = {c.MATCHED: 9}
    service = make_service(repo)
    result = service.get_report_summary(7, 1)

    assert result["summary"][c.MATCHED] == 9
    assert result["summary"]["total_results"] == 9
    assert result["summary"]["unmatched"] == 0


def test_get_report_summary_scoped_to_company():
    service = make_service()
    assert service.get_report_summary(999, 1) is None
    assert service.get_report_summary(7, 99) is None


# ---------------------------------------------------------------------------
# Paginated results
# ---------------------------------------------------------------------------


def test_paginate_results_envelope_math():
    service = make_service()
    payload = service.paginate_results(7, 1, page=2, page_size=10)

    assert payload["page"] == 2
    assert payload["page_size"] == 10
    assert payload["total"] == 25
    assert payload["total_pages"] == 3
    assert payload["items"][0]["id"] == 11
    assert len(payload["items"]) == 10


def test_paginate_results_last_page():
    service = make_service()
    payload = service.paginate_results(7, 1, page=5, page_size=5)

    assert payload["total_pages"] == 5
    assert payload["items"][0]["id"] == 21
    assert len(payload["items"]) == 5


def test_paginate_results_page_beyond_data():
    service = make_service()
    payload = service.paginate_results(7, 1, page=99, page_size=10)

    assert payload["total_pages"] == 3
    assert payload["items"] == []


def test_paginate_results_empty_run():
    repo = FakeReconRepo()
    repo.results = []
    service = make_service(repo)
    payload = service.paginate_results(7, 1, page=1, page_size=10)

    assert payload["total"] == 0
    assert payload["total_pages"] == 0
    assert payload["items"] == []


def test_paginate_results_forwards_filters():
    service = make_service()
    filters = {"match_status": c.MISMATCHED, "uuid": "abc"}
    service.paginate_results(7, 1, page=1, page_size=5, filters=filters)

    assert service._recon_repo.count_results_filters == filters
    assert service._recon_repo.list_results_filters == filters


def test_paginate_results_deterministic_ordering():
    repo = FakeReconRepo()
    service = make_service(repo)
    payload = service.paginate_results(7, 1, page=1, page_size=25)
    ids = [item["id"] for item in payload["items"]]
    assert ids == sorted(ids)


def test_paginate_results_scoped_to_company():
    service = make_service()
    assert service.paginate_results(999, 1, 1, 10) is None


# ---------------------------------------------------------------------------
# Paginated errors
# ---------------------------------------------------------------------------


def test_paginate_errors_envelope():
    service = make_service()
    payload = service.paginate_errors(7, 1, page=2, page_size=2)

    assert payload["total"] == 5
    assert payload["total_pages"] == 3
    assert payload["items"][0]["id"] == 3
    assert payload["items"][0]["error_type"] == c.E_TOTAL_AMOUNT_MISMATCH


def test_paginate_errors_empty_run():
    repo = FakeReconRepo()
    repo.errors = []
    service = make_service(repo)
    payload = service.paginate_errors(7, 1, page=1, page_size=10)

    assert payload["items"] == []
    assert payload["total_pages"] == 0


def test_paginate_errors_scoped_to_company():
    service = make_service()
    assert service.paginate_errors(7, 99, 1, 10) is None


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_export_results_csv_payload():
    service = make_service()
    outcome = service.export_results(7, 1, "csv")

    assert outcome is not None
    filename, mimetype, payload = outcome
    assert filename == "reconciliation_results_7.csv"
    assert mimetype == "text/csv"
    assert b"result_id,run_id,match_status" in payload


def test_export_errors_xlsx_payload():
    service = make_service()
    outcome = service.export_errors(7, 1, "xlsx")

    assert outcome is not None
    filename, mimetype, _ = outcome
    assert filename == "reconciliation_errors_7.xlsx"
    assert mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_export_scoped_to_company():
    service = make_service()
    assert service.export_results(7, 99, "csv") is None
    assert service.export_errors(7, 99, "csv") is None


# ---------------------------------------------------------------------------
# Money helpers (used as-is from the engine contract for report mapping)
# ---------------------------------------------------------------------------


def test_report_money_values_are_decimals():
    repo = FakeReconRepo()
    repo.results = [{"id": 1, "discrepancy_amount": Decimal("150.00")}]
    service = make_service(repo)
    items = service.paginate_results(7, 1, 1, 10, {"match_status": c.MISMATCHED})["items"]
    assert isinstance(items[0]["discrepancy_amount"], Decimal)