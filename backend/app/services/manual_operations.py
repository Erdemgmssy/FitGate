"""Human-attested operations. Never create device evidence or send servo commands."""
from datetime import timedelta
from app import models as m
from app.core import time as timezone
from .business import require, get, parse_time, member_debt
from .membership import entry_sub, member_frozen
from .plans import entry_error
from .system_settings import permitted, open_for_entry
from .personnel import scoped_employee, permissions, rules

ACTIONS = {'manualMemberEntry', 'manualMemberExit', 'adminManualEntryOverride',
           'correctManualVisit', 'manualPersonnelOperation'}

def attest(p):
    require(p.get('confirmed') is True, 'Kişinin işlemini açıkça doğrulamanız gerekiyor.')
    reason = p.get('reason')
    require(isinstance(reason, str) and 3 <= len(reason.strip()) <= 600,
            'İşlem gerekçesi 3-600 karakter olmalı.')
    return reason.strip()

def pending(subject, now):
    field = 'member' if isinstance(subject, m.Member) else 'employee'
    require(not m.Grant.objects.filter(**{field: subject}, confirmed=False, expires_at__gt=now).exists(),
            'Bekleyen RFID geçişi var; tamamlanmasını veya izin süresinin dolmasını bekleyin.')

def recent_human_visit(member, now):
    cutoff = now-timedelta(seconds=10)
    return (m.Visit.objects.filter(member=member, entry_actor_id__isnull=False, entry__gt=cutoff).exists()
            or m.Visit.objects.filter(member=member, exit_actor_id__isnull=False, exit__gt=cutoff).exists())

def audit(action, obj, p, user, branch, before=None):
    from .projection import wire
    m.Audit.objects.create(branch=branch, actor=user, type=action, entity_id=str(obj.id),
        detail={'reason': p['reason'].strip(), 'faultDescription': str(p.get('faultDescription', ''))[:600],
                'confirmed': True, 'source': 'MANUAL_PERSONNEL' if isinstance(obj, m.Shift) else 'MANUAL',
                'operation': p.get('operation'), 'exception': action == 'adminManualEntryOverride',
                'physicalVerified': False}, before=before, after=wire(obj))

def apply(action, p, user, branch):
    require(user is not None, 'Personel oturumu gerekli.')
    reason = attest(p)
    now = timezone.now()
    if action == 'manualPersonnelOperation':
        return personnel(p, user, branch, now, reason)
    require(user.role in ['admin', 'staff'] and permitted(user, 'manualVisits')
            and permitted(user, 'memberManagement'), 'Manuel üye geçiş yetkiniz yok.')
    if action in ['adminManualEntryOverride', 'correctManualVisit']:
        require(user.role == 'admin', 'Bu işlem yalnızca admin tarafından yapılabilir.')
    if action == 'correctManualVisit':
        return correct(p, user, branch, now, reason)
    member = get(m.Member, p.get('memberId'), branch)
    pending(member, now)
    visits = list(m.Visit.objects.filter(member=member, exit__isnull=True))
    require(len(visits) <= 1, 'Ziyaret kayıtları tutarsız; yönetici incelemesi gerekiyor.')
    if action == 'manualMemberExit':
        require(len(visits) == 1, 'Açık ziyaret yok; ikinci çıkış oluşturulamaz.')
        visit = visits[0]
        require(visit.branch_id == branch.id and visit.entry <= now, 'Ziyaret zamanı/şubesi tutarsız.')
        from .projection import wire
        before = wire(visit)
        visit.exit = now; visit.exit_method = 'MANUAL'; visit.exit_actor = user; visit.exit_reason = reason
        visit.save()
        audit(action, visit, p, user, branch, before)
        return {'visitId': str(visit.id), 'method': 'MANUAL', 'direction': 'exit', 'physicalVerified': False}
    require(not visits, 'Üye zaten içeride; ikinci giriş oluşturulamaz.')
    require(not recent_human_visit(member, now), 'Tekrarlı manuel işlem; kısa süre bekleyin.')
    require(m.Visit.objects.filter(branch=branch, exit__isnull=True).count()
            + m.Grant.objects.filter(branch=branch, direction='entry', confirmed=False, expires_at__gt=now).count()
            < branch.capacity, 'Kapasite dolu.')
    sub = None
    if action == 'adminManualEntryOverride':
        require(p.get('acknowledgeException') is True, 'Admin istisnasını ayrıca onaylamalısınız.')
    else:
        require(member.active and not member.blocked, 'Üye pasif veya engelli.')
        require(not member_frozen(member, timezone.localdate(now)), 'Üyelik dondurulmuş.')
        sub = entry_sub(member, now)
        require(sub is not None, 'Üyelik geçerli değil.')
        error = entry_error(sub, now); require(not error, error)
        require(open_for_entry(branch, now), 'Salon çalışma takvimi dışında.')
        require(not branch.debt_block or member_debt(member) == 0, 'Borç nedeniyle giriş engeli.')
    visit = m.Visit.objects.create(branch=branch, member=member, subscription=sub, entry=now,
        method='MANUAL', entry_actor=user, entry_reason=reason)
    if sub and sub.remaining is not None:
        previous = sub.remaining
        require(previous > 0, 'Seans hakkı kalmadı.')
        sub.remaining -= 1; sub.save()
        m.Audit.objects.create(branch=branch, actor=user, type='sessionUsed', entity_id=str(sub.id),
            detail={'visitId': str(visit.id), 'source': 'MANUAL'},
            before={'remaining': previous}, after={'remaining': sub.remaining})
    audit(action, visit, p, user, branch)
    return {'visitId': str(visit.id), 'method': 'MANUAL', 'direction': 'entry',
            'physicalVerified': False, 'exception': sub is None}

