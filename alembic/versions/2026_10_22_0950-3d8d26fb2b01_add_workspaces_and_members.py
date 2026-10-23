"""add workspaces and members

Viết tay phần lớn (autogenerate sẽ DROP cột owner_id rồi ADD cột creator_id -> mất dữ liệu,
và thêm cột NOT NULL vào bảng đã có dữ liệu -> lỗi). Các bước:
1. Tạo bảng workspaces, workspace_members.
2. Đổi tên projects.owner_id -> creator_id (giữ dữ liệu, đổi luôn tên index / FK cho khớp
   naming convention).
3. Chuyển dữ liệu cũ: mỗi người đã tạo project có 1 workspace (là OWNER), project của họ
   vào workspace đó; ai đã tham gia project (tạo task, được assign, comment) thành EDITOR,
   ai chỉ bookmark task thành VIEWER -> không ai mất quyền truy cập dữ liệu cũ.
4. projects.workspace_id thành NOT NULL + FK.

Revision ID: 3d8d26fb2b01
Revises: 6e7c27a183ff
Create Date: 2026-10-22 09:50:12.418532

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d8d26fb2b01'
down_revision: Union[str, Sequence[str], None] = '6e7c27a183ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('workspaces',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_workspaces_owner_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_workspaces'))
    )
    op.create_index(op.f('ix_workspaces_owner_id'), 'workspaces', ['owner_id'], unique=False)
    op.create_table('workspace_members',
    sa.Column('workspace_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.Enum('OWNER', 'EDITOR', 'VIEWER', name='workspacerole', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_workspace_members_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_workspace_members_workspace_id_workspaces'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('workspace_id', 'user_id', name=op.f('pk_workspace_members'))
    )
    op.create_index(op.f('ix_workspace_members_user_id'), 'workspace_members', ['user_id'], unique=False)
    # Mỗi workspace tối đa 1 dòng OWNER (partial unique index, chỉ áp cho dòng role = 'OWNER')
    op.create_index('uq_workspace_members_one_owner', 'workspace_members', ['workspace_id'], unique=True, postgresql_where=sa.text("role = 'OWNER'"))

    # 2. owner_id -> creator_id: đổi tên, không drop / add (giữ dữ liệu)
    op.alter_column('projects', 'owner_id', new_column_name='creator_id')
    op.execute('ALTER INDEX ix_projects_owner_id RENAME TO ix_projects_creator_id')
    op.execute(
        'ALTER TABLE projects RENAME CONSTRAINT fk_projects_owner_id_users '
        'TO fk_projects_creator_id_users'
    )

    # 3. Chuyển dữ liệu cũ sang workspace
    op.add_column('projects', sa.Column('workspace_id', sa.Integer(), nullable=True))
    op.execute("""
        INSERT INTO workspaces (name, owner_id)
        SELECT 'Workspace of ' || u.full_name, u.id
        FROM users u
        WHERE u.id IN (SELECT DISTINCT creator_id FROM projects)
        ORDER BY u.id
    """)
    op.execute("""
        UPDATE projects p SET workspace_id = w.id
        FROM workspaces w
        WHERE w.owner_id = p.creator_id
    """)
    op.execute("""
        INSERT INTO workspace_members (workspace_id, user_id, role)
        SELECT id, owner_id, 'OWNER' FROM workspaces
    """)
    op.execute("""
        INSERT INTO workspace_members (workspace_id, user_id, role)
        SELECT DISTINCT p.workspace_id, x.user_id, 'EDITOR'
        FROM (
            SELECT project_id, creator_id AS user_id FROM tasks
            UNION SELECT project_id, assignee_id FROM tasks WHERE assignee_id IS NOT NULL
            UNION SELECT t.project_id, c.author_id FROM comments c JOIN tasks t ON t.id = c.task_id
            WHERE c.author_id IS NOT NULL
        ) x
        JOIN projects p ON p.id = x.project_id
        WHERE NOT EXISTS (
            SELECT 1 FROM workspace_members m
            WHERE m.workspace_id = p.workspace_id AND m.user_id = x.user_id
        )
    """)

    op.execute("""
        INSERT INTO workspace_members (workspace_id, user_id, role)
        SELECT DISTINCT p.workspace_id, b.user_id, 'VIEWER'
        FROM task_bookmarks b
        JOIN tasks t ON t.id = b.task_id
        JOIN projects p ON p.id = t.project_id
        WHERE NOT EXISTS (
            SELECT 1 FROM workspace_members m
            WHERE m.workspace_id = p.workspace_id AND m.user_id = b.user_id
        )
    """)

    # 4. Mọi project đã có workspace -> NOT NULL + FK + index
    op.alter_column('projects', 'workspace_id', nullable=False)
    op.create_index(op.f('ix_projects_workspace_id'), 'projects', ['workspace_id'], unique=False)
    op.create_foreign_key(op.f('fk_projects_workspace_id_workspaces'), 'projects', 'workspaces', ['workspace_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    """Downgrade schema (mất thông tin workspace / role, project giữ nguyên người tạo)."""
    op.drop_constraint(op.f('fk_projects_workspace_id_workspaces'), 'projects', type_='foreignkey')
    op.drop_index(op.f('ix_projects_workspace_id'), table_name='projects')
    op.drop_column('projects', 'workspace_id')
    op.execute(
        'ALTER TABLE projects RENAME CONSTRAINT fk_projects_creator_id_users '
        'TO fk_projects_owner_id_users'
    )
    op.execute('ALTER INDEX ix_projects_creator_id RENAME TO ix_projects_owner_id')
    op.alter_column('projects', 'creator_id', new_column_name='owner_id')
    op.drop_index('uq_workspace_members_one_owner', table_name='workspace_members')
    op.drop_index(op.f('ix_workspace_members_user_id'), table_name='workspace_members')
    op.drop_table('workspace_members')
    op.drop_index(op.f('ix_workspaces_owner_id'), table_name='workspaces')
    op.drop_table('workspaces')
