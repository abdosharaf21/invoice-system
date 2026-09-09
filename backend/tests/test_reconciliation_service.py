"""Service tests: run orchestration, counts, transaction safety and scoping.

The service talks to fake repositories but runs the real engine, so these
tests exercise the end-to-end orchestration without a database.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.modules.invoices.model import Invoice
from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.model import ReconciliationRun
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.tax_authority.model import TaxInvoice


def _uuid(seed):
    return str(uuid5(NAMESPACE_URL, f"service-{seed}"))


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeReconRepo:
    def __init__(self):
        self.created = []
        self.finished = {}
        self.failed = 0
        self.started = []

    def create_run(self, run):
        run.id = 100 + len(self.created)
        self.created.append(run)
        return run

    def start_run(self, run_id):
        self.started.append(run_id)
        return True

    def finish_run_transaction(self, run_id, results, errors, **counts):
        self.finished[run_id] = {
            "results": results, "errors": errors, "counts": counts,
        }
        return True

    def fail_run(self, run_id):
        self.failed += 1
        return True

    def get_run_by_id(self, run_id):
        run = ReconciliationRun(
            id=run_id, company_id=1, period="2024-03", status=c.RUN_COMPLETED
        )
        return run

    def list_runs_by_company(self, company_id, limit=50, offset=0):
        return []

    def get_results_summary(self, run_id):
        return {}

    def get_results_with_details(self, run_id):
        return [{"id": 1, "run_id": run_id, "match_status": c.MATCHED}]

    def list_errors(self, run_id):
        return []


class FakeInvoiceRepo:
    def __init__(self, invoices):
        self.invoices = invoices
        self.raise_on_list = False

    def list_by_company_and_period(self, company_id, period):
        if self.raise_on_list:
            raise RuntimeError("boom")
        return self.invoices


class FakeTaxRepo:
    def __init__(self, tax_invoices):
        self.tax_invoices = tax_invoices

    def list_by_company_and_period(self, company_id, period):
        return self.tax_invoices


class FakeUserRepo:
    def get_by_id(self, user_id):
        return type("U", (), {"company_id": 7})()


def _invoice(uuid, number="INV"):
    return Invoice(
        id=1, uuid=uuid, company_id=1, invoice_number=number,
        invoice_date=date(2024, 3, 1), currency="EGP",
        counterparty_name="Acme", subtotal_amount=Decimal("100.00"),
        discount_amount=Decimal("0.00"), vat_amount=Decimal("14.00"),
        total_amount=Decimal("114.00"),
    )


def _tax(uuid, id=10):
    return TaxInvoice(
        id=id, uuid=uuid, company_id=1, issue_datetime=datetime(2024, 3, 1),
        currency="EGP", seller_name="Mega", total_sales=Decimal("100.00"),
        total_discount=Decimal("0.00"), net_amount=Decimal("100.00"),
        vat_amount=Decimal("14.00"), total_amount=Decimal("114.00"),
        buyer_name="Acme", buyer_tax_id=None, seller_tax_id=None,
    )


def _service(recon_repo, invoice_repo, tax_repo, user_repo=None):
    return ReconciliationService(recon_repo, invoice_repo, tax_repo, user_repo)


# ---------------------------------------------------------------------------
# start_run
# ---------------------------------------------------------------------------


def test_start_run_persists_counts_and_completes():
    recon = FakeReconRepo()
    invoices = [_invoice(_uuid("matched")), _invoice(_uuid("missing"), "B")]
    tax = [_tax(_uuid("matched"), 10), _tax(_uuid("extra"), 11)]
    service = _service(recon, FakeInvoiceRepo(invoices), FakeTaxRepo(tax))

    run, counts = service.start_run(1, "2024-03")

    assert run.status == c.RUN_COMPLETED
    assert counts[c.MATCHED] == 1
    assert counts[c.MISSING_IN_TAX_AUTHORITY] == 1
    assert counts[c.EXTRA_IN_TAX_AUTHORITY] == 1

    finished = recon.finished[run.id]["counts"]
    assert finished["invoice_count"] == 2
    assert finished["tax_invoice_count"] == 2
    assert finished["matched_count"] == 1
    assert finished["unmatched_count"] == 2
    assert finished["error_count"] == 0
    assert recon.started == [run.id]


def test_start_run_invalid_period_raises_before_creating_run():
    recon = FakeReconRepo()
    service = _service(recon, FakeInvoiceRepo([]), FakeTaxRepo([]))

    with pytest.raises(ValueError):
        service.start_run(1, "2024-13")

    assert recon.created == []


def test_start_run_marks_failed_on_engine_data_failure():
    recon = FakeReconRepo()
    invoices = FakeInvoiceRepo([_invoice(_uuid("u1"))])
    invoices.raise_on_list = True
    service = _service(recon, invoices, FakeTaxRepo([]))

    with pytest.raises(RuntimeError):
        service.start_run(1, "2024-03")

    assert recon.failed == 1


def test_start_run_marks_failed_when_persistence_fails():
    recon = FakeReconRepo()
    recon.finish_run_transaction = lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("db down")
    )
    service = _service(
        recon, FakeInvoiceRepo([_invoice(_uuid("u1"))]), FakeTaxRepo([_tax(_uuid("u1"))])
    )

    with pytest.raises(RuntimeError):
        service.start_run(1, "2024-03")

    assert recon.failed == 1


def test_mismatches_generate_error_count_but_still_complete():
    recon = FakeReconRepo()
    invoice = _invoice(_uuid("u1"))
    invoice.subtotal_amount = Decimal("999.00")
    tax = _tax(_uuid("u1"))
    service = _service(
        recon, FakeInvoiceRepo([invoice]), FakeTaxRepo([tax])
    )

    run, counts = service.start_run(1, "2024-03")

    assert run.status == c.RUN_COMPLETED
    assert counts[c.MISMATCHED] == 1
    finished = recon.finished[run.id]["counts"]
    assert finished["error_count"] >= 1
    assert finished["unmatched_count"] == 1


def test_start_run_normalizes_period_with_whitespace():
    recon = FakeReconRepo()
    service = _service(recon, FakeInvoiceRepo([]), FakeTaxRepo([]))
    run, counts = service.start_run(1, " 2024-03 ")

    assert run.period == "2024-03"
    assert recon.created[0].period == "2024-03"


# ---------------------------------------------------------------------------
# company_for_user + scoping
# ---------------------------------------------------------------------------


def test_company_for_user():
    service = _service(
        FakeReconRepo(), FakeInvoiceRepo([]), FakeTaxRepo([]),
        user_repo=FakeUserRepo(),
    )
    assert service.company_for_user(42) == 7


def test_get_run_scopes_to_company():
    recon = FakeReconRepo()
    recon.get_run_by_id = lambda run_id: ReconciliationRun(
        id=run_id, company_id=2, period="2024-03", status=c.RUN_COMPLETED
    )
    service = _service(recon, FakeInvoiceRepo([]), FakeTaxRepo([]))

    assert service.get_run(1, company_id=2) is not None
    assert service.get_run(1, company_id=9) is None


def test_get_results_and_errors_scope_to_company():
    recon = FakeReconRepo()
    recon.get_run_by_id = lambda run_id: ReconciliationRun(
        id=run_id, company_id=1, period="2024-03", status=c.RUN_COMPLETED
    )
    service = _service(recon, FakeInvoiceRepo([]), FakeTaxRepo([]))

    assert service.get_results(1, company_id=1) == [
        {"id": 1, "run_id": 1, "match_status": c.MATCHED}
    ]
    assert service.get_results(1, company_id=9) is None
    assert service.get_errors(1, company_id=1) == []
    assert service.get_errors(1, company_id=9) is None