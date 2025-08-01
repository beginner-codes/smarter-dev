"""Add welcome_message to Squad model

Revision ID: 0909774e3297
Revises: 1823b62b9ffc
Create Date: 2025-07-27 12:10:11.915554

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0909774e3297'
down_revision = '1823b62b9ffc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('squads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('welcome_message', sa.String(length=500), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('squads', schema=None) as batch_op:
        batch_op.drop_column('welcome_message')

    # ### end Alembic commands ###