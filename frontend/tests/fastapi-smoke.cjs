const { chromium } = require('./playwright-runtime.cjs');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const email = process.env.FITGATE_SMOKE_EMAIL;
  const password = process.env.FITGATE_SMOKE_PASSWORD;
  if (!email || !password) throw new Error('Set local smoke account environment variables');
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const page = await context.newPage();
    const errors = [];
    const failedApi = [];
    page.on('pageerror',error => errors.push(error.message));
    page.on('response',response => {
      if (response.url().includes('/api/v1/') && response.status() >= 400 && !response.url().includes('/auth/'))
        failedApi.push({url:new URL(response.url()).pathname,status:response.status()});
    });
    await page.goto('http://127.0.0.1:5174/');
    await page.locator('input[name=email]').fill(email);
    await page.locator('input[name=password]').fill(password);
    await page.getByRole('button',{name:'Giris yap',exact:true}).count().then(async n => {
      if (n) await page.getByRole('button',{name:'Giris yap',exact:true}).click();
      else await page.locator('button[type=submit]').click();
    });
    await page.locator('.sidebar').waitFor({timeout:15000});
    const state = await page.evaluate(async () => (await fetch('/api/v1/state/')).json());
    if (!state.db || state.db.source !== 'server') throw new Error('No real API state');
    const account = await page.evaluate(async () => (await fetch('/api/v1/auth/me/')).json());
    const role = account.user.role;
    if (role === 'staff' && (state.db.rates.length || state.db.audit.length || state.db.employees.some(employee => employee.hourlyRate)))
      throw new Error('Staff private data leaked');
    await page.waitForTimeout(500);
    await page.screenshot({path:path.resolve(`../outputs/fastapi-${role}-desktop.png`),fullPage:true});
    const navigation = page.locator('.sidebar button[title]');
    const labels = await navigation.evaluateAll(items => items.map(item => item.title));
    for (const label of labels) {
      await page.locator('.sidebar button[title]').filter({hasText:label}).first().click();
      await page.waitForTimeout(250);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2);
      if (overflow) errors.push('Horizontal overflow: '+label);
    }
    await page.reload();
    await page.locator('.sidebar').waitFor({timeout:15000});
    await page.setViewportSize({width:390,height:844});
    await page.waitForTimeout(600);
    await page.screenshot({path:path.resolve(`../outputs/fastapi-${role}-mobile.png`),fullPage:true});
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 2);
    if (overflow) errors.push('Mobile horizontal overflow');
    const report = {role,members:state.db.members.length,visitedPages:labels,errors,failedApi};
    fs.writeFileSync(path.resolve(`../outputs/fastapi-browser-${role}.json`),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
    if (errors.length || failedApi.length) process.exitCode=1;
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode=1; });
