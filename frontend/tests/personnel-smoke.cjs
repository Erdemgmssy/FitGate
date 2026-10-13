const {chromium}=require('./playwright-runtime.cjs');
const assert=require('node:assert/strict');
const path=require('node:path');

(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    // Never send a mutation to the live FitGate database.
    await page.route('**/api/v1/**',async route=>route.fulfill({response:await route.fetch({url:route.request().url().replace('127.0.0.1:5174','127.0.0.1:8002')})}));
    async function login(email) {
      await page.locator('input[name=email]').fill(email);
      await page.locator('input[name=password]').fill('LongTest123!');
      await page.locator('button[type=submit]').click();await page.locator('.sidebar').waitFor();
    }
    async function save() {const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Kaydet',exact:true}).click();await dialog.waitFor({state:'hidden'});}
    async function state() {return page.evaluate(async()=>(await fetch('/api/v1/state/')).json());}
    async function tab(name) {await page.getByRole('tab',{name,exact:true}).click();}
    await page.goto('http://127.0.0.1:5174/');await login('admin@test.com');
    await page.locator('.sidebar button[title="Personel ve mesai"]').click();
    await page.getByRole('button',{name:'Yeni personel',exact:true}).click();
    let dialog=page.getByRole('dialog');const unique=Date.now(),name='Personnel QA '+unique,email=`personnel-${unique}@example.com`,uid='PQA-'+unique;
    await dialog.locator('input[name=name]').fill(name);
    await dialog.locator('input[name=phone]').fill('05'+String(unique).slice(-9));
    await dialog.locator('input[name=email]').fill(email);
    await dialog.locator('input[name=jobTitle]').fill('Resepsiyon görevlisi');
    await dialog.locator('input[name=startDate]').fill('2020-01-01');
    await dialog.locator('input[name=card]').fill(uid);
    await dialog.getByLabel('Giriş hesabı oluştur').check();
    await dialog.locator('input[name=password]').fill('LongTest123!');
    await dialog.locator('input[type=file]').setInputFiles({name:'employee.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jBCEAAAAASUVORK5CYII=','base64')});
    await save();
    let data=await state();const employee=data.db.employees.find(e=>e.email===email);assert.ok(employee.userId);assert.equal(employee.card,uid);
    await page.getByRole('searchbox',{name:'Personel ara'}).fill(name);
    await page.locator('.personnel-detail h2').filter({hasText:name}).waitFor();
    await page.screenshot({path:path.resolve('../outputs/personnel-admin-desktop.png'),fullPage:true});
    await tab('Kurallar ve yetkiler');
    await page.getByRole('button',{name:'Yetkileri düzenle: Resepsiyon',exact:true}).click();dialog=page.getByRole('dialog');
    await dialog.getByLabel('Kendi manuel mesai işlemi').check();await dialog.getByLabel('Kontrollü simülasyon').check();await save();
    await page.getByRole('button',{name:'Kuralları düzenle',exact:true}).click();dialog=page.getByRole('dialog');await dialog.locator('input[name=duplicateSeconds]').fill('1');await save();
    await tab('Vardiyalar');await page.getByRole('button',{name:'Vardiya oluştur',exact:true}).click();dialog=page.getByRole('dialog');
    await dialog.getByRole('combobox',{name:'Personel',exact:true}).selectOption(employee.id);
    const tomorrow=await page.evaluate(async()=>{const {trDay,plusDay}=await import('/src/personnel-rules.mjs');return plusDay(trDay(),1);});
    await dialog.locator('input[name=day]').fill(tomorrow);await dialog.locator('input[name=from]').fill('22:00');await dialog.locator('input[name=to]').fill('06:00');await save();
    data=await state();const planned=data.db.personnel.plannedShifts.find(p=>p.employeeId===employee.id);assert.equal(new Date(planned.end)-new Date(planned.start),8*3600000);
    await tab('İzin yönetimi');await page.getByRole('button',{name:'İzin türü ekle',exact:true}).click();dialog=page.getByRole('dialog');
    await dialog.locator('input[name=name]').fill('Configured QA leave');await dialog.locator('input[name=annualDays]').fill('12');await save();
    await page.reload();await page.locator('.sidebar button[title="Personel ve mesai"]').click();assert.ok((await state()).db.employees.some(e=>e.id===employee.id));
    await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await login(email);
    await page.locator('.sidebar button[title="Mesailerim"]').click();
    assert.equal(await page.locator('.personnel-page .metric').count(),4);
    assert.equal(await page.getByRole('tab',{name:'Personel listesi',exact:true}).count(),0);
    data=await state();assert.deepEqual(data.db.employees.map(e=>e.id),[employee.id]);assert.equal(data.db.personnel.accounts.length,0);
    await tab('Vardiyalarım');assert.ok((await page.locator('.personnel-page').innerText()).includes('22:00 - 06:00'));
    await tab('Mesai geçmişim');await page.getByRole('button',{name:'Manuel mesai',exact:true}).click();dialog=page.getByRole('dialog');await dialog.locator('textarea[name=reason]').fill('Manual QA entry');await save();
    await page.getByRole('button',{name:'Mola başlat',exact:true}).click();await page.getByRole('button',{name:'Molayı bitir',exact:true}).click();await page.waitForTimeout(1100);
    await page.getByRole('button',{name:'Manuel mesai',exact:true}).click();dialog=page.getByRole('dialog');await dialog.locator('select[name=direction]').selectOption('exit');await dialog.locator('textarea[name=reason]').fill('Manual QA exit');await save();
    data=await state();assert.ok(data.db.shifts.find(s=>s.employeeId===employee.id&&!s.simulated)?.exit);assert.ok(data.db.personnel.shiftMetrics[0].workedMs>=0);
    const forbidden=await page.evaluate(async(id)=>{const {operation,request}=await import('/src/api.mjs');await request('auth/csrf/');try{await operation('saveEmployee',{id,name:'Forbidden'});return 200;}catch(error){return error.status;}},employee.id);assert.equal(forbidden,403);
    await page.waitForTimeout(1100);await page.getByLabel('Simülasyon kart UID').fill(uid);await page.getByRole('button',{name:'Kart okumayı simüle et',exact:true}).click();
    await page.locator('.personnel-simulation .success-message').waitFor();
    const before=(await state()).db.shifts.length;
    await page.getByRole('button',{name:'Kart okumayı simüle et',exact:true}).click();await page.locator('.personnel-simulation .form-error').waitFor();assert.equal((await state()).db.shifts.length,before);
    await page.waitForTimeout(1100);await page.getByRole('button',{name:'Kart okumayı simüle et',exact:true}).click();await page.locator('.personnel-simulation .success-message').waitFor();
    await tab('İzinlerim');await page.getByRole('button',{name:'İzin talebi',exact:true}).click();dialog=page.getByRole('dialog');await dialog.locator('input[name=start]').fill(tomorrow);await dialog.locator('input[name=end]').fill(tomorrow);await dialog.locator('textarea[name=reason]').fill('QA leave request');await save();
    await tab('Mesai geçmişim');await page.screenshot({path:path.resolve('../outputs/personnel-worker-desktop.png'),fullPage:true});
    const download=page.waitForEvent('download');await page.getByRole('button',{name:'Mesai CSV indir',exact:true}).click();assert.ok((await download).suggestedFilename().endsWith('.csv'));
    await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);await page.screenshot({path:path.resolve('../outputs/personnel-worker-mobile.png'),fullPage:true});assert.equal(await page.locator('.personnel-page').evaluate(node=>node.getBoundingClientRect().right<=innerWidth+2),true);
    await page.reload();await page.locator('.sidebar').waitFor();await page.getByRole('button',{name:'Menüyü aç',exact:true}).click();await page.locator('.sidebar button[title="Mesailerim"]').click();assert.equal((await state()).db.shifts.length,2);
    await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await login('admin@test.com');await page.getByRole('button',{name:'Menüyü aç',exact:true}).click();await page.locator('.sidebar button[title="Personel ve mesai"]').click();
    await tab('İzin yönetimi');await page.getByRole('button',{name:'İzni onayla',exact:true}).click();dialog=page.getByRole('dialog');await dialog.locator('textarea[name=reason]').fill('QA coverage checked');await save();assert.ok((await state()).db.personnel.leaveRequests.some(r=>r.employeeId===employee.id&&r.status==='approved'));
    await tab('Mesai takibi');await page.getByRole('combobox',{name:'Personel',exact:true}).selectOption(employee.id);await page.getByRole('button',{name:'Mesai düzelt',exact:true}).click();dialog=page.getByRole('dialog');await dialog.locator('textarea[name=reason]').fill('QA verified correction');await save();
    assert.ok((await state()).db.audit.some(a=>a.type==='correctAttendance'));
    const trainerEmail=`trainer-${unique}@example.com`;
    await page.evaluate(async email=>{const {operation,request}=await import('/src/api.mjs');await request('auth/csrf/');await operation('saveEmployee',{name:'Trainer QA',email,role:'trainer',createAccount:true,password:'LongTest123!'});},trainerEmail);
    await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await login(trainerEmail);
    for(const title of ['Üye yönetimi','Ödemeler','Cihaz durumu','Ayarlar'])assert.equal(await page.locator(`.sidebar button[title="${title}"]`).count(),0);
    assert.equal(await page.getByRole('tab',{name:'Vardiyalarım',exact:true}).count(),1);
    assert.deepEqual(errors,[]);
    console.log('Personnel UI passed: create/photo/card/account, overnight schedule, role policy/rules, own-only staff data, manual entry/exit, breaks, explicit simulation/repeated scan, leave approval, correction audit, CSV, persistence, trainer access, desktop/mobile. Isolated PostgreSQL only.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
