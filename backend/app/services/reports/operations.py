from sqlalchemy import select,func,literal,case,and_,or_,exists,cast,String,Interval,union_all
from sqlalchemy.orm import aliased
from datetime import timedelta
from app import models as m
from .common import *

def physical(f):
    q=select(m.Passage.id.label('id'),m.Passage.occurred_at.label('at'),m.Grant.direction.label('direction'),m.Member.name.label('member'),m.Device.code.label('device')).join(m.Grant,m.Grant.id==m.Passage.grant_id).join(m.Device,m.Device.id==m.Passage.device_id).join(m.Member,m.Member.id==m.Grant.member_id).where(m.Passage.branch_id==f.branch,m.Grant.branch_id==f.branch,m.Device.branch_id==f.branch,m.Grant.confirmed.is_(True),m.Device.simulated.is_(False),f.range(m.Passage.occurred_at))
    q=q.where(func.coalesce(m.Grant.context['validationMode'].as_string(),'two_sensor')!='single_sensor_prototype')
    if f.plan:q=q.join(m.Subscription,m.Subscription.id==m.Grant.subscription_id).where(m.Subscription.plan_id==f.plan)
    if f.type in ['entry','exit']:q=q.where(m.Grant.direction==f.type)
    if f.hour is not None:q=q.where(func.extract('hour',local(m.Passage.occurred_at))==f.hour)
    if f.weekday is not None:q=q.where(func.extract('dow',local(m.Passage.occurred_at))==f.weekday)
    return q

def valid_visits(f):
    ep,eg,ed,xp,xg,xd=[aliased(cls) for cls in [m.Passage,m.Grant,m.Device,m.Passage,m.Grant,m.Device]]
    q=select(m.Visit.id.label('id'),m.Visit.entry.label('entry'),m.Visit.exit.label('exit'),m.Member.name.label('member'),ed.code.label('device')).join(ep,ep.id==m.Visit.entry_event_id).join(eg,eg.id==ep.grant_id).join(ed,ed.id==ep.device_id).join(m.Member,m.Member.id==m.Visit.member_id).outerjoin(xp,xp.id==m.Visit.exit_event_id).outerjoin(xg,xg.id==xp.grant_id).outerjoin(xd,xd.id==xp.device_id).where(m.Visit.branch_id==f.branch,ep.branch_id==f.branch,eg.confirmed.is_(True),eg.direction=='entry',ed.simulated.is_(False),or_(m.Visit.exit.is_(None),and_(xp.branch_id==f.branch,xg.confirmed.is_(True),xg.direction=='exit',xd.simulated.is_(False))))
    q=q.where(func.coalesce(eg.context['validationMode'].as_string(),'two_sensor')!='single_sensor_prototype',
              or_(m.Visit.exit.is_(None),func.coalesce(xg.context['validationMode'].as_string(),'two_sensor')!='single_sensor_prototype'))
    if f.plan:q=q.join(m.Subscription,m.Subscription.id==eg.subscription_id).where(m.Subscription.plan_id==f.plan)
    if f.hour is not None:q=q.where(func.extract('hour',local(m.Visit.entry))==f.hour)
    if f.weekday is not None:q=q.where(func.extract('dow',local(m.Visit.entry))==f.weekday)
    return q.subquery()

def visit_density(f,v=None):
    if v is None:v=valid_visits(f)
    length=max(0,(f.cutoff-f.start).total_seconds())
    if not length:return None
    seconds=func.greatest(0,func.extract('epoch',func.least(func.coalesce(v.c.exit,f.cutoff),f.cutoff)-func.greatest(v.c.entry,f.start)))
    occupancy=scalar(select(func.coalesce(func.sum(seconds),0)).where(v.c.entry<f.cutoff,or_(v.c.exit.is_(None),v.c.exit>f.start)))
    return float(occupancy or 0)/length

