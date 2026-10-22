"""index refresh_tokens replaced_by_id

Revision ID: ab1e40a471cc
Revises: f191f4c9226b
Create Date: 2026-10-22 09:36:31.627229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab1e40a471cc'
down_revision: Union[str, Sequence[str], None] = 'f191f4c9226b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # FK tự tham chiếu ON DELETE SET NULL: xóa 1 token thì DB phải tìm các dòng trỏ tới nó
    op.create_index(
        op.f('ix_refresh_tokens_replaced_by_id'), 'refresh_tokens', ['replaced_by_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_refresh_tokens_replaced_by_id'), table_name='refresh_tokens')
