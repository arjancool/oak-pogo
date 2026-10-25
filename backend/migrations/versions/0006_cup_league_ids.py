"""cup league ids: room for PvP cup IDs in league columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-26

ADR-0027. A cup is stored like a league, under an ID such as ``fantasy-1500``. The longest
ones PvPoke uses today, such as ``battlefrontiermaster-10000``, do not fit in 16 characters.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TABLES = ("pvp_rankings", "battle_teams")


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column("league", existing_type=sa.String(length=16), type_=sa.String(length=48))


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column("league", existing_type=sa.String(length=48), type_=sa.String(length=16))
