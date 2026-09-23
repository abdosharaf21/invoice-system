"""Offline tests for the migration catalog audit (Phase 12).

Exercises ``backend.database.migration_audit`` without any database: the
catalog manifest / digest validation, verify-hint parsing and tracker-state
classification all run against fake files on disk.
"""

import hashlib

import pytest

from backend.database.migration_audit import (
    MigrationRecord,
    MigrationStatus,
    MIGRATIONS,
    analyze_tracker,
    checksum,
    discover_migration_files,
    expected_sequence,
    parse_migration_index,
    tracker_summary,
    verify_catalog,
    verify_hints,
)
from backend.database.schema_manifest import EXPECTED_TABLES


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class TestIndexAndSequence:
    def test_parse_migration_index(self):
        assert parse_migration_index("000_foundation_schema.sql") == 0
        assert parse_migration_index("011_audit_traceability.sql") == 11
        assert parse_migration_index("009_integrity_constraints.sql") == 9

    def test_parse_migration_index_rejects_non_catalog_names(self):
        assert parse_migration_index("schema.sql") is None
        assert parse_migration_index("misc/002_x.sql") is None
        assert parse_migration_index("02_x.sql") is None

    def test_expected_sequence_is_contiguous_000_to_011(self):
        assert list(expected_sequence()) == list(range(len(MIGRATIONS)))
        assert len(MIGRATIONS) >= 12

    def test_discover_sorts_lexicographically(self):
        files = discover_migration_files()
        names = [f.name for f in files]
        assert names == sorted(names)
        assert names == [name for name, _ in MIGRATIONS]


class TestCatalogManifest:
    def test_catalog_is_clean(self):
        assert verify_catalog() == []

    def test_manifest_digests_match_disk_content(self):
        for name, recorded in MIGRATIONS:
            path = discover_migration_files()[0].parent / name
            assert checksum(path) == recorded, f"{name} digest drifted"

    def test_digest_mismatch_is_reported(self, tmp_path):
        mig = tmp_path / "999_new.sql"
        mig.write_text("SELECT 1;\n")
        from unittest.mock import patch
        with patch(
            "backend.database.migration_audit.MIGRATIONS",
            (("999_new.sql", "0" * 64),),
        ), patch(
            "backend.database.migration_audit.MIGRATIONS_DIR", tmp_path
        ):
            problems = verify_catalog(tmp_path)
        assert any(
            "content differs from the recorded digest" in p
            and checksum(mig) in p
            for p in problems
        )

    def test_missing_file_is_reported(self, tmp_path):
        from unittest.mock import patch
        from backend.database.migration_audit import verify_catalog as vc
        with patch(
            "backend.database.migration_audit.MIGRATIONS",
            (("000_foundation_schema.sql", "0" * 64),
             ("001_missing_never_created.sql", "1" * 64)),
        ):
            problems = vc(tmp_path)
        assert any("migration file set differs" in p for p in problems)


class TestVerifyHints:
    def test_hint_blocks_are_parsed_completely(self):
        hints = verify_hints()
        assert hints["000_foundation_schema.sql"] == [
            "companies", "users", "roles", "user_roles",
        ]
        assert hints["002_einvoice_domain.sql"] == ["reconciliation_runs"]
        assert "006_settings.sql" not in hints  # no hint declared
        assert hints["009_integrity_constraints.sql"] == [
            "invoices", "invoice_items", "tax_invoices", "tax_invoice_items",
            "import_batches", "reconciliation_runs", "reconciliation_results",
            "email_deliveries", "audit_logs",
        ]

    def test_prose_comment_tables_are_not_picked_up(self):
        # 002's prose block ("  * import tracking -> import_batches, ...")
        # must NOT leak tables into the hint.
        hints = verify_hints()
        assert hints["002_einvoice_domain.sql"] == ["reconciliation_runs"]
        assert "import_batches" not in hints["002_einvoice_domain.sql"]

    def test_hint_tables_exist_in_expected_schema(self):
        hints = verify_hints()
        for tables in hints.values():
            for table in tables:
                assert table in EXPECTED_TABLES, (
                    f"verify hint references unknown table {table}"
                )


class TestTrackerAnalysis:
    def _write_canonical_file(self, directory, name, content):
        path = directory / name
        path.write_text(content)
        return path

    def test_empty_tracker_is_all_pending(self, tmp_path):
        for name, _ in MIGRATIONS[:3]:
            self._write_canonical_file(tmp_path, name, f"-- {name}\n")
        items = analyze_tracker([], directory=tmp_path)
        statuses = {i.name: i.status for i in items}
        for name, _ in MIGRATIONS[:3]:
            assert statuses[name] is MigrationStatus.PENDING
        # canonical files not created here are missing from the tmp dir, so
        # their paths just don't exist; only recorded names matter.
        assert any(i.status is MigrationStatus.PENDING for i in items)

    def test_checksums_classify_applied_state(self, tmp_path):
        names = [name for name, _ in MIGRATIONS[:3]]
        files = [self._write_canonical_file(tmp_path, n, f"-- {n}\n") for n in names]
        records = [
            MigrationRecord(name=names[0], applied_at="2026-01-01", checksum=checksum(files[0])),
            MigrationRecord(name=names[1], applied_at="2026-01-01", checksum=None),
            MigrationRecord(name=names[2], applied_at="2026-01-01", checksum="a" * 64),
        ]
        items = {i.name: i for i in analyze_tracker(records, directory=tmp_path)}
        assert items[names[0]].status is MigrationStatus.APPLIED_CURRENT
        assert items[names[1]].status is MigrationStatus.APPLIED_LEGACY
        assert items[names[2]].status is MigrationStatus.APPLIED_MISMATCH

    def test_orphan_and_unexpected_file(self, tmp_path):
        names = [name for name, _ in MIGRATIONS[:1]]
        self._write_canonical_file(tmp_path, names[0], "-- header\n")
        extra_file = self._write_canonical_file(tmp_path, "099_late_addition.sql", "-- nope\n")
        records = [
            MigrationRecord(name=names[0], applied_at="2026-01-01", checksum=checksum(tmp_path / names[0])),
            MigrationRecord(name="ghost_migration.sql", applied_at="2026-01-01", checksum=None),
            MigrationRecord(name="099_late_addition.sql", applied_at="2026-01-01", checksum=checksum(extra_file)),
        ]
        items = {i.name: i for i in analyze_tracker(records, directory=tmp_path)}
        assert items["ghost_migration.sql"].status is MigrationStatus.ORPHAN
        assert items["099_late_addition.sql"].status is MigrationStatus.UNKNOWN_FILE

    def test_tracker_summary_counts_states(self, tmp_path):
        from backend.database.migration_audit import MIGRATIONS_DIR
        name = MIGRATIONS[0][0]
        path = MIGRATIONS_DIR / name
        records = [
            MigrationRecord(name=name, applied_at="2026-01-01", checksum=checksum(path)),
            MigrationRecord(name="orphan.sql", applied_at="2026-01-01", checksum=None),
        ]
        summary = tracker_summary(records)
        assert "1 current" in summary
        assert "1 orphan" in summary