"""API tests for the reconciliation report endpoints (mocked service).

Covers the report surface added in Phase 5:
* GET /api/reconciliation/runs/<id>/summary
* paginated + filtered GET .../results and .../errors
* CSV/XLSX export endpoints

Authentication, RBAC and company scoping follow the existing reconciliation
conventions and are exercised here at the HTTP layer.
"""

from datetime import date

from backend.modules.reconciliation import contract as c

_SUMMARY = {
    "run": {
        "id": 1, "company_id": 1, "period": "2024-03",
        "status": c.RUN_COMPLETED,
        "started_at": "2024-04-01T10:00:00",
        "finished_at": "2024-04-01T10:00:05",
    },
    "summary": {
        c.MATCHED: 2,
        c.MISMATCHED: 1,
        c.MISSING_IN_TAX_AUTHORITY: 1,
        c.EXTRA_IN_TAX_AUTHORITY: 1,
        c.INVALID: 1,
        "total_results": 6,
        "unmatched": 4,
        "errors": 3,
    },
}

_ENVELOPE = {
    "items": [{"id": 1, "match_status": c.MATCHED}],
    "page": 1,
    "page_size": 50,
    "total": 1,
    "total_pages": 1,
}


# ---------------------------------------------------------------------------
# Authentication / RBAC
# ---------------------------------------------------------------------------


def test_summary_requires_authentication(client):
    response = client.get("/api/reconciliation/runs/1/summary")
    assert response.status_code == 401


def test_summary_forbidden_for_viewer(client, viewer_headers):
    response = client.get("/api/reconciliation/runs/1/summary", headers=viewer_headers)
    assert response.status_code == 403


def test_summary_forbidden_for_employee(client, employee_headers):
    response = client.get("/api/reconciliation/runs/1/summary", headers=employee_headers)
    assert response.status_code == 403


def test_results_report_forbidden_for_viewer(client, viewer_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results?page=1", headers=viewer_headers
    )
    assert response.status_code == 403


def test_export_requires_authentication(client):
    response = client.get("/api/reconciliation/runs/1/results/export?format=csv")
    assert response.status_code == 401


