"""HTTP tests for reconciliation query/body validation branches (Phase 14 G5).

Every request below is rejected by the route validation layer BEFORE any
service call, so the mocked reconciliation service only needs the default
``company_for_user`` fixture value. Covers the negative paths that the
existing report tests only exercised on the happy path.
"""

import pytest

_VALID_PERIOD = "2025-03"


class _Harness:
    """Bundles the request helpers so tests stay terse."""


def _start_run(client, headers, body):
    return client.post("/api/reconciliation/runs", json=body, headers=headers)


class TestStartRunValidation:
    def test_invalid_period_rejected(self, client, admin_headers):
        for bad in ("2025", "2025-13", "abc", "2025-1-1", ""):
            response = _start_run(client, admin_headers, {"period": bad})
            assert response.status_code == 400
            assert "Invalid period" in response.get_json()["message"]

    def test_missing_period_rejected(self, client, admin_headers):
        response = _start_run(client, admin_headers, {})
        assert response.status_code == 400

    def test_negative_tolerance_rejected(self, client, admin_headers):
        response = _start_run(client, admin_headers, {"period": _VALID_PERIOD, "money_tolerance": "-1"})
        assert response.status_code == 400
        assert "zero or positive" in response.get_json()["message"]

    def test_non_numeric_tolerance_rejected(self, client, admin_headers):
        for bad in ("abc", "1,5", "12.3.4"):
            response = _start_run(client, admin_headers, {"period": _VALID_PERIOD, "money_tolerance": bad})
            assert response.status_code == 400
            assert "must be a decimal number" in response.get_json()["message"]

    def test_no_company_rejected(self, client, admin_headers, mock_repos):
        mock_repos.reconciliation_service.company_for_user.return_value = None
        response = _start_run(client, admin_headers, {"period": _VALID_PERIOD})
        assert response.status_code == 400
        assert "does not belong to a company" in response.get_json()["message"]


class TestListRunsValidation:
    def test_out_of_range_limit_rejected(self, client, admin_headers):
        for bad in ("0", "201", "9999"):
            response = client.get(f"/api/reconciliation/runs?limit={bad}", headers=admin_headers)
            assert response.status_code == 400
            assert "out of range" in response.get_json()["message"]

    def test_non_integer_limit_rejected(self, client, admin_headers):
        response = client.get("/api/reconciliation/runs?limit=abc", headers=admin_headers)
        assert response.status_code == 400
        assert "must be integers" in response.get_json()["message"]


class TestResultsReportValidation:
    @pytest.mark.parametrize("param,value", [("page", "abc"), ("page_size", "x")])
    def test_non_integer_pagination_rejected(self, client, admin_headers, param, value):
        response = client.get(
            f"/api/reconciliation/runs/1/results?{param}={value}", headers=admin_headers
        )
        assert response.status_code == 400
        assert "must be integers" in response.get_json()["message"]

    def test_page_size_above_max_rejected(self, client, admin_headers):
        response = client.get(
            "/api/reconciliation/runs/1/results?page_size=999", headers=admin_headers
        )
        assert response.status_code == 400
        assert "out of range" in response.get_json()["message"]

    def test_invalid_match_status_rejected(self, client, admin_headers):
        response = client.get(
            "/api/reconciliation/runs/1/results?match_status=BOGUS", headers=admin_headers
        )
        assert response.status_code == 400
        assert "match_status must be one of" in response.get_json()["message"]

    def test_date_from_after_date_to_rejected(self, client, admin_headers):
        response = client.get(
            "/api/reconciliation/runs/1/results"
            "?date_from=2025-03-13&date_to=2025-03-01",
            headers=admin_headers,
        )
        assert response.status_code == 400
        assert "date_from must not be after date_to" in response.get_json()["message"]

    def test_bad_date_format_rejected(self, client, admin_headers):
        response = client.get(
            "/api/reconciliation/runs/1/results?date_from=not-a-date", headers=admin_headers
        )
        assert response.status_code == 400
        assert "'YYYY-MM-DD'" in response.get_json()["message"]


class TestErrorsReportValidation:
    def test_invalid_source_type_rejected(self, client, admin_headers):
        response = client.get(
            "/api/reconciliation/runs/1/errors?source_type=bogus", headers=admin_headers
        )
        assert response.status_code == 400
        assert "must be 'account' or 'tax'" in response.get_json()["message"]

    def test_valid_source_types_forwarded(self, client, admin_headers, mock_repos):
        mock_repos.reconciliation_service.paginate_errors.return_value = {
            "items": [], "page": 1, "page_size": 50, "total": 0, "total_pages": 0,
        }
        for src in ("account", "tax"):
            response = client.get(
                f"/api/reconciliation/runs/1/errors?source_type={src}", headers=admin_headers
            )
            assert response.status_code == 200
            filters = mock_repos.reconciliation_service.paginate_errors.call_args.args[4]
            assert filters["source_type"] == src


class TestExportValidation:
    @pytest.mark.parametrize("fmt", ["xml", "xlsx2", "PDF"])
    def test_invalid_export_format_rejected(self, client, admin_headers, fmt):
        response = client.get(
            f"/api/reconciliation/runs/1/results/export?format={fmt}", headers=admin_headers
        )
        assert response.status_code == 400
        assert "format must be 'csv' or 'xlsx'" in response.get_json()["message"]


class TestStartRunHappyPath:
    def test_start_run_returns_created_run(self, client, admin_headers, mock_repos):
        run = object.__new__(type("Run", (), {}))
        run.to_dict = lambda: {"id": 1, "company_id": 1, "period": "2025-03"}
        mock_repos.reconciliation_service.start_run.return_value = (run, {"matched": 0}, True)
        response = _start_run(client, admin_headers, {"period": _VALID_PERIOD})
        assert response.status_code == 201
        assert response.get_json()["data"]["run"]["period"] == "2025-03"
        mock_repos.reconciliation_service.start_run.assert_called_once_with(
            company_id=1, period=_VALID_PERIOD, money_tolerance=None
        )