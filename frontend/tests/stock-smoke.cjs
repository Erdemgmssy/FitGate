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
    await page.route("**/stock-preview", (r) =>
      r.fulfill({
        contentType: "text/html",
        body: '<div id="root"></div><script type="module" src="/tests/stock-preview.jsx"></script>',
      }),
    );
    await page.goto("http://127.0.0.1:5174/stock-preview");
    await page
      .getByLabel("Ürün adı veya barkod", { exact: true })
      .fill("8690001");
    await page
      .getByLabel("Ürün adı veya barkod", { exact: true })
      .press("Enter");
    await page
      .getByRole("button", { name: "Sepete ekle: Protein Bar", exact: true })
      .click();
    await page.getByRole("button", { name: "Artır: Su", exact: true }).click();
    await page.getByLabel("İndirim (TL)", { exact: true }).fill("1.01");
    await page.getByLabel("İndirim gerekçesi").fill("QA promotion");
    await page.getByLabel("Ödeme yöntemi", { exact: true }).selectOption("pos");
    await page.screenshot({
      path: path.resolve("../outputs/stock-desktop.png"),
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Satışı tamamla", exact: true })
      .click();
    let d = page.getByRole("dialog");
    await d
      .getByRole("heading", { name: "Ürün satış belgesi", exact: true })
      .waitFor();
    const action = await page.evaluate(() => window.stockAction);
    assert.equal(action.type, "checkoutProducts");
    assert.equal(action.payload.items.length, 2);
    assert.equal(action.payload.items[0].quantity, 2);
    assert.equal(action.payload.discount, "1.01");
    assert.equal(action.payload.method, "pos");
    await d
      .getByText("Bu belge resmi mali fatura veya e-Arşiv faturası değildir.", {
        exact: true,
      })
      .waitFor();
    await page.emulateMedia({ media: "print" });
    assert.equal(await page.locator(".stock-receipt").isVisible(), true);
    await page.screenshot({
      path: path.resolve("../outputs/stock-receipt.png"),
      fullPage: true,
    });
    await page.emulateMedia({ media: "screen" });
    await d.getByRole("button", { name: "Kapat", exact: true }).click();
    await page.getByRole("tab", { name: "Satış Geçmişi", exact: true }).click();
    await page.getByRole("button", { name: "Su iade", exact: true }).click();
    d = page.getByRole("dialog");
    await d.getByLabel("Ürün satılabilir durumda, stoğa geri al").uncheck();
    await d.getByLabel("İade gerekçesi").fill("Damaged");
    await d.getByRole("button", { name: "Kaydet", exact: true }).click();
    await d.waitFor({ state: "hidden" });
    assert.equal(
      (await page.evaluate(() => window.stockAction)).payload.restock,
      false,
    );
    await page.getByRole("tab", { name: "Ürünler", exact: true }).click();
    await page
      .getByRole("button", { name: "Ürünü düzenle: Su", exact: true })
      .click();
    d = page.getByRole("dialog");
    assert.equal(await d.getByLabel("Açılış stok", { exact: true }).count(), 0);
    await d.getByLabel("Satış fiyatı (TL)", { exact: true }).fill("15");
    await d.getByRole("button", { name: "Kaydet", exact: true }).click();
    await d.waitFor({ state: "hidden" });
    await page
      .getByRole("button", { name: "Stok işlemi", exact: true })
      .first()
      .click();
    d = page.getByRole("dialog");
    await d.getByLabel("Stok işlem türü").selectOption("count");
    await d.getByLabel("Sayılan miktar").fill("7");
    await d.getByLabel("İşlem gerekçesi").fill("Physical count");
    await d.getByRole("button", { name: "Kaydet", exact: true }).click();
    await d.waitFor({ state: "hidden" });
    assert.equal(
      (await page.evaluate(() => window.stockAction)).payload.kind,
      "count",
    );
    await page.getByRole("tab", { name: "Tedarikçiler", exact: true }).click();
    await page
      .getByRole("button", { name: "Alış geçmişi", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Kapat", exact: true })
      .click();
    await page.getByRole("tab", { name: "Hızlı Satış", exact: true }).click();
    await page
      .getByRole("button", { name: "Sepete ekle: Su", exact: true })
      .click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.resolve("../outputs/stock-mobile.png"),
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
      ),
      false,
      "page overflow",
    );
    await page.getByRole("tab", { name: "Ürünler", exact: true }).click();
    await page.getByRole("button", { name: "Ürün ekle", exact: true }).click();
    await page.screenshot({
      path: path.resolve("../outputs/stock-mobile-form.png"),
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () =>
          document.querySelector('[role="dialog"]').getBoundingClientRect()
            .width > innerWidth,
      ),
      false,
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS: barcode/cart/multiple items/discount/POS/receipt/return/product/count/supplier and desktop/mobile. Isolated fixtures; no live mutations.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
