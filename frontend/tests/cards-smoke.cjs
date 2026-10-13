const {
  chromium,
} = require("./playwright-runtime.cjs");
const assert = require("node:assert/strict");
const path = require("node:path");

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 850 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/**", (route) => route.abort());
    await page.route("**/cards-preview", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: '<html><body><div id="root"></div><script type="module" src="/tests/cards-preview.jsx"></script></body></html>',
      }),
    );
    await page.goto("http://127.0.0.1:5174/cards-preview");
    await page
      .getByRole("button", { name: "Kartı teslim al", exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "Kartı teslim al" });
    await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
    assert.equal(await dialog.count(), 1);
    await dialog.getByLabel("Kart fiziksel olarak teslim alındı").check();
    await dialog.getByRole("button", { name: "Kaydet", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    let state = await page.evaluate(() => window.cardsPreviewState),
      card = state.cards.find((row) => row.id === "c1");
    assert.equal(card.memberId, null);
    assert.equal(card.status, "available");
    assert.equal(await page.locator(".card-record").count(), 0);
    await page.getByLabel("Üye", { exact: true }).selectOption("m2");
    await page
      .getByLabel("Teslim alınan boş kartlar", { exact: true })
      .selectOption(card.uid);
    assert.equal(
      await page.getByLabel("Kart UID", { exact: true }).inputValue(),
      card.uid,
    );
    await page.getByRole("button", { name: "Ata", exact: true }).click();
    await page.getByText(card.uid, { exact: true }).waitFor();
    state = await page.evaluate(() => window.cardsPreviewState);
    assert.equal(state.cards[0].memberId, "m2");
    assert.equal(state.cards.length, 1);
    assert.equal(state.visits[0].memberId, "m1");
    await page.screenshot({
      path: path.resolve("../outputs/cards-reuse-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.resolve("../outputs/cards-reuse-mobile.png"),
      fullPage: true,
    });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 2,
      ),
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS: explicit return confirmation, old owner detached, stock selection, same UID reassigned, old visit retained, desktop/mobile. Isolated fixture; no live mutation.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
