"""Migration inventory and tracker-state analysis (Phase 12).

Pure, offline helpers for auditing the migration catalog and the state of
the ``schema_migrations`` tracker. Units here must not require a database so
they can be exercised by the pytest suite (see ``tests/test_migration_audit.py``).

The runtime counterpart lives in ``deploy/migrate.sh``: it records a
SHA-256 checksum per applied migration and refuses to apply anything if an
*already-applied* file no longer matches what was recorded on the database —
the anti-drift guarantee this module reasons about.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

# Canonical, ordered migration catalog. The tuple pairs each filename with the
# SHA-256 of its *committed* content; tests recompute the digest of the file on
# disk and assert it matches, so editing an applied migration without updating
# this manifest is caught at test time before it ever becomes schema drift.
MIGRATIONS: Tuple[Tuple[str, str], ...] = (
    (
        "000_foundation_schema.sql",
        "4862d7692687ef1e2a07c0ac54f3edd0fa0aac89bcde12a32a0227e64200b021",
    ),
    (
        "001_reconcile_foundation_schema.sql",
        "84055f097bbbe87fa847ea91dcb8face2c017821dec4fbf5a97c5b24f72d05d9",
    ),
    (
        "002_einvoice_domain.sql",
        "83a02434957cff336220beda0e3ee3f44485fd2a658377673afc73030e6cd1fd",
    ),
    (
        "003_import_columns.sql",
        "c9720af0ef8af1e7b33dbbb94089c4f2132fc1576a5841e300748f145f3a5db8",
    ),
    (
        "004_reconciliation_error_columns.sql",
        "91bc9023a0c14a8bb795ed715aeb9ce37f2efb0c4bdc4d1bd033a155dceec2e5",
    ),
    (
        "005_widen_reconciliation_match_status.sql",
        "8953aace872d925e569b0795f8ce61780a924be166bd6c9ed47467b777e666c2",
    ),
    (
        "006_settings.sql",
        "d364948cd14bb9150f3d00a5f7ce59a0b5459b6f9fb4267e5a850eaa282d61aa",
    ),
    (
        "007_email_deliveries.sql",
        "d050bbdcd9b6854d56bc1dce80c59070c2fdd29757082af5b43aed12ba68aedb",
    ),
    (
        "008_audit_logs.sql",
        "4c5f43e9c871bcd92d497c36c0480ff6af69044c69ac433c4ac06da2acb95cf5",
    ),
    (
        "009_integrity_constraints.sql",
        "64d820cedf394e80a17e541ce6d6311528cea89df8f3602faafe9e6eceb62d53",
    ),
    (
        "010_performance_indexes.sql",
        "b5821b93550ec26e4dc417be54ac872f18f377939acc99a99596e16e153bae87",
    ),
    (
        "011_audit_traceability.sql",
        "7a8e87d43a32f67b65c39c2ed00ed758c98f28a84feb176a17784de3868bd885",
    ),
    (
        "012_reconcile_discrepancy_range.sql",
        "852316f36aa069e53647c329bc02c2505de17515aa74b0be6ffc2c935150b4b9",
    ),
)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_INDEX_RE = re.compile(r"^(\d{3})_")
# Marker line that opens a verify block: "-- verify: <table[, ...]>".
_VERIFY_MARKER_RE = re.compile(
    r"^\s*--\s*verify:\s*([a-z_0-9`]+(?:\s*,\s*[a-z_0-9`]+)*)\s*,?\s*$",
    re.IGNORECASE,
)
# A continuation line inside a verify block: only table tokens and commas.
# Prose such as "--   reconciliation -> reconciliation_errors" or the
# blank "--" line (both token-free/punctuated) terminates the block.
_VERIFY_TOKEN_RE = re.compile(
    r"^\s*--\s+([a-z_0-9`]+(?:\s*,\s*[a-z_0-9`]+)*)\s*,?\s*$",
    re.IGNORECASE,
)


class MigrationStatus(str, Enum):
    """Status of one migration from the tracker's point of view."""

    APPLIED_CURRENT = "applied_current"
    APPLIED_LEGACY = "applied_legacy"
    APPLIED_MISMATCH = "applied_checksum_mismatch"
    PENDING = "pending"
    UNKNOWN_FILE = "unexpected_file"
    ORPHAN = "orphan_record"


@dataclass(frozen=True)
class MigrationRecord:
    """One row of ``schema_migrations`` as handed back by a read cursor."""

    name: str
    applied_at: str
    checksum: Optional[str] = None


@dataclass(frozen=True)
class TrackerItem:
    """Audit outcome for a single migration."""

    name: str
    status: MigrationStatus
    detail: str = ""


def parse_migration_index(name: str) -> Optional[int]:
    """Extract the numeric order of a migration filename.

    ``003_import_columns.sql`` -> ``3``. Anything that is not a three-digit
    prefixed SQL file returns ``None``.
    """
    match = _INDEX_RE.match(name)
    if not match:
        return None
    return int(match.group(1))


def expected_sequence() -> Sequence[int]:
    """The order of the canonical catalog, as 0-based indexes."""
    return tuple(range(0, len(MIGRATIONS)))


