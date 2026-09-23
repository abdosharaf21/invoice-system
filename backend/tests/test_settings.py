"""Tests for the Phase 6.5 Application & Organization Settings feature.

Covers the ApplicationSetting model, SettingsValidator, the settings
services, and the new settings API routes (application/company/user)
including authorization and company isolation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.modules.settings.model import ApplicationSetting
from backend.modules.settings.service import ApplicationSettingService
from backend.modules.settings.validator import SettingsValidator
from backend.modules.companies.model import Company
from backend.modules.companies.service import CompanyService
from backend.modules.users.model import User


def _user(company_id: int = 22, role: str = "admin") -> User:
    return User(
        id=1,
        company_id=company_id,
        username="admin_test",
        email="admin@test.local",
        first_name="Admin",
        last_name="Test",
        roles=[role],
        language="en",
        theme="light",
        date_format="YYYY-MM-DD",
        number_format="#,##0.00",
        timezone="UTC",
        pagination_size=25,
    )


def _company(company_id: int = 22) -> Company:
    return Company(
        id=company_id,
        name="Frontend Test Company",
        tax_registration_number="FRT-TEMP-001",
        email="admin@test.local",
        phone="+201000000000",
        address="Cairo",
        default_currency="EGP",
        default_tax_rate=0.0,
        fiscal_year_start="01-01",
    )


# ---------------------------------------------------------------------------
# ApplicationSetting model
# ---------------------------------------------------------------------------

class TestApplicationSettingModel:
    def test_typed_value_returns_raw_string_for_string_type(self):
        s = ApplicationSetting(setting_key="application_name", setting_value="Acme", value_type="string")
        assert s.typed_value() == "Acme"

    def test_typed_value_casts_integer(self):
        s = ApplicationSetting(setting_key="pagination_size", setting_value="25", value_type="integer")
        assert s.typed_value() == 25
        assert isinstance(s.typed_value(), int)

    def test_typed_value_casts_boolean(self):
        s = ApplicationSetting(setting_key="flag", setting_value="true", value_type="boolean")
        assert s.typed_value() is True

    def test_typed_value_parses_json(self):
        s = ApplicationSetting(setting_key="cfg", setting_value='{"a": 1}', value_type="json")
        assert s.typed_value() == {"a": 1}

    def test_typed_value_none(self):
        s = ApplicationSetting(setting_key="k", setting_value=None, value_type="string")
        assert s.typed_value() is None

    def test_to_dict_shape(self):
        s = ApplicationSetting(id=1, setting_key="application_name", setting_value="Acme", value_type="string")
        d = s.to_dict()
        assert d["setting_key"] == "application_name"
        assert d["setting_value"] == "Acme"
        assert d["value_type"] == "string"


# ---------------------------------------------------------------------------
# SettingsValidator
# ---------------------------------------------------------------------------

class TestSettingsValidator:
    def test_rejects_invalid_language(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_setting("default_language", "xx", "string")

    def test_accepts_supported_language(self):
        s = SettingsValidator.validate_setting("default_language", "ar", "string")
        assert s.setting_value == "ar"

    def test_rejects_invalid_theme(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_setting("default_theme", "neon", "string")

    def test_rejects_invalid_date_format(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_setting("date_format", "YY/XX", "string")

    def test_rejects_pagination_out_of_bounds(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_setting("pagination_size", 3, "integer")

    def test_accepts_pagination_boundary(self):
        s = SettingsValidator.validate_setting("pagination_size", 5, "integer")
        assert s.setting_value == "5"

    def test_validate_application_settings_update_infers_integer(self):
        validated = SettingsValidator.validate_application_settings_update({"pagination_size": 50})
        assert validated["pagination_size"].value_type == "integer"
        assert validated["pagination_size"].setting_value == "50"

    def test_validate_application_settings_update_empty_raises(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_application_settings_update({})

    def test_validate_user_preferences_filters_unknown_keys(self):
        data = SettingsValidator.validate_user_preferences({"theme": "dark", "some_unknown": "x"})
        assert data == {"theme": "dark"}

    def test_validate_user_preferences_rejects_bad_language(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_user_preferences({"language": "xx"})

    def test_validate_user_preferences_bounds_pagination(self):
        data = SettingsValidator.validate_user_preferences({"pagination_size": 200})
        assert data["pagination_size"] == 200
        with pytest.raises(ValueError):
            SettingsValidator.validate_user_preferences({"pagination_size": 9999})

    def test_validate_company_settings_valid_email(self):
        data = SettingsValidator.validate_company_settings({"email": "billing@acme.com"})
        assert data["email"] == "billing@acme.com"

    def test_validate_company_settings_rejects_bad_email(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_company_settings({"email": "not-an-email"})

    def test_validate_company_settings_currency_upper_3(self):
        data = SettingsValidator.validate_company_settings({"default_currency": "usd"})
        assert data["default_currency"] == "USD"
        with pytest.raises(ValueError):
            SettingsValidator.validate_company_settings({"default_currency": "US"})

    def test_validate_company_settings_name_required(self):
        with pytest.raises(ValueError):
            SettingsValidator.validate_company_settings({"name": "  "})

    def test_validate_company_settings_fiscal_year_format(self):
        data = SettingsValidator.validate_company_settings({"fiscal_year_start": "07-01"})
        assert data["fiscal_year_start"] == "07-01"
        with pytest.raises(ValueError):
            SettingsValidator.validate_company_settings({"fiscal_year_start": "2024/07"})


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class TestApplicationSettingService:
    def test_get_all_settings_delegates(self):
        repo = MagicMock()
        repo.get_all_as_dict.return_value = {"application_name": "Acme"}
        service = ApplicationSettingService(repo)
        assert service.get_all_settings() == {"application_name": "Acme"}

    def test_get_setting_raises_when_missing(self):
        repo = MagicMock()
        repo.get_by_key.return_value = None
        service = ApplicationSettingService(repo)
        with pytest.raises(ValueError):
            service.get_setting("missing")

    def test_update_settings_validates_and_upserts(self):
        repo = MagicMock()
        repo.get_all_as_dict.return_value = {"default_theme": "dark"}
        service = ApplicationSettingService(repo)
        result = service.update_settings({"default_theme": "dark"})
        repo.upsert_many.assert_called_once()
        assert result == {"default_theme": "dark"}

    def test_update_settings_rejects_bad_value(self):
        repo = MagicMock()
        service = ApplicationSettingService(repo)
        with pytest.raises(ValueError):
            service.update_settings({"default_theme": "neon"})
        repo.upsert_many.assert_not_called()

    def test_get_settings_for_frontend_returns_safe_subset(self):
        repo = MagicMock()
        repo.get_all_as_dict.return_value = {
            "application_name": "Acme",
            "application_subtitle": "Sub",
            "default_language": "en",
            "default_theme": "light",
            "date_format": "YYYY-MM-DD",
            "number_format": "#,##0.00",
            "timezone": "UTC",
            "pagination_size": 25,
            "internal_secret": "shhh",
        }
        service = ApplicationSettingService(repo)
        data = service.get_settings_for_frontend()
        assert "internal_secret" not in data
        assert data["application_name"] == "Acme"
        assert data["pagination_size"] == 25


class TestCompanyService:
    def test_get_company_raises_when_missing(self):
        repo = MagicMock()
        repo.get_by_id.return_value = None
        service = CompanyService(repo)
        with pytest.raises(ValueError):
            service.get_company(99)

    def test_get_company_returns_company(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _company()
        service = CompanyService(repo)
        c = service.get_company(22)
        assert c.name == "Frontend Test Company"

    def test_update_company_validates_and_persists(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _company()
        updated_company = _company()
        updated_company.website = "https://acme.com"
        updated_company.default_currency = "USD"
        repo.update.return_value = updated_company
        service = CompanyService(repo)
        updated = service.update_company(22, {"website": "https://acme.com", "default_currency": "USD"})
        assert updated.website == "https://acme.com"
        assert updated.default_currency == "USD"

    def test_update_company_rejects_bad_email(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _company()
        service = CompanyService(repo)
        with pytest.raises(ValueError):
            service.update_company(22, {"email": "nope"})
        repo.update.assert_not_called()


class TestUserSettingsMethods:
    def test_get_user_settings_returns_prefs(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _user()
        service = __import__("backend.modules.users.service", fromlist=["UserService"]).UserService(repo)
        prefs = service.get_user_settings(1)
        assert prefs["theme"] == "light"
        assert prefs["pagination_size"] == 25

    def test_get_user_settings_raises_when_missing(self):
        repo = MagicMock()
        repo.get_by_id.return_value = None
        service = __import__("backend.modules.users.service", fromlist=["UserService"]).UserService(repo)
        with pytest.raises(ValueError):
            service.get_user_settings(1)

    def test_update_user_settings_validates_and_persists(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _user()
        service = __import__("backend.modules.users.service", fromlist=["UserService"]).UserService(repo)
        service.update_user_settings(1, {"theme": "dark"})
        repo.update_preferences.assert_called_once()
        assert repo.update_preferences.call_args[0][1]["theme"] == "dark"

    def test_update_user_settings_rejects_bad_theme(self):
        repo = MagicMock()
        repo.get_by_id.return_value = _user()
        service = __import__("backend.modules.users.service", fromlist=["UserService"]).UserService(repo)
        with pytest.raises(ValueError):
            service.update_user_settings(1, {"theme": "neon"})
        repo.update_preferences.assert_not_called()


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@pytest.fixture
def _settings_repo(app, mock_repos):
    state = {
        "application_name": "E-Invoice & Reconciliation",
        "application_subtitle": "Tax authority compliance",
        "default_language": "en",
        "default_theme": "light",
        "date_format": "YYYY-MM-DD",
        "number_format": "#,##0.00",
        "timezone": "UTC",
        "pagination_size": 25,
    }
    patcher = patch(
        "backend.modules.settings.repository.ApplicationSettingRepository.get_all_as_dict",
        side_effect=lambda: dict(state),
    )
    patcher.start()
    upsert_patcher = patch(
        "backend.modules.settings.repository.ApplicationSettingRepository.upsert_many",
        side_effect=lambda settings: [
            state.update({s.setting_key: s.typed_value()}) for s in settings
        ],
    )
    upsert_patcher.start()
    mock_repos.settings_state = state
    mock_repos.settings_patcher = patcher
    mock_repos.settings_upsert_patcher = upsert_patcher
    yield patcher
    upsert_patcher.stop()
    patcher.stop()


class TestApplicationSettingsApi:
    def test_get_application_settings_authenticated(self, client, admin_headers, _settings_repo):
        resp = client.get("/api/settings/application", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["application_name"] == "E-Invoice & Reconciliation"

    def test_get_application_settings_no_token_unauthorized(self, client):
        resp = client.get("/api/settings/application")
        assert resp.status_code == 401

    def test_update_application_settings_admin(self, client, admin_headers, _settings_repo):
        resp = client.put(
            "/api/settings/application",
            json={"application_name": "Acme Suite"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["application_name"] == "Acme Suite"

    def test_update_application_settings_manager_forbidden(
        self, client, manager_headers, _settings_repo
    ):
        resp = client.put(
            "/api/settings/application",
            json={"application_name": "Acme Suite"},
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_update_application_settings_invalid_admin(self, client, admin_headers, _settings_repo):
        resp = client.put(
            "/api/settings/application",
            json={"default_theme": "neon"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_update_application_settings_empty_body(self, client, admin_headers):
        resp = client.put("/api/settings/application", json={}, headers=admin_headers)
        assert resp.status_code == 400

    def test_get_all_application_settings_admin(self, client, admin_headers, _settings_repo):
        resp = client.get("/api/settings/application/all", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_get_all_application_settings_viewer_forbidden(self, client, viewer_headers, _settings_repo):
        resp = client.get("/api/settings/application/all", headers=viewer_headers)
        assert resp.status_code == 403


class TestCompanySettingsApi:
    @pytest.fixture(autouse=True)
    def _mock_company_services(self, app, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _user(company_id=22)
        get_p = patch(
            "backend.modules.companies.repository.CompanyRepository.get_by_id",
            return_value=_company(),
        )
        upd_p = patch(
            "backend.modules.companies.repository.CompanyRepository.update",
            return_value=_company(),
        )
        get_p.start()
        upd_p.start()
        mock_repos.company_get_patcher = get_p
        mock_repos.company_upd_patcher = upd_p
        yield
        get_p.stop()
        upd_p.stop()

    def test_get_company_settings_authenticated(self, client, admin_headers):
        resp = client.get("/api/settings/company", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["name"] == "Frontend Test Company"
        assert data["tax_registration_number"] == "FRT-TEMP-001"

    def test_get_company_settings_no_token_unauthorized(self, client):
        resp = client.get("/api/settings/company")
        assert resp.status_code == 401

    def test_update_company_settings_admin(self, client, admin_headers, mock_repos):
        resp = client.put(
            "/api/settings/company",
            json={"website": "https://acme.com"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_update_company_settings_non_admin_forbidden(self, client, viewer_headers):
        resp = client.put(
            "/api/settings/company",
            json={"website": "https://acme.com"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    def test_update_company_settings_invalid_email(self, client, admin_headers):
        resp = client.put(
            "/api/settings/company",
            json={"email": "bad"},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_company_isolation_resolves_admin_company(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _user(company_id=22)
        resp = client.get("/api/settings/company", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["id"] == 22


class TestCurrentUserSettingsApi:
    def test_get_user_settings_authenticated(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _user()
        resp = client.get("/api/settings/user", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["theme"] == "light"

    def test_get_user_settings_no_token_unauthorized(self, client):
        resp = client.get("/api/settings/user")
        assert resp.status_code == 401

    def test_update_user_settings_own_prefs(self, client, admin_headers, mock_repos):
        updated = _user()
        updated.theme = "dark"
        mock_repos.user_repo.get_by_id.return_value = updated
        mock_repos.user_repo.update_preferences.return_value = updated
        resp = client.put(
            "/api/settings/user",
            json={"theme": "dark"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["theme"] == "dark"

    def test_update_user_settings_invalid_value(self, client, admin_headers, mock_repos):
        mock_repos.user_repo.get_by_id.return_value = _user()
        resp = client.put(
            "/api/settings/user",
            json={"theme": "neon"},
            headers=admin_headers,
        )
        assert resp.status_code == 400