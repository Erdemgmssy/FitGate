"""Keep returned RFID cards in stock without a current member assignment."""
from alembic import op
import sqlalchemy as sa

revision = '0007_reusable_cards'
down_revision = '0006_device_purpose'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('gym_card', 'member_id', existing_type=sa.Uuid(), nullable=True)
    op.create_check_constraint('card_available_without_member', 'gym_card', "(status = 'available') = (member_id IS NULL)")


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM gym_card WHERE member_id IS NULL')):
        raise RuntimeError('Returned cards exist. Reassign them before downgrade; no cards were deleted.')
    op.drop_constraint('card_available_without_member', 'gym_card', type_='check')
    op.alter_column('gym_card', 'member_id', existing_type=sa.Uuid(), nullable=False)
