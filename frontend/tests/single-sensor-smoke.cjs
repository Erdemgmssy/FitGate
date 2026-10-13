const {chromium}=require('./playwright-runtime.cjs');
const assert=require('node:assert/strict');
const path=require('node:path');

(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[]; page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/api/**',route=>route.abort());
    await page.route('**/prototype-preview',route=>route.fulfill({contentType:'text/html',body:'<html><body><div id="root"></div><script type="module" src="/tests/device-preview.jsx"></script></body></html>'}));
    await page.addInitScript(()=>{const now=new Date().toISOString();window.deviceFixture={
      devices:[{id:'proto',code:'PROTO-UI-TEST',name:'Synthetic prototype reader',model:'UNO',status:'online',
        purpose:'mixed',mode:'auto',sensor:'ready',lastSeen:now,telemetryAt:now,
        lastPassageValidationMode:'single_sensor_prototype',lastPassageAt:now,
        telemetry:{firmware:'7',validationMode:'single_sensor_prototype',outsideCm:20,insideCm:80,
          rfid:'ready',servo:'open',passageState:'prototype_triggered',detectedDirection:'entry',progressAt:now}}],
      attempts:[],deviceEvents:[],deviceCommands:[]};});
    await page.goto('http://127.0.0.1:5174/prototype-preview');
    const device=page.locator('.device-item'); await device.waitFor();
    const text=await device.innerText();
    assert.ok(text.includes('tam fiziksel geçiş kanıtı değildir'));
    assert.ok(text.includes('Tek sensör olayı; güvenli kapanma bekleniyor'));
    assert.ok(text.includes('Ziyaretten belirlenen yön'));
    assert.ok(text.includes('Son prototip olayı'));
    assert.ok(text.includes('20 cm')&&text.includes('80 cm'));
    assert.ok(!text.includes('İkinci sensör bekleniyor'));
    await page.screenshot({path:path.resolve('../outputs/single-sensor-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.resolve('../outputs/single-sensor-mobile.png'),fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
    assert.deepEqual(errors,[]);
    console.log('PASS: explicit prototype warning, single trigger at 20 cm with other sensor 80 cm, visit-derived direction, weak evidence label, desktop/mobile. Mock UI only; no hardware or live writes.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
