const { chromium } = require('./playwright-runtime.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = 'http://127.0.0.1:5184';
const output = path.resolve(__dirname, '../../work/isolated-demo');

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (let i = 0; i < 6; i++) {
      const email = i === 0 ? 'admin@fitgate.demo' : `personel${i}@fitgate.demo`;
      const role = i === 0 ? 'admin' : i === 2 ? 'trainer' : 'staff';
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      try {
        const errors = [];
        const page = await context.newPage();
        page.on('pageerror', e => errors.push(e.message));
        const csrf = await context.request.get(`${base}/api/v1/auth/csrf/`);
        assert.equal(csrf.status(), 200);
        const token = (await csrf.json()).csrfToken;
        const login = await context.request.post(`${base}/api/v1/auth/login/`, {
          headers: { 'X-CSRFToken': token, Origin: base },
          data: { email, password: 'FitGateDemo2026!' },
        });
        assert.equal(login.status(), 200);
        assert.equal((await login.json()).user.role, role);
        // Use a fresh context to also exercise the actual login form.
        await context.clearCookies();
        await page.goto(base);
        await page.locator('input[name=email]').fill(email);
        await page.locator('input[name=password]').fill('FitGateDemo2026!');
        await page.locator('button[type=submit]').click();
        await page.locator('.sidebar').waitFor();
        const state = await page.evaluate(async () => ({
          ...(await (await fetch('/api/v1/state/')).json()),
          ...(await (await fetch('/api/v1/auth/me/')).json()),
        }));
        assert.equal(state.user.role, role);
        if (i === 0) {
          assert.equal(state.db.members.length, 20);
          assert.equal(state.db.employees.length, 5);
          assert.equal(state.db.plans.length, 5);
          assert.ok(state.db.payments.length > 0);
          const buttons = page.locator('.sidebar button[title]');
          const titles = await buttons.evaluateAll(nodes => nodes.map(n => n.title));
          for (const title of titles) {
            console.log('Checking admin screen:', title);
            await page.getByTitle(title, { exact: true }).click();
            await page.locator('.page-heading h1').waitFor();
            try {
              await page.waitForFunction(min => (document.querySelector('.page-content')?.innerText.length || 0) > min, title === 'Cihaz durumu' ? 0 : 30, { timeout: 10000 });
              assert.equal(await page.locator('.page-heading h1').innerText(), title);
              if (title === 'Cihaz durumu') assert.match(await page.locator('.page-content').innerText(), /0 gerçek cihaz çevrimiçi/);
            } catch (error) {
              console.log('Screen diagnostic:', await page.locator('.page-content').innerText());
              await page.screenshot({ path: path.join(output, 'screen-failure.png'), fullPage: true });
              throw error;
            }
          }
          results.push({ adminScreenTitles: titles, members: state.db.members.length, employees: state.db.employees.length, payments: state.db.payments.length });
        } else {
          assert.equal(state.db.employees.length, 1);
          assert.equal(state.db.employees[0].userId, state.user.id);
          assert.equal(await page.locator('.sidebar button[title="Ayarlar"]').count(), 0);
          const denied = await context.request.get(`${base}/api/v1/finance/export/`);
          assert.equal(denied.status(), 403);
        }
        await page.screenshot({ path: path.join(output, `account-${i}-desktop.png`), fullPage: true });
        await page.reload();
        await page.locator('.sidebar').waitFor();
        assert.equal((await (await context.request.get(`${base}/api/v1/auth/me/`)).json()).user.id, state.user.id);
        await page.setViewportSize({ width: 390, height: 844 });
        await page.waitForFunction(() => document.querySelector('.sidebar').getBoundingClientRect().right <= 1);
        assert.ok(await page.locator('.page-content').evaluate(n => n.getBoundingClientRect().right <= innerWidth + 2));
        await page.screenshot({ path: path.join(output, `account-${i}-mobile.png`), fullPage: true });
        assert.deepEqual(errors, []);
        results.push({ email, role, apiLogin: true, formLogin: true, reload: true, mobile: true, runtimeErrors: 0 });
      } finally { await context.close(); }
    }
    fs.writeFileSync(path.join(output, 'ui-results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
