"""
add saved_articles

Revision ID: 9a350880ec3f
Revises: fdfe1c760f72
Create Date: 2025-08-13 04:55:13.672009
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a350880ec3f'
down_revision = 'fdfe1c760f72'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'saved_articles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('article_id', sa.Integer(), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'article_id', name='uq_saved_user_article'),
    )


def downgrade() -> None:
    op.drop_table('saved_articles')

