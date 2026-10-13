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
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route("**/api/**", (route) => route.abort());
    await page.route("**/finance-preview", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<div id="root"></div><script type="module" src="/tests/finance-preview.jsx"></script>',
      }),
    );
    await page.goto("http://127.0.0.1:5174/finance-preview");
    assert.equal(await page.locator(".metric").count(), 9);
    await page.getByRole("button", { name: "Ödeme al", exact: true }).click();
    let dialog = page.getByRole("dialog");
    await dialog.getByLabel("Ödenen tutar (TL)").fill("0.01");
    await dialog.getByLabel("Ödeme yöntemi").selectOption("pos");
    await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    const action = await page.evaluate(() => window.financeAction);
    assert.equal(action.type, "collect");
    assert.equal(action.payload.amount, "0.01");
    assert.equal(action.payload.method, "pos");
    assert.ok(action.payload.invoiceId);
    await page.getByLabel("Yöntem", { exact: true }).selectOption("pos");
    await page
      .getByRole("button", { name: "Tahsilat belgesini aç" })
      .first()
      .click();
    dialog = page.getByRole("dialog");
    await dialog
      .getByText("Bu belge resmi mali fatura veya e-Arşiv faturası değildir.")
      .waitFor();
    await page.emulateMedia({ media: "print" });
    assert.equal(
      await page
        .locator(".receipt-document")
        .evaluate((el) => getComputedStyle(el).visibility),
      "visible",
    );
    await page.emulateMedia({ media: "screen" });
    await dialog.getByRole("button", { name: "Kapat", exact: true }).click();
    await page
      .getByRole("button", { name: "Taksit düzenle", exact: true })
      .click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel("Taksit sayısı").fill("3");
    await dialog
      .getByRole("button", { name: "Plan oluştur", exact: true })
      .click();
    assert.equal(await dialog.locator("input[type=number]").count(), 4);
    await dialog
      .getByLabel("Plan değişikliği gerekçesi")
      .fill("QA repayment plan");
    await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    assert.equal(
      (await page.evaluate(() => window.financeAction)).type,
      "saveInstallments",
    );
    await page.screenshot({
      path: path.resolve("../outputs/finance-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.resolve("../outputs/finance-mobile.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
      "Mobile overflow",
    );
    await page.getByRole("button", { name: "Ödeme al", exact: true }).click();
    await page.screenshot({
      path: path.resolve("../outputs/finance-form-mobile.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
      "Mobile dialog overflow",
    );
    await page.addInitScript(() => (window.financeAdmin = false));
    await page.reload();
    assert.equal(
      await page.getByRole("button", { name: "İade", exact: true }).count(),
      0,
    );
    assert.equal(
      await page
        .getByRole("button", { name: "Ödeme bilgilerini düzelt" })
        .count(),
      0,
    );
    await page.addInitScript(() => (window.financeMember = true));
    await page.reload();
    await page.getByText("Tahsilat ve iade geçmişi", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "Tahsilat belgesini aç" })
      .first()
      .click();
    await page
      .getByRole("dialog")
      .getByText("Bu belge resmi mali fatura veya e-Arşiv faturası değildir.")
      .waitFor();
    assert.deepEqual(errors, []);
    console.log(
      "PASS: finance summaries, collection/sale selection, POS recording, receipt print, plan editing, admin controls, desktop/mobile. Isolated fixtures; no live mutations.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
