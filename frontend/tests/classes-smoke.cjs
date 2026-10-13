const {
  chromium,
} = require("./playwright-runtime.cjs");
const assert = require("node:assert/strict"),
  path = require("node:path");
(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({
        viewport: { width: 1440, height: 1000 },
      }),
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/api/**", (r) => r.abort());
    await page.route("**/classes-preview", (r) =>
      r.fulfill({
        contentType: "text/html",
        body: '<div id="root"></div><script type="module" src="/tests/classes-preview.jsx"></script>',
      }),
    );
    await page.goto("http://127.0.0.1:5174/classes-preview");
    await page
      .getByRole("button", { name: "Ders oluştur", exact: true })
      .click();
    let d = page.getByRole("dialog");
    await d.getByLabel("Ders adı", { exact: true }).fill("Yoga QA");
    await d.getByLabel("Antrenör", { exact: true }).selectOption("trainer-1");
    await d.getByLabel("Salon / stüdyo", { exact: true }).fill("Stüdyo B");
    await d
      .getByLabel("Başlangıç (Türkiye saati)", { exact: true })
      .fill("2026-11-03T16:30");
    await d.getByLabel("Haftalık tekrar sayısı").fill("4");
    await d.getByRole("button", { name: "Kaydet", exact: true }).click();
    await d.waitFor({ state: "hidden" });
    assert.equal(
      (await page.evaluate(() => window.classAction)).payload.at,
      "2026-11-03T16:30:00+03:00",
    );
    assert.equal(
      (await page.evaluate(() => window.classAction)).payload.repeatCount,
      "4",
    );
    await page
      .getByRole("button", { name: "Özel ders oluştur", exact: true })
      .click();
    d = page.getByRole("dialog");
    assert.equal(await d.getByLabel("Kontenjan", { exact: true }).count(), 0);
    await d.getByRole("button", { name: "Vazgeç", exact: true }).click();
    await page
      .getByRole("row")
      .filter({ hasText: "Pilates" })
      .getByRole("button", { name: "Detaylar", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Rezervasyon ekle", exact: true })
      .click();
    d = page.getByRole("dialog");
    await d.getByLabel("Üye", { exact: true }).selectOption({ index: 1 });
    await d
      .getByRole("button", { name: "Rezervasyon oluştur", exact: true })
      .click();
    await d.waitFor({ state: "hidden" });
    assert.equal((await page.evaluate(() => window.classAction)).type, "book");
    await page.getByText("Ayrıldı", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "Rezervasyon geçmişi", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByText("Pilates", { exact: true })
      .waitFor();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Kapat", exact: true })
      .click();
    await page.screenshot({
      path: path.resolve("../outputs/classes-desktop.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Ay", exact: true }).click();
    assert.equal(await page.locator(".lesson-day").count(), 42);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.resolve("../outputs/classes-mobile.png"),
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
      ),
      false,
      "page overflow",
    );
    await page
      .getByRole("button", { name: "Ders oluştur", exact: true })
      .click();
    await page.screenshot({
      path: path.resolve("../outputs/classes-mobile-form.png"),
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(() => {
        const el = document.querySelector('[role="dialog"]');
        return el.getBoundingClientRect().width > innerWidth;
      }),
      false,
    );
    assert.deepEqual(errors, []);
    console.log(
      "Classes desktop/mobile, create/recurring/private/booking/calendar checks passed.",
    );
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
