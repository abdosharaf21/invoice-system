"""Import service: orchestrates accounting file imports end to end.

The service is the single entry point for the Phase 3 import feature.
It owns the whole lifecycle of an import batch:

1. create the batch row (``source_type='file'``),
2. validate the uploaded file (extension, size, content),
3. parse the file into raw rows via the parser registry,
4. normalise + validate every row into typed canonical values,
5. group rows into invoices and detect duplicates (in file + in DB),
6. compute monetary totals and persist fully-valid invoices,
7. finish the batch with accurate counters and a status.

The flow is deliberately defensive: a bad row never blocks the good
rows around it, and a bad invoice never reaches the ``invoices`` table.
"""

import logging
from dataclasses import dataclass, field as dataclass_field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from backend.modules.imports import model as models
from backend.modules.imports import repository as repo
from backend.modules.imports.contract import (
    DEFAULT_INVOICE_STATUS,
    DEFAULT_INVOICE_TYPE,
    IMPORT_SOURCE_FILE,
)
from backend.modules.imports.errors import (
    E_DUPLICATE_IN_DB,
    E_DUPLICATE_IN_FILE,
    E_FILE_ERROR,
    ImportErrorInfo,
    format_raw_row,
)
from backend.modules.imports.file_safety import validate_file
from backend.modules.imports.grouping import (
    ROW_NUMBER_KEY,
    build_column_map,
    group_rows,
    map_row,
)
from backend.modules.imports.normalizer import normalize_row
from backend.modules.imports.parsers import get_parser
from backend.modules.imports.parsers.base import FileParseError
from backend.modules.imports.validator import validate_group, validate_row
from backend.modules.invoices.model import Invoice, InvoiceItem
from backend.modules.audit_trail.model import AuditLog
from backend.modules.audit_trail.service import record_event

logger = logging.getLogger(__name__)

_TWO = Decimal("0.01")


def _q2(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_TWO, rounding=ROUND_HALF_UP)


@dataclass
class ImportResult:
    """Outcome of an accounting file import.

    Attributes:
        batch: Persisted ImportBatch with final counters and status.
        errors: Structured per-file and per-row errors.
    """

    batch: models.ImportBatch
    errors: List[ImportErrorInfo] = dataclass_field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "batch": self.batch.to_dict(),
            "errors": [error.to_dict() for error in self.errors],
        }


