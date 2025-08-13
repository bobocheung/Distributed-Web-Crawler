"""add article.categories multi-tag field

Revision ID: aa0000000001
Revises: 9a350880ec3f
Create Date: 2025-08-13
"""

from alembic import op
import sqlalchemy as sa

revision = 'aa0000000001'
down_revision = '9a350880ec3f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('categories', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('articles', 'categories')

