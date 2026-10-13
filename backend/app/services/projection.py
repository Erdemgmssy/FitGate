import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from app.core import time as timezone
from app import models as m
from .membership import status, remaining_days, freeze_records
from app.repositories.query import Q

# A single wire contract keeps the React UI independent of Django field names.
SPECS = {
 'members': (m.Member, {'number':'number','name':'name','phone':'phone','email':'email','birthDate':'birth_date','active':'active','blocked':'blocked','trainer':'trainer','emergency':'emergency','emergencyPhone':'emergency_phone','address':'address','note':'note','photo':'photo','consent':'consent','marketing':'marketing','createdAt':'created_at'}),
 'plans': (m.Plan, {'name':'name','days':'days','durationValue':'duration_value','durationUnit':'duration_unit','price':'price','active':'active','sessions':'sessions','from':'allowed_from','to':'allowed_to','weekdays':'weekdays','freezeDays':'freeze_days','description':'description','kind':'kind','revision':'revision','dailyLimit':'daily_limit','weeklyLimit':'weekly_limit','freezeMin':'freeze_min','freezeMax':'freeze_max','freezeLimit':'freeze_limit','saleStart':'sale_start','saleEnd':'sale_end','campaigns':'campaigns'}),
 'subscriptions': (m.Subscription, {'memberId':'member_id','planId':'plan_id','planName':'plan_name','start':'start','end':'end','status':'status','priceCents':'price_cents','remaining':'remaining','totalSessions':'total_sessions','rules':'rules','frozenAt':'frozen_at','frozenDays':'frozen_days','createdAt':'created_at'}),
 'freezes': (m.Freeze, {'subscriptionId':'subscription_id','start':'start','end':'end','plannedEnd':'planned_end','reason':'reason','actor':'actor'}),
 'invoices': (m.Invoice, {'number':'number','memberId':'member_id','subscriptionId':'subscription_id','totalCents':'total_cents','discountCents':'discount_cents','status':'status','createdAt':'created_at'}),
 'installments': (m.Installment, {'invoiceId':'invoice_id','due':'due','amountCents':'amount_cents','archived':'archived'}),
 'payments': (m.Payment, {'number':'number','invoiceId':'invoice_id','amountCents':'amount_cents','method':'method','note':'note','actor':'actor','actorId':'actor_id','at':'at','recordedAt':'recorded_at'}),
 'refunds': (m.Refund, {'paymentId':'payment_id','amountCents':'amount_cents','reason':'reason','actor':'actor','actorId':'actor_id','at':'at'}),
 'cards': (m.Card, {'uid':'uid','memberId':'member_id','status':'status','at':'at'}),
 'devices': (m.Device, {'code':'code','name':'name','direction':'direction','purpose':'purpose','credentialContext':'credential_context','mode':'mode','sensor':'sensor','model':'model','lastSeen':'last_seen','telemetry':'telemetry','telemetryAt':'telemetry_at'}),
 'attempts': (m.Attempt, {'memberId':'member_id','employeeId':'employee_id','card':'card','deviceId':'device_id','direction':'direction','status':'status','reason':'reason','at':'at'}),
 'grants': (m.Grant, {'attemptId':'attempt_id','memberId':'member_id','subscriptionId':'subscription_id','deviceId':'device_id','direction':'direction','confirmed':'confirmed','expiresAt':'expires_at'}),
 'visits': (m.Visit, {'memberId':'member_id','deviceId':'device_id','subscriptionId':'subscription_id','entry':'entry','exit':'exit','method':'method','exitMethod':'exit_method','entryActor':'entry_actor','exitActor':'exit_actor','entryReason':'entry_reason','exitReason':'exit_reason','entryEventId':'entry_event_id','exitEventId':'exit_event_id','correctionReason':'correction_reason'}),
 'employees': (m.Employee, {'name':'name','type':'type','card':'card','hourlyRate':'hourly_rate','role':'role','active':'active','phone':'phone','email':'email','photo':'photo','jobTitle':'job_title','startDate':'start_date','userId':'user_id','passageIntent':'passage_intent'}),
 'rates': (m.Rate, {'employeeId':'employee_id','effectiveAt':'effective_at','rate':'rate'}),
 'shifts': (m.Shift, {'employeeId':'employee_id','entry':'entry','exit':'exit','reason':'reason','plannedId':'planned_id','source':'source','simulated':'simulated','deviceId':'device_id'}),
 'plannedShifts': (m.PlannedShift, {'employeeId':'employee_id','start':'start','end':'end','kind':'kind','autoStart':'auto_start','breakMinutes':'break_minutes','cancelled':'cancelled','actor':'actor'}),
 'shiftBreaks': (m.ShiftBreak, {'shiftId':'shift_id','start':'start','end':'end','paid':'paid'}),
 'leaveTypes': (m.LeaveType, {'name':'name','annualDays':'annual_days','serviceMonths':'service_months','weekdays':'weekdays','active':'active'}),
 'leaveRequests': (m.LeaveRequest, {'employeeId':'employee_id','typeId':'type_id','start':'start','end':'end','reason':'reason','status':'status','actor':'actor','reviewer':'reviewer','reviewedAt':'reviewed_at','reviewReason':'review_reason','rules':'rules'}),
 'employeeCards': (m.EmployeeCard, {'employeeId':'employee_id','uid':'uid','status':'status','createdAt':'created_at'}),
 'rolePolicies': (m.RolePolicy, {'role':'role','permissions':'permissions'}),
 'attendanceEvents': (m.AttendanceEvent, {'employeeId':'employee_id','shiftId':'shift_id','deviceId':'device_id','passageId':'passage_id','at':'at','occurredAt':'occurred_at','direction':'direction','source':'source','uid':'uid','approved':'approved','message':'message','actor':'actor'}),
 'personnelVisits': (m.PersonnelVisit, {'employeeId':'employee_id','deviceId':'device_id','entryEventId':'entry_event_id','exitEventId':'exit_event_id','entry':'entry','exit':'exit','correctionReason':'correction_reason'}),
 'deviceCommands': (m.DeviceCommand, {'deviceId':'device_id','action':'action','status':'status','expiresAt':'expires_at','completedAt':'completed_at','result':'result','actor':'actor'}),
 'classes': (m.ClassSession, {'name':'name','trainer':'trainer','room':'room','at':'at','duration':'duration','capacity':'capacity','cancelled':'cancelled'}),
 'bookings': (m.Booking, {'classId':'class_session_id','memberId':'member_id','status':'status','at':'at'}),
 'products': (m.Product, {'name':'name','code':'code','barcode':'barcode','category':'category','price':'price','cost':'cost','stock':'stock','minimum':'minimum','supplier':'supplier'}),
 'suppliers': (m.Supplier, {'name':'name','phone':'phone','email':'email','contact':'contact','active':'active'}),
 'sales': (m.Sale, {'productId':'product_id','memberId':'member_id','productName':'product_name','quantity':'quantity','totalCents':'total_cents','method':'method','at':'at','actor':'actor','returned':'returned','returnedAt':'returned_at'}),
 'stockMovements': (m.StockMovement, {'productId':'product_id','quantity':'quantity','reason':'reason','at':'at'}),
 'notices': (m.Notice, {'message':'message','at':'at','actor':'actor','channel':'channel'}),
 'audit': (m.Audit, {'type':'type','actor':'actor','at':'at','entityId':'entity_id','detail':'detail','before':'before','after':'after'}),
 'cashSessions': (m.CashSession, {'openedAt':'opened_at','openingCents':'opening_cents','actor':'actor','closedAt':'closed_at','expectedCents':'expected_cents','countedCents':'counted_cents','closedBy':'closed_by','note':'note'}),
 'deviceEvents': (m.DeviceEvent, {'deviceId':'device_id','at':'at','message':'message','actor':'actor'}),
}


