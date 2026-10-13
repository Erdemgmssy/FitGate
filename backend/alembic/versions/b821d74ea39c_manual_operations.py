"""Manual visit provenance on the existing visit ledger."""
from alembic import op
import sqlalchemy as sa

revision = 'b821d74ea39c'
down_revision = 'a710e63d928b'
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column('gym_visit', 'device_id', existing_type=sa.Uuid(), nullable=True)
    for name, table, typ in [('subscription_id', 'gym_subscription', sa.Uuid()),
                             ('entry_actor_id', 'gym_user', sa.BigInteger()),
                             ('exit_actor_id', 'gym_user', sa.BigInteger())]:
        op.add_column('gym_visit', sa.Column(name, typ, nullable=True))
        op.create_foreign_key('fk_visit_'+name, 'gym_visit', table, [name], ['id'], ondelete='RESTRICT')
    for name, typ in [('exit_method', sa.String(30)), ('entry_reason', sa.Text()), ('exit_reason', sa.Text())]:
        op.add_column('gym_visit', sa.Column(name, typ, nullable=False, server_default=''))

def downgrade():
    # Restoring NOT NULL would discard cardless history; refuse a lossy downgrade.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM gym_visit WHERE device_id IS NULL OR subscription_id IS NOT NULL OR entry_actor_id IS NOT NULL OR exit_actor_id IS NOT NULL OR exit_method != '')")).scalar():
        raise RuntimeError('Visit provenance exists; downgrade requires an explicit archival plan.')
    for name in ['exit_reason', 'entry_reason', 'exit_method']:
        op.drop_column('gym_visit', name)
    for name in ['exit_actor_id', 'entry_actor_id', 'subscription_id']:
        op.drop_constraint('fk_visit_'+name, 'gym_visit', type_='foreignkey')
        op.drop_column('gym_visit', name)
    op.alter_column('gym_visit', 'device_id', existing_type=sa.Uuid(), nullable=False)
