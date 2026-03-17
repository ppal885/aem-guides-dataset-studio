"""Add saved_recipes table

Revision ID: add_saved_recipes
Revises: 
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_saved_recipes'
down_revision = None  # Update this with your latest revision
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'saved_recipes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('recipe_config', sa.JSON(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tags', sa.JSON(), nullable=True, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_saved_recipes_user_id', 'saved_recipes', ['user_id'])
    op.create_index('ix_saved_recipes_is_public', 'saved_recipes', ['is_public'])
    op.create_index('ix_saved_recipes_created_at', 'saved_recipes', ['created_at'])


def downgrade():
    op.drop_index('ix_saved_recipes_created_at', table_name='saved_recipes')
    op.drop_index('ix_saved_recipes_is_public', table_name='saved_recipes')
    op.drop_index('ix_saved_recipes_user_id', table_name='saved_recipes')
    op.drop_table('saved_recipes')
