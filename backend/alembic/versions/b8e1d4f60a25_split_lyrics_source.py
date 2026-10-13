"""split lyrics source: embedded vs sidecar file

Revision ID: b8e1d4f60a25
Revises: a7f3c9e21b04
Create Date: 2026-10-13 13:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8e1d4f60a25'
down_revision: str | None = 'a7f3c9e21b04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('track', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'has_embedded_lyrics', sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(
            sa.Column('has_lyrics_file', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('track', schema=None) as batch_op:
        batch_op.drop_column('has_lyrics_file')
        batch_op.drop_column('has_embedded_lyrics')
