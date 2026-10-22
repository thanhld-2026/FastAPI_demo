"""users login by email, keep comments of deleted users

Theo đặc tả phụ lục: bảng users không có username, đăng nhập bằng email; full_name là tên hiển
thị nên bắt buộc (user cũ chưa có full_name -> lấy username làm tên). Xóa user thì comment vẫn
giữ (author_id -> NULL) thay vì bị xóa theo.

Revision ID: 50f3714e5988
Revises: ab1e40a471cc
Create Date: 2026-10-22 09:37:33.096993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50f3714e5988'
down_revision: Union[str, Sequence[str], None] = 'ab1e40a471cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE users SET full_name = username WHERE full_name IS NULL OR full_name = ''")
    op.alter_column('users', 'full_name', existing_type=sa.String(length=100), nullable=False)
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'username')

    op.alter_column('comments', 'author_id', existing_type=sa.Integer(), nullable=True)
    op.drop_constraint(op.f('fk_comments_author_id_users'), 'comments', type_='foreignkey')
    op.create_foreign_key(
        op.f('fk_comments_author_id_users'), 'comments', 'users', ['author_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema: username lấy lại từ phần trước @ của email (+ id để không trùng);
    comment đã mất tác giả (author_id NULL) bị xóa vì cột lại thành NOT NULL."""
    op.drop_constraint(op.f('fk_comments_author_id_users'), 'comments', type_='foreignkey')
    op.execute("DELETE FROM comments WHERE author_id IS NULL")
    op.alter_column('comments', 'author_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        op.f('fk_comments_author_id_users'), 'comments', 'users', ['author_id'], ['id'],
        ondelete='CASCADE',
    )

    op.add_column('users', sa.Column('username', sa.String(length=50), nullable=True))
    op.execute(
        "UPDATE users SET username = left(split_part(email, '@', 1), 40) || '_' || id"
    )
    op.alter_column('users', 'username', existing_type=sa.String(length=50), nullable=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.alter_column('users', 'full_name', existing_type=sa.String(length=100), nullable=True)