class ImportService:
    """Coordinates one accounting file import end to end."""

    def __init__(
        self,
        batch_repo: repo.ImportBatchRepository,
        invoice_repo,
        user_repo=None,
    ) -> None:
        self._batch_repo = batch_repo
        self._invoice_repo = invoice_repo
        self._user_repo = user_repo

    def company_for_user(self, user_id: int) -> Optional[int]:
        """Resolve the company id a user belongs to, if any."""
        if self._user_repo is None:
            return None
        user = self._user_repo.get_by_id(user_id)
        if user is None:
            return None
        return user.company_id

    def recover_interrupted(self) -> int:
        """Mark any batch left in a temporary state as failed.

        Called once at application startup so batches interrupted by a crash
        or an unhandled system failure are surfaced as ``failed`` instead of
        staying ``uploaded``/``processing`` forever.

        Returns:
            The number of batches transitioned to ``failed``.
        """
        return self._batch_repo.recover_interrupted_batches()

    def import_file(
        self,
        company_id: int,
        uploaded_by: int,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> ImportResult:
        """Import an uploaded accounting file for a company.

        Args:
            company_id: Owning company id.
            uploaded_by: Id of the user performing the upload.
            filename: Upload filename.
            content_type: Client-reported Content-Type header.
            content: Raw file bytes.

        Returns:
            An ImportResult with the final batch state and any errors.
        """
        batch = self._batch_repo.create(models.ImportBatch(
            company_id=company_id,
            filename=filename,
            file_type="csv",
            source_type=IMPORT_SOURCE_FILE,
            status="uploaded",
            total_rows=0,
            processed_rows=0,
            error_rows=0,
            uploaded_by=uploaded_by,
        ))
        logger.info(
            "Import started batch=%s company=%s file=%r uploaded_by=%s",
            batch.id, company_id, filename, uploaded_by,
        )

        errors: List[ImportErrorInfo] = []

        file_type, file_error = validate_file(filename, content_type, content)
        if file_error is not None:
            errors.append(file_error)
            record_event(
                action=AuditLog.ACTION_IMPORT,
                resource_type="import",
                resource_id=str(batch.id),
                result=AuditLog.RESULT_FAILURE,
                company_id=company_id,
                metadata={"filename": filename, "file_type": file_type, "reason": file_error.message},
            )
            return self._finish_failed(batch, errors)

        batch.file_type = file_type

        parser = get_parser(file_type)
        if parser is None:
            errors.append(ImportErrorInfo(
                row_number=0,
                field="filename",
                error_code=E_FILE_ERROR,
                message=f"No parser available for file type '{file_type}'.",
            ))
            record_event(
                action=AuditLog.ACTION_IMPORT,
                resource_type="import",
                resource_id=str(batch.id),
                result=AuditLog.RESULT_FAILURE,
                company_id=company_id,
                metadata={"filename": filename, "file_type": file_type, "reason": f"No parser for '{file_type}'."},
            )
            return self._finish_failed(batch, errors)

        try:
            parsed = parser.parse(content)
        except FileParseError as exc:
            errors.append(ImportErrorInfo(
                row_number=0,
                field="file_content",
                error_code=E_FILE_ERROR,
                message=str(exc),
            ))
            record_event(
                action=AuditLog.ACTION_IMPORT,
                resource_type="import",
                resource_id=str(batch.id),
                result=AuditLog.RESULT_FAILURE,
                company_id=company_id,
                metadata={"filename": filename, "file_type": file_type, "reason": str(exc)},
            )
            return self._finish_failed(batch, errors)

        self._batch_repo.start(batch.id)
        persisted_invoice_rows = 0

        try:
            mapping, header_errors = build_column_map(parsed.headers)
            errors.extend(header_errors)
            if header_errors:
                return self._finish_failed(batch, errors, total_rows=parsed.total_rows)

            normalized_rows, row_errors = self._normalize_rows(parsed, mapping)
            errors.extend(row_errors)

            raw_by_number, groups = self._group_rows(normalized_rows, parsed)

            groups_to_persist, group_errors, duplicate_keys = self._detect_duplicates(
                groups, company_id
            )
            errors.extend(group_errors)

            for group in groups_to_persist:
                invoice = self._build_invoice(group, batch.id, company_id)
                if invoice is None:
                    continue
                try:
                    self._invoice_repo.create(invoice)
                except Exception:
                    invoice_error = ImportErrorInfo(
                        row_number=group.first_row,
                        field="invoice_number",
                        error_code=E_FILE_ERROR,
                        message=(
                            f"Failed to persist '{group.invoice_values.get('invoice_number')}': "
                            "a database error occurred."
                        ),
                    )
                    errors.append(invoice_error)
                    logger.exception("Failed to persist invoice for import batch %s", batch.id)
                    continue
                persisted_invoice_rows += len(group.item_values)

            status = "completed"
            if persisted_invoice_rows == 0 and (errors or parsed.total_rows == 0):
                status = "failed"

            self._persist_errors(batch.id, errors)

            error_rows = max(parsed.total_rows - persisted_invoice_rows, 0)
            self._batch_repo.update_counts(
                batch.id,
                total_rows=parsed.total_rows,
                processed_rows=persisted_invoice_rows,
                error_rows=error_rows,
                status=status,
            )
            logger.info(
                "Import finished batch=%s status=%s total=%d processed=%d errors=%d",
                batch.id, status, parsed.total_rows, persisted_invoice_rows, error_rows,
            )
            batch.status = status
            batch.processed_rows = persisted_invoice_rows
            batch.error_rows = error_rows
            batch.total_rows = parsed.total_rows

            record_event(
                action=AuditLog.ACTION_IMPORT,
                resource_type="import",
                resource_id=str(batch.id),
                result=(
                    AuditLog.RESULT_SUCCESS if status == "completed"
                    else AuditLog.RESULT_FAILURE
                ),
                company_id=company_id,
                metadata={
                    "filename": filename,
                    "status": status,
                    "total_rows": parsed.total_rows,
                    "processed_rows": persisted_invoice_rows,
                    "error_rows": error_rows,
                },
            )

            return ImportResult(batch=batch, errors=errors)
        except Exception:
            logger.error("Import batch %s failed unexpectedly", batch.id)
            errors.append(ImportErrorInfo(
                row_number=0,
                field="file_content",
                error_code=E_FILE_ERROR,
                message=(
                    "The import failed unexpectedly. The batch was marked "
                    "failed and no further invoices were processed."
                ),
            ))
            self._persist_errors(batch.id, errors)
            batch.status = "failed"
            batch.total_rows = parsed.total_rows
            batch.processed_rows = persisted_invoice_rows
            batch.error_rows = max(parsed.total_rows - persisted_invoice_rows, 0)
            try:
                self._batch_repo.update_counts(
                    batch.id,
                    total_rows=batch.total_rows,
                    processed_rows=batch.processed_rows,
                    error_rows=batch.error_rows,
                    status="failed",
                )
            except Exception:
                logger.exception(
                    "Failed to persist failed status for import batch %s", batch.id
                )
            raise

    # ------------------------------------------------------------------
    # Internal pipeline steps
    # ------------------------------------------------------------------

    def _normalize_rows(self, parsed, mapping) -> tuple:
        """Normalize and validate every parsed row -> (rows, errors)."""
        normalized_rows: List[Dict[str, Any]] = []
        errors: List[ImportErrorInfo] = []
        for index, cells in enumerate(parsed.rows, start=1):
            values = map_row(mapping, cells, index)
            typed, field_errors = normalize_row(index, values)
            semantic_errors = validate_row(index, typed)

            row_errors = field_errors + semantic_errors
            raw_text = format_raw_row(cells)
            for error in row_errors:
                error.raw_data = raw_text
            if row_errors:
                errors.extend(row_errors)
                continue

            typed[ROW_NUMBER_KEY] = index
            normalized_rows.append(typed)
        return normalized_rows, errors

    def _group_rows(self, normalized_rows, parsed) -> tuple:
        raw_by_number = {
            index: cells for index, cells in enumerate(parsed.rows, start=1)
        }
        groups, group_errors = group_rows(normalized_rows, raw_by_number)
        for error in group_errors:
            error.raw_data = format_raw_row(
                raw_by_number.get(error.row_number, [])
            )
        return raw_by_number, groups

    def _detect_duplicates(self, groups, company_id: int) -> tuple:
        """Filter groups that fail validation or duplicate detection.

        Returns ``(to_persist, group_errors, seen_keys)``.
        """
        to_persist: List = []
        errors: List[ImportErrorInfo] = []
        seen_keys: Dict[tuple, int] = {}
        seen_numbers: Dict[str, int] = {}

        for group in groups:
            group_problems = validate_group(group)
            if group_problems:
                for problem in group_problems:
                    if problem.raw_data is None:
                        raw = group.raw_rows[0] if group.raw_rows else []
                        problem.raw_data = format_raw_row(raw)
                errors.extend(group_problems)
                continue

            key = ("uuid", group.uuid) if group.uuid else ("number", group.invoice_number)
            if key in seen_keys:
                error = ImportErrorInfo(
                    row_number=group.first_row,
                    field="invoice_number",
                    error_code=E_DUPLICATE_IN_FILE,
                    message=(
                        f"Invoice '{group.invoice_values.get('invoice_number')}' "
                        f"appears more than once in this file (first seen on row "
                        f"{seen_keys[key]})."
                    ),
                )
                error.raw_data = format_raw_row(group.raw_rows[0] if group.raw_rows else [])
                errors.append(error)
                continue

            number = group.invoice_values.get("invoice_number")
            if number is not None and number in seen_numbers:
                error = ImportErrorInfo(
                    row_number=group.first_row,
                    field="invoice_number",
                    error_code=E_DUPLICATE_IN_FILE,
                    message=(
                        f"Invoice number '{number}' appears more than once in "
                        f"this file (first seen on row {seen_numbers[number]})."
                    ),
                )
                error.raw_data = format_raw_row(group.raw_rows[0] if group.raw_rows else [])
                errors.append(error)
                continue

            existing = self._find_existing_invoice(group, company_id)
            if existing is not None:
                error = ImportErrorInfo(
                    row_number=group.first_row,
                    field="invoice_number" if not group.uuid else "uuid",
                    error_code=E_DUPLICATE_IN_DB,
                    message=(
                        f"Invoice '{group.invoice_values.get('invoice_number')}' "
                        "already exists in the system."
                    ),
                )
                error.raw_data = format_raw_row(group.raw_rows[0] if group.raw_rows else [])
                errors.append(error)
                continue

            seen_keys[key] = group.first_row
            if number is not None:
                seen_numbers[number] = group.first_row
            to_persist.append(group)

        return to_persist, errors, seen_keys

    def _find_existing_invoice(self, group, company_id: int):
        if group.uuid:
            return self._invoice_repo.get_by_uuid(company_id, group.uuid)
        return self._invoice_repo.get_by_company_and_number(
            company_id, group.invoice_number
        )

    def _build_invoice(self, group, batch_id: int, company_id: int) -> Optional[Invoice]:
        values = group.invoice_values
        totals = self._compute_totals(group.item_values)
        if totals is None:
            return None

        subtotal, discount, vat, total = totals
        try:
            return Invoice(
                uuid=values.get("uuid"),
                company_id=company_id,
                import_batch_id=batch_id,
                invoice_number=values["invoice_number"],
                invoice_type=values.get("invoice_type", DEFAULT_INVOICE_TYPE),
                invoice_date=values["invoice_date"],
                due_date=values.get("due_date"),
                currency=values.get("currency", "EGP"),
                counterparty_name=values["counterparty_name"],
                counterparty_tax_id=values.get("counterparty_tax_id"),
                counterparty_email=values.get("counterparty_email"),
                subtotal_amount=subtotal,
                discount_amount=discount,
                vat_amount=vat,
                total_amount=total,
                status=DEFAULT_INVOICE_STATUS,
                items=[self._build_item(item) for item in group.item_values],
            )
        except KeyError:
            return None

    def _build_item(self, item_values: Dict[str, Any]) -> InvoiceItem:
        quantity = item_values.get("quantity", Decimal("1"))
        unit_price = item_values.get("unit_price", Decimal("0"))
        discount = item_values.get("item_discount_amount", Decimal("0"))
        vat_rate = item_values.get("vat_rate", Decimal("0"))

        subtotal_line = _q2(unit_price * quantity)
        taxable = _q2(subtotal_line - discount)
        vat_amount = item_values.get("vat_amount") or _q2(taxable * vat_rate / Decimal("100"))
        line_total = item_values.get("line_total")
        if line_total is None:
            line_total = _q2(taxable + vat_amount)

        return InvoiceItem(
            description=item_values["item_description"],
            quantity=quantity,
            unit_price=unit_price,
            discount_amount=discount,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            line_total=line_total,
        )

    def _compute_totals(self, item_values: List[Dict[str, Any]]):
        try:
            subtotal = Decimal("0")
            discount = Decimal("0")
            vat = Decimal("0")
            total = Decimal("0")
            for item in item_values:
                quantity = item.get("quantity", Decimal("1"))
                unit_price = item.get("unit_price", Decimal("0"))
                item_discount = item.get("item_discount_amount", Decimal("0"))
                vat_rate = item.get("vat_rate", Decimal("0"))
                item_vat = item.get("vat_amount")
                item_total = item.get("line_total")

                subtotal_line = _q2(unit_price * quantity)
                taxable = _q2(subtotal_line - item_discount)
                if item_vat is None:
                    item_vat = _q2(taxable * vat_rate / Decimal("100"))
                if item_total is None:
                    item_total = _q2(taxable + item_vat)

                subtotal += subtotal_line
                discount += item_discount
                vat += item_vat
                total += item_total
            return (
                _q2(subtotal),
                _q2(discount),
                _q2(vat),
                _q2(total),
            )
        except KeyError:
            return None

    def _persist_errors(self, batch_id: int, errors: List[ImportErrorInfo]) -> None:
        for error in errors:
            try:
                self._batch_repo.add_error(models.ImportBatchError(
                    batch_id=batch_id,
                    row_number=error.row_number,
                    field=error.field,
                    error_code=error.error_code,
                    error_message=error.message,
                    raw_data=error.raw_data,
                ))
            except Exception:
                logger.exception("Failed to persist import error for batch %s", batch_id)

    def _finish_failed(
        self,
        batch: models.ImportBatch,
        errors: List[ImportErrorInfo],
        total_rows: int = 0,
    ) -> ImportResult:
        self._persist_errors(batch.id, errors)

        error_rows = 1 if errors else 0
        self._batch_repo.update_counts(
            batch.id,
            total_rows=total_rows,
            processed_rows=0,
            error_rows=error_rows,
            status="failed",
        )
        batch.status = "failed"
        batch.processed_rows = 0
        batch.error_rows = error_rows
        batch.total_rows = total_rows
        return ImportResult(batch=batch, errors=errors)

    def get_batch(self, batch_id: int, company_id: int) -> Optional[models.ImportBatch]:
        """Fetch a batch by id, scoped to a company."""
        batch = self._batch_repo.get_by_id(batch_id)
        if batch is None or batch.company_id != company_id:
            return None
        return batch

    def list_errors(self, batch_id: int) -> List[ImportErrorInfo]:
        persisted = self._batch_repo.list_errors(batch_id)
        return [
            ImportErrorInfo(
                row_number=item.row_number,
                field=item.field,
                error_code=item.error_code,
                message=item.error_message,
                raw_data=item.raw_data,
            )
            for item in persisted
        ]