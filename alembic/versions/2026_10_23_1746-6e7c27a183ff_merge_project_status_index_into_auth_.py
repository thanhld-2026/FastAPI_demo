"""merge project status index into auth branch

Migration "merge" (không có thao tác nào): PR #4 thêm f475f70535b5 sau khi PR #5 đã có chuỗi
f191f4c9226b -> ab1e40a471cc -> 50f3714e5988 cùng xuất phát từ fe3d8d9fbe4a -> lịch sử tách thành 2
nhánh (2 head). Migration này nối 2 head lại để `alembic upgrade head` có đúng 1 đích. Không sửa
`down_revision` của các migration đã public.

Revision ID: 6e7c27a183ff
Revises: 50f3714e5988, f475f70535b5
Create Date: 2026-10-23 17:46:12.714570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e7c27a183ff'
down_revision: Union[str, Sequence[str], None] = ('50f3714e5988', 'f475f70535b5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
