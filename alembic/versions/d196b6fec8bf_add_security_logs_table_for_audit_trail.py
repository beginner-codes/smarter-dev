"""Add security_logs table for audit trail

Revision ID: d196b6fec8bf
Revises: ba7d71351c54
Create Date: 2025-07-28 15:46:20.045003

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd196b6fec8bf'
down_revision = 'ba7d71351c54'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('security_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('api_key_id', sa.UUID(), nullable=True),
    sa.Column('user_identifier', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('request_id', sa.String(length=100), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('details', sa.Text(), nullable=False),
    sa.Column('event_metadata', sa.JSON(), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], name=op.f('fk_security_logs_api_key_id_api_keys'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_security_logs'))
    )
    with op.batch_alter_table('security_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_security_logs_action'), ['action'], unique=False)
        batch_op.create_index('ix_security_logs_action_timestamp', ['action', 'timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_logs_api_key_id'), ['api_key_id'], unique=False)
        batch_op.create_index('ix_security_logs_api_key_timestamp', ['api_key_id', 'timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_logs_ip_address'), ['ip_address'], unique=False)
        batch_op.create_index('ix_security_logs_ip_timestamp', ['ip_address', 'timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_logs_request_id'), ['request_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_logs_success'), ['success'], unique=False)
        batch_op.create_index('ix_security_logs_success_timestamp', ['success', 'timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_logs_timestamp'), ['timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_security_logs_user_identifier'), ['user_identifier'], unique=False)
        batch_op.create_index('ix_security_logs_user_timestamp', ['user_identifier', 'timestamp'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('security_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_security_logs_user_timestamp')
        batch_op.drop_index(batch_op.f('ix_security_logs_user_identifier'))
        batch_op.drop_index(batch_op.f('ix_security_logs_timestamp'))
        batch_op.drop_index('ix_security_logs_success_timestamp')
        batch_op.drop_index(batch_op.f('ix_security_logs_success'))
        batch_op.drop_index(batch_op.f('ix_security_logs_request_id'))
        batch_op.drop_index('ix_security_logs_ip_timestamp')
        batch_op.drop_index(batch_op.f('ix_security_logs_ip_address'))
        batch_op.drop_index('ix_security_logs_api_key_timestamp')
        batch_op.drop_index(batch_op.f('ix_security_logs_api_key_id'))
        batch_op.drop_index('ix_security_logs_action_timestamp')
        batch_op.drop_index(batch_op.f('ix_security_logs_action'))

    op.drop_table('security_logs')
    # ### end Alembic commands ###