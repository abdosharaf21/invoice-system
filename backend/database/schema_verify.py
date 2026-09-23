"""Schema drift verification against the expected manifest (Phase 12).

Two layers, kept separate so the diff logic is fully offline-testable:

  * ``collect_facts(connection, schema)`` — reads ``information_schema`` for a
    live database and returns a plain ``dict[str, TableFacts]``.
  * ``diff_schema(expected, actual)`` — pure function comparing facts to the
    golden ``schema_manifest.EXPECTED_TABLES`` and returning structured drift
    reports. No database needed; exercised directly by the pytest suite with
    purpose-built facts.

CLI
```bash
PYTHONPATH=. ../.venv/bin/python -m backend.database.schema_verify \
    --db invoice_system            # default: DB_NAME / env / .env
```
Prints every drift and exits 0 (in sync) / 1 (drift found) / 2 (error).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Tuple

from backend.database.config import DatabaseConfig, get_database_config
from backend.database.schema_manifest import (
    ALLOWED_EXTRA_TABLES,
    Column,
    EXPECTED_TABLES,
    TableRule,
)


# ---------------------------------------------------------------------------
# Facts model (what a live database reports through information_schema)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnFacts:
    name: str
    type: str
    nullable: bool
    default: Optional[str]
    ordinal: int


@dataclass(frozen=True)
class IndexFacts:
    name: str
    unique: bool
    columns: Tuple[str, ...]


@dataclass(frozen=True)
class ForeignKeyFacts:
    name: str
    table: str
    columns: Tuple[str, ...]
    referenced_table: str
    referenced_columns: Tuple[str, ...]
    delete_rule: str
    update_rule: str


@dataclass(frozen=True)
class TableFacts:
    name: str
    engine: str
    collation: str
    columns: Tuple[ColumnFacts, ...]  # ordered
    indexes: Dict[str, IndexFacts]
    foreign_keys: Dict[str, ForeignKeyFacts]
    checks: Tuple[str, ...]


@dataclass(frozen=True)
class Drift:
    table: str
    code: str
    detail: str
    severity: str = "error"


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def norm_type(type_: str) -> str:
    """Comparison-safe column type: lowercase, whitespace stripped."""
    return type_.strip().lower().replace(" ", "")


def norm_default(value: Optional[str]):
    """Comparison-safe default: numeric values compare numerically.

    ``0`` and ``0.00`` (and ``1.0000`` vs ``1.0000``) are equivalent; string
    defaults (``'uploaded'``, ``'CURRENT_TIMESTAMP'``, ``''``) compare as
    casefolded strings. ``None`` (no default / DEFAULT NULL) is returned as-is.
    """
    if value is None:
        return None
    text = str(value).strip()
    try:
        return ("num", float(Decimal(text)))
    except (InvalidOperation, ValueError):
        return ("str", text.casefold())


# ---------------------------------------------------------------------------
# Facts collection (requires a live database)
# ---------------------------------------------------------------------------


def collect_facts(connection, schema: str) -> Dict[str, TableFacts]:
    """Query ``information_schema`` and return facts for every base table."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            """,
            (schema,),
        )
        tables: Dict[str, TableFacts] = {}
        for name, engine, collation in cursor.fetchall():
            tables[name] = TableFacts(
                name=name,
                engine=engine,
                collation=collation,
                columns=(),
                indexes={},
                foreign_keys={},
                checks=(),
            )

        for name in tables:
            cursor.execute(
                """
                SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       ORDINAL_POSITION
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (schema, name),
            )
            columns = tuple(
                ColumnFacts(
                    name=cname,
                    type=ctype,
                    nullable=is_nullable == "YES",
                    default=default,
                    ordinal=ordinal,
                )
                for cname, ctype, is_nullable, default, ordinal in cursor.fetchall()
            )

            cursor.execute(
                """
                SELECT INDEX_NAME, SEQ_IN_INDEX, COLUMN_NAME, NON_UNIQUE
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY INDEX_NAME, SEQ_IN_INDEX
                """,
                (schema, name),
            )
            raw = cursor.fetchall()
            index_cols: Dict[str, List[Tuple[str, int]]] = {}
            index_unique: Dict[str, bool] = {}
            for index_name, seq, column_name, non_unique in raw:
                index_cols.setdefault(index_name, []).append(column_name)
                index_unique[index_name] = not bool(non_unique)
            indexes = {
                iname: IndexFacts(
                    name=iname,
                    unique=index_unique[iname],
                    columns=tuple(cols),
                )
                for iname, cols in index_cols.items()
            }

            cursor.execute(
                """
                SELECT rc.CONSTRAINT_NAME, rc.REFERENCED_TABLE_NAME,
                       rc.DELETE_RULE, rc.UPDATE_RULE, kcu.COLUMN_NAME,
                       kcu.REFERENCED_COLUMN_NAME, kcu.ORDINAL_POSITION
                FROM information_schema.REFERENTIAL_CONSTRAINTS rc
                JOIN information_schema.KEY_COLUMN_USAGE kcu
                  ON kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
                 AND kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                 AND kcu.TABLE_NAME = rc.TABLE_NAME
                WHERE rc.CONSTRAINT_SCHEMA = %s AND rc.TABLE_NAME = %s
                ORDER BY rc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
                """,
                (schema, name),
            )
            fk_rows = cursor.fetchall()
            fk_cols: Dict[str, List[tuple]] = {}
            for fname, ref_table, del_rule, upd_rule, col_name, ref_col, _pos in fk_rows:
                fk_cols.setdefault(fname, []).append(
                    (col_name, ref_col, ref_table, del_rule, upd_rule)
                )
            foreign_keys = {
                fname: ForeignKeyFacts(
                    name=fname,
                    table=name,
                    columns=tuple(col for col, *_ in cols),
                    referenced_table=cols[0][2],
                    referenced_columns=tuple(ref_col for _, ref_col, *_ in cols),
                    delete_rule=cols[0][3],
                    update_rule=cols[0][4],
                )
                for fname, cols in fk_cols.items()
            }

            cursor.execute(
                """
                SELECT tc.CONSTRAINT_NAME
                FROM information_schema.TABLE_CONSTRAINTS tc
                WHERE tc.CONSTRAINT_SCHEMA = %s
                  AND tc.TABLE_NAME = %s
                  AND tc.CONSTRAINT_TYPE = 'CHECK'
                ORDER BY tc.CONSTRAINT_NAME
                """,
                (schema, name),
            )
            checks = tuple(row[0] for row in cursor.fetchall())

            tables[name] = TableFacts(
                name=name,
                engine=tables[name].engine,
                collation=tables[name].collation,
                columns=columns,
                indexes=indexes,
                foreign_keys=foreign_keys,
                checks=checks,
            )
        return tables
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Pure drift diff (offline-testable)
# ---------------------------------------------------------------------------


def _check_column(
    table: str, expected: Column, actual: "ColumnFacts",
) -> List[Drift]:
    drifts: List[Drift] = []
    if norm_type(expected.type) != norm_type(actual.type):
        drifts.append(
            Drift(
                table,
                "column_type",
                f"{actual.name}: expected {expected.type}, found {actual.type}",
            )
        )
    if expected.nullable != actual.nullable:
        drifts.append(
            Drift(
                table,
                "column_nullable",
                f"{actual.name}: expected nullable={expected.nullable}, "
                f"found {actual.nullable}",
            )
        )
    if norm_default(expected.default) != norm_default(actual.default):
        drifts.append(
            Drift(
                table,
                "column_default",
                f"{actual.name}: expected default {expected.default!r}, "
                f"found {actual.default!r}",
            )
        )
    return drifts


def diff_schema(
    expected: Dict[str, TableRule],
    actual: Dict[str, TableFacts],
) -> List[Drift]:
    """Compare live facts to the golden manifest; return all drift reports.

    Only the catalog of expected tables is validated: extra tables outside
    ``ALLOWED_EXTRA_TABLES`` are flagged. Checks are compared by constraint
    name (MySQL reformats CHECK clauses, so clause text is not reliable).
    """
    drifts: List[Drift] = []

    for table, rule in expected.items():
        facts = actual.get(table)
        if facts is None:
            drifts.append(
                Drift(table, "missing_table", "expected table not present")
            )
            continue

        if facts.engine != rule.engine:
            drifts.append(
                Drift(
                    table,
                    "engine_mismatch",
                    f"expected {rule.engine}, found {facts.engine}",
                )
            )
        if facts.collation != rule.collation:
            drifts.append(
                Drift(
                    table,
                    "collation_mismatch",
                    f"expected {rule.collation}, found {facts.collation}",
                )
            )

        # --- columns -----------------------------------------------------
        fact_columns = {c.name: c for c in facts.columns}
        expected_names = [name for name, _ in rule.columns]
        required = [(name, col) for name, col in rule.columns]
        for name, col in required:
            fact = fact_columns.get(name)
            if fact is None:
                drifts.append(
                    Drift(table, "missing_column", f"{table}.{name} not present")
                )
            else:
                drifts.extend(_check_column(table, col, fact))

        actual_names = [c.name for c in facts.columns]
        for name in actual_names:
            if name not in dict(required):
                drifts.append(
                    Drift(table, "unexpected_column", f"extra column {name}")
                )
        if sorted(actual_names) == sorted(expected_names) and list(actual_names) != expected_names:
            drifts.append(
                Drift(
                    table,
                    "column_order_mismatch",
                    f"expected order {expected_names}, found {actual_names}",
                    severity="info",
                )
            )

        # --- indexes -----------------------------------------------------
        for iname, index in rule.indexes.items():
            fact_index = facts.indexes.get(iname)
            if fact_index is None:
                drifts.append(
                    Drift(table, "missing_index", f"index {iname} not present")
                )
                continue
            if fact_index.unique != index.unique or list(fact_index.columns) != list(index.columns):
                drifts.append(
                    Drift(
                        table,
                        "index_mismatch",
                        f"index {iname}: expected unique={index.unique} "
                        f"columns={list(index.columns)}, found unique="
                        f"{fact_index.unique} columns={list(fact_index.columns)}",
                    )
                )
        for iname in facts.indexes:
            if iname not in rule.indexes:
                drifts.append(
                    Drift(table, "unexpected_index", f"extra index {iname}")
                )

        # --- foreign keys -------------------------------------------------
        for fname, fk in rule.foreign_keys.items():
            fact_fk = facts.foreign_keys.get(fname)
            if fact_fk is None:
                drifts.append(
                    Drift(table, "missing_fk", f"foreign key {fname} not present")
                )
                continue
            expected_ref = fk.table
            if (
                fact_fk.referenced_table != expected_ref
                or list(fact_fk.columns) != list(fk.columns)
                or list(fact_fk.referenced_columns) != list(fk.referenced_columns)
                or fact_fk.delete_rule != fk.delete_rule
                or fact_fk.update_rule != fk.update_rule
            ):
                drifts.append(
                    Drift(
                        table,
                        "fk_mismatch",
                        f"foreign key {fname}: expected columns={list(fk.columns)} "
                        f"-> {expected_ref}{list(fk.referenced_columns)} "
                        f"{fk.delete_rule}/{fk.update_rule}, found "
                        f"columns={list(fact_fk.columns)} -> "
                        f"{fact_fk.referenced_table}"
                        f"{list(fact_fk.referenced_columns)} "
                        f"{fact_fk.delete_rule}/{fact_fk.update_rule}",
                    )
                )
        for fname in facts.foreign_keys:
            if fname not in rule.foreign_keys:
                drifts.append(
                    Drift(table, "unexpected_fk", f"extra foreign key {fname}")
                )

        # --- check constraints ------------------------------------------
        for cname in rule.checks:
            if cname not in facts.checks:
                drifts.append(
                    Drift(table, "missing_check", f"check constraint {cname} missing")
                )
        for cname in facts.checks:
            if cname not in rule.checks:
                drifts.append(
                    Drift(table, "unexpected_check", f"extra check constraint {cname}")
                )

    # --- unexpected tables ------------------------------------------------
    for name in sorted(actual):
        if name not in expected and name not in ALLOWED_EXTRA_TABLES:
            drifts.append(
                Drift(name, "unexpected_table", "table not in the expected schema")
            )

    return drifts


def drift_count_by_code(drifts: Iterable[Drift]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for drift in drifts:
        counts[drift.code] = counts.get(drift.code, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def collect_facts_live(schema: str, config: Optional[DatabaseConfig] = None) -> Dict[str, TableFacts]:
    """Open a live connection and collect facts (used by the CLI)."""
    import mysql.connector

    config = config or get_database_config()
    connection = mysql.connector.connect(
        host=config.host,
        port=config.port,
        database=schema,
        user=config.user,
        password=config.password,
    )
    try:
        return collect_facts(connection, schema)
    finally:
        connection.close()


def render(drifts: List[Drift]) -> str:
    if not drifts:
        return "RESULT: PASS — database matches the expected schema manifest."
    lines = [f"RESULT: DRIFT — {len(drifts)} difference(s) found:"]
    for drift in sorted(drifts, key=lambda d: (d.severity, d.table, d.code)):
        lines.append(f"  [{drift.severity}] {drift.table}: {drift.code} — {drift.detail}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a database against the schema manifest."
    )
    parser.add_argument(
        "--db", dest="schema", default=None, help="database schema to verify"
    )
    args = parser.parse_args(argv)

    config = get_database_config()
    schema = args.schema or config.name
    try:
        facts = collect_facts_live(schema, config)
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"ERROR: could not collect facts for '{schema}': {exc}", file=_err)
        return 2

    drifts = diff_schema(EXPECTED_TABLES, facts)
    print(render(drifts))
    return 0 if not drifts else 1


_err = sys.stderr


if __name__ == "__main__":
    sys.exit(main())