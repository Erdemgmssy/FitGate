const {
  chromium,
} = require("./playwright-runtime.cjs");
const assert = require("node:assert/strict"),
  path = require("node:path");
(async () => {
  const {email,password}=require('./smoke-credentials.cjs').configuredCredentials();
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({
        viewport: { width: 1440, height: 1000 },
      }),
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("http://127.0.0.1:5174/");
    await page
      .getByLabel("E-posta", { exact: true })
      .fill(email);
    await page
      .getByLabel("Şifre", { exact: true })
      .fill(password);
    await page.getByRole("button", { name: "Giriş yap", exact: true }).click();
    await page
      .getByRole("heading", { name: "Giriş yoğunluğu", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "Raporlar", exact: true }).click();
    await page
      .getByRole("heading", { name: "Genel özet kayıtları", exact: true })
      .waitFor();
    await page.screenshot({
      path: path.resolve("../outputs/reports-live-desktop.png"),
      fullPage: true,
    });
    for (const tab of [
      "Finans",
      "Üyelikler",
      "Ziyaretler",
      "Dersler",
      "Personel ve mesai",
      "Stok ve satış",
      "Cihazlar",
      "Denetim günlüğü",
    ]) {
      await page.getByRole("tab", { name: tab, exact: true }).click();
      await page
        .getByRole("heading", { name: `${tab} kayıtları`, exact: true })
        .waitFor();
      assert.equal(await page.getByRole("alert").count(), 0);
    }
    const check = await page.evaluate(async () => {
      const get = async (path) => {
        const r = await fetch("/api/v1/" + path);
        if (!r.ok) throw Error(path + ": " + r.status);
        return r.json();
      };
      const data = await get("reports/?tab=finance&all=true");
      const net = data.metrics.find((m) => m.key === "net").value;
      const sum = data.table.rows.reduce((sum, row) => sum + row[7], 0);
      const csv = await get("reports/export/?tab=finance&format=csv"),
        xlsx = await get("reports/export/?tab=finance&format=xlsx");
      return {
        netMatches: sum === net,
        csvBom: atob(csv.base64).startsWith("\xEF\xBB\xBF"),
        xlsxZip: atob(xlsx.base64).startsWith("PK"),
        rows: data.table.count,
      };
    });
    assert.equal(check.netMatches, true);
    assert.equal(check.csvBom, true);
    assert.equal(check.xlsxZip, true);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("tab", { name: "Genel özet", exact: true }).click();
    await page
      .getByRole("heading", { name: "Genel özet kayıtları", exact: true })
      .waitFor();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    await page.screenshot({
      path: path.resolve("../outputs/reports-live-mobile.png"),
      fullPage: true,
    });
    await page.reload();
    await page
      .getByRole("heading", { name: "Giriş yoğunluğu", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "Menüyü aç", exact: true }).click();
    await page.getByRole("button", { name: "Raporlar", exact: true }).click();
    await page
      .getByRole("heading", { name: "Genel özet kayıtları", exact: true })
      .waitFor();
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        livePostgres: true,
        tabs: 9,
        desktopMobile: "passed",
        reload: "passed",
        ...check,
        errors,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
