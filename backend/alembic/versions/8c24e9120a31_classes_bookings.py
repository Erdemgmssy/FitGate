"""Extend existing lessons, bookings, invoices and notices without deleting history."""
from alembic import op
import sqlalchemy as sa

revision='8c24e9120a31'
down_revision='61237db607fd'
branch_labels=None
depends_on=None

def upgrade():
    def add(table,name,type_,default=None,nullable=False):
        op.add_column(table,sa.Column(name,type_,nullable=nullable,server_default=sa.text(default) if default is not None else None))
        if default is not None: op.alter_column(table,name,server_default=None)
    add('gym_plan','lesson_types',sa.JSON(),"'[\"group\"]'::json")
    add('gym_plan','lesson_sessions',sa.Integer(),nullable=True)
    # Existing sale contracts keep their original group-class eligibility.
    op.execute("UPDATE gym_subscription SET rules=(rules::jsonb || jsonb_build_object('lessonTypes',jsonb_build_array('group'),'lessonSessions',NULL))::json WHERE NOT rules::jsonb ? 'lessonTypes'")
    for name,type_,default,nullable in [
        ('trainer_id',sa.Uuid(),None,True),('description',sa.String(600),"''",False),
        ('kind',sa.String(12),"'group'",False),('series_id',sa.Uuid(),None,True),
        ('outcome',sa.String(12),"''",False),('booking_minutes',sa.Integer(),'0',False),
        ('cancel_minutes',sa.Integer(),'120',False),('require_membership',sa.Boolean(),'true',False),
        ('require_lesson',sa.Boolean(),'false',False),('late_cancel_consumes',sa.Boolean(),'true',False),
        ('no_show_consumes',sa.Boolean(),'true',False),('price_cents',sa.BigInteger(),'0',False)]:
        add('gym_classsession',name,type_,default,nullable)
    op.create_foreign_key('class_trainer_employee','gym_classsession','gym_employee',['trainer_id'],['id'],ondelete='RESTRICT')
    op.create_index('ix_gym_classsession_series_id','gym_classsession',['series_id'])
    op.execute("UPDATE gym_classsession c SET trainer_id=e.id FROM gym_employee e WHERE c.branch_id=e.branch_id AND c.trainer=e.name AND (SELECT count(*) FROM gym_employee x WHERE x.branch_id=e.branch_id AND x.name=e.name)=1")
    for name,type_,default,nullable in [('subscription_id',sa.Uuid(),None,True),('terms',sa.JSON(),"'{}'::json",False),('right_state',sa.String(12),"'none'",False),('reason',sa.String(1500),"''",False),('actor_id',sa.BigInteger(),None,True),('updated_at',sa.DateTime(timezone=True),None,True)]:
        add('gym_booking',name,type_,default,nullable)
    op.create_foreign_key('booking_subscription','gym_booking','gym_subscription',['subscription_id'],['id'],ondelete='RESTRICT')
    op.create_foreign_key('booking_actor','gym_booking','gym_user',['actor_id'],['id'],ondelete='RESTRICT')
    op.drop_index('one_active_class_booking',table_name='gym_booking')
    op.create_index('one_active_class_booking','gym_booking',['class_session_id','member_id'],unique=True,postgresql_where=sa.text("status IN ('booked','waiting','attended','late','absent')"))
    op.alter_column('gym_invoice','subscription_id',existing_type=sa.Uuid(),nullable=True)
    add('gym_invoice','booking_id',sa.Uuid(),nullable=True)
    add('gym_invoice','description',sa.String(240),"''")
    op.create_foreign_key('invoice_booking','gym_invoice','gym_booking',['booking_id'],['id'],ondelete='RESTRICT')
    op.create_unique_constraint('invoice_booking_unique','gym_invoice',['booking_id'])
    op.create_check_constraint('invoice_one_origin','gym_invoice','(subscription_id IS NOT NULL) <> (booking_id IS NOT NULL)')
    add('gym_notice','event_key',sa.String(150),nullable=True)
    op.create_unique_constraint('notice_event_unique','gym_notice',['event_key'])
    op.create_check_constraint('plan_lesson_nonnegative','gym_plan','lesson_sessions >= 0')
    op.create_check_constraint('class_price_nonnegative','gym_classsession','price_cents >= 0')

def downgrade():
    raise RuntimeError('Lesson contracts and financial history must be preserved. Restore a verified backup instead.')
