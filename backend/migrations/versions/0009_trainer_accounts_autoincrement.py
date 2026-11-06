"""trainer accounts: AUTOINCREMENT, so the ID of a deleted account is never used again

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-06

SQLite gives a new row the highest rowid plus one, so after the newest account is deleted its ID
comes back for the next account (issue #55). With AUTOINCREMENT that never happens.

Adding AUTOINCREMENT rebuilds the table. app/core/migrations.py runs every migration with foreign
keys off, so dropping the old table does not delete the Pokémon, imports and other rows of the
accounts, and checks every foreign key afterwards. The sequence starts at the highest ID that is
still there: an account deleted before this migration with an even higher ID is not known.
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trainer_accounts", recreate="always", table_kwargs={"sqlite_autoincrement": True}):
        pass


def downgrade() -> None:
    with op.batch_alter_table("trainer_accounts", recreate="always"):
        pass
