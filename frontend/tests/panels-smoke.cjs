const {chromium}=require('./playwright-runtime.cjs');
const assert=require('node:assert/strict');
const path=require('node:path');

(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];let paymentKey;page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().endsWith('/actions/collect/'))paymentKey=r.headers()['idempotency-key'];});
    // All reads and writes use the disposable panel fixture, never the live database.
    await page.route('**/api/v1/**',async route=>route.fulfill({response:await route.fetch({url:route.request().url().replace('127.0.0.1:5174','127.0.0.1:8002')})}));
    async function login(email){await page.locator('input[name=email]').fill(email);await page.locator('input[name=password]').fill('LongTest123!');await page.locator('button[type=submit]').click();try{await page.locator('.sidebar button[title="Genel bakış"]').waitFor({state:'attached'});}catch(e){console.log(email,await page.locator('body').innerText(),errors);throw e;}}
    async function nav(title){await page.locator(`.sidebar button[title="${title}"]`).click();}
    async function state(){return page.evaluate(async()=>(await fetch('/api/v1/state/')).json());}
    async function save(){const d=page.getByRole('dialog');await d.getByRole('button',{name:/^(Kaydet|Üyeyi kaydet)$/}).click();await d.waitFor({state:'hidden'});}
    await page.goto('http://127.0.0.1:5174/');await login('admin@test.com');
    const adminMenu=await page.locator('.sidebar nav button').evaluateAll(nodes=>nodes.map(n=>n.title));
    for(const title of ['Genel bakış','Üye yönetimi','Üyelik paketleri','Ödemeler','Personel ve mesai','Cihaz durumu','Raporlar','Ayarlar'])assert.ok(adminMenu.includes(title),title);
    assert.ok(!adminMenu.includes('RFID kart işlemleri'));
    await page.screenshot({path:path.resolve('../outputs/panel-admin-desktop.png'),fullPage:true});
    await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await login('staff@test.com');
    const staffMenu=await page.locator('.sidebar nav button').evaluateAll(nodes=>nodes.map(n=>n.title));
    assert.deepEqual(staffMenu,['Genel bakış','Üye işlemleri','Ödeme al','RFID kart işlemleri','Giriş terminali','Giriş / çıkış','Ders ve randevular','Hızlı satış','Mesailerim','Bildirimler']);
    await page.screenshot({path:path.resolve('../outputs/panel-staff-desktop.png'),fullPage:true});
    await nav('Üye işlemleri');await page.getByRole('button',{name:'Yeni üye',exact:true}).click();
    let dialog=page.getByRole('dialog');const unique=Date.now(),name='Panel QA '+unique;
    await dialog.locator('input[name=name]').fill(name);await dialog.locator('input[name=phone]').fill('05'+String(unique).slice(-9));await dialog.locator('input[name=consent]').check();await save();
    let data=await state();const member=data.db.members.find(m=>m.name===name),existing=data.db.members.find(m=>m.name==='Panel Existing');assert.ok(member);assert.ok(existing);
    assert.ok((await page.locator('.page-content').innerText()).includes(name));
    await nav('Ödeme al');await page.locator('.page-content').getByRole('combobox',{name:'Üye',exact:true}).selectOption('all');await page.locator('.page-content').getByRole('button',{name:'Ödeme al',exact:true}).click();dialog=page.getByRole('dialog');await dialog.getByRole('combobox',{name:'Üye',exact:true}).selectOption(existing.id);await dialog.locator('input[name=amount]').fill('10');await save();
    data=await state();assert.equal(data.db.payments.length,1);assert.equal(data.db.invoices.find(i=>i.memberId===existing.id).netPaidCents,4000);assert.equal(await page.getByRole('button',{name:'Ödeme bilgilerini düzelt',exact:true}).count(),0);
    await page.getByRole('button',{name:'Tahsilat belgesini aç',exact:true}).click();await page.getByRole('dialog').waitFor();await page.getByRole('button',{name:'Kapat',exact:true}).click();
    await page.screenshot({path:path.resolve('../outputs/panel-staff-payments.png'),fullPage:true});
    await nav('RFID kart işlemleri');await page.getByRole('combobox',{name:'Üye',exact:true}).selectOption(member.id);await page.getByLabel('Kart UID',{exact:true}).fill('PQA-'+unique);await page.getByRole('button',{name:'Ata',exact:true}).click();await page.waitForFunction(id=>document.querySelector('.page-content')?.textContent.includes(id),'PQA-'+unique);assert.ok((await state()).db.cards.some(c=>c.memberId===member.id));
    await nav('Ders ve randevular');await page.getByRole('row').filter({hasText:'Yoga QA'}).getByRole('button',{name:'Detaylar',exact:true}).click();await page.getByRole('button',{name:'Rezervasyon ekle',exact:true}).click();dialog=page.getByRole('dialog');await dialog.getByRole('combobox',{name:'Üye',exact:true}).selectOption(existing.id);await dialog.getByRole('button',{name:'Rezervasyon oluştur',exact:true}).click();await dialog.waitFor({state:'hidden'});assert.ok((await state()).db.bookings.some(b=>b.memberId===existing.id));
    await nav('Hızlı satış');await page.getByRole('searchbox',{name:'Ürün adı veya barkod',exact:true}).fill('869000000001');await page.getByRole('searchbox',{name:'Ürün adı veya barkod',exact:true}).press('Enter');await page.getByRole('button',{name:'Satışı tamamla',exact:true}).click();await page.getByRole('dialog').waitFor();await page.getByRole('button',{name:'Kapat',exact:true}).click();data=await state();assert.equal(data.db.sales.length,1);assert.ok(data.db.products.every(p=>!('costCents' in p)&&!('supplierId' in p)));
    await nav('Mesailerim');assert.equal((await state()).db.employees.length,1);assert.equal(await page.getByRole('tab',{name:'Personel listesi',exact:true}).count(),0);await page.getByRole('button',{name:'Kendi mesai raporum',exact:true}).click();assert.equal(await page.getByRole('tab',{name:'Finans',exact:true}).count(),0);
    await nav('Giriş terminali');assert.ok((await page.locator('.page-content').innerText()).includes('Çevrimdışı'));assert.equal(await page.getByLabel('Kart UID',{exact:true}).count(),0);
    const denied=await page.evaluate(async()=>{const {request}=await import('/src/api.mjs');await request('auth/csrf/');const results=[];for(const route of ['actions/saveSettings/','actions/savePlan/','actions/refund/']){try{await request(route,{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({payload:{}})});results.push(200);}catch(e){results.push(e.status);}}return results;});assert.deepEqual(denied,[403,403,403]);
    await page.reload();await page.locator('.sidebar').waitFor();assert.equal(await page.locator('.page-heading h1').innerText(),'Genel bakış');assert.equal((await state()).db.payments.length,1);
    await page.setViewportSize({width:390,height:844});await page.waitForTimeout(450);await page.getByRole('button',{name:'Menüyü aç',exact:true}).click();assert.equal(await page.locator('.sidebar.open nav button').count(),10);await page.getByRole('button',{name:'Menüyü kapat',exact:true}).click();await page.waitForTimeout(450);await page.screenshot({path:path.resolve('../outputs/panel-staff-mobile.png'),fullPage:true});assert.equal(await page.locator('.page-content').evaluate(n=>n.getBoundingClientRect().right<=innerWidth+2),true);
    const staffId=(await state()).db.employees[0].userId;assert.ok(staffId);assert.ok(paymentKey);await page.evaluate(({id,key})=>sessionStorage.setItem(`fitgate-pending:${id}`,JSON.stringify({key,signature:'a'.repeat(64)})),{id:staffId,key:paymentKey});
    await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await login('admin@test.com');await page.screenshot({path:path.resolve('../outputs/panel-admin-mobile.png'),fullPage:true});assert.equal((await state()).db.payments.length,2);assert.equal(await page.locator('.page-content').evaluate(n=>n.getBoundingClientRect().right<=innerWidth+2),true);assert.equal(await page.getByRole('button',{name:'Son işlemi doğrula',exact:true}).count(),0);
    await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await page.setViewportSize({width:1440,height:1000});await login('staff@test.com');await page.getByRole('button',{name:'Son işlemi doğrula',exact:true}).click();await page.getByText('İşlem kaydı doğrulandı.',{exact:true}).waitFor();assert.equal((await state()).db.payments.length,1);assert.equal(await page.evaluate(id=>sessionStorage.getItem(`fitgate-pending:${id}`),staffId),null);
    assert.deepEqual(errors,[]);
    console.log('Panel UI passed: preserved admin menu/dashboard, staff 10-item menu, member creation/detail, collection/own history/full debt, receipt, RFID assignment, booking, checkout/private costs, own attendance/report, real offline terminal, API denials, account switching, persistence, desktop/mobile. Isolated PostgreSQL only.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
