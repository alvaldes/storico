"""drop workspace_prompts.few_shot_examples

``workspace_prompts.few_shot_examples`` was the pre-Qdrant home of manual
few-shot examples: a JSONB document of ``{"items": [...]}`` the repository
wrapped and unwrapped around the domain entity. Since automatic retrieval
landed (0020), few-shot examples live as points in the vector store and are
retrieved per workspace at extraction time; the column was kept read-only only
so the one-time seed job (``storico.cli.seed_few_shot``) could migrate legacy
values into Qdrant. The dev database holds 14 rows and none of them carried
content, so there was nothing to migrate — the seed job, its tests, and this
column go together.

The API already rejects the field (``PromptRequest`` sets ``extra="forbid"``,
posting it answers 422), so no API surface changes here.

**Deploy the release that stops reading the column BEFORE running this
revision.** The previous ORM model selects ``few_shot_examples`` on every
``workspace_prompts`` load, so the old code fails outright against a dropped
column. New code never names the column, and a database that still carries it
is invisible to the new model — so code-first is the only safe order, the same
class as revision 0022 and the opposite of 0023. The ``downgrade`` restores the
column as nullable JSONB, which is exactly what 0009 left it as; a downgrade
after the new release is live is harmless because the new model ignores
unknown columns.

Like 0022 and 0023, that instruction describes a migration run against a live
release. The current deploy workflow applies migrations inside a maintenance
window with no release running (``docs/deployment.md``), and that is what makes
this revision's ordering and 0023's opposite one compatible.

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the legacy ``few_shot_examples`` column.

    Measured on the **dev** database before this revision ran: 14 rows, **none of
    them carrying content** (0 non-empty payloads), so the drop destroys no value
    there. That measurement is pre-drop and stops being reproducible once the
    column is gone. **Production was not measured**, because its database is Neon
    and its credentials live in the VM's ``.env`` — so the deploy that runs this
    revision should confirm the same shape first: the ``downgrade`` restores the
    column but not the values it held.

    The few-shot retrieval config columns added by 0020 (``few_shot_enabled``/
    ``few_shot_limit``/``few_shot_threshold``) are untouched.
    """
    op.drop_column("workspace_prompts", "few_shot_examples")


def downgrade() -> None:
    """Restore the column as nullable JSONB, matching what 0009 established.

    Restored rows read as null, which the pre-removal code treats as "no legacy
    examples" — the same state every real row was already in.
    """
    op.add_column(
        "workspace_prompts",
        sa.Column("few_shot_examples", postgresql.JSONB(), nullable=True),
    )
