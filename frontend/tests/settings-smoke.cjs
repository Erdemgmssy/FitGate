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
    await page.route(
      (u) => u.pathname === "/settings-preview",
      (r) =>
        r.fulfill({
          contentType: "text/html",
          body: '<div id="root"></div><script type="module" src="/tests/settings-preview.jsx"></script>',
        }),
    );
    await page.goto("http://127.0.0.1:5174/settings-preview");
    const section = (name) =>
      page
        .getByRole("navigation", { name: "Ayar bölümleri" })
        .getByRole("button", { name, exact: true })
        .click();
    const save = () =>
      page.getByRole("button", { name: "Kaydet", exact: true });
    await page.getByLabel("Salon adı", { exact: true }).waitFor();
    assert.ok(await save().isDisabled());
    await page.getByLabel("Salon adı", { exact: true }).fill("Yeni Salon");
    assert.ok(await save().isEnabled());
    await page.getByRole("button", { name: "İptal", exact: true }).click();
    assert.equal(
      await page.getByLabel("Salon adı", { exact: true }).inputValue(),
      "FitGate Salon",
    );
    await page.getByLabel("Salon adı", { exact: true }).fill("Yeni Salon");
    await save().click();
    await page
      .getByRole("button", { name: "Onayla ve kaydet", exact: true })
      .click();
    await page.getByRole("status").waitFor();
    assert.ok(await save().isDisabled());
    assert.equal(
      (await page.evaluate(() => window.settingsAction)).action,
      "saveBranchProfile",
    );
    await section("Çalışma Saatleri");
    await page.getByLabel("Açılış saati", { exact: true }).fill("22:00");
    await save().click();
    await page.evaluate(() => (window.failSettings = true));
    await page
      .getByRole("button", { name: "Onayla ve kaydet", exact: true })
      .click();
    await page.getByRole("dialog").getByRole("alert").waitFor();
    await page.getByRole("button", { name: "Vazgeç", exact: true }).click();
    assert.equal(
      await page.getByLabel("Açılış saati", { exact: true }).inputValue(),
      "22:00",
    );
    await page.evaluate(() => (window.failSettings = false));
    await section("Fiyatlandırma");
    const price = page.locator(".price-input input").first();
    const original = await price.inputValue();
    assert.ok(
      await page
        .getByRole("button", { name: "Değişiklikleri kaydet", exact: true })
        .isDisabled(),
    );
    await price.fill(String(Number(original) + 1));
    await page
      .getByLabel("Fiyat ve ücret değişikliklerini onaylıyorum")
      .check();
    await page
      .getByRole("button", { name: "Değişiklikleri kaydet", exact: true })
      .click();
    await page.getByRole("dialog").waitFor();
    await page
      .getByRole("button", { name: "Onayla ve kaydet", exact: true })
      .click();
    assert.equal(
      (await page.evaluate(() => window.settingsAction)).action,
      "saveRates",
    );
    await section("Kullanıcı ve Rol Yönetimi");
    await page
      .getByRole("button", { name: "Düzenle / kilitle", exact: true })
      .last()
      .click();
    await page
      .getByLabel("İşlem gerekçesi", { exact: true })
      .fill("Hesap kilitlenecek");
    await page
      .getByLabel("Hesap aktif; kapatıldığında giriş kilitlenir")
      .uncheck();
    await save().last().click();
    await page
      .getByRole("button", { name: "Onayla ve kaydet", exact: true })
      .click();
    assert.equal(
      (await page.evaluate(() => window.settingsAction)).p.active,
      false,
    );
    await section("Güvenlik");
    assert.match(await page.locator(".settings-body").innerText(), /Argon2/);
    assert.ok(await save().isDisabled());
    await section("Cihaz Yapılandırması");
    assert.match(
      await page.locator(".settings-body").innerText(),
      /Çevrimdışı/,
    );
    assert.match(
      await page.locator(".settings-body").innerText(),
      /Simülasyon/,
    );
    await page
      .getByRole("button", { name: "Cihazı yönet", exact: true })
      .first()
      .click();
    assert.equal((await page.evaluate(() => window.destination))[2], "d1");
    await section("Bildirim Tercihleri");
    await page
      .getByLabel("Üyelik bitişinden kaç gün önce", { exact: true })
      .fill("14");
    await save().click();
    await page
      .getByRole("button", { name: "Onayla ve kaydet", exact: true })
      .click();
    assert.equal(
      (await page.evaluate(() => window.settingsAction)).p.membershipDays,
      14,
    );
    await section("Veri ve Yedekleme");
    assert.match(
      await page.locator(".settings-body").innerText(),
      /PostgreSQL bağlantısı doğrulandı/,
    );
    assert.equal(await page.locator('a[href$=".dump"]').count(), 0);
    await page.screenshot({
      path: path.resolve("../outputs/ayarlar-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    for (const name of [
      "Salon Bilgileri",
      "Çalışma Saatleri",
      "Fiyatlandırma",
      "Kullanıcı ve Rol Yönetimi",
      "Güvenlik",
      "Cihaz Yapılandırması",
      "Bildirim Tercihleri",
      "Veri ve Yedekleme",
    ]) {
      await section(name);
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        "Overflow: " + name,
      );
    }
    await section("Bildirim Tercihleri");
    await page.screenshot({
      path: path.resolve("../outputs/ayarlar-mobile.png"),
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    console.log(
      "PASS: eight settings sections, dirty/cancel, confirmation, validation failure, pricing, account lock, device routing, preferences, backup metadata, desktop/mobile",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
