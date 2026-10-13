const { chromium } = require('./playwright-runtime.cjs');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const {email,password}=require('./smoke-credentials.cjs').configuredCredentials();
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Mutations are routed exclusively to fitgate_fastapi_test on port 8002.
    await page.route('**/api/v1/**', async route => {
      const response = await route.fetch({ url: route.request().url().replace('127.0.0.1:5174', '127.0.0.1:8002') });
      await route.fulfill({ response });
    });
    await page.goto('http://127.0.0.1:5174/');
    await page.locator('input[name=email]').fill(email);
    await page.locator('input[name=password]').fill(password);
    await page.locator('button[type=submit]').click();
    await page.locator('.sidebar').waitFor();
    const fixture = await page.evaluate(async () => {
      const { operation, request } = await import('/src/api.mjs');
      const account = await request('auth/me/');
      const { dateKey } = await import('/src/attendance.mjs');
      const { addDays } = await import('/src/gym.mjs');
      const name = 'Membership QA ' + Date.now();
      await operation('savePlan', {name,price:1500,durationUnit:'day',durationValue:30,weekdays:[0,1,2,3,4,5,6],from:'00:00',to:'23:59',freezeDays:10,sessions:5});
      let state = await request('state/');
      const plan = state.db.plans.find(row => row.name === name);
      const created = await operation('addMember', {name,phone:'05'+String(Date.now()).slice(-9),consent:true,planId:plan.id,paid:'500',method:'cash'});
      await operation('renew', {memberId:created.result,planId:plan.id,start:addDays(dateKey(),-60)});
      const unlimited = state.db.plans.find(row => row.sessions == null && row.active);
      await operation('renew', {memberId:created.result,planId:unlimited.id,start:addDays(dateKey(),40)});
      return {name, memberId:created.result, planId:plan.id, today:dateKey(), actorName:account.user.name};
    });
    await page.reload();
    await page.locator('.sidebar button[title="Üye yönetimi"]').click();
    await page.getByLabel('Üye ara').fill(fixture.name);
    await page.locator('.member-directory .member-link').filter({ hasText: fixture.name }).click();
    await page.getByRole('tab', {name:'Üyelikler', exact:true}).click();
    const tab = page.locator('.membership-tab');
    assert.equal(await tab.locator('table').first().locator('thead th').count(),9);
    assert.equal(await tab.locator('table').first().locator('tbody tr').count(),3);
    assert.ok((await tab.innerText()).includes('Sınırsız'));
    await tab.locator('select').selectOption('expired');
    assert.equal(await tab.locator('table').first().locator('tbody tr').count(),1);
    await tab.locator('select').selectOption('all');
    const activeRow = tab.locator('table').first().locator('tbody tr').filter({has:page.getByRole('button',{name:`Dondur: ${fixture.name}`,exact:true})});
    await activeRow.getByRole('button',{name:`Dondur: ${fixture.name}`,exact:true}).click();
    let dialog = page.getByRole('dialog');
    assert.equal(await dialog.locator('input[readonly]').nth(1).inputValue(),fixture.actorName);
    await dialog.locator('textarea[name=reason]').fill('Browser freeze test');
    await dialog.getByRole('button',{name:'Kaydet',exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    assert.ok((await tab.innerText()).includes('Browser freeze test'));
    await tab.getByRole('button',{name:`Dondurmayı bitir: ${fixture.name}`,exact:true}).click();
    dialog=page.getByRole('dialog');
    await dialog.getByRole('button',{name:'Kaydet',exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    await tab.getByRole('button',{name:'Üyelik yenile',exact:true}).click();
    dialog=page.getByRole('dialog');
    await dialog.locator('select[name=planId]').selectOption(fixture.planId);
    await dialog.locator('input[name=discount]').fill('100');
    await dialog.locator('input[name=installments]').fill('2');
    await dialog.locator('input[name=paid]').fill('200');
    await dialog.getByRole('button',{name:'Kaydet',exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    assert.equal(await tab.locator('table').first().locator('tbody tr').count(),4);
    const stateBefore=await page.evaluate(async()=>(await fetch('/api/v1/state/')).json());
    const row=tab.locator('table').first().locator('tbody tr').filter({has:page.getByRole('button',{name:`Dondur: ${fixture.name}`,exact:true})}).first();
    await row.getByRole('button',{name:`Sonlandır: ${fixture.name}`,exact:true}).click();
    dialog=page.getByRole('dialog');
    await dialog.locator('textarea[name=reason]').fill('Browser cancellation test');
    await dialog.locator('input[name=confirmed]').check();
    await dialog.getByRole('button',{name:'Üyeliği sonlandır',exact:true}).click();
    await dialog.waitFor({state:'hidden'});
    const stateAfter=await page.evaluate(async()=>(await fetch('/api/v1/state/')).json());
    assert.deepEqual(stateAfter.db.invoices,stateBefore.db.invoices);
    assert.deepEqual(stateAfter.db.payments,stateBefore.db.payments);
    await tab.locator('select').selectOption('cancelled');
    assert.equal(await tab.locator('table').first().locator('tbody tr').count(),1);
    await tab.locator('select').selectOption('all');
    await tab.locator('.table-scroll').evaluateAll(nodes=>nodes.forEach(node=>{node.scrollLeft=0;}));
    await page.screenshot({path:path.resolve('../outputs/memberships-desktop.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
    await page.setViewportSize({width:390,height:844});
    if(await page.getByRole('button',{name:'Menüyü kapat',exact:true}).isVisible()) {
      await page.getByRole('button',{name:'Menüyü kapat',exact:true}).click({position:{x:380,y:400}});
    }
    await page.waitForTimeout(300);
    await tab.locator('.table-scroll').evaluateAll(nodes=>nodes.forEach(node=>{node.scrollLeft=0;}));
    assert.equal(await tab.evaluate(node=>node.getBoundingClientRect().right<=innerWidth),true);
    await page.screenshot({path:path.resolve('../outputs/memberships-mobile.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
    for(const title of ['Bilgiler','Ödemeler','İşlemler']) {
      await page.getByRole('tab',{name:title,exact:true}).click();
      assert.ok(await page.locator('.member-detail').isVisible());
    }
    assert.deepEqual(errors,[]);
    console.log('Membership UI passed: history, finite/unlimited sessions, freeze/resume, renewal, cancellation preserves finances, other tabs, desktop/mobile. Isolated PostgreSQL only.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
