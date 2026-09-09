"""Reconciliation domain module for the E-Invoice System.

Models reconciliation between the accounting side (invoices) and the tax
authority side (tax_invoices): runs, per-invoice results and errors.
The matching algorithm itself is implemented in a later phase.
"""

from backend.modules.reconciliation.model import (
    ReconciliationError,
    ReconciliationResult,
    ReconciliationRun,
)
from backend.modules.reconciliation.repository import ReconciliationRepository

__all__ = [
    "ReconciliationRun",
    "ReconciliationResult",
    "ReconciliationError",
    "ReconciliationRepository",
]