def visits(f,export=False):
    require(f.type in ['', 'entry','exit','approved','rejected','duplicates','timeout','manual'],'Geçiş filtresi geçersiz.')
    require((f.actor is None and f.employee is None) or (f.type=='manual' and f.actor is not None),'Personel filtresi yalnızca manuel işlem türünde kullanılabilir.')
    def human_event(direction,at,method,actor,reason):
        q=select(m.Visit.id.label('id'),m.Member.name.label('member'),at.label('at'),literal(direction).label('direction'),
            method.label('method'),m.User.full_name.label('actor'),reason.label('reason')).join(m.Member,m.Member.id==m.Visit.member_id).join(m.User,m.User.id==actor).where(
            m.Visit.branch_id==f.branch,method.in_(['MANUAL','ADMIN_CORRECTION']),f.range(at))
        if f.actor is not None:q=q.where(actor==f.actor)
        if f.plan:q=q.join(m.Subscription,m.Subscription.id==m.Visit.subscription_id).where(m.Subscription.plan_id==f.plan)
        if f.hour is not None:q=q.where(func.extract('hour',local(at))==f.hour)
        if f.weekday is not None:q=q.where(func.extract('dow',local(at))==f.weekday)
        return q
    h=union_all(human_event('entry',m.Visit.entry,m.Visit.method,m.Visit.entry_actor_id,m.Visit.entry_reason),
                human_event('exit',m.Visit.exit,m.Visit.exit_method,m.Visit.exit_actor_id,m.Visit.exit_reason)).subquery()
    human_metrics=[metric('manualEntry','Manuel / düzeltilmiş giriş',count(select(h.c.id).where(h.c.direction=='entry'))),
                   metric('manualExit','Manuel / düzeltilmiş çıkış',count(select(h.c.id).where(h.c.direction=='exit')))]
    opened=select(m.Visit.id).where(m.Visit.branch_id==f.branch,m.Visit.entry_actor_id.is_not(None),
        m.Visit.entry_event_id.is_(None),m.Visit.method.in_(['MANUAL','ADMIN_CORRECTION']),
        m.Visit.entry<f.cutoff,or_(m.Visit.exit.is_(None),m.Visit.exit>=f.cutoff))
    if f.actor is not None:opened=opened.where(m.Visit.entry_actor_id==f.actor)
    if f.plan:opened=opened.join(m.Subscription,m.Subscription.id==m.Visit.subscription_id).where(m.Subscription.plan_id==f.plan)
    if f.hour is not None:opened=opened.where(func.extract('hour',local(m.Visit.entry))==f.hour)
    if f.weekday is not None:opened=opened.where(func.extract('dow',local(m.Visit.entry))==f.weekday)
    human_metrics.append(metric('manualInside','Manuel kayıt: dönem sonu içeride',count(opened),'count','asof'))
    if f.type=='manual':
        query=select(h.c.member,h.c.at,h.c.direction,h.c.method,h.c.actor,h.c.reason).order_by(h.c.at.desc(),h.c.id)
        return result(f,human_metrics,[],query,[('Üye','text'),('Tarih','datetime'),('Yön','text'),('Yöntem','text'),('Personel','text'),('Gerekçe','text')],
                      ['Manuel işlemler insan doğrulamasıdır; cihazla doğrulanmış fiziksel geçiş değildir.'],export)
    p=physical(f).subquery();v=valid_visits(f)
    counts={r[0]:int(r[1]) for r in rows(select(p.c.direction,func.count()).group_by(p.c.direction))}
    entry=counts.get('entry',0);exit=counts.get('exit',0)
    avg=scalar(select(func.avg(func.extract('epoch',v.c.exit-v.c.entry)/60)).where(v.c.exit.is_not(None),v.c.exit<f.cutoff,v.c.entry>=f.start,v.c.entry<f.end))
    inside=int(scalar(select(func.count()).select_from(v).where(v.c.entry<f.cutoff,or_(v.c.exit.is_(None),v.c.exit>=f.cutoff))) or 0)
    density=visit_density(f,v)
    attempt=select(m.Attempt.id.label('id'),m.Attempt.status.label('status'),m.Attempt.reason.label('reason'),m.Attempt.at.label('at'),m.Device.code.label('device')).join(m.Device,m.Device.id==m.Attempt.device_id).where(m.Attempt.branch_id==f.branch,m.Device.simulated.is_(False),m.Attempt.employee_id.is_(None),f.range(m.Attempt.at))
    if f.plan:attempt=attempt.join(m.Grant,m.Grant.attempt_id==m.Attempt.id).join(m.Subscription,m.Subscription.id==m.Grant.subscription_id).where(m.Subscription.plan_id==f.plan)
    if f.hour is not None:attempt=attempt.where(func.extract('hour',local(m.Attempt.at))==f.hour)
    if f.weekday is not None:attempt=attempt.where(func.extract('dow',local(m.Attempt.at))==f.weekday)
    a=attempt.subquery();approved=int(scalar(select(func.count()).select_from(a).where(a.c.status.in_(['granted','confirmed']))) or 0);rejected=int(scalar(select(func.count()).select_from(a).where(a.c.status=='rejected')) or 0)
    duplicates=int(scalar(select(func.count()).select_from(a).where(a.c.reason.ilike('%tekrar%'))) or 0)
    timeout_query=select(m.Grant.expires_at,m.Device.code,m.Grant.direction,m.Grant.confirmed).join(m.Device,m.Device.id==m.Grant.device_id).where(m.Grant.branch_id==f.branch,m.Grant.member_id.is_not(None),m.Grant.confirmed.is_(False),m.Grant.expires_at<f.cutoff,m.Device.simulated.is_(False),f.range(m.Grant.expires_at))
    if f.plan:timeout_query=timeout_query.join(m.Subscription,m.Subscription.id==m.Grant.subscription_id).where(m.Subscription.plan_id==f.plan)
    if f.hour is not None:timeout_query=timeout_query.where(func.extract('hour',local(m.Grant.expires_at))==f.hour)
    if f.weekday is not None:timeout_query=timeout_query.where(func.extract('dow',local(m.Grant.expires_at))==f.weekday)
    timeout=count(timeout_query)
    metrics=[metric('entry','Doğrulanmış giriş',entry),metric('exit','Doğrulanmış çıkış',exit),metric('inside','Dönem sonu içeride',inside,'count','asof'),metric('duration','Ortalama tamamlanmış ziyaret',float(avg) if avg is not None else None,'minutes'),metric('density','Zaman ağırlıklı ortalama içeride',density,'decimal'),metric('approved','Kart izni / onayı',approved),metric('rejected','Reddedilen kart',rejected),metric('duplicates','Tekrarlı okutma',duplicates),metric('timeout','Doğrulanmamış süre dolumu',timeout)]
    if not f.type: metrics+=human_metrics
    hour=func.extract('hour',local(p.c.at));day=func.extract('dow',local(p.c.at))
    charts=[chart('Günlük doğrulanmış geçişler',points(select(bucket(p.c.at,f),func.count()).group_by(bucket(p.c.at,f)).order_by(bucket(p.c.at,f)),filterKey='date'),'line'),chart('Saatlik fiziksel giriş',points(select(hour,func.count()).where(p.c.direction=='entry').group_by(hour).order_by(hour),filterKey='hour'),'bar'),chart('Haftanın günlerine göre giriş',points(select(day,func.count()).where(p.c.direction=='entry').group_by(day).order_by(day),filterKey='weekday'),'distribution')]
    if f.type in ['approved','rejected','duplicates']:
        cond=a.c.status.in_(['granted','confirmed']) if f.type=='approved' else a.c.status=='rejected' if f.type=='rejected' else a.c.reason.ilike('%tekrar%')
        query=select(a.c.at,a.c.device,a.c.status,a.c.reason).where(cond).order_by(a.c.at.desc(),a.c.id);columns=[('Tarih','datetime'),('Cihaz','text'),('Kart olayı','text'),('Neden','text')]
        metrics=[metric(f.type,{'approved':'Kart izni / onayı','rejected':'Reddedilen kart','duplicates':'Tekrarlı okutma'}[f.type],count(query))]
        charts=[chart('Seçili kart olayları',points(select(bucket(a.c.at,f),func.count()).where(cond).group_by(bucket(a.c.at,f)).order_by(bucket(a.c.at,f)),filterKey='date'),'line')]
    elif f.type=='timeout':
        query=timeout_query.order_by(m.Grant.expires_at.desc(),m.Grant.id);columns=[('Süre dolumu','datetime'),('Cihaz','text'),('Yön','text'),('Doğrulandı','boolean')]
        metrics=[metric('timeout','Doğrulanmamış süre dolumu',timeout)];charts=[]
    else:
        query=select(p.c.member,p.c.at,p.c.direction,p.c.device).order_by(p.c.at.desc(),p.c.id);columns=[('Üye','text'),('Fiziksel geçiş','datetime'),('Yön','text'),('Cihaz','text')]
    return result(f,metrics,charts,query,columns,['RFID izni ziyaret değildir. Yalnızca onaylı, simülasyon olmayan Passage kayıtları fiziksel giriş/çıkışa dahil edilir.','Ortalama süre iki fiziksel olayı doğrulanmış tamamlanmış ziyaretlerden gelir. İçerideki sayı ve ortalama doluluk doğrulanmış ziyaretleri kullanır; doluluk seçili dönemin 24 saatlik zamanına ağırlıklıdır.','Tekrarlı okutma kayıtlı neden metninden, süre dolumu süresi geçmiş doğrulanmamış izinlerden hesaplanır; cihazın ayrıca zaman aşımı mesajı üretmiş olduğu iddia edilmez.'],export)

