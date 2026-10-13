import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AccessPage, ReceptionPage } from '../src/AccessPages.jsx';
import { EmployeesPage } from '../src/Personnel.jsx';
import '../src/styles.css';

function Preview() {
  const [db, setDb] = useState(window.manualFixture);
  const isAdmin = window.manualRole === 'admin';
  const run = async (action, payload) => {
    window.manualActions.push({ action, payload });
    const now = new Date().toISOString();
    if (action === 'manualMemberEntry') setDb(old => ({ ...old, visits: [...old.visits, {
      id: 'manual-visit', memberId: payload.memberId, entry: now, exit: null, method: 'MANUAL',
      entryActor: 'Synthetic operator', entryReason: payload.reason,
    }], subscriptions: old.subscriptions.map(row => ({ ...row, remaining: row.remaining - 1 })) }));
    if (action === 'manualMemberExit') setDb(old => ({ ...old, visits: old.visits.map(row => row.memberId === payload.memberId && !row.exit ? {
      ...row, exit: now, exitMethod: 'MANUAL', exitActor: 'Synthetic operator', exitReason: payload.reason,
    } : row) }));
    if (action === 'manualPersonnelOperation') setDb(old => {
      const shifts = payload.operation === 'start' ? [{ id: 'manual-shift', employeeId: 'own', entry: now, exit: null, source: 'MANUAL_PERSONNEL', simulated: false }] : old.shifts.map(row => payload.operation === 'finish' ? { ...row, exit: now } : row);
      return { ...old, shifts, personnel: { ...old.personnel, shiftMetrics: shifts.map(row => ({ id: row.id, onBreak: payload.operation === 'break' })) } };
    });
    return { ok: true };
  };
  return <main className="main-content">
    {window.manualPage === 'personnel' ? <EmployeesPage db={db} run={run} isAdmin={false} user={{ role: 'staff' }} /> :
      isAdmin ? <AccessPage db={db} run={run} isAdmin /> : <ReceptionPage db={db} run={run} />}
  </main>;
}
createRoot(document.getElementById('root')).render(<Preview />);
