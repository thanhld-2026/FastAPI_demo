"""replace global tags with project labels

Tag dùng chung toàn hệ thống -> label riêng của từng project (phụ lục feature 6).
Viết tay: autogenerate chỉ DROP tags / task_tags (mất dữ liệu) và còn sai thứ tự (drop tags
trước task_tags đang có FK trỏ tới tags -> PostgreSQL báo lỗi). Dữ liệu cũ được chuyển:
mỗi (project, tag) đang được task trong project dùng -> 1 label của project đó, giữ nguyên
việc gắn nhãn của từng task.

Revision ID: 521095b09985
Revises: 3d8d26fb2b01
Create Date: 2026-10-22 10:00:53.204117

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '521095b09985'
down_revision: Union[str, Sequence[str], None] = '3d8d26fb2b01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_COLOR = "#6b7280"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('labels',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=30), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_labels_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_labels')),
    sa.UniqueConstraint('project_id', 'name', name='uq_labels_project_id_name')
    )
    op.create_table('task_labels',
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('label_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['label_id'], ['labels.id'], name=op.f('fk_task_labels_label_id_labels'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_task_labels_task_id_tasks'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('task_id', 'label_id', name=op.f('pk_task_labels'))
    )
    op.create_index(op.f('ix_task_labels_label_id'), 'task_labels', ['label_id'], unique=False)

    # Chuyển dữ liệu: (project, tag) đang được dùng -> label của project
    op.execute(f"""
        INSERT INTO labels (project_id, name, color)
        SELECT DISTINCT t.project_id, g.name, '{DEFAULT_COLOR}'
        FROM task_tags tt
        JOIN tasks t ON t.id = tt.task_id
        JOIN tags g ON g.id = tt.tag_id
    """)
    op.execute("""
        INSERT INTO task_labels (task_id, label_id)
        SELECT tt.task_id, l.id
        FROM task_tags tt
        JOIN tasks t ON t.id = tt.task_id
        JOIN tags g ON g.id = tt.tag_id
        JOIN labels l ON l.project_id = t.project_id AND l.name = g.name
    """)

    # Bảng con (có FK) phải drop trước bảng cha
    op.drop_index(op.f('ix_task_tags_tag_id'), table_name='task_tags')
    op.drop_table('task_tags')
    op.drop_index(op.f('ix_tags_name'), table_name='tags')
    op.drop_table('tags')


def downgrade() -> None:
    """Downgrade schema: label (gộp theo tên) -> tag dùng chung; màu label bị bỏ."""
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=30), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tags'))
    )
    op.create_index(op.f('ix_tags_name'), 'tags', ['name'], unique=True)
    op.create_table('task_tags',
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], name=op.f('fk_task_tags_tag_id_tags'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('fk_task_tags_task_id_tasks'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('task_id', 'tag_id', name=op.f('pk_task_tags'))
    )
    op.create_index(op.f('ix_task_tags_tag_id'), 'task_tags', ['tag_id'], unique=False)
    op.execute("INSERT INTO tags (name) SELECT DISTINCT name FROM labels")
    op.execute("""
        INSERT INTO task_tags (task_id, tag_id)
        SELECT DISTINCT tl.task_id, g.id
        FROM task_labels tl
        JOIN labels l ON l.id = tl.label_id
        JOIN tags g ON g.name = l.name
    """)
    op.drop_index(op.f('ix_task_labels_label_id'), table_name='task_labels')
    op.drop_table('task_labels')
    op.drop_table('labels')
