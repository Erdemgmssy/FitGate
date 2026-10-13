"""Preserve nonnegative constraints from the original positive integer fields."""
from alembic import op

revision = '0002_nonnegative'
down_revision = '0001_fastapi'
branch_labels = None
depends_on = None

def upgrade():
    op.create_check_constraint('gym_branch_capacity_nonnegative', 'gym_branch', 'capacity >= 0')
    op.create_check_constraint('gym_branch_member_counter_nonnegative', 'gym_branch', 'member_counter >= 0')
    op.create_check_constraint('gym_branch_invoice_counter_nonnegative', 'gym_branch', 'invoice_counter >= 0')
    op.create_check_constraint('gym_branch_payment_counter_nonnegative', 'gym_branch', 'payment_counter >= 0')
    op.create_check_constraint('gym_plan_duration_value_nonnegative', 'gym_plan', 'duration_value >= 0')
    op.create_check_constraint('gym_plan_days_nonnegative', 'gym_plan', 'days >= 0')
    op.create_check_constraint('gym_plan_sessions_nonnegative', 'gym_plan', 'sessions >= 0')
    op.create_check_constraint('gym_plan_freeze_days_nonnegative', 'gym_plan', 'freeze_days >= 0')
    op.create_check_constraint('gym_subscription_remaining_nonnegative', 'gym_subscription', 'remaining >= 0')
    op.create_check_constraint('gym_subscription_frozen_days_nonnegative', 'gym_subscription', 'frozen_days >= 0')
    op.create_check_constraint('gym_classsession_duration_nonnegative', 'gym_classsession', 'duration >= 0')
    op.create_check_constraint('gym_classsession_capacity_nonnegative', 'gym_classsession', 'capacity >= 0')
    op.create_check_constraint('gym_product_stock_nonnegative', 'gym_product', 'stock >= 0')
    op.create_check_constraint('gym_product_minimum_nonnegative', 'gym_product', 'minimum >= 0')
    op.create_check_constraint('gym_sale_quantity_nonnegative', 'gym_sale', 'quantity >= 0')
    op.create_check_constraint('gym_loginattempt_failures_nonnegative', 'gym_loginattempt', 'failures >= 0')

def downgrade():
    op.drop_constraint('gym_loginattempt_failures_nonnegative', 'gym_loginattempt', type_='check')
    op.drop_constraint('gym_sale_quantity_nonnegative', 'gym_sale', type_='check')
    op.drop_constraint('gym_product_minimum_nonnegative', 'gym_product', type_='check')
    op.drop_constraint('gym_product_stock_nonnegative', 'gym_product', type_='check')
    op.drop_constraint('gym_classsession_capacity_nonnegative', 'gym_classsession', type_='check')
    op.drop_constraint('gym_classsession_duration_nonnegative', 'gym_classsession', type_='check')
    op.drop_constraint('gym_subscription_frozen_days_nonnegative', 'gym_subscription', type_='check')
    op.drop_constraint('gym_subscription_remaining_nonnegative', 'gym_subscription', type_='check')
    op.drop_constraint('gym_plan_freeze_days_nonnegative', 'gym_plan', type_='check')
    op.drop_constraint('gym_plan_sessions_nonnegative', 'gym_plan', type_='check')
    op.drop_constraint('gym_plan_days_nonnegative', 'gym_plan', type_='check')
    op.drop_constraint('gym_plan_duration_value_nonnegative', 'gym_plan', type_='check')
    op.drop_constraint('gym_branch_payment_counter_nonnegative', 'gym_branch', type_='check')
    op.drop_constraint('gym_branch_invoice_counter_nonnegative', 'gym_branch', type_='check')
    op.drop_constraint('gym_branch_member_counter_nonnegative', 'gym_branch', type_='check')
    op.drop_constraint('gym_branch_capacity_nonnegative', 'gym_branch', type_='check')