def personnel(f,export=False):
    from app.services.personnel import rules
    config=rules(get_session().get(m.Branch,f.branch))
    shift=m.Shift;plan=aliased(m.PlannedShift)
    fallback=aliased(m.PlannedShift)
    matched=select(fallback.id).where(fallback.branch_id==f.branch,fallback.employee_id==shift.employee_id,fallback.cancelled.is_(False),fallback.kind=='work',fallback.start-interval(hours=4)<=shift.entry,fallback.end>shift.entry).order_by(func.abs(func.extract('epoch',fallback.start-shift.entry)),fallback.id).limit(1).correlate(shift).scalar_subquery()
    plan_id=func.coalesce(shift.planned_id,matched)
    def elapsed_seconds(first,last,correlated=()):
        begin=func.greatest(shift.entry,first);finish=func.least(func.coalesce(shift.exit,f.now),last)
        pauses=select(func.coalesce(func.sum(func.greatest(0,func.extract('epoch',func.least(func.coalesce(m.ShiftBreak.end,f.now),finish)-func.greatest(m.ShiftBreak.start,begin)))),0)).where(m.ShiftBreak.shift_id==shift.id,m.ShiftBreak.paid.is_(False)).correlate(shift,*correlated).scalar_subquery()
        return func.greatest(0,func.extract('epoch',finish-begin)-pauses)
    def elapsed(first,last,correlated=()):return elapsed_seconds(first,last,correlated)/3600
    hours=elapsed(f.start,f.cutoff)
    late=func.greatest(0,func.floor(func.extract('epoch',shift.entry-plan.start)/60)-config['lateGraceMinutes'])
    overtime=case((and_(shift.exit.is_not(None),f.range(shift.exit),plan.id.is_not(None)),func.greatest(0,func.floor(elapsed_seconds(shift.entry,func.coalesce(shift.exit,f.now))/60)-func.floor(func.extract('epoch',plan.end-plan.start)/60)+plan.break_minutes-config['overtimeGraceMinutes'])/60),else_=None)
    base=[shift.branch_id==f.branch,shift.simulated.is_(False),shift.entry<f.cutoff,or_(shift.exit.is_(None),shift.exit>f.start)]
    if f.employee:base.append(shift.employee_id==f.employee)
    elif f.actor is not None:base.append(literal(False))
    query=select(m.Employee.name.label('name'),shift.entry.label('entry'),shift.exit.label('exit'),hours.label('hours'),case((f.range(shift.entry),late),else_=None).label('late'),overtime.label('overtime'),shift.source.label('source')).join(m.Employee,m.Employee.id==shift.employee_id).outerjoin(plan,plan.id==plan_id).where(*base)
    if f.type=='late':query=query.where(f.range(shift.entry),late>0)
    if f.type=='overtime':query=query.where(overtime>0)
    require(f.type in ['', 'late','overtime','absent','leave'],'Mesai filtresi geçersiz.')
    q=query.add_columns(shift.id.label('id')).subquery();values=rows(select(func.coalesce(func.sum(q.c.hours),0),func.coalesce(func.sum(q.c.overtime),0),func.count().filter(q.c.late>0)))[0]
    schedule=[m.PlannedShift.branch_id==f.branch,m.PlannedShift.cancelled.is_(False),m.PlannedShift.kind=='work',m.PlannedShift.start<f.cutoff,m.PlannedShift.end>f.start]
    # Match leave overlap and the same fallback shift selection as the personnel module.
    from sqlalchemy import DateTime
    leave_start=func.timezone(literal_column("'Europe/Istanbul'"),cast(m.LeaveRequest.start,DateTime()))
    leave_end=func.timezone(literal_column("'Europe/Istanbul'"),cast(m.LeaveRequest.end,DateTime())+interval(days=1))
    leave=exists(select(m.LeaveRequest.id).where(m.LeaveRequest.branch_id==f.branch,m.LeaveRequest.employee_id==m.PlannedShift.employee_id,m.LeaveRequest.status=='approved',m.PlannedShift.start<leave_end,m.PlannedShift.end>leave_start))
    attended=exists(select(shift.id).where(shift.employee_id==m.PlannedShift.employee_id,shift.branch_id==f.branch,shift.simulated.is_(False),or_(shift.planned_id==m.PlannedShift.id,and_(shift.planned_id.is_(None),matched==m.PlannedShift.id))))
    if f.employee:schedule.append(m.PlannedShift.employee_id==f.employee)
    elif f.actor is not None:schedule.append(literal(False))
    missing=and_(m.PlannedShift.end<f.cutoff,~leave,~attended)
    absences=int(scalar(select(func.count()).select_from(m.PlannedShift).where(*schedule,missing)) or 0)
    leave_base=[m.LeaveRequest.branch_id==f.branch,m.LeaveRequest.status=='approved',m.LeaveRequest.start<=f.last,m.LeaveRequest.end>=f.first]
    if f.employee:leave_base.append(m.LeaveRequest.employee_id==f.employee)
    elif f.actor is not None:leave_base.append(literal(False))
    leaves=int(scalar(select(func.count()).select_from(m.LeaveRequest).where(*leave_base)) or 0)
    metrics=[metric('hours','Çalışılan saat',float(values[0]),'hours'),metric('overtime','Tamamlanan fazla mesai',float(values[1]),'hours'),metric('late','Geç kalınan vardiya',int(values[2])),metric('absent','Devamsız vardiya',absences),metric('leave','Onaylı izin kaydı',leaves),metric('planned','Planlı çalışma vardiyası',int(scalar(select(func.count()).select_from(m.PlannedShift).where(*schedule)) or 0))]
    charts=[chart('Personel bazında çalışma saati',points(select(q.c.name,func.sum(q.c.hours)).group_by(q.c.name)),'bar','hours')]
    days=func.generate_series(f.start,f.end-timedelta(days=1),literal('1 day').cast(Interval)).table_valued('day').render_derived()
    day_query=select(days.c.day,func.coalesce(func.sum(elapsed(days.c.day,func.least(days.c.day+interval(days=1),f.cutoff),(days,))),0).label('hours')).select_from(days).outerjoin(shift,and_(shift.branch_id==f.branch,shift.simulated.is_(False),shift.entry<days.c.day+interval(days=1),func.coalesce(shift.exit,f.now)>days.c.day,shift.employee_id==f.employee if f.employee else literal(False) if f.actor is not None else literal(True))).group_by(days.c.day).order_by(days.c.day)
    if f.type in ['late','overtime']:day_query=day_query.where(shift.id.in_(select(q.c.id)))
    daily=day_query.subquery();group=bucket(daily.c.day,f)
    period_query=select(group,func.sum(daily.c.hours)).group_by(group).order_by(group)
    charts.append(chart('Çalışma saati (gece vardiyası gün sınırından bölünür)',points(period_query,filterKey='date') if count(select(q.c.id)) else [],'line','hours'))
    if f.type=='leave':
        query=select(m.Employee.name,m.LeaveRequest.start,m.LeaveRequest.end,m.LeaveType.name,m.LeaveRequest.status).select_from(m.LeaveRequest).join(m.Employee).join(m.LeaveType,m.LeaveType.id==m.LeaveRequest.type_id).where(*leave_base).order_by(m.LeaveRequest.start.desc(),m.LeaveRequest.id);columns=[('Personel','text'),('Başlangıç','date'),('Bitiş','date'),('İzin türü','text'),('Durum','text')]
    elif f.type=='absent':
        query=select(m.Employee.name,m.PlannedShift.start,m.PlannedShift.end).select_from(m.PlannedShift).join(m.Employee).where(*schedule,missing).order_by(m.PlannedShift.start.desc(),m.PlannedShift.id);columns=[('Personel','text'),('Planlanan giriş','datetime'),('Planlanan çıkış','datetime')]
    else:query=query.order_by(shift.entry.desc(),shift.id);columns=[('Personel','text'),('Giriş','datetime'),('Çıkış','datetime'),('Dönemde çalışılan saat','hours'),('Geç kalma (dk)','minutes'),('Fazla mesai (sa)','hours'),('Kaynak','text')]
    if f.type in ['leave','absent']:
        metrics=[metric(f.type,'Onaylı izin kaydı' if f.type=='leave' else 'Devamsız vardiya',leaves if f.type=='leave' else absences)]
        charts=[]
    if f.type in ['late','overtime']:metrics=metrics[:3]
    return result(f,metrics,charts,query,columns,['Simülasyon mesaisi dışarıda tutulur. Ücretsiz molalar çıkarılır; ücretli molalar korunur. Gece vardiyaları günlük grafikte gerçek gün sınırından bölünür.','Fazla mesai tamamlanmış vardiyanın çıkış dönemine, geç kalma giriş dönemine yazılır. Mevcut personel modülünün vardiya, mola ve tolerans kuralları kullanılır; maaş/gider kaydı üretilmez.'],export)

