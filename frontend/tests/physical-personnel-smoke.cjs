const {chromium} = require('./playwright-runtime.cjs');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/**', route => route.abort());
    await page.route('**/physical-personnel-preview', route => route.fulfill({contentType: 'text/html', body: '<div id="root"></div><script type="module" src="/tests/physical-personnel-preview.jsx"></script>'}));
    const entry = new Date(Date.now() - 3600000).toISOString();
    const fixture = {employees: [{id:'employee', name:'QA Worker', role:'staff', active:true, passageIntent:{}}], shifts:[{id:'shift', employeeId:'employee', entry, exit:null, source:'device', simulated:false}], personnel:{ownEmployeeId:'employee', personnelVisits:[{id:'visit', employeeId:'employee', entry, exit:null, entryEventId:'physical-event'}], permissions:{attendanceBreak:true}, rules:{}, plannedShifts:[], shiftBreaks:[], leaveRequests:[], leaveTypes:[], employeeCards:[], attendanceEvents:[], shiftMetrics:[{id:'shift', onBreak:false, workedMs:3600000}], scheduleStatus:[], accounts:[], rolePolicies:[]}};
    await page.addInitScript(value => window.personnelFixture = value, fixture);
    await page.goto('http://127.0.0.1:5174/physical-personnel-preview');
    await page.getByRole('button',{name:'Molaya çık',exact:true}).click();
    assert.deepEqual(await page.evaluate(() => window.personnelAction), {action:'physicalAttendanceIntent',payload:{intent:'break'}});
    await page.getByRole('status').filter({hasText:'fiziksel çıkış bekleniyor'}).waitFor();
    assert.equal(await page.evaluate(() => window.personnelFixture.shifts[0].exit),null);
    await page.getByRole('button',{name:'Mesaiyi Bitir',exact:true}).click();
    assert.equal((await page.evaluate(() => window.personnelAction)).payload.intent,'finish');
    await page.getByRole('button',{name:'Seçimi iptal et',exact:true}).click();
    assert.equal((await page.evaluate(() => window.personnelAction)).payload.intent,'cancel');
    await page.screenshot({path:path.resolve('../outputs/personnel-physical-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.resolve('../outputs/personnel-physical-mobile.png'),fullPage:true});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2),'Mobile overflow');
    await page.evaluate(value => window.setPersonnelFixture({...value, shifts:[], personnel:{...value.personnel, personnelVisits:[{...value.personnel.personnelVisits[0], entryEventId:null}]}}),fixture);
    await page.getByText('Yönetici düzeltmesi: içeride',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Mesaiyi başlat',exact:true}).count(),0);
    assert.deepEqual(errors,[]);
    console.log('PASS: physical attendance intents, no premature shift close, manual presence distinction, desktop/mobile. Isolated fixture; no live mutations.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