def test_export_forbidden_for_viewer(client, viewer_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results/export?format=csv",
        headers=viewer_headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_get_summary(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_report_summary.return_value = _SUMMARY

    response = client.get("/api/reconciliation/runs/1/summary", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["run"]["period"] == "2024-03"
    assert data["summary"][c.MATCHED] == 2
    assert data["summary"]["total_results"] == 6
    assert data["summary"]["errors"] == 3
    service.get_report_summary.assert_called_once_with(1, 1)


def test_get_summary_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_report_summary.return_value = None

    response = client.get("/api/reconciliation/runs/999/summary", headers=admin_headers)
    assert response.status_code == 404
    assert response.get_json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Paginated + filtered results
# ---------------------------------------------------------------------------


def test_results_paginated_envelope(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    envelope = {
        "items": [{"id": 1, "match_status": c.MATCHED}],
        "page": 2,
        "page_size": 25,
        "total": 27,
        "total_pages": 2,
    }
    service.paginate_results.return_value = envelope

    response = client.get(
        "/api/reconciliation/runs/1/results?page=2&page_size=25&match_status=matched",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["items"] == envelope["items"]
    # The route must echo the service's pagination metadata verbatim.
    assert data["page"] == 2
    assert data["page_size"] == 25
    assert data["total"] == 27
    assert data["total_pages"] == 2
    service.paginate_results.assert_called_once()
    args = service.paginate_results.call_args.args
    assert args[:4] == (1, 1, 2, 25)
    assert args[4] == {"match_status": "matched"}


def test_results_legacy_shape_without_report_params(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_results.return_value = [{"id": 1, "match_status": c.MATCHED}]

    response = client.get("/api/reconciliation/runs/1/results", headers=admin_headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["results"][0]["id"] == 1
    service.get_results.assert_called_once_with(1, 1)
    service.paginate_results.assert_not_called()


def test_results_paginated_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.paginate_results.return_value = None

    response = client.get(
        "/api/reconciliation/runs/999/results?page=1", headers=admin_headers
    )
    assert response.status_code == 404


def test_results_passes_uuid_invoice_number_and_date_filters(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.paginate_results.return_value = _ENVELOPE

    response = client.get(
        "/api/reconciliation/runs/1/results"
        "?uuid=abc-123&invoice_number=INV-1&date_from=2024-03-01&date_to=2024-03-31",
        headers=admin_headers,
    )
    assert response.status_code == 200
    filters = service.paginate_results.call_args.args[4]
    assert filters["uuid"] == "abc-123"
    assert filters["invoice_number"] == "INV-1"
    assert filters["date_from"] == date(2024, 3, 1)
    assert filters["date_to"] == date(2024, 3, 31)


def test_results_rejects_invalid_page(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results?page=0", headers=admin_headers
    )
    assert response.status_code == 400


def test_results_rejects_oversized_page_size(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results?page_size=1000", headers=admin_headers
    )
    assert response.status_code == 400


def test_results_rejects_non_integer_page_size(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results?page_size=abc", headers=admin_headers
    )
    assert response.status_code == 400


def test_results_rejects_unknown_match_status(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results?match_status=bogus", headers=admin_headers
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "BAD_REQUEST"


def test_results_rejects_bad_date(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results?date_from=not-a-date", headers=admin_headers
    )
    assert response.status_code == 400


def test_results_rejects_inverted_date_range(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results?date_from=2024-03-31&date_to=2024-03-01",
        headers=admin_headers,
    )
    assert response.status_code == 400


def test_results_maximum_page_size_allowed(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.paginate_results.return_value = _ENVELOPE

    response = client.get(
        "/api/reconciliation/runs/1/results?page_size=200", headers=admin_headers
    )
    assert response.status_code == 200
    assert service.paginate_results.call_args.args[3] == 200


# ---------------------------------------------------------------------------
# Paginated + filtered errors
# ---------------------------------------------------------------------------


def test_errors_paginated_envelope(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.paginate_errors.return_value = _ENVELOPE

    response = client.get(
        "/api/reconciliation/runs/1/errors?page=1&page_size=10&error_type=TOTAL_AMOUNT_MISMATCH",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["items"] == _ENVELOPE["items"]
    service.paginate_errors.assert_called_once()
    args = service.paginate_errors.call_args.args
    assert args[:4] == (1, 1, 1, 10)
    assert args[4] == {"error_type": "TOTAL_AMOUNT_MISMATCH"}


def test_errors_legacy_shape_without_report_params(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_errors.return_value = []

    response = client.get("/api/reconciliation/runs/1/errors", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["errors"] == []
    service.paginate_errors.assert_not_called()


def test_errors_paginated_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.paginate_errors.return_value = None

    response = client.get(
        "/api/reconciliation/runs/999/errors?page=1", headers=admin_headers
    )
    assert response.status_code == 404


def test_errors_passes_source_type_filter(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.paginate_errors.return_value = _ENVELOPE

    response = client.get(
        "/api/reconciliation/runs/1/errors?source_type=tax", headers=admin_headers
    )
    assert response.status_code == 200
    filters = service.paginate_errors.call_args.args[4]
    assert filters == {"source_type": "tax"}


def test_errors_rejects_unknown_source_type(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/errors?source_type=bogus", headers=admin_headers
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_export_results_csv(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.export_results.return_value = (
        "reconciliation_results_1.csv",
        "text/csv",
        b"result_id,run_id\n1,1\n",
    )

    response = client.get(
        "/api/reconciliation/runs/1/results/export?format=csv", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "reconciliation_results_1.csv" in response.headers["Content-Disposition"]
    assert response.data == b"result_id,run_id\n1,1\n"
    service.export_results.assert_called_once()
    assert service.export_results.call_args.args[2] == "csv"


def test_export_results_defaults_to_csv(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.export_results.return_value = ("reconciliation_results_1.csv", "text/csv", b"a\n")
    response = client.get(
        "/api/reconciliation/runs/1/results/export", headers=admin_headers
    )
    assert response.status_code == 200
    assert service.export_results.call_args.args[2] == "csv"


def test_export_errors_xlsx(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.export_errors.return_value = (
        "reconciliation_errors_1.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        b"PK\x03\x04xlsx-bytes",
    )

    response = client.get(
        "/api/reconciliation/runs/1/errors/export?format=xlsx", headers=admin_headers
    )
    assert response.status_code == 200
    assert "spreadsheetml" in response.mimetype
    assert "reconciliation_errors_1.xlsx" in response.headers["Content-Disposition"]
    assert response.data == b"PK\x03\x04xlsx-bytes"


def test_export_rejects_unknown_format(client, admin_headers):
    response = client.get(
        "/api/reconciliation/runs/1/results/export?format=pdf", headers=admin_headers
    )
    assert response.status_code == 400


def test_export_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.export_results.return_value = None

    response = client.get(
        "/api/reconciliation/runs/999/results/export?format=csv", headers=admin_headers
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Company isolation (other-company run is treated as not found)
# ---------------------------------------------------------------------------


def test_summary_other_company_returns_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.get_report_summary.return_value = None

    response = client.get("/api/reconciliation/runs/2/summary", headers=admin_headers)
    assert response.status_code == 404


def test_export_other_company_returns_not_found(client, admin_headers, mock_repos):
    service = mock_repos.reconciliation_service
    service.export_errors.return_value = None

    response = client.get(
        "/api/reconciliation/runs/2/errors/export?format=xlsx", headers=admin_headers
    )
    assert response.status_code == 404