def discover_migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """All ``.sql`` files in a migrations directory, sorted lexicographically.

    Lexicographic order of zero-padded filenames is the *deployment* order;
    the caller verifies it equals the canonical sequence.
    """
    return sorted(directory.glob("*.sql"))


def checksum(path: Path) -> str:
    """SHA-256 hex digest of a migration file's content."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_catalog(directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Check the on-disk catalog against the canonical ordered manifest.

    Returns a list of human-readable problems (empty when the catalog is
    exactly the canonical set, in order, with intact digests).
    """
    problems: list[str] = []
    files = discover_migration_files(directory)
    names = [f.name for f in files]

    expected_names = [name for name, _ in MIGRATIONS]
    if names != expected_names:
        problems.append(
            "migration file set differs from the canonical manifest:\n"
            + "  missing:   "
            + ", ".join(sorted(set(expected_names) - set(names)))
            + "\n"
            + "  unexpected: "
            + ", ".join(sorted(set(names) - set(expected_names)))
        )
        return problems

    for path in files:
        recorded = dict(MIGRATIONS)
        digest = checksum(path)
        if digest != recorded[path.name]:
            problems.append(
                f"{path.name}: content differs from the recorded digest "
                f"({digest} != {recorded[path.name]}) — the committed "
                "manifest is stale or the file was modified"
            )

    indexes = [parse_migration_index(name) for name in names]
    if indexes != list(expected_sequence()):
        problems.append(
            f"migration order is not a contiguous 000..%03d "
            f"sequence (got {indexes})" % (len(MIGRATIONS) - 1,)
        )
    return problems


def verify_hints(directory: Path = MIGRATIONS_DIR) -> dict[str, list[str]]:
    """Map each migration to its ``-- verify: <table[, ...]>`` tables.

    Not every migration declares a hint (006 does not); files that declare
    one list the tables the runner row-count-checks after applying.  A hint
    opens with a ``-- verify:`` marker line and may continue over the next
    comment lines while they contain only table tokens and commas.
    """
    hints: dict[str, list[str]] = {}
    for path in sorted(directory.glob("*.sql")):
        tables: list[str] = []
        in_block = False
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _VERIFY_MARKER_RE.match(line)
            if match:
                in_block = True
            else:
                match = _VERIFY_TOKEN_RE.match(line) if in_block else None
                if not match:
                    in_block = False
                    continue
            tables.extend(
                token.strip().strip("`")
                for token in re.split(r"\s*,\s*", match.group(1))
                if token.strip()
            )
        if tables:
            hints[path.name] = tables
    return hints


def analyze_tracker(
    records: Iterable[MigrationRecord],
    directory: Path = MIGRATIONS_DIR,
) -> list[TrackerItem]:
    """Classify every known file and every tracker row.

    ``records`` are the ``schema_migrations`` rows (name/applied_at/checksum).
    The result is a list of ``TrackerItem`` objects, one per canonical
    migration plus one for any orphan (recorded name with no file).
    """
    files = {path.name for path in discover_migration_files(directory)}
    canonical = {name for name, _ in MIGRATIONS}
    by_name: dict[str, MigrationRecord] = {}
    for record in records:
        by_name[record.name] = by_name.get(record.name) or record

    items: list[TrackerItem] = []
    for name, _expected_digest in MIGRATIONS:
        record = by_name.get(name)
        path = directory / name
        file_digest = checksum(path) if path.is_file() else None
        if record is None:
            items.append(TrackerItem(name, MigrationStatus.PENDING, "not recorded"))
        elif not record.checksum:
            items.append(
                TrackerItem(
                    name,
                    MigrationStatus.APPLIED_LEGACY,
                    "applied before checksums were tracked; digest unknown",
                )
            )
        elif file_digest is not None and record.checksum == file_digest:
            items.append(
                TrackerItem(
                    name,
                    MigrationStatus.APPLIED_CURRENT,
                    f"sha256 {record.checksum[:12]}…",
                )
            )
        else:
            shown = file_digest if file_digest else "missing-file"
            src = "file" if file_digest else "no file on disk"
            items.append(
                TrackerItem(
                    name,
                    MigrationStatus.APPLIED_MISMATCH,
                    f"recorded {record.checksum[:12]}… != "
                    f"{src} {shown[:12]}…",
                )
            )

    recorded_names = {r.name for r in records}
    for extra in sorted(recorded_names - canonical):
        if extra not in files:
            items.append(TrackerItem(extra, MigrationStatus.ORPHAN, "no file"))
        else:
            items.append(TrackerItem(extra, MigrationStatus.UNKNOWN_FILE))
    return items


def tracker_summary(records: Iterable[MigrationRecord]) -> str:
    """One-line summary of tracker health used by scripts and reports."""
    items = analyze_tracker(records)
    counts: dict[MigrationStatus, int] = {}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return (
        f"{counts.get(MigrationStatus.APPLIED_CURRENT, 0)} current, "
        f"{counts.get(MigrationStatus.APPLIED_LEGACY, 0)} legacy, "
        f"{counts.get(MigrationStatus.APPLIED_MISMATCH, 0)} drifted, "
        f"{counts.get(MigrationStatus.PENDING, 0)} pending, "
        f"{counts.get(MigrationStatus.ORPHAN, 0)} orphan"
    )