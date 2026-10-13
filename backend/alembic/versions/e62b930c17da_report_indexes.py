"""Read-only report query indexes; no tables or business data changed."""
from alembic import op

revision='e62b930c17da'
down_revision='c97af583bc41'
branch_labels=None
depends_on=None

DATES=[('gym_member','created_at'),('gym_subscription','created_at'),('gym_invoice','created_at'),('gym_payment','at'),('gym_refund','at'),('gym_attempt','at'),('gym_grant','expires_at'),('gym_passage','occurred_at'),('gym_visit','entry'),('gym_shift','entry'),('gym_plannedshift','start'),('gym_classsession','at'),('gym_booking','at'),('gym_sale','at'),('gym_stockmovement','at'),('gym_deviceevent','at'),('gym_devicecommand','created_at'),('gym_audit','at')]
EXTRA=[('report_subscription_member_created','gym_subscription',['branch_id','member_id','created_at']),('report_audit_entity_action','gym_audit',['branch_id','entity_id','type','at']),('report_planned_employee_start','gym_plannedshift',['branch_id','employee_id','start'])]
def upgrade():
    for table,column in DATES:op.create_index(f'report_{table}_date',table,['branch_id',column])
    for name,table,columns in EXTRA:op.create_index(name,table,columns)
def downgrade():
    for name,table,columns in reversed(EXTRA):op.drop_index(name,table_name=table)
    for table,column in reversed(DATES):op.drop_index(f'report_{table}_date',table_name=table)
