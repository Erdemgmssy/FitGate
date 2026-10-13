"""Separate member access devices from personnel attendance devices."""
from alembic import op
import sqlalchemy as sa

revision = '0006_device_purpose'
down_revision = '0005_personnel'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gym_device', sa.Column('purpose', sa.String(20), nullable=False, server_default='access'))
    op.alter_column('gym_device', 'purpose', server_default=None)


def downgrade():
    op.drop_column('gym_device', 'purpose')
