"""add has_word_lyrics to track

Revision ID: a7f3c9e21b04
Revises: fe60847783ad
Create Date: 2026-10-13 12:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7f3c9e21b04'
down_revision: str | None = 'fe60847783ad'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('track', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('has_word_lyrics', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('track', schema=None) as batch_op:
        batch_op.drop_column('has_word_lyrics')