def devices(f,export=False):
    base=[m.DeviceEvent.branch_id==f.branch,f.range(m.DeviceEvent.at),actor_condition(m.DeviceEvent.actor_id,f)]
    if f.type:base.append(m.DeviceEvent.event_type==f.type)
    events=select(m.DeviceEvent.at,m.Device.code,m.Device.simulated,m.DeviceEvent.level,m.DeviceEvent.event_type,m.DeviceEvent.message).join(m.Device,m.Device.id==m.DeviceEvent.device_id).where(*base).order_by(m.DeviceEvent.at.desc(),m.DeviceEvent.id)
    totals={r[0]:int(r[1]) for r in rows(select(m.DeviceEvent.event_type,func.count()).where(*base).group_by(m.DeviceEvent.event_type))}
    metric_rows=[metric('events','Kayıtlı cihaz olayı',sum(totals.values())),metric('rfid','RFID olayı',totals.get('rfid',0)),metric('errors','Hata / uyarı',int(scalar(select(func.count()).select_from(m.DeviceEvent).where(*base,m.DeviceEvent.level.in_(['warning','error']))) or 0)),metric('devices','Kayıtlı cihaz',int(scalar(select(func.count()).select_from(m.Device).where(m.Device.branch_id==f.branch)) or 0),'count','current')]
    connections=[]
    if f.actor is None and f.employee is None:
        for row in get_session().scalars(select(m.Device).where(m.Device.branch_id==f.branch)).all():
            connections.append({'code':row.code,'lastSeen':cell(row.last_seen),'simulated':row.simulated,'status':'offline' if not row.enabled or not row.last_seen or row.last_seen<f.now-timedelta(seconds=60) else 'online'})
    output=result(f,metric_rows,[chart('Cihaz olay türleri',[{'label':k or 'Diğer','value':v,'filter':{'type':k}} for k,v in totals.items()],'distribution')],events,[('Tarih','datetime'),('Cihaz','text'),('Simülasyon','boolean'),('Seviye','text'),('Olay türü','text'),('Mesaj','text')],['Cihaz geçmişi yalnızca mevcut DeviceEvent kayıtlarıdır; kayıt yoksa bağlantı/servo/sensör olayı uydurulmaz.','Son bağlantı tablosu güncel durumdur; geçmiş çevrimiçi/çevrimdışı durumu heartbeat zamanlarından türetilmez. USB Bridge hatası yalnızca sistemde kaydedilmişse görünür.'],export)
    output['connections']=connections
    commands=select(m.DeviceCommand.created_at,m.Device.code,m.DeviceCommand.action,m.DeviceCommand.status,m.DeviceCommand.result).join(m.Device,m.Device.id==m.DeviceCommand.device_id).where(m.DeviceCommand.branch_id==f.branch,f.range(m.DeviceCommand.created_at),actor_condition(m.DeviceCommand.actor_id,f)).order_by(m.DeviceCommand.created_at.desc(),m.DeviceCommand.id)
    output['commands']=table(commands,[('Talep tarihi','datetime'),('Cihaz','text'),('Tanılama','text'),('Durum','text'),('Sonuç','text')],f,export)
    return output

def audit(f,export=False):
    base=[m.Audit.branch_id==f.branch,f.range(m.Audit.at),actor_condition(m.Audit.actor_id,f)]
    if f.type:base.append(m.Audit.type==f.type)
    query=select(m.Audit.at,m.User.full_name,m.Audit.type,m.Audit.entity_id,m.Audit.detail).outerjoin(m.User,m.User.id==m.Audit.actor_id).where(*base).order_by(m.Audit.at.desc(),m.Audit.id)
    return result(f,[metric('events','Denetim kaydı',count(query))],[chart('İşlem dağılımı',points(select(m.Audit.type,func.count()).where(*base).group_by(m.Audit.type).order_by(func.count().desc()).limit(20),filterKey='type'),'bar')],query,[('Tarih','datetime'),('Personel','text'),('İşlem','text'),('Kayıt','text'),('Gerekçe / değerler','text')],['Denetim raporunda gereksiz iletişim, sağlık, kimlik ve gizli anahtar alanları gösterilmez. Rapor isteği kayıtları değiştirmez.'],export)
