"""Notification severity, routing and persistent lifecycle on the existing table."""
from alembic import op
import sqlalchemy as sa
revision='f48b6a10cd23'
down_revision='e62b930c17da'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('gym_notice',sa.Column('details',sa.JSON(),nullable=False,server_default=sa.text("'{}'")))
    op.alter_column('gym_notice','details',server_default=None)
def downgrade():op.drop_column('gym_notice','details')
