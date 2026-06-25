"""threading depth + reactions + categories

Phase 76 first sub-sprint.  Extends the Discussion-tab data
model on three axes:

* `data_product_comments` gains a `category` enum ('general' /
  'question' / 'announcement' / 'idea') and an
  `is_accepted_answer` boolean so a steward or the OP can mark
  an answer on a question-category thread.
* `data_product_comment_reactions` records GitHub-style 6-emoji
  reactions on individual comments (one row per
  comment/user/emoji triple).
* `data_product_reactions` records the same on a data product
  itself, surfaced above the comment list.

The threading-depth lift (2 → 5) is purely an app-level change
in the comments POST handler — the column itself already
accepts arbitrary nesting, no migration needed.

Emoji validation is intentionally app-level (the bell-emoji
"❤️" is U+2764 U+FE0F — two codepoints — and a literal-string
SQL `CHECK` constraint risks Unicode-normalisation drift across
SQLite + PostgreSQL).  Routes validate against a canonical
Python tuple before INSERT.

Revision ID: 0069
Revises: 0068
Create Date: 2026-05-13 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend comments + add two reaction tables."""
    with op.batch_alter_table("data_product_comments") as batch:
        batch.add_column(
            sa.Column(
                "category",
                sa.String(length=20),
                nullable=False,
                server_default="general",
            )
        )
        batch.add_column(
            sa.Column(
                "is_accepted_answer",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.create_check_constraint(
            "ck_dp_comment_category",
            "category IN ('general','question','announcement','idea')",
        )

    op.create_table(
        "data_product_comment_reactions",
        sa.Column(
            "comment_id",
            sa.Integer(),
            sa.ForeignKey("data_product_comments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("emoji", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "comment_id",
            "user_id",
            "emoji",
            name="pk_dp_comment_reactions",
        ),
    )
    op.create_index(
        "ix_dp_comment_reactions_comment",
        "data_product_comment_reactions",
        ["comment_id"],
    )

    op.create_table(
        "data_product_reactions",
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("emoji", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "data_product_id",
            "user_id",
            "emoji",
            name="pk_dp_reactions",
        ),
    )
    op.create_index(
        "ix_dp_reactions_dp",
        "data_product_reactions",
        ["data_product_id"],
    )


def downgrade() -> None:
    """Drop reactions tables + comment columns."""
    op.drop_index("ix_dp_reactions_dp", table_name="data_product_reactions")
    op.drop_table("data_product_reactions")
    op.drop_index(
        "ix_dp_comment_reactions_comment",
        table_name="data_product_comment_reactions",
    )
    op.drop_table("data_product_comment_reactions")

    with op.batch_alter_table("data_product_comments") as batch:
        batch.drop_constraint("ck_dp_comment_category", type_="check")
        batch.drop_column("is_accepted_answer")
        batch.drop_column("category")
