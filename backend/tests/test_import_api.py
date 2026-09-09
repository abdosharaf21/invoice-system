"""Tests for the import API routes.

Verifies RBAC, payload handling and the JSON contract of
``POST /api/imports`` and ``GET /api/imports/<id>`` using the mocked
app fixtures.
"""

import io
from unittest.mock import MagicMock

from backend.modules.imports.errors import ImportErrorInfo
from backend.modules.imports.model import ImportBatch


def _batch_dict(overrides=None):
    data = {
        "id": 7,
        "company_id": 1,
        "filename": "invoices.csv",
        "file_type": "csv",
        "source_type": "file",
        "status": "completed",
        "total_rows": 2,
        "processed_rows": 2,
        "error_rows": 0,
        "uploaded_by": 1,
        "started_at": "2024-01-01T10:00:00",
        "finished_at": "2024-01-01T10:00:01",
        "created_at": "2024-01-01T10:00:00",
        "updated_at": "2024-01-01T10:00:01",
    }
    data.update(overrides or {})
    return data


class TestCreateImport:
    def _post(self, client, headers, content=None, filename="invoices.csv"):
        content = content or b"invoice_number\nINV-1\n"
        return client.post(
            "/api/imports",
            headers=headers,
            data={
                "file": (io.BytesIO(content), filename),
            },
            content_type="multipart/form-data",
        )

    def test_requires_auth(self, client):
        response = self._post(client, {})
        assert response.status_code == 401

    def test_forbidden_for_employee(self, client, employee_headers):
        response = self._post(client, employee_headers)
        assert response.status_code == 403

    def test_forbidden_for_viewer(self, client, viewer_headers):
        response = self._post(client, viewer_headers)
        assert response.status_code == 403

    def test_allowed_for_manager(self, client, manager_headers, mock_repos):
        mock_repos.import_service.import_file.return_value = MagicMock(
            to_dict=lambda: {"batch": _batch_dict(), "errors": []}
        )
        response = self._post(client, manager_headers)
        assert response.status_code == 201
        assert response.get_json()["success"] is True
        assert response.get_json()["data"]["batch"]["status"] == "completed"
        mock_repos.import_service.import_file.assert_called_once()

    def test_allowed_for_admin(self, client, admin_headers, mock_repos):
        mock_repos.import_service.import_file.return_value = MagicMock(
            to_dict=lambda: {"batch": _batch_dict(), "errors": []}
        )
        response = self._post(client, admin_headers)
        assert response.status_code == 201

    def test_missing_file_field(self, client, admin_headers, mock_repos):
        response = client.post("/api/imports", headers=admin_headers)
        assert response.status_code == 400

    def test_company_resolution(self, client, admin_headers, mock_repos):
        mock_repos.import_service.import_file.return_value = MagicMock(
            to_dict=lambda: {"batch": _batch_dict(), "errors": []}
        )
        self._post(client, admin_headers)
        _, kwargs = mock_repos.import_service.import_file.call_args
        assert kwargs["company_id"] == 1
        assert kwargs["filename"] == "invoices.csv"


class TestGetImport:
    def test_returns_batch(self, client, admin_headers, mock_repos):
        batch = ImportBatch.from_dict(_batch_dict())
        mock_repos.import_service.get_batch.return_value = batch
        response = client.get("/api/imports/7", headers=admin_headers)
        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["batch"]["id"] == 7
        assert "errors" not in data

    def test_include_errors(self, client, admin_headers, mock_repos):
        batch = ImportBatch.from_dict(_batch_dict())
        mock_repos.import_service.get_batch.return_value = batch
        mock_repos.import_service.list_errors.return_value = [
            ImportErrorInfo(
                row_number=2,
                field="unit_price",
                error_code="INVALID_MONEY",
                message="bad money",
            )
        ]
        response = client.get(
            "/api/imports/7?include=errors",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.get_json()["data"]
        assert "errors" in data
        assert data["errors"][0]["error_code"] == "INVALID_MONEY"

    def test_not_found(self, client, admin_headers, mock_repos):
        mock_repos.import_service.get_batch.return_value = None
        response = client.get("/api/imports/999", headers=admin_headers)
        assert response.status_code == 404

    def test_forbidden_for_employee(self, client, employee_headers):
        response = client.get("/api/imports/7", headers=employee_headers)
        assert response.status_code == 403