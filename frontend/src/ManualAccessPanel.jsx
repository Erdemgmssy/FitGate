import React, { useRef, useState } from 'react';
import { LogIn, LogOut, Wrench, ShieldAlert } from 'lucide-react';
import { Button, Field, Table, Empty, Badge, ActionForm } from './ui';
import { currentSubscription, subscriptionStatus, dayDiff } from './gym.mjs';
import { dateKey, displayDate, displayTime } from './attendance.mjs';
import { inputTime, isoTime } from './personnel-rules.mjs';

export default function ManualAccessPanel({ db, run, isAdmin = false }) {
  const [query, setQuery] = useState(''), [selected, setSelected] = useState('');
  const [operation, setOperation] = useState(null), [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const allowed = isAdmin || (db.personnel?.permissions?.manualVisits && db.personnel?.permissions?.memberManagement);
  const members = db.members.filter(member => `${member.name} ${member.number} ${member.phone}`.toLocaleLowerCase('tr').includes(query.toLocaleLowerCase('tr')));
  const member = db.members.find(row => row.id === selected);
  const sub = member && currentSubscription(db, member.id), inside = db.visits.filter(row => !row.exit);
  const name = id => db.members.find(row => row.id === id)?.name || 'Üye';
  const devices = db.devices.filter(row => !row.simulated && ['access', 'mixed'].includes(row.purpose));
  const history = db.visits.filter(row => ['MANUAL', 'ADMIN_CORRECTION'].includes(row.method) || row.exitActor || row.correctionReason)
    .slice().sort((a, b) => new Date(b.exit || b.entry) - new Date(a.exit || a.entry)).slice(0, 20);
  const perform = async values => {
    if (saving.current) return;
    saving.current = true; setBusy(true);
    try {
      const payload = { ...values, memberId: operation.memberId };
      if (operation.action === 'correctManualVisit') {
        payload.id = operation.visit.id; payload.entry = isoTime(values.entry);
        payload.exit = values.exit ? isoTime(values.exit) : null;
      }
      return await run(operation.action, payload);
    } finally { saving.current = false; setBusy(false); }
  };
  return <section className="page-grid manual-access" aria-label="Manuel geçiş yönetimi">
    <div className="filter-bar">
      {devices.map(row => <span key={row.id}><strong>{row.name}</strong> <Badge status={row.status} />
        {row.lastError && <small>{row.lastError}</small>}</span>)}
      {!devices.length && <span>Arduino bağlantısı: veri yok</span>}
    </div>
    <p className="member-note" role="note">Manuel kayıt turnikeyi açmaz. Kişinin giriş veya çıkışı personel tarafından doğrulanmalıdır. Acil tahliye ve mekanik emniyet bağımsızdır.</p>
    {!allowed ? <Empty>Manuel geçiş yetkiniz yok. Yönetici rol izinlerini kontrol edebilir.</Empty> : <>
      <div className="filter-bar">
        <Field label="Üye ara"><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Ad, üye numarası veya telefon" /></Field>
        <Field label="Üye"><select value={selected} onChange={e => setSelected(e.target.value)}>
          <option value="">Üye seçin</option>
          {members.map(row => <option key={row.id} value={row.id}>{row.name} · {row.number}</option>)}
        </select></Field>
      </div>
      {member && <>
        <div className="filter-bar">
          <strong>{member.name} · {member.number}</strong>
          <Badge status={member.blocked ? 'blocked' : !member.active ? 'inactive' : subscriptionStatus(sub)} />
          <span>{sub?.planName || 'Paket yok'}</span>
          <span>{sub ? `${displayDate(sub.start)} — ${sub.end ? displayDate(sub.end) : 'Süre sınırı yok'}` : 'Geçerli üyelik gerekli'}</span>
          {sub && <span>Kalan: {sub.end ? `${Math.max(0, dayDiff(sub.end, dateKey()) + 1)} gün` : 'Süresiz'} · {sub.remaining == null ? 'Sınırsız giriş' : `${sub.remaining} seans`}</span>}
          <span>{inside.some(row => row.memberId === member.id) ? 'İçeride' : 'Dışarıda'}</span>
        </div>
        <div className="button-group">
          <Button icon={LogIn} tone="primary" disabled={busy || inside.some(row => row.memberId === member.id)} onClick={() => setOperation({ action: 'manualMemberEntry', memberId: member.id, title: 'Manuel giriş onayı' })}>Manuel Giriş</Button>
          {isAdmin && <Button icon={ShieldAlert} disabled={busy || inside.some(row => row.memberId === member.id)} onClick={() => setOperation({ action: 'adminManualEntryOverride', memberId: member.id, title: 'Admin giriş istisnası' })}>Gerekçeli admin istisnası</Button>}
        </div>
      </>}
      <h3>İçerideki üyeler</h3>
      <Table headers={['Üye', 'Giriş', 'Yöntem', 'İşlem']}>
        {inside.map(row => <tr key={row.id}><td>{name(row.memberId)}</td><td>{displayDate(row.entry)} {displayTime(row.entry)}</td><td>{row.method}</td><td>
          <Button icon={LogOut} disabled={busy} onClick={() => setOperation({ action: 'manualMemberExit', memberId: row.memberId, title: 'Manuel çıkış onayı' })}>Manuel Çıkış</Button>
        </td></tr>)}
      </Table>
      {!inside.length && <Empty>İçeride üye yok.</Empty>}
    </>}
    <h3>Son manuel işlemler</h3>
    <Table headers={['Üye', 'Giriş', 'Çıkış', 'Yöntem', 'Personel / Gerekçe', 'İşlem']}>
      {history.map(row => <tr key={row.id}><td>{name(row.memberId)}</td><td>{displayDate(row.entry)} {displayTime(row.entry)}</td>
        <td>{row.exit ? `${displayDate(row.exit)} ${displayTime(row.exit)}` : 'Açık ziyaret'}</td><td>{row.method}<small>{row.exitMethod || '—'}</small></td>
        <td>{row.entryActor}<small>{row.entryReason}</small>{row.exitActor}<small>{row.exitReason || row.correctionReason}</small></td>
        <td>{isAdmin && ['MANUAL', 'ADMIN_CORRECTION'].includes(row.method) && !row.entryEventId && !row.exitEventId && <Button icon={Wrench} disabled={busy} onClick={() => setOperation({ action: 'correctManualVisit', visit: row, title: 'Manuel ziyaret düzeltmesi' })}>Düzelt</Button>}</td>
      </tr>)}
    </Table>
    {!history.length && <Empty>Manuel işlem kaydı yok.</Empty>}
    {operation && <ActionForm title={operation.title} onClose={() => !busy && setOperation(null)} onSave={perform}
      initial={operation.visit ? { entry: inputTime(operation.visit.entry), exit: inputTime(operation.visit.exit) } : {}}
      fields={[
        ...(operation.visit ? [{ name: 'entry', label: 'Giriş zamanı (Türkiye)', type: 'datetime-local', step: '0.001' }, { name: 'exit', label: 'Çıkış zamanı (Türkiye)', type: 'datetime-local', step: '0.001', required: false }] : []),
        { name: 'reason', label: 'İşlem gerekçesi', type: 'textarea' },
        { name: 'faultDescription', label: 'Cihaz arıza açıklaması (isteğe bağlı)', type: 'textarea', required: false },
        { name: 'confirmed', label: operation.visit ? 'Düzeltme bilgilerini doğruluyorum' : 'Kişinin giriş / çıkış işlemini bizzat doğruluyorum', type: 'checkbox' },
        ...(operation.action === 'adminManualEntryOverride' ? [{ name: 'acknowledgeException', label: 'Üyelik kurallarını aşan istisnayı onaylıyorum; üyelik aktifleşmez ve seans düşülmez', type: 'checkbox' }] : []),
      ]}>
      <p><strong>{name(operation.memberId || operation.visit?.memberId)}</strong></p>
      {operation.action === 'correctManualVisit' && <p className="member-note">Önceki değerler denetim günlüğünde korunur. Seans, ödeme ve borç değişmez.</p>}
    </ActionForm>}
  </section>;
}
