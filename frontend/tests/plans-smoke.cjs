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
      }),
      errors = [];
    page.on("pageerror", (err) => errors.push(err.message));
    await page.route("**/api/**", (route) => route.abort());
    await page.route("**/plans-preview", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<div id="root"></div><script type="module" src="/tests/plans-preview.jsx"></script>',
      }),
    );
    await page.goto("http://127.0.0.1:5174/plans-preview");
    await page
      .getByRole("button", { name: "Paket oluştur", exact: true })
      .click();
    let dialog = page.getByRole("dialog");
    await dialog
      .getByLabel("Paket türü", { exact: true })
      .selectOption("sessions");
    assert.equal(
      await dialog.getByLabel("Süre değeri", { exact: true }).count(),
      0,
    );
    await dialog.getByLabel("Paket adı", { exact: true }).fill("QA 10 Seans");
    await dialog
      .getByLabel("Satış fiyatı (TL)", { exact: true })
      .fill("2000.01");
    await dialog.getByLabel("Toplam seans hakkı", { exact: true }).fill("10");
    await dialog
      .getByRole("button", { name: "Kampanya ekle", exact: true })
      .click();
    await dialog.getByLabel("Kampanya 1 adı").fill("QA promotion");
    await dialog.getByLabel("Kampanya 1 başlangıcı").fill("2026-10-01");
    await dialog.getByLabel("Kampanya 1 bitişi").fill("2026-10-31");
    await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    const result = await page.evaluate(() => window.planAction);
    assert.equal(result.type, "savePlan");
    assert.equal(result.payload.kind, "sessions");
    assert.equal(result.payload.durationValue, 0);
    assert.equal(result.payload.sessions, 10);
    assert.equal(result.payload.campaigns.length, 1);
    await page.getByLabel("Paket ara", { exact: true }).fill("QA");
    const card = page.locator(".plan-item");
    assert.equal(await card.count(), 1);
    await card.getByRole("button", { name: "Düzenle", exact: true }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel("Satış fiyatı (TL)", { exact: true }).fill("3000");
    await dialog
      .getByLabel("Fiyat ve koşul değişikliklerini onaylıyorum")
      .check();
    await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    assert.equal(
      (await page.evaluate(() => window.planAction)).payload.confirmed,
      true,
    );
    await card
      .getByRole("button", { name: "Paketi pasife al", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Onayla", exact: true })
      .click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert.equal(
      (await page.evaluate(() => window.planAction)).payload.active,
      false,
    );
    await page.getByLabel("Durum", { exact: true }).selectOption("inactive");
    assert.equal(await card.count(), 1);
    await page
      .getByRole("button", { name: "Paket detayları", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByText("QA promotion", { exact: true })
      .waitFor();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Kapat", exact: true })
      .click();
    await page.getByLabel("Paket ara", { exact: true }).fill("");
    await page.getByLabel("Durum", { exact: true }).selectOption("all");
    await page.screenshot({
      path: path.resolve("../outputs/plans-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.resolve("../outputs/plans-mobile.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
    );
    await page
      .getByRole("button", { name: "Paket oluştur", exact: true })
      .click();
    dialog = page.getByRole("dialog");
    await dialog
      .getByLabel("Paket türü", { exact: true })
      .selectOption("hybrid");
    await dialog.getByLabel("Toplam dondurma hakkı (gün)").fill("14");
    await dialog
      .getByRole("button", { name: "Kampanya ekle", exact: true })
      .click();
    await page.screenshot({
      path: path.resolve("../outputs/plans-form-mobile.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS: plan types/dynamic form, campaign, confirmation, passive/history, search/filters/detail, desktop/mobile. Isolated fixture; no live mutation.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