def scalar(value):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, UUID): return str(value)
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, m.User): return value.full_name
    return value


def wire(record, mapping=None):
    if mapping is None:
        mapping = next(fields for cls, fields in SPECS.values() if isinstance(record, cls))
    data = {'id': str(record.pk), 'branchId': str(record.branch_id)}
    for key, attr in mapping.items():
        value = getattr(record, attr)
        data[key] = scalar(value)
        if isinstance(record, m.Audit) and key in ['detail','before','after']:
            data[key] = json.dumps(value, ensure_ascii=False)
    if isinstance(record, m.Device):
        healthy = record.enabled and record.last_seen and record.last_seen >= timezone.now()-timedelta(seconds=60)
        data['status'] = 'online' if healthy else 'offline'
        data['simulated'] = record.simulated
        data['enabled'] = record.enabled
        latest_scan=m.DeviceEvent.objects.filter(device=record,event_type='rfid').order_by('-at').first()
        latest_pass=m.Passage.objects.filter(device=record).order_by('-occurred_at').first()
        latest_error=m.DeviceEvent.objects.filter(device=record,level__in=['error','warning']).order_by('-at').first()
        data['lastRfidAt']=scalar(latest_scan.at) if latest_scan else None
        data['lastPassageAt']=scalar(latest_pass.occurred_at) if latest_pass else None
        data['lastPassageValidationMode']=latest_pass.grant.context.get('validationMode','two_sensor') if latest_pass else None
        data['lastError']=latest_error.message if latest_error else record.telemetry.get('lastError','')
        for direction,key in [('entry','lastEntryAt'),('exit','lastExitAt')]:
            passage=m.Passage.objects.filter(device=record,grant__direction=direction).order_by('-occurred_at').first()
            data[key]=scalar(passage.occurred_at) if passage else None
        attendance=m.AttendanceEvent.objects.filter(device_id=record.id,passage_id__isnull=False).order_by('-occurred_at').first()
        data['lastAttendance']=attendance.message if attendance else None
    if isinstance(record,m.Grant):
        data['validationMode']=record.context.get('validationMode','two_sensor')
        data['physicalVerified']=record.confirmed and data['validationMode']!='single_sensor_prototype'
    if isinstance(record,m.Subscription):
        periods=freeze_records(record)
        data['status']=status(record)
        data['freezePeriods']=[{'start':scalar(row.start),'end':scalar(row.end),'plannedEnd':scalar(row.planned_end)} for row in periods]
        data['legacyFrozen']=record.status=='frozen' and not any(row.planned_end for row in periods)
        data['remainingDays']=remaining_days(record)
        total=record.total_sessions
        if record.remaining is not None and total is None:
            total=record.rules.get('sessions')
            if total is None: total=record.remaining+m.Grant.objects.filter(subscription=record,confirmed=True,direction='entry').count()
        data['totalSessions']=total
        data['usedSessions']=None if record.remaining is None else max(0,total-record.remaining)
        invoice=m.Invoice.objects.filter(subscription=record).first()
        data['salePriceCents']=invoice.total_cents if invoice else record.price_cents
    if isinstance(record,m.Plan):
        from .plans import campaign_price, available
        price,discount,campaign=campaign_price(record)
        data.update(effectivePriceCents=price,campaignDiscountCents=discount,appliedCampaign=campaign,saleAvailable=available(record),usedCount=m.Subscription.objects.filter(plan=record).count())
        data.update(lessonTypes=record.lesson_types,lessonSessions=record.lesson_sessions)
    if isinstance(record,m.Subscription):
        from .classes import lesson_usage
        total=record.rules.get('lessonSessions')
        data.update(lessonTotal=total,lessonReserved=m.Booking.objects.filter(subscription=record,right_state='reserved').count(),lessonUsed=m.Booking.objects.filter(subscription=record,right_state='consumed').count(),lessonRemaining=None if total is None else max(0,total-lesson_usage(record)))
    if isinstance(record,m.ClassSession):
        from .classes import state, end
        data.update(trainerId=scalar(record.trainer_id),description=record.description,kind=record.kind,seriesId=scalar(record.series_id),endAt=scalar(end(record)),state=state(record),bookingMinutes=record.booking_minutes,cancelMinutes=record.cancel_minutes,requireMembership=record.require_membership,requireLesson=record.require_lesson,lateCancelConsumes=record.late_cancel_consumes,noShowConsumes=record.no_show_consumes,priceCents=record.price_cents)
    if isinstance(record,m.Booking):
        data['attendanceRecorded']=record.terms.get('attendanceRecorded',False)
        invoice=m.Invoice.objects.filter(booking_id=record.id).first()
        data.update(subscriptionId=scalar(record.subscription_id),terms=record.terms,rightState=record.right_state,reason=record.reason,actorId=record.actor_id,updatedAt=scalar(record.updated_at),invoiceId=str(invoice.id) if invoice else None)
    if isinstance(record,m.Invoice): data.update(bookingId=scalar(record.booking_id),description=record.description)
    if isinstance(record,m.Product): data.update(supplierId=scalar(record.supplier_id),description=record.description,unit=record.unit,image=record.image,active=record.active,revision=record.revision,expires=scalar(record.expires))
    if isinstance(record,m.Sale): data.update(checkoutId=scalar(record.checkout_id),number=record.number,unitPriceCents=record.unit_price_cents,unitCostCents=record.unit_cost_cents,discountCents=record.discount_cents,returnedQuantity=record.returned_quantity,refundedCents=record.refunded_cents,unit=record.unit,actorId=record.actor_id)
    if isinstance(record,m.StockMovement): data.update(kind=record.kind,actor=scalar(record.actor) if record.actor else None,actorId=record.actor_id,supplierId=scalar(record.supplier_id),saleId=scalar(record.sale_id),receivedCode=record.received_code,unitCostCents=record.unit_cost_cents,returnedUnits=record.returned_units,refundCents=record.refund_cents,restocked=record.restocked,method=record.method)
    return data


