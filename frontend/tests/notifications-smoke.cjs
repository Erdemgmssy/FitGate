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
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/api/**", (r) => r.abort());
    await page.route(
      (url) => url.pathname === "/notifications-preview",
      (r) =>
        r.fulfill({
          contentType: "text/html",
          body: '<div id="root"></div><script type="module" src="/tests/notifications-preview.jsx"></script>',
        }),
    );
    const url = "http://127.0.0.1:5174/notifications-preview";
    await page.goto(url);
    await page.locator(".notice-row").first().waitFor();
    assert.equal(await page.locator(".notice-row").count(), 3);
    assert.match(
      await page.locator(".notice-row").first().innerText(),
      /Turnike RFID/,
    );
    await page.screenshot({
      path: path.resolve("../outputs/bildirimler-desktop.png"),
      fullPage: true,
    });
    await page
      .getByLabel("Bildirim türü", { exact: true })
      .selectOption("class");
    assert.equal(await page.locator(".notice-row").count(), 1);
    await page
      .getByRole("button", { name: "Yaklaşan Yoga dersi", exact: true })
      .click();
    assert.deepEqual(await page.evaluate(() => window.navigation), {
      page: "classes",
      memberId: undefined,
      targetId: "class-1",
    });
    await page.getByText("Bu filtrelerle bildirim bulunamadı.").waitFor();
    await page
      .getByLabel("Okunma durumu", { exact: true })
      .selectOption("read");
    assert.equal(await page.locator(".notice-row").count(), 1);
    await page.getByLabel("Bildirim türü", { exact: true }).selectOption("");
    await page.getByLabel("Okunma durumu", { exact: true }).selectOption("");
    await page.getByLabel("Başlangıç", { exact: true }).fill("2026-10-13");
    await page.getByLabel("Bitiş", { exact: true }).fill("2026-10-13");
    assert.equal(await page.locator(".notice-row").count(), 2);
    await page.getByLabel("Başlangıç", { exact: true }).fill("");
    await page.getByLabel("Bitiş", { exact: true }).fill("");
    await page
      .getByLabel("Bildirim durumu", { exact: true })
      .selectOption("resolved");
    assert.equal(await page.locator(".notice-row").count(), 1);
    assert.match(await page.locator(".notice-row").innerText(), /Çözüldü/);
    await page
      .getByLabel("Bildirim durumu", { exact: true })
      .selectOption("active");
    await page
      .getByLabel("Bildirim türü", { exact: true })
      .selectOption("device");
    await page.evaluate(() => (window.failRead = true));
    await page
      .getByRole("button", { name: "İlgili kayıt", exact: true })
      .click();
    await page
      .getByRole("alert")
      .filter({ hasText: "Bağlantı hatası" })
      .waitFor();
    assert.equal(await page.locator(".notice-row").count(), 1);
    await page.evaluate(() => (window.failRead = false));
    await page
      .getByRole("button", { name: "İlgili kayıt", exact: true })
      .click();
    assert.equal(
      (await page.evaluate(() => window.navigation)).targetId,
      "device-1",
    );
    await page.goto(url + "?staff");
    await page
      .getByRole("button", { name: "Panel bildirimi oluştur", exact: true })
      .click();
    assert.equal(
      await page
        .getByLabel("Önem derecesi", { exact: true })
        .last()
        .locator('option[value="critical"]')
        .count(),
      0,
    );
    await page.getByRole("button", { name: "Kapat", exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.resolve("../outputs/bildirimler-mobile.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "Mobile horizontal overflow",
    );
    for (const row of await page.locator(".notice-row").all()) {
      const bounds = await row.boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 390);
    }
    assert.deepEqual(errors, []);
    console.log(
      "PASS: severity, read/type/date/status filters, resolution, navigation, failure, staff compose permissions, desktop/mobile layout",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
