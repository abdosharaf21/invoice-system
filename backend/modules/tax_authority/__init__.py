"""Tax authority domain module for the E-Invoice System.

Holds the E-Invoice document representation exchanged with the tax
authority (TaxInvoice) plus its line items. Linked to the accounting
side (Invoice) through account_invoice_id for reconciliation.
"""

from backend.modules.tax_authority.model import TaxInvoice, TaxInvoiceItem
from backend.modules.tax_authority.repository import TaxInvoiceRepository

__all__ = ["TaxInvoice", "TaxInvoiceItem", "TaxInvoiceRepository"]