def snapshot(user):
    from . import personnel
    db = {'version': 3, 'source': 'server', 'branches': [{'id':str(user.branch_id),'name':user.branch.name}],
          'settings': {'capacity':user.branch.capacity,'debtBlock':user.branch.debt_block},
          'readNotices':list(m.ReadNotice.objects.filter(user=user).values_list('notice_id',flat=True))}
    private = ['rates','audit','cashSessions','deviceEvents','deviceCommands','suppliers']
    personnel_tables={'plannedShifts','shiftBreaks','leaveTypes','leaveRequests','employeeCards','rolePolicies','attendanceEvents','personnelVisits'}
    for key, (cls, fields) in SPECS.items():
        if key in personnel_tables: continue
        if user.role=='trainer' and key not in ['employees','shifts','classes','bookings','members']:
            db[key]=[]; continue
        if user.role != 'admin' and key in private:
            db[key] = []; continue
        records = cls.objects.filter(branch=user.branch_id)
        if user.role=='trainer':
            own=[row.id for row in m.Employee.objects.filter(branch_id=user.branch_id,user_id=user.id,active=True)]
            lessons=list(m.ClassSession.objects.filter(branch_id=user.branch_id,trainer_id__in=own))
            lesson_ids=[row.id for row in lessons]
            if key=='classes': records=records.filter(pk__in=lesson_ids)
            if key=='bookings': records=records.filter(class_session_id__in=lesson_ids)
            if key=='members': records=records.filter(pk__in=[row.member_id for row in m.Booking.objects.filter(branch_id=user.branch_id,class_session_id__in=lesson_ids)])
        if user.role!='admin' and key in ['attempts','grants']:
            records=records.filter(Q(employee_id__isnull=True)|Q(employee__user_id=user.id))
        if user.role!='admin' and key=='employees': records=records.filter(user_id=user.id)
        if user.role!='admin' and key=='shifts': records=records.filter(employee_id__in=[e.id for e in m.Employee.objects.filter(branch_id=user.branch_id,user_id=user.id)])
        if 'actor' in fields.values(): records = records.select_related('actor')
        if 'closed_by' in fields.values(): records = records.select_related('closed_by')
        order = 'created_at' if 'created_at' in cls.__table__.c else 'at' if 'at' in cls.__table__.c else 'pk'
        records = records.order_by(order)
        db[key] = [wire(item,fields) for item in records]
        if user.role!='admin' and key in ['products','sales','stockMovements']:
            for item in db[key]:
                item.pop('cost',None);item.pop('unitCostCents',None)
        if user.role=='trainer' and key=='members': db[key]=[{key:row[key] for key in ['id','name','number']} for row in db[key]]
        if user.role=='trainer' and key=='bookings':
            for booking in db[key]:
                for field in ['invoiceId','terms','subscriptionId','actorId']: booking.pop(field,None)
        if user.role!='admin' and key=='employees':
            for employee in db[key]: employee.pop('hourlyRate',None)
    db['personnel']=personnel.state(user)
    if user.role=='admin':
        from .system_settings import state
        db['systemSettings']=state(user)
    from .classes import permissions
    db['classPermissions']=permissions(user)
    from .stock import permissions as stock_permissions,summary as stock_summary
    db['stockPermissions']=stock_permissions(user)
    db['stockSummary']=stock_summary(db)
    if user.role=='admin':
        from .finance import summary
        db['finance']=summary(db)
    from .notifications import sync
    db['notificationItems']=sync(user)
    db['notices']=db['notificationItems']
    if user.role=='staff':
        permissions=personnel.permissions(user)
        from .business import net_paid
        for invoice in db['invoices']:
            record=m.Invoice.objects.get(pk=invoice['id'],branch_id=user.branch_id)
            invoice['netPaidCents']=net_paid(record)
        db['payments']=[row for row in db['payments'] if row['actorId']==user.id]
        own_payments={row['id'] for row in db['payments']}
        db['refunds']=[row for row in db['refunds'] if row['paymentId'] in own_payments]
        if not db['stockPermissions']['returns']:db['sales']=[row for row in db['sales'] if row['actorId']==user.id]
        visible_sales={row['id'] for row in db['sales']}
        db['stockMovements']=[row for row in db['stockMovements'] if row['saleId'] in visible_sales or row['actorId']==user.id]
        for row in db['products']+db['stockMovements']:
            row.pop('supplierId',None);row.pop('supplier',None);row.pop('receivedCode',None)
        from .stock import summary as staff_stock_summary
        own_sales=[row for row in db['sales'] if row['actorId']==user.id];own_sale_ids={row['id'] for row in own_sales}
        db['stockSummary']=staff_stock_summary({**db,'sales':own_sales,'stockMovements':[row for row in db['stockMovements'] if row['saleId'] in own_sale_ids]})
        if not permissions['memberManagement']:
            if permissions['collections'] or permissions['cardManagement']:db['memberDirectory']=[{key:row[key] for key in ['id','name','number']} for row in db['members']]
            for key in ['members','subscriptions','freezes','visits','attempts','grants']:db[key]=[]
        if not permissions['cardManagement']:db['cards']=[]
        if not permissions['collections']:
            for key in ['invoices','payments','refunds','installments']:db[key]=[]
        db['devices']=[{key:row.get(key) for key in ['id','name','code','purpose','credentialContext','mode','direction','status','simulated','enabled','lastSeen']} for row in db['devices']]
    return db
