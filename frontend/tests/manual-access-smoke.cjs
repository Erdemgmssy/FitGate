const { chromium } = require('./playwright-runtime.cjs');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  let checks = 0;
  try {
    for (const role of ['admin', 'staff', 'denied']) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.route('**/api/**', route => route.abort());
      await page.route('**/manual-preview', route => route.fulfill({ contentType: 'text/html', body: '<html><body><div id="root"></div><script type="module" src="/tests/manual-access-preview.jsx"></script></body></html>' }));
      await page.addInitScript(({ role }) => {
        const day = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Istanbul' }).format(new Date());
        window.manualRole = role; window.manualActions = [];
        window.manualFixture = {
          source: 'server', members: [{ id: 'member', name: 'Synthetic Member', number: 'GYM-TEST-1', phone: '05550000000', active: true }],
          subscriptions: [{ id: 'sub', memberId: 'member', planName: 'Synthetic Sessions', status: 'active', start: day, end: null, remaining: 3 }],
          visits: [], attempts: [], grants: [], shifts: [], employees: [{ id: 'own', name: 'Synthetic Employee', active: true, role: 'staff', type: 'fixed' }],
          settings: { capacity: 100 },
          devices: [{ id: 'offline', name: 'Synthetic Arduino', code: 'UI-TEST', purpose: 'mixed', mode: 'auto', status: 'offline', enabled: true, simulated: false, lastError: 'Synthetic offline fault' }],
          personnel: { ownEmployeeId: 'own', permissions: { manualVisits: role !== 'denied', memberManagement: true, manualAttendance: true, attendanceBreak: true },
            plannedShifts: [], shiftBreaks: [], leaveRequests: [], leaveTypes: [], employeeCards: [], attendanceEvents: [], personnelVisits: [], shiftMetrics: [], scheduleStatus: [], accounts: [], rolePolicies: [], rules: {} },
        };
      }, { role });
      await page.goto('http://127.0.0.1:5174/manual-preview');
      await page.getByRole(role === 'admin' ? 'tab' : 'button', { name: role === 'admin' ? 'Manuel işlemler' : 'Manuel İşlem Modu', exact: true }).click();
      await page.getByRole('heading', { name: 'Son manuel işlemler' }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Gerekçeli admin istisnası' }).count(), 0);
      if (role === 'denied') {
        assert.ok(await page.getByText('Manuel geçiş yetkiniz yok.', { exact: false }).isVisible());
        assert.equal(await page.getByRole('button', { name: 'Manuel Giriş', exact: true }).count(), 0); checks++;
      } else {
        await page.getByLabel('Üye ara', { exact: true }).fill('GYM-TEST');
        await page.getByLabel('Üye', { exact: true }).selectOption('member');
        assert.ok(await page.getByText('3 seans', { exact: false }).isVisible());
        assert.equal(await page.getByRole('button', { name: 'Gerekçeli admin istisnası' }).count(), role === 'admin' ? 1 : 0);
        await page.getByRole('button', { name: 'Manuel Giriş', exact: true }).click();
        const dialog = page.getByRole('dialog');
        await dialog.getByLabel('İşlem gerekçesi', { exact: true }).fill('Human verified entry');
        await dialog.getByLabel('Kişinin giriş / çıkış işlemini bizzat doğruluyorum').check();
        await dialog.getByRole('button', { name: 'Kaydet', exact: true }).click();
        await page.getByRole('heading', { name: 'Manuel giriş onayı' }).waitFor({ state: 'hidden' });
        assert.equal((await page.evaluate(() => window.manualActions))[0].action, 'manualMemberEntry');
        assert.equal((await page.evaluate(() => window.manualActions))[0].payload.confirmed, true); checks++;
        if (role === 'staff') {
          await page.getByRole('button', { name: 'Otomatik RFID Modu' }).click();
          await page.getByRole('button', { name: 'Manuel İşlem Modu' }).click();
          assert.ok(await page.getByRole('button', { name: 'Manuel Çıkış' }).isVisible()); checks++;
        }
        await page.screenshot({ path: path.resolve(`../outputs/manual-${role}-desktop.png`), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        await page.screenshot({ path: path.resolve(`../outputs/manual-${role}-mobile.png`), fullPage: true });
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)); checks++;
        await page.getByRole('button', { name: 'Manuel Çıkış' }).click();
        await dialog.getByLabel('İşlem gerekçesi', { exact: true }).fill('Human verified exit');
        await dialog.getByLabel('Kişinin giriş / çıkış işlemini bizzat doğruluyorum').check();
        await dialog.getByRole('button', { name: 'Kaydet', exact: true }).click();
        await page.getByRole('heading', { name: 'Manuel çıkış onayı' }).waitFor({ state: 'hidden' });
        assert.equal((await page.evaluate(() => window.manualActions)).at(-1).action, 'manualMemberExit'); checks++;
      }
      assert.deepEqual(errors, []); await page.close();
    }
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.route('**/manual-preview', route => route.fulfill({ contentType: 'text/html', body: '<html><body><div id="root"></div><script type="module" src="/tests/manual-access-preview.jsx"></script></body></html>' }));
    await page.addInitScript(() => {
      window.manualPage = 'personnel'; window.manualActions = [];
      window.manualFixture = { employees: [{ id: 'own', name: 'Synthetic Employee', active: true, role: 'staff', type: 'fixed' }], shifts: [],
        personnel: { ownEmployeeId: 'own', permissions: { manualAttendance: true, attendanceBreak: true }, plannedShifts: [], shiftBreaks: [], leaveRequests: [], leaveTypes: [], employeeCards: [], attendanceEvents: [], personnelVisits: [], shiftMetrics: [], scheduleStatus: [], accounts: [], rolePolicies: [], rules: {} } };
    });
    await page.goto('http://127.0.0.1:5174/manual-preview');
    for (const [operation, label] of [['start', 'Manuel Mesai Başlat'], ['break', 'Manuel Molaya Çık'], ['resume', 'Manuel Moladan Dön'], ['finish', 'Manuel Mesai Bitir']]) {
      await page.getByRole('button', { name: label, exact: true }).click();
      const dialog = page.getByRole('dialog');
      await dialog.getByLabel('Gerekçe').fill('Human verified work operation');
      await dialog.getByLabel('Personelin mesai / mola işlemini doğruluyorum').check();
      await dialog.getByRole('button', { name: 'Kaydet', exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal((await page.evaluate(() => window.manualActions)).at(-1).payload.operation, operation); checks++;
    }
    await page.screenshot({ path: path.resolve('../outputs/manual-personnel-mobile.png'), fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)); checks++;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: path.resolve('../outputs/manual-personnel-desktop.png'), fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)); checks++;
    console.log(`PASS: ${checks} manual UI checks, offline admin/staff, confirmation, mode preservation, role denial, four work operations, desktop/mobile. Mock UI only; no live writes or hardware tests.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
