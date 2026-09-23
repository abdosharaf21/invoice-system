"""Offline tests for schema drift verification (Phase 12).

``backend.database.schema_verify`` splits fact collection (live database)
from the diff (pure). These tests exercise the pure layer with constructed
facts — no database is needed.
"""

import pytest

from backend.database.schema_manifest import (
    ALLOWED_EXTRA_TABLES,
    Column,
    EXPECTED_TABLES,
    ForeignKey,
    Index,
    TableRule,
)
from backend.database.schema_verify import (
    ColumnFacts,
    Drift,
    ForeignKeyFacts,
    IndexFacts,
    TableFacts,
    diff_schema,
    drift_count_by_code,
    norm_default,
    norm_type,
    render,
)


def _facts(rule: TableRule, name: str) -> TableFacts:
    """Materialise a TableRule into matching TableFacts (a faithful DB view)."""
    columns = tuple(
        ColumnFacts(
            name=cname,
            type=column.type,
            nullable=column.nullable,
            default=column.default,
            ordinal=idx + 1,
        )
        for idx, (cname, column) in enumerate(rule.columns)
    )
    indexes = {
        iname: IndexFacts(name=iname, unique=index.unique, columns=index.columns)
        for iname, index in rule.indexes.items()
    }
    foreign_keys = {
        fname: ForeignKeyFacts(
            name=fname,
            table=name,
            columns=fk.columns,
            referenced_table=fk.table,
            referenced_columns=fk.referenced_columns,
            delete_rule=fk.delete_rule,
            update_rule=fk.update_rule,
        )
        for fname, fk in rule.foreign_keys.items()
    }
    return TableFacts(
        name=name,
        engine=rule.engine,
        collation=rule.collation,
        columns=columns,
        indexes=indexes,
        foreign_keys=foreign_keys,
        checks=tuple(rule.checks),
    )


def _table(**kwargs) -> TableRule:
    defaults = dict(columns=(("id", Column(type="bigint unsigned")),))
    defaults.update(kwargs)
    return TableRule(**defaults)


class TestNormalization:
    def test_norm_type_lowercases_and_strips_spaces(self):
        assert norm_type(" VARCHAR(255) ") == "varchar(255)"
        assert norm_type("Bigint Unsigned") == "bigintunsigned"

    def test_norm_default_numeric_equivalence(self):
        assert norm_default("0") == norm_default("0.00")
        assert norm_default("1") != norm_default("0")
        assert norm_default("1.0000") == norm_default("1.0000")

    def test_norm_default_strings_and_none(self):
        assert norm_default(None) is None
        assert norm_default("uploaded") == ("str", "uploaded")
        assert norm_default("CURRENT_TIMESTAMP") == ("str", "current_timestamp")
        assert norm_default("") == ("str", "")