def correct(p, user, branch, now, reason):
    visit = get(m.Visit, p.get('id'), branch)
    require(visit.method in ['MANUAL', 'ADMIN_CORRECTION'] and visit.entry_actor_id is not None
            and visit.entry_event_id is None and visit.exit_event_id is None,
            'Yalnızca cihaz olayı olmayan manuel ziyaret bu işlemle düzeltilebilir.')
    pending(visit.member, now)
    entry = parse_time(p.get('entry'))
    exit = parse_time(p['exit']) if p.get('exit') else None
    require(entry <= now and (exit is None or entry <= exit <= now), 'Giriş/çıkış zamanı geçersiz.')
    for other in m.Visit.objects.filter(member_id=visit.member_id).exclude(pk=visit.pk):
        require(not (entry < (other.exit or now+timedelta(seconds=1))
                     and other.entry < (exit or now+timedelta(seconds=1))), 'Başka bir ziyaretle çakışıyor.')
        require(exit is not None or other.exit is not None, 'Üyenin başka açık ziyareti var.')
    from .projection import wire
    before = wire(visit)
    visit.entry = entry; visit.exit = exit; visit.method = 'ADMIN_CORRECTION'
    visit.correction_reason = reason
    if exit is not None:
        visit.exit_method = 'ADMIN_CORRECTION'; visit.exit_actor = user; visit.exit_reason = reason
    else:
        visit.exit_method = ''; visit.exit_actor = None; visit.exit_reason = ''
    visit.save(); audit('correctManualVisit', visit, p, user, branch, before)
    return {'visitId': str(visit.id), 'method': 'ADMIN_CORRECTION', 'physicalVerified': False}

def personnel(p, user, branch, now, reason):
    require(permissions(user)['manualAttendance'], 'Manuel mesai yetkiniz yok.')
    employee = scoped_employee(user, branch, p.get('employeeId'))
    pending(employee, now)
    operation = p.get('operation')
    require(operation in ['start', 'break', 'resume', 'finish'], 'Mesai işlemi geçersiz.')
    opened = list(m.Shift.objects.filter(employee=employee, exit__isnull=True))
    require(len(opened) <= 1 and not any(row.simulated for row in opened), 'Açık mesai tutarsız veya simülasyon kaydı var.')
    shift = opened[0] if opened else None
    before = None
    if operation == 'start':
        from .physical_personnel import work_plan, attendance_allowed
        require(employee.active and not shift, 'Personel pasif veya mesai zaten açık.')
        plan = work_plan(employee, now)
        require(plan and attendance_allowed(employee, now), 'Şu anda geçerli çalışma vardiyası yok veya personel izinli.')
        require(not m.Shift.objects.filter(employee=employee, planned_id=plan.id, simulated=False).exists(),
                'Bu vardiyanın mesaisi zaten kaydedilmiş.')
        shift = m.Shift.objects.create(branch=branch, employee=employee, entry=now, planned_id=plan.id,
                                      source='MANUAL_PERSONNEL', reason=reason)
    else:
        require(shift and shift.entry <= now, 'Geçerli açık mesai yok.')
        from .projection import wire
        before = wire(shift)
        pauses = list(m.ShiftBreak.objects.filter(shift=shift, end__isnull=True))
        require(len(pauses) <= 1, 'Mola kayıtları tutarsız.')
        pause = pauses[0] if pauses else None
        if operation in ['break', 'resume']:
            require(permissions(user)['attendanceBreak'], 'Mola yetkiniz yok.')
        if operation == 'break':
            require(not pause, 'Mola zaten açık.')
            m.ShiftBreak.objects.create(branch_id=branch.id, shift=shift, start=now, paid=rules(branch)['paidBreaks'])
        else:
            if operation == 'resume': require(pause is not None, 'Açık mola yok.')
            if pause:
                require(pause.start < now, 'Mola bitişi başlangıcından sonra olmalı.')
                pause.end = now; pause.save()
            if operation == 'finish':
                require(shift.entry < now, 'Mesai bitişi başlangıcından sonra olmalı.')
                shift.exit = now; shift.save()
    employee.passage_intent = {}; employee.save()
    direction = {'start': 'entry', 'break': 'break', 'resume': 'resume', 'finish': 'exit'}[operation]
    event = m.AttendanceEvent.objects.create(branch_id=branch.id, employee_id=employee.id, shift_id=shift.id,
        occurred_at=now, direction=direction, source='MANUAL_PERSONNEL', actor=user,
        approved=True, message=reason)
    audit('manualPersonnelOperation', shift, p, user, branch, before)
    return {'shiftId': str(shift.id), 'eventId': str(event.id), 'source': 'MANUAL_PERSONNEL',
            'physicalVerified': False, 'operation': operation}
