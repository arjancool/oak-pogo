"""cleanup scores: battle score and keep score per Pokémon (ADR-0019)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23

The cleanup recommendations are a projection. Existing rows get empty scores here; the
application recomputes every analysis at startup because the engine version changed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cleanup_recommendations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("battle_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("keep_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("scores", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("cleanup_recommendations", schema=None) as batch_op:
        batch_op.drop_column("scores")
        batch_op.drop_column("keep_score")
        batch_op.drop_column("battle_score")
