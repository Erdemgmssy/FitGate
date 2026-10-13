"""Snapshot session entitlements and support dated freezes; do not alter financial records."""
from alembic import op
import sqlalchemy as sa

revision='0004_membership_history'
down_revision='0003_member_contact'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('gym_subscription',sa.Column('total_sessions',sa.Integer(),nullable=True))
    op.add_column('gym_freeze',sa.Column('planned_end',sa.Date(),nullable=True))
    op.execute("""UPDATE gym_subscription s SET total_sessions = GREATEST(remaining,
        CASE WHEN rules->>'sessions' ~ '^[0-9]+$' THEN (rules->>'sessions')::integer
        ELSE remaining + (SELECT COUNT(*) FROM gym_grant g WHERE g.subscription_id=s.id AND g.confirmed AND g.direction='entry') END)
        WHERE remaining IS NOT NULL""")
    op.create_check_constraint('subscription_total_sessions_nonnegative','gym_subscription','total_sessions >= 0')
    op.create_check_constraint('subscription_session_bounds','gym_subscription','remaining <= total_sessions')
    op.create_check_constraint('freeze_planned_date_order','gym_freeze','planned_end >= start')

def downgrade():
    op.drop_constraint('freeze_planned_date_order','gym_freeze',type_='check')
    op.drop_constraint('subscription_session_bounds','gym_subscription',type_='check')
    op.drop_constraint('subscription_total_sessions_nonnegative','gym_subscription',type_='check')
    op.drop_column('gym_freeze','planned_end')
    op.drop_column('gym_subscription','total_sessions')
