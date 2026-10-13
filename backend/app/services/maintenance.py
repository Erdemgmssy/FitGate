"""Explicit, opt-in maintenance operations. Never invoked on server startup."""
from app import models as m
from app.db import transaction
from app.db.session import get_session


@transaction.atomic
def reset_members(branch_id, database, confirm=False):
    if database != get_session().bind.url.database:
        raise ValueError('Database name does not match; nothing deleted')
    branch = m.Branch.objects.select_for_update().get(pk=branch_id)
    count = m.Member.objects.filter(branch=branch).count()
    if not confirm:
        return {'dryRun':True,'members':count}
    members = m.Member.objects.filter(branch=branch).values_list('id',flat=True)
    for sale in m.Sale.objects.filter(member_id__in=members,returned=False):
        sale.product.stock += sale.quantity-sale.returned_quantity
        sale.product.save()
        m.StockMovement.objects.create(branch=branch,product=sale.product,quantity=sale.quantity-sale.returned_quantity,reason='Test members reset: member sale removed')
    for model, filters in [
        (m.StockMovement, {'sale__member_id__in':members}),
        (m.Sale, {'member_id__in':members}),
        (m.Visit, {'branch':branch}),
        (m.Passage, {'branch':branch}),
        (m.Grant, {'branch':branch}),
        (m.Attempt, {'branch':branch}),
        (m.CardCapture, {'member_id__in':members}),
        (m.Card, {'member_id__in':members}),
        (m.Refund, {'payment__invoice__member_id__in':members}),
        (m.Payment, {'invoice__member_id__in':members}),
        (m.Installment, {'invoice__member_id__in':members}),
        (m.Invoice, {'member_id__in':members}),
        (m.Booking, {'member_id__in':members}),
        (m.Freeze, {'subscription__member_id__in':members}),
        (m.Subscription, {'member_id__in':members}),
        (m.Member, {'id__in':members}),
    ]:
        model.objects.filter(**filters).delete()
    m.DeviceEvent.objects.filter(branch=branch).delete()
    branch.member_counter=0
    branch.save()
    m.Audit.objects.create(branch=branch,type='resetMembers',detail={'membersDeleted':count})
    return {'dryRun':False,'members':count}
