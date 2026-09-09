"""Companies domain module for the E-Invoice System."""

from backend.modules.companies.model import Company
from backend.modules.companies.repository import CompanyRepository

__all__ = ["Company", "CompanyRepository"]