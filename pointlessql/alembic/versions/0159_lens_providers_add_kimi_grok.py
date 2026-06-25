"""lens providers add kimi grok

Extends the two Lens provider CHECK constraints so the Kimi (Moonshot)
and Grok (xAI) adapters can be selected as BYO LLM providers.  The
``LENS_PROVIDERS`` tuple in
``pointlessql/models/lens/_provider_creds.py`` is the source of truth;
this migration brings the deployed DB's ``ck_lens_sessions_provider``
and ``ck_lens_provider_creds_provider`` constraints into agreement so
unmigrated databases stop rejecting ``'kimi'`` / ``'grok'`` with
``CHECK constraint failed``.

Revision ID: 0159
Revises: 0158
Create Date: 2026-06-20 16:25:06.644481
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0159"
down_revision: str | None = "0158"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "('openai', 'anthropic')"
_NEW = "('openai', 'anthropic', 'kimi', 'grok')"


def upgrade() -> None:
    with op.batch_alter_table("lens_sessions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_lens_sessions_provider", type_="check")
        batch_op.create_check_constraint(
            "ck_lens_sessions_provider",
            f"llm_provider IN {_NEW}",
        )
    with op.batch_alter_table("lens_provider_creds", schema=None) as batch_op:
        batch_op.drop_constraint("ck_lens_provider_creds_provider", type_="check")
        batch_op.create_check_constraint(
            "ck_lens_provider_creds_provider",
            f"provider IN {_NEW}",
        )


def downgrade() -> None:
    with op.batch_alter_table("lens_sessions", schema=None) as batch_op:
        batch_op.drop_constraint("ck_lens_sessions_provider", type_="check")
        batch_op.create_check_constraint(
            "ck_lens_sessions_provider",
            f"llm_provider IN {_OLD}",
        )
    with op.batch_alter_table("lens_provider_creds", schema=None) as batch_op:
        batch_op.drop_constraint("ck_lens_provider_creds_provider", type_="check")
        batch_op.create_check_constraint(
            "ck_lens_provider_creds_provider",
            f"provider IN {_OLD}",
        )
