const { chromium } = require('./playwright-runtime.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const credentialFile = path.resolve(root, 'work/demo-reset/Giris-Bilgileri.json');
  execFileSync('git', ['check-ignore', '--quiet', credentialFile], { cwd: root });
  const accounts = JSON.parse(fs.readFileSync(credentialFile, 'utf8')).accounts;
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const account of accounts) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      try {
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.name));
        await page.goto('http://127.0.0.1:5174/');
        await page.locator('input[name=email]').fill(account.email);
        await page.locator('input[name=password]').fill(account.password);
        await page.locator('button[type=submit]').click();
        await page.locator('.sidebar').waitFor();
        const state = await page.evaluate(async () => ({
          ...(await (await fetch('/api/v1/state/')).json()),
          ...(await (await fetch('/api/v1/auth/me/')).json()),
        }));
        assert.equal(state.user.role, account.role);
        if (account.role === 'admin') {
          assert.equal(state.db.members.length, 24);
          assert.equal(state.db.plans.length, 5);
          assert.equal(state.db.payments.length, 15);
          assert.equal(state.db.bookings.length, 7);
          for (const title of ['Üye yönetimi', 'Üyelik paketleri', 'Ödemeler', 'Personel ve mesai',
            'Ders ve randevular', 'Stok ve satış', 'Raporlar', 'Bildirimler', 'Ayarlar', 'Cihaz durumu']) {
            const nav = page.locator(`.sidebar button[title="${title}"]`);
            assert.equal(await nav.count(), 1);
            await nav.click();
            await page.locator('.page-heading h1').waitFor();
            assert.ok((await page.locator('.page-content').innerText()).length > 30);
          }
        } else {
          assert.equal(state.db.employees.length, 1);
          assert.equal(state.db.employees[0].userId, state.user.id);
          assert.equal(await page.locator('.sidebar button[title="Ayarlar"]').count(), 0);
          assert.equal(await page.locator('.sidebar button[title="Ödemeler"]').count(), 0);
        }
        await page.screenshot({ path: path.join(root, 'outputs', `demo-${account.key}-desktop.png`), fullPage: true });
        await page.reload();
        await page.locator('.sidebar').waitFor();
        const refreshed = await page.evaluate(async () => ({
          ...(await (await fetch('/api/v1/state/')).json()),
          ...(await (await fetch('/api/v1/auth/me/')).json()),
        }));
        assert.equal(refreshed.user.id, state.user.id);
        assert.equal(refreshed.db.members.length, state.db.members.length);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.waitForTimeout(350);
        assert.ok(await page.locator('.page-content').evaluate(node => node.getBoundingClientRect().right <= innerWidth + 2));
        await page.screenshot({ path: path.join(root, 'outputs', `demo-${account.key}-mobile.png`), fullPage: true });
        assert.deepEqual(errors, []);
      } finally {
        await context.close();
      }
    }
    console.log('Demo UI: 4 account logins, role scopes, admin screens, persistence and desktop/mobile passed. No physical hardware tested.');
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(`Demo UI failed (${error.name}); credentials and request contents withheld.`);
  process.exitCode = 1;
});
