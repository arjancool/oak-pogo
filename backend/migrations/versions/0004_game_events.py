"""game events: the event calendar and events users add themselves

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25

ADR-0021. Feed events come from LeekDuck.com via ScrapedDuck and belong to the installation.
Events a user adds belong to one trainer account.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=False),
        sa.Column("trainer_account_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("local_time", sa.Boolean(), nullable=False),
        sa.Column("link", sa.String(length=300), nullable=True),
        sa.Column("featured", sa.Text(), nullable=False),
        sa.Column("featured_dex", sa.Text(), nullable=False),
        sa.Column("bonuses", sa.Text(), nullable=False),
        sa.Column("feed_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["trainer_account_id"], ["trainer_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("game_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_game_events_trainer_account_id"), ["trainer_account_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_game_events_ends_at"), ["ends_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("game_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_game_events_ends_at"))
        batch_op.drop_index(batch_op.f("ix_game_events_trainer_account_id"))
    op.drop_table("game_events")
