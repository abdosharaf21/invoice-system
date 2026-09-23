"""API tests for the reconciliation endpoints (mocked service)."""

from datetime import datetime
from decimal import Decimal

from backend.modules.reconciliation import contract as c
from backend.modules.reconciliation.model import (
    ReconciliationError,
    ReconciliationRun,
)

_RUN = ReconciliationRun(
    id=1, company_id=1, period="2024-03", status=c.RUN_COMPLETED,
    invoice_count=2, tax_invoice_count=2,
    matched_count=1, unmatched_count=1, error_count=0,
    started_at=datetime(2024, 4, 1, 10, 0, 0),
    finished_at=datetime(2024, 4, 1, 10, 0, 5),
)

_COUNTS = {
    c.MATCHED: 1,
    c.MISMATCHED: 0,
    c.MISSING_IN_TAX_AUTHORITY: 1,
    c.EXTRA_IN_TAX_AUTHORITY: 0,
    c.INVALID: 0,
}

_RESULTS = [
    {"id": 1, "run_id": 1, "account_invoice_id": 10,
     "tax_invoice_id": 20, "match_status": c.MATCHED,
     "discrepancy_amount": 0.0, "notes": None, "created_at": None,
     "account_invoice_number": "INV-1", "account_uuid": "u1",
     "tax_uuid": "u1", "tax_internal_id": None},
]

_ERRORS = [
    ReconciliationError(
        id=1, run_id=1, source_type="account", entity_id=10,
        error_type=c.E_TOTAL_AMOUNT_MISMATCH, field="total_amount",
        accounting_value="100.00", tax_authority_value="120.00",
        difference=Decimal("-20.00"),
        message="total_amount differs.",
    ),
]


def _launch(client, headers, payload=None):
    return client.post(
        "/api/reconciliation/runs",
        headers=headers,
        json=payload or {"period": "2024-03"},
    )


# ---------------------------------------------------------------------------
# Authentication / RBAC
# ---------------------------------------------------------------------------


def test_post_requires_authentication(client):
    response = _launch(client, {})
    assert response.status_code == 401


def test_post_forbidden_for_viewer(client, viewer_headers):
    response = _launch(client, viewer_headers)
    assert response.status_code == 403


def test_post_forbidden_for_employee(client, employee_headers):
    response = _launch(client, employee_headers)
    assert response.status_code == 403


def test_get_run_requires_reconciliation_role(client, viewer_headers):
    response = client.get("/api/reconciliation/runs/1", headers=viewer_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/reconciliation/runs
# ---------------------------------------------------------------------------


def test_post_valid_run(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.start_run.return_value = (_RUN, _COUNTS, True)

    response = _launch(client, admin_headers)
    assert response.status_code == 201
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["run"]["id"] == 1
    assert body["data"]["counts"][c.MATCHED] == 1
    service.start_run.assert_called_once()
    _, kwargs = service.start_run.call_args
    assert kwargs["company_id"] == 1
    assert kwargs["period"] == "2024-03"


def test_post_existing_active_run_returns_200(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.start_run.return_value = (_RUN, _COUNTS, False)

    response = _launch(client, admin_headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["run"]["id"] == 1


def test_post_forwards_money_tolerance(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.start_run.return_value = (_RUN, _COUNTS, True)

    response = _launch(client, admin_headers, {"period": "2024-03", "money_tolerance": "0.01"})
    assert response.status_code == 201
    assert service.start_run.call_args.kwargs["money_tolerance"] == Decimal("0.01")


def test_post_rejects_invalid_period(client, admin_headers):
    response = _launch(client, admin_headers, {"period": "not-a-period"})
    assert response.status_code == 400
    assert response.get_json()["code"] == "BAD_REQUEST"


def test_post_rejects_missing_period(client, admin_headers):
    response = _launch(client, admin_headers, {})
    assert response.status_code == 400


def test_post_rejects_bad_money_tolerance(client, admin_headers):
    response = _launch(client, admin_headers, {"period": "2024-03", "money_tolerance": "abc"})
    assert response.status_code == 400


def test_post_rejects_negative_money_tolerance(client, admin_headers):
    response = _launch(client, admin_headers, {"period": "2024-03", "money_tolerance": "-1"})
    assert response.status_code == 400


def test_post_requires_company_membership(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.company_for_user.return_value = None

    response = _launch(client, admin_headers)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET run + list
# ---------------------------------------------------------------------------


def test_get_run_detail(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_run.return_value = _RUN
    service.get_summary.return_value = _COUNTS

    response = client.get("/api/reconciliation/runs/1", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["run"]["id"] == 1
    assert data["run"]["status"] == c.RUN_COMPLETED
    assert data["counts"] == _COUNTS


def test_get_run_not_found_for_other_company(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_run.return_value = None

    response = client.get("/api/reconciliation/runs/999", headers=admin_headers)
    assert response.status_code == 404
    assert response.get_json()["code"] == "NOT_FOUND"


def test_list_runs(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.list_runs.return_value = [_RUN]

    response = client.get("/api/reconciliation/runs", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["count"] == 1
    assert data["runs"][0]["id"] == 1


def test_list_runs_rejects_non_integer_pagination(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs?limit=abc", headers=admin_headers
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET results / errors
# ---------------------------------------------------------------------------


def test_get_results(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_results.return_value = _RESULTS

    response = client.get("/api/reconciliation/runs/1/results", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["results"][0]["account_invoice_number"] == "INV-1"


def test_get_results_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_results.return_value = None

    response = client.get("/api/reconciliation/runs/999/results", headers=admin_headers)
    assert response.status_code == 404


def test_get_errors(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_errors.return_value = _ERRORS

    response = client.get("/api/reconciliation/runs/1/errors", headers=admin_headers)
    assert response.status_code == 200
    error = response.get_json()["data"]["errors"][0]
    assert error["field"] == "total_amount"
    assert error["accounting_value"] == "100.00"
    assert error["tax_authority_value"] == "120.00"
    assert error["difference"] == -20.0


def test_get_errors_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_errors.return_value = None

    response = client.get("/api/reconciliation/runs/999/errors", headers=admin_headers)
    assert response.status_code == 404