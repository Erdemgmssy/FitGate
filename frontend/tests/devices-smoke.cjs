const {
  chromium,
} = require("./playwright-runtime.cjs");
const assert = require("node:assert/strict");
const path = require("node:path");

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    // Isolated rendering fixtures only; no request may reach the real API.
    await page.route("**/api/**", (route) => route.abort());
    await page.route("**/device-preview", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<html><body><div id="root"></div><script type="module" src="/tests/device-preview.jsx"></script></body></html>',
      }),
    );
    const now = new Date().toISOString();
    await page.addInitScript(
      (fixture) => {
        window.deviceFixture = fixture;
      },
      {
        devices: [
          {
            id: "real",
            code: "QA-REAL",
            name: "Arduino QA fixture",
            model: "UNO",
            status: "online",
            purpose: "access",
            mode: "auto",
            sensor: "fault",
            lastSeen: now,
            telemetryAt: now,
            telemetry: {
              port: "COM6",
              connection: "connected",
              rfid: "ready",
              servo: "closed",
              outsideCm: null,
              insideCm: 22,
              passageState: "detected",
              detectedDirection: "entry",
              progressAt: now,
            },
            lastError: "Dış sensör ölçümü yok",
          },
          {
            id: "offline",
            code: "QA-OFF",
            name: "Offline QA fixture",
            status: "offline",
            telemetry: { rfid: "ready", servo: "open" },
            purpose: "access",
          },
          {
            id: "sim",
            code: "QA-SIM",
            name: "Simulation QA fixture",
            status: "online",
            simulated: true,
            telemetry: { rfid: "ready", servo: "open" },
          },
        ],
        attempts: [],
        deviceEvents: [],
      },
    );
    await page.goto("http://127.0.0.1:5174/device-preview");
    await page.getByText("Arduino QA fixture", { exact: true }).waitFor();
    const real = page.locator(".device-item").nth(0),
      offline = page.locator(".device-item").nth(1),
      sim = page.locator(".device-item").nth(2);
    assert.ok((await real.innerText()).includes("22 cm"));
    assert.ok((await real.innerText()).includes("Geçerli ölçüm yok"));
    assert.ok((await real.innerText()).includes("Giriş algılandı"));
    assert.ok((await real.innerText()).includes("İkinci sensör bekleniyor"));
    assert.ok((await offline.innerText()).includes("Veri yok"));
    assert.ok(!(await offline.innerText()).includes("Yanıt veriyor"));
    assert.ok(!(await sim.innerText()).includes("Yanıt veriyor"));
    await real.getByRole("combobox").selectOption("attendance");
    assert.deepEqual(await page.evaluate(() => window.deviceAction), {
      action: "devicePurpose",
      payload: { id: "real", purpose: "attendance" },
    });
    await real.getByRole("button", {name: "Donanım testi"}).click();
    const diagnostic = page.getByRole("dialog");
    await diagnostic.getByRole("combobox").selectOption("indicators");
    await diagnostic.getByRole("checkbox").check();
    await diagnostic.getByRole("button", {name: "Kaydet", exact: true}).click();
    await diagnostic.waitFor({state: "hidden"});
    assert.deepEqual(await page.evaluate(() => window.deviceAction), {
      action: "queueDeviceDiagnostic",
      payload: {deviceId: "real", action: "indicators", confirmed: true},
    });
    await real.getByRole("button", { name: "Olay geçmişi" }).click();
    await page.getByText("Cihaz olayları", { exact: true }).waitFor();
    await page.screenshot({
      path: path.resolve("../outputs/arduino-devices-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.resolve("../outputs/arduino-devices-mobile.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
      "Mobile layout must not overflow",
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS: device fixture rendering, real/offline/simulation separation, reported components, sensor fault, purpose action, desktop/mobile layout. No live mutation.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
