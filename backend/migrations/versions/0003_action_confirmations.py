"""action confirmations: the protections the user confirmed per Pokémon on an action list

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23

Audit A03. OAK checks protection again whenever an action list is read, exported or completed,
and compares it with what the user confirmed for that Pokémon. Existing rows start without
confirmations, so a favorite that is already on a list asks to be confirmed once more.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("planned_actions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("confirmed", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("planned_actions", schema=None) as batch_op:
        batch_op.drop_column("confirmed")
