"""Service layer for company settings business logic."""

from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import build_snapshot, record_event
from backend.modules.companies.model import Company
from backend.modules.companies.repository import CompanyRepository
from backend.modules.settings.validator import SettingsValidator


class CompanyService:
    """Manages company settings (read/write)."""

    def __init__(self, repository: CompanyRepository) -> None:
        self._repository = repository

    def get_company(self, company_id: int) -> Company:
        """Fetch a company by ID. Raises ValueError if not found."""
        c = self._repository.get_by_id(company_id)
        if c is None:
            raise ValueError("Company not found")
        return c

    def update_company(self, company_id: int, data: dict) -> Company:
        """Validate and persist company settings update."""
        company = self.get_company(company_id)
        before = build_snapshot("company", company.to_dict())
        validated = SettingsValidator.validate_company_settings(data)
        for k, v in validated.items():
            setattr(company, k, v)
        updated = self._repository.update(company)
        if updated is None:
            raise ValueError("Failed to update company")
        record_event(
            action=AuditLog.ACTION_UPDATE,
            resource_type="company",
            resource_id=str(company_id),
            result=AuditLog.RESULT_SUCCESS,
            company_id=company_id,
            before_state=before,
            after_state=build_snapshot("company", updated.to_dict()),
        )
        return updated
