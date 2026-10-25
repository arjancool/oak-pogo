"""pokemon in gym: whether a Pokémon defends a gym right now

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25

ADR-0026. Only the fact is kept, never which gym or where it is. Existing rows start as
unknown and are filled by the next import.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pokemon", schema=None) as batch_op:
        batch_op.add_column(sa.Column("in_gym", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pokemon", schema=None) as batch_op:
        batch_op.drop_column("in_gym")
