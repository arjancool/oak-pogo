"""costume form: the Game Master marks the form as a costume

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-28

PGSharp does not always fill the costume field, for example for a Pikachu with an event hat.
The Game Master marks such forms with isCostume. This derived column keeps that fact, so the
costume protection and the keep points also apply to them. Existing rows are filled when the
derived columns are recomputed at startup (DERIVE_REVISION 3).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pokemon", schema=None) as batch_op:
        batch_op.add_column(sa.Column("costume_form", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pokemon", schema=None) as batch_op:
        batch_op.drop_column("costume_form")
