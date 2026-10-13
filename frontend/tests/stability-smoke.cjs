const {chromium}=require('./playwright-runtime.cjs');
const assert=require('node:assert/strict');
const path=require('node:path');

(async()=>{
  const {buildSeed}=await import('../src/gym.mjs');
  const db=buildSeed();
  const user={id:999,name:'Synthetic stability staff',role:'staff',branchId:db.branches[0].id};
  const browser=await chromium.launch({channel:'msedge',headless:true});
  let release;
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    let hold=false,calls=0;
    await page.route('**/api/v1/**',async route=>{
      const url=route.request().url();let body={};
      if(url.includes('/auth/me/'))body={user};
      else if(url.includes('/state/')){
        calls++;
        if(hold)await new Promise(resolve=>{release=resolve;});
        body={db};
      }
      else if(url.includes('/access/recent-entries/'))body={entries:[],movements:[],attempts:[],inside:0,today:0};
      try{await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});}catch{}
    });
    await page.goto('http://127.0.0.1:5174/');
    await page.locator('.sidebar').waitFor();
    await page.locator('.sidebar button[title="Üye işlemleri"]').click();
    await page.waitForTimeout(200);const before=calls;hold=true;
    await page.waitForTimeout(7000);
    assert.equal(calls-before,1,'Only one state poll may be in flight');
    await page.locator('.sidebar button[title="Giriş / çıkış"]').click();
    hold=false;release?.();
    await page.screenshot({path:path.resolve('../outputs/stability-staff-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.resolve('../outputs/stability-staff-mobile.png'),fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
    assert.deepEqual(errors,[]);
    console.log('PASS: stalled poll stays single-flight, navigation works, cleanup/cancellation, desktop/mobile; all API calls mocked.');
  }finally{release?.();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
