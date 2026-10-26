"""message data: the values in stored import and Game Data messages

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-26

ADR-0025. OAK stores messages about imports and Game Data versions in Dutch. With the code it
now also keeps the values that go into the message, so the interface can build the message in
the chosen language. Existing rows keep only their Dutch text, which stays the fallback.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

COLUMNS = (
    ("import_errors", "data"),
    ("import_jobs", "error_data"),
    ("game_data_versions", "errors"),
)


def upgrade() -> None:
    for table, column in COLUMNS:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column(column, sa.Text(), nullable=True))


def downgrade() -> None:
    for table, column in COLUMNS:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column(column)
