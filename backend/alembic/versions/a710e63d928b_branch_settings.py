"""Branch-scoped settings on the existing branch record."""
from alembic import op
import sqlalchemy as sa
revision='a710e63d928b'
down_revision='f48b6a10cd23'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('gym_branch',sa.Column('configuration',sa.JSON(),nullable=False,server_default=sa.text("'{}'")))
    op.alter_column('gym_branch','configuration',server_default=None)

def downgrade():op.drop_column('gym_branch','configuration')
