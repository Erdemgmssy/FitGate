"""Optional member date of birth and emergency contact phone; preserve existing records."""
from alembic import op
import sqlalchemy as sa

revision = '0003_member_contact'
down_revision = '0002_nonnegative'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('gym_member', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('gym_member', sa.Column('emergency_phone', sa.String(30), nullable=False, server_default=''))
    op.alter_column('gym_member', 'emergency_phone', server_default=None)

def downgrade():
    op.drop_column('gym_member', 'emergency_phone')
    op.drop_column('gym_member', 'birth_date')
