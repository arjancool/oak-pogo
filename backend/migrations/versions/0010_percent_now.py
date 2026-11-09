"""pvp rankings: how strong a Pokémon is as it is now

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-09

percent_now is the stat product on the current level as a percentage of the best in the league.
The Team Builder picks the strongest team as the Pokémon are now with it, also in the Master
League, where hardly anyone is at 95 percent of level 40. It is a projection: the analysis that
runs at startup for the new engine version fills it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pvp_rankings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("percent_now", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pvp_rankings", schema=None) as batch_op:
        batch_op.drop_column("percent_now")