class TestDiffSchema:
    def test_identical_schema_is_clean(self):
        for name, rule in EXPECTED_TABLES.items():
            drifts = diff_schema({name: rule}, {name: _facts(rule, name)})
            assert drifts == []

    def test_missing_table(self):
        drifts = diff_schema({"companies": _table()}, {})
        assert any(d.code == "missing_table" for d in drifts)

    def test_unexpected_table_flag_but_allowed_ones_ignored(self):
        companies_rule = _table()
        actual = {"companies": _facts(companies_rule, "companies")}
        actual["surprise_table"] = _facts(_table(), "surprise_table")
        for allowed in ALLOWED_EXTRA_TABLES:
            actual[allowed] = _facts(_table(), allowed)
        drifts = diff_schema({"companies": companies_rule}, actual)
        codes = {d.code for d in drifts}
        assert "unexpected_table" in codes
        for d in drifts:
            assert d.table == "surprise_table"
        assert not any(d.table in ALLOWED_EXTRA_TABLES for d in drifts)

    def test_column_type_nullable_default_drifts(self):
        rule = _table(columns=(
            ("id", Column(type="bigint unsigned")),
            ("name", Column(type="varchar(255)")),
        ))
        actual = _facts(rule, "companies")
        broken = TableFacts(
            name=actual.name, engine=actual.engine, collation=actual.collation,
            columns=(
                ColumnFacts("id", "varchar(20)", False, None, 1),
                ColumnFacts("name", "varchar(255)", True, "anon", 2),
            ),
            indexes={}, foreign_keys={}, checks=(),
        )
        drifts = diff_schema({"companies": rule}, {"companies": broken})
        codes = {d.code for d in drifts}
        assert "column_type" in codes
        assert "column_nullable" in codes
        assert "column_default" in codes

    def test_missing_and_unexpected_column(self):
        rule = _table(columns=(
            ("id", Column(type="bigint unsigned")),
            ("name", Column(type="varchar(255)")),
        ))
        actual = _facts(rule, "companies")
        trimmed = TableFacts(
            name=actual.name, engine=actual.engine, collation=actual.collation,
            columns=(actual.columns[0],),
            indexes={}, foreign_keys={}, checks=(),
        )
        with_extra = TableFacts(
            name=actual.name, engine=actual.engine, collation=actual.collation,
            columns=tuple(list(actual.columns) + [
                ColumnFacts("bonus", "int", True, None, 3)]),
            indexes={}, foreign_keys={}, checks=(),
        )
        assert any(d.code == "missing_column" for d in diff_schema({"companies": rule}, {"companies": trimmed}))
        assert any(d.code == "unexpected_column" for d in diff_schema({"companies": rule}, {"companies": with_extra}))

    def test_column_order_reordered_is_info_severity(self):
        rule = _table(columns=(
            ("id", Column(type="bigint unsigned")),
            ("name", Column(type="varchar(255)")),
        ))
        actual = _facts(rule, "companies")
        reordered = TableFacts(
            name=actual.name, engine=actual.engine, collation=actual.collation,
            columns=(actual.columns[1], actual.columns[0]),
            indexes={}, foreign_keys={}, checks=(),
        )
        drifts = diff_schema({"companies": rule}, {"companies": reordered})
        order = [d for d in drifts if d.code == "column_order_mismatch"]
        assert len(order) == 1
        assert order[0].severity == "info"

    def test_index_and_engine_collation_drifts(self):
        rule = _table(indexes={
            "PRIMARY": Index(True, ("id",)),
        })
        actual = _facts(rule, "companies")
        downgraded = TableFacts(
            name=actual.name, engine="MyISAM", collation="latin1_swedish_ci",
            columns=actual.columns, indexes={}, foreign_keys={}, checks=(),
        )
        drifts = diff_schema({"companies": rule}, {"companies": downgraded})
        codes = {d.code for d in drifts}
        assert "engine_mismatch" in codes
        assert "collation_mismatch" in codes
        assert "missing_index" in codes

    def test_index_shape_mismatch_and_unexpected(self):
        rule = _table(indexes={
            "idx_x": Index(True, ("a",)),
        })
        actual = _facts(rule, "companies")
        wrong = TableFacts(
            name=actual.name, engine=actual.engine, collation=actual.collation,
            columns=actual.columns,
            indexes={"idx_x": IndexFacts("idx_x", False, ("b",))},
            foreign_keys={}, checks=(),
        )
        drifts = diff_schema({"companies": rule}, {"companies": wrong})
        assert any(d.code == "index_mismatch" for d in drifts)

    def test_foreign_key_drifts(self):
        rule = _table(foreign_keys={
            "fk_a": ForeignKey("parents", ("a",), ("id",), "CASCADE"),
        })
        actual = _facts(rule, "companies")
        broken = TableFacts(
            name=actual.name, engine=actual.engine, collation=actual.collation,
            columns=actual.columns, indexes={},
            foreign_keys={
                "fk_a": ForeignKeyFacts("fk_a", "companies", ("a",), "other", ("id",), "SET NULL", "CASCADE"),
            },
            checks=(),
        )
        assert any(d.code == "fk_mismatch" for d in diff_schema({"companies": rule}, {"companies": broken}))

    def test_check_constraint_drifts(self):
        rule = _table(checks=("chk_a", "chk_b"))
        actual = _facts(rule, "companies")
        partial = TableFacts(
            name=actual.name, engine=actual.engine, collation=actual.collation,
            columns=actual.columns, indexes={}, foreign_keys={},
            checks=("chk_a", "chk_unexpected"),
        )
        drifts = diff_schema({"companies": rule}, {"companies": partial})
        codes = {d.code for d in drifts}
        assert "missing_check" in codes
        assert "unexpected_check" in codes

    def test_render_pass_text(self):
        assert "PASS" in render([])

    def test_drift_count_by_code(self):
        drifts = [
            Drift("a", "missing_table", "x"),
            Drift("b", "missing_table", "y"),
            Drift("c", "engine_mismatch", "z"),
        ]
        counts = drift_count_by_code(drifts)
        assert counts == {"missing_table": 2, "engine_mismatch": 1}