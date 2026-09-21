"""Tests for migration 0025 — the value check that guards its enum cast.

``0025_convert_extractions_status_to_enum`` converts ``extractions.status`` from ``VARCHAR(20)``
to the ``extraction_status_new`` enum, and it refuses to run when the column holds a value the
enum does not declare: the ``USING`` cast would otherwise abort with a Postgres error and take
the whole chain with it, because a revision runs in one transaction.

The integration test that runs the chain proves the conversion on Postgres, but its container
database is **empty**, so it only ever exercises the happy path — the guard's raising branch runs
nowhere, in CI or on a laptop. That is the gap this module closes: the check 0025 relies on is the
most valuable half of that revision, and until it is separated from the connection it can only be
proven by reading.

So the decision is a pure function, and the bulk of this file needs no database at all. One test
then wires it through a scratch in-memory SQLite database, the way the sibling per-revision tests
do, to show that 0025 really does call it against the column — testing the helper without that
would not prove the revision relies on it.

The revision module is loaded from its path rather than imported: the file name starts with a
digit and ``versions`` is not a package, so it has no importable module name.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import storico
from storico.domain.entities.extraction import ExtractionStatus
from storico.infrastructure.database.models.extraction import ExtractionModel

_MIGRATION_PATH = (
    Path(storico.__file__).parent
    / "infrastructure"
    / "database"
    / "alembic"
    / "versions"
    / "0025_convert_extractions_status_to_enum.py"
)

# ``extractions`` at the shape 0025 is applied to: the column is still the ``VARCHAR(20)`` 0002
# created. Built with Core rather than from the model, because the model already declares the enum
# and the revision has to face the schema it actually faced.
_EXTRACTIONS_AT_0024 = sa.Table(
    "extractions",
    sa.MetaData(),
    sa.Column("status", sa.String(20), nullable=False),
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_migration_0025", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decide(stored: object, labels: object = ("pending", "completed", "failed")) -> list[str]:
    """Run the revision's pure decision over ``stored``, with ``labels`` it is given."""
    return _load_migration()._values_outside_labels(labels, stored)


class TestTheDecision:
    """The pure function, which needs no database to be exercised."""

    @pytest.mark.unit
    def test_no_stored_values_means_nothing_is_stray(self) -> None:
        """An empty column is the case every fresh database and every CI run hits."""
        assert _decide([]) == []

    @pytest.mark.unit
    def test_all_values_inside_the_labels_means_nothing_is_stray(self) -> None:
        """The happy path: the cast can proceed and the guard must stay quiet."""
        assert _decide(["pending", "completed", "failed"]) == []

    @pytest.mark.unit
    def test_a_single_stray_value_is_reported(self) -> None:
        """The case the whole check exists for: a value the cast would abort on.

        It must not be swallowed into an empty result. A check that quietly reports "nothing
        stray" for a stray input is worse than no check, because the revision would then fail
        with the truncated Postgres error this guard was written to replace.
        """
        assert _decide(["pending", "processing"]) == ["processing"]

    @pytest.mark.unit
    def test_several_stray_values_are_all_reported(self) -> None:
        """Not just the first one: an operator should see every value that is in the way."""
        assert _decide(["processing", "error", "pending"]) == ["error", "processing"]

    @pytest.mark.unit
    def test_the_result_is_sorted_and_deduplicated(self) -> None:
        """With many rows, one stray value is one line of output, in a stable order."""
        assert _decide(["zzz", "aaa", "zzz", "aaa"]) == ["aaa", "zzz"]

    @pytest.mark.unit
    def test_none_is_not_reported_as_a_stray(self) -> None:
        """A null is a different failure, not an unknown label.

        The column is ``NOT NULL``, so this cannot arise through this schema; it is filtered
        anyway so that a NULL would never be reported as a value the operator must go and
        rename. A null would not fail the cast at all.
        """
        assert _decide(["pending", None]) == []

    @pytest.mark.unit
    def test_the_labels_argument_decides_not_a_hardcoded_list(self) -> None:
        """The function judges against the labels it is handed, wherever they came from.

        This is what makes it testable without a database and what keeps it honest for 0025:
        if it silently compared against its own copy of the extraction labels, the next caller
        with a different enum would get a wrong answer that nothing here would catch.
        """
        assert _decide(["a", "c"], labels=("a", "b")) == ["c"]

    @pytest.mark.unit
    def test_a_label_valid_for_a_different_enum_is_still_stray(self) -> None:
        """``extracted`` is a ``user_story_status`` label and not an extraction one.

        0018 and 0016 create four enums with overlapping-looking labels, so comparing this
        column against the wrong one is a plausible mistake with a silent result: the guard
        would pass and the cast would fail later.
        """
        assert _decide(["extracted"]) == ["extracted"]


class TestTheRevisionUsesTheDecision:
    """0025 has to actually call the decision, against the right column and labels."""

    @pytest.fixture
    def engine(self) -> Iterator[Engine]:
        """A scratch database holding ``extractions`` at its pre-0025 shape.

        ``StaticPool`` keeps every connection on the single in-memory database; without it each
        new connection would get its own empty one and the revision would find no table.
        """
        engine = sa.create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        _EXTRACTIONS_AT_0024.create(engine)
        yield engine
        engine.dispose()

    def _seed(self, engine: Engine, *statuses: str) -> None:
        # Through a Session and a Core insert, as the sibling 0022 migration test seeds: the
        # statement is built from the table declaration and every value travels as a bound
        # parameter, so no status is ever composed into SQL text.
        with Session(engine) as session:
            session.execute(
                _EXTRACTIONS_AT_0024.insert(), [{"status": status} for status in statuses]
            )
            session.commit()

    def _strays_the_revision_reads(self, engine: Engine) -> list[str]:
        """``_stray_statuses()`` as ``upgrade`` calls it — real connection, real query."""
        migration = _load_migration()
        with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                return migration._stray_statuses()

    @pytest.mark.unit
    def test_it_reads_the_column_and_reports_the_stray_it_finds(self, engine: Engine) -> None:
        """The wiring, end to end but without Postgres: valid rows plus one stray."""
        self._seed(engine, "pending", "completed", "processing", "failed")

        assert self._strays_the_revision_reads(engine) == ["processing"]

    @pytest.mark.unit
    def test_it_reads_the_column_and_finds_nothing_when_the_data_is_clean(
        self, engine: Engine
    ) -> None:
        """The CI path, pinned: clean data means the guard stays silent and the cast runs."""
        self._seed(engine, "pending", "failed")

        assert self._strays_the_revision_reads(engine) == []

    @pytest.mark.unit
    def test_it_does_not_judge_against_another_enums_labels(self, engine: Engine) -> None:
        """A ``user_story_status`` label in this column must be reported, not accepted.

        0016's labels include ``extracted`` and 0018's do not, so if 0025 read its labels from
        the wrong enum the guard would pass and the cast would abort on that same value.
        """
        self._seed(engine, "extracted")

        assert self._strays_the_revision_reads(engine) == ["extracted"]

    @pytest.mark.unit
    def test_the_labels_it_checks_against_are_the_enum_it_converts_to(self) -> None:
        """The revision, the domain enum and the model must name the same three labels.

        Three independent declarations of one list — the revision's own copy, the StrEnum the
        application writes, and the ``PGEnum`` the model declares — and the revision only works
        while all three agree. This is the drift that would otherwise surface as a failing cast
        in production.
        """
        migration = _load_migration()
        model_column = ExtractionModel.__table__.c.status
        enum_type = model_column.type
        assert isinstance(enum_type, sa.Enum), (
            f"the model declares {type(enum_type).__name__}, so there are no labels to compare"
        )

        assert list(migration._ALLOWED_STATUSES) == [status.value for status in ExtractionStatus]
        assert list(migration._ALLOWED_STATUSES) == list(enum_type.enums)
        assert migration._ENUM_TYPE_NAME == enum_type.name

    @pytest.mark.unit
    def test_the_revision_follows_0024(self) -> None:
        """A wrong ``down_revision`` would leave the migration chain with two heads."""
        migration = _load_migration()

        assert migration.revision == "0025"
        assert migration.down_revision == "0024"

    @pytest.mark.unit
    def test_upgrade_refuses_and_names_the_value_it_will_not_cast(self, engine: Engine) -> None:
        """The refusal path, exercised against a real database instead of proven by reading.

        ``upgrade`` checks the stored values **before** it touches any DDL, so this holds on SQLite
        even though the cast that follows is Postgres-only: the guard raises first. That is the
        point of the test — the CI container starts with an **empty** database, so the happy path
        is the only one CI ever runs, and until this existed the refusal was proven by reading
        alone.

        The duplicate ``processing`` is deliberate: the message names *distinct* values, so an
        operator gets one line per offending value rather than one per row.
        """
        self._seed(engine, "pending", "processing", "processing", "failed")

        migration = _load_migration()
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                with pytest.raises(RuntimeError) as caught:
                    migration.upgrade()

        message = str(caught.value)
        # It names what is in the way — once — and what the column does accept.
        assert message.count("processing") == 1
        assert "pending" in message and "failed" in message
        assert "Nothing has been changed" in message
        # And the promise the message makes is measured rather than asserted in prose: the rows
        # are still there, because the check runs before anything is altered.
        with engine.connect() as conn:
            survivors = conn.execute(sa.select(_EXTRACTIONS_AT_0024.c.status)).scalars().all()
        assert sorted(survivors) == ["failed", "pending", "processing", "processing"]
