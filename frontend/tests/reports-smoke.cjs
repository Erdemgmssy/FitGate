const {
  chromium,
} = require("./playwright-runtime.cjs");
const assert = require("node:assert/strict"),
  path = require("node:path");
const tabs = {
  overview: "Genel özet",
  finance: "Finans",
  members: "Üyelikler",
  visits: "Ziyaretler",
  classes: "Dersler",
  personnel: "Personel ve mesai",
  stock: "Stok ve satış",
  devices: "Cihazlar",
  audit: "Denetim günlüğü",
};
// Browser-only fixtures, never sent to the live database.
function fixture(p) {
  const tab = p.get("tab"),
    empty = p.get("from") === "2000-01-01";
  return {
    title: tabs[tab],
    context: {
      branchName: "FitGate İstanbul",
      from: p.get("from"),
      to: p.get("to"),
      asOf: "2026-10-13T10:00:00Z",
      generatedAt: "2026-10-13T10:00:00Z",
    },
    metrics: [
      {
        key: "net",
        label: "Net tahsilat",
        value: 125001,
        format: "money",
        scope: "period",
      },
      {
        key: "unknown",
        label: "Doğrulanmamış veri",
        value: null,
        format: "count",
        scope: "current",
      },
    ],
    charts: [
      {
        title: "Tahsilat ve iadeler",
        type: "line",
        format: "money",
        points: empty
          ? []
          : [
              {
                label: "2026-10-10",
                value: 200000,
                filter: { date: "2026-10-10" },
              },
              {
                label: "2026-10-11",
                value: -74999,
                filter: { date: "2026-10-11" },
              },
            ],
      },
      {
        title: "Kaynak dağılımı",
        type: "distribution",
        format: "money",
        points: empty
          ? []
          : [
              {
                label: "membership",
                value: 125001,
                filter: { type: "membership" },
              },
            ],
      },
    ],
    table: {
      columns: [
        { label: "Tarih", format: "datetime" },
        { label: "Üye", format: "text" },
        { label: "Tutar", format: "money" },
      ],
      rows: empty
        ? []
        : [
            [
              "2026-10-10T12:30:00Z",
              "Uzun Adlı Üye Yönetimi Görünüm Testi",
              125001,
            ],
          ],
      count: empty ? 0 : 201,
      page: Number(p.get("page") || 1),
      pageSize: Number(p.get("pageSize") || 50),
    },
    definitions: [
      "Tahsilat ve satış farklıdır. Test verileri yalnızca tarayıcı belleğindedir.",
    ],
  };
}
(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({
        viewport: { width: 1440, height: 1000 },
      }),
      errors = [],
      requests = [];
    let failure = false,
      slow = false;
    page.on("pageerror", (e) => errors.push(e.message));
    await page.route(/\/reports-preview(?:\?.*)?$/, (r) =>
      r.fulfill({
        contentType: "text/html",
        body: '<div id="root"></div><script type="module" src="/tests/reports-preview.jsx"></script>',
      }),
    );
    await page.route("**/api/v1/**", async (r) => {
      assert.equal(r.request().method(), "GET");
      const url = new URL(r.request().url());
      requests.push(url.searchParams);
      if (url.pathname.endsWith("/options/"))
        return r.fulfill({
          json: {
            branches: [{ id: "b", name: "FitGate İstanbul" }],
            people: [{ id: "u:1", name: "Personel" }],
            plans: [{ id: "p", name: "Üç Aylık Paket" }],
            categories: ["İçecek"],
            tabs:
              url.searchParams.get("role") === "staff"
                ? { personnel: tabs.personnel }
                : tabs,
          },
        });
      if (url.pathname.endsWith("/export/"))
        return r.fulfill({
          json: {
            filename: `report.${url.searchParams.get("format")}`,
            base64: Buffer.from("Türkçe CSV Testi").toString("base64"),
          },
        });
      if (slow) await new Promise((resolve) => setTimeout(resolve, 350));
      if (failure)
        return r.fulfill({
          status: 503,
          json: { message: "Test rapor bağlantısı kesildi" },
        });
      return r.fulfill({ json: fixture(url.searchParams) });
    });
    await page.goto("http://127.0.0.1:5174/reports-preview");
    await page.getByRole("heading", { name: "Genel özet kayıtları" }).waitFor();
    assert.equal(await page.getByRole("tab").count(), 9);
    await page.screenshot({
      path: path.resolve("../outputs/reports-desktop.png"),
      fullPage: true,
    });
    await page.getByRole("tab", { name: "Finans", exact: true }).click();
    await page.getByRole("heading", { name: "Finans kayıtları" }).waitFor();
    await page
      .getByLabel("Ödeme yöntemi", { exact: true })
      .selectOption("cash");
    await page.getByRole("heading", { name: "Finans kayıtları" }).waitFor();
    assert.equal(requests.at(-1).get("method"), "cash");
    await page.getByLabel("İşlem türü", { exact: true }).selectOption("debt");
    await page.getByRole("heading", { name: "Finans kayıtları" }).waitFor();
    assert.equal(requests.at(-1).get("method"), null);
    await page.getByLabel("İşlem türü", { exact: true }).selectOption("");
    await page.getByRole("heading", { name: "Finans kayıtları" }).waitFor();
    await page.locator(".report-point-list button").first().click();
    await page.getByRole("heading", { name: "Finans kayıtları" }).waitFor();
    assert.equal(
      await page.getByLabel("Başlangıç", { exact: true }).inputValue(),
      "2026-10-10",
    );
    assert.equal(
      await page.getByLabel("Bitiş", { exact: true }).inputValue(),
      "2026-10-10",
    );
    await page
      .getByRole("button", { name: "Sonraki sayfa", exact: true })
      .click();
    await page.getByRole("heading", { name: "Finans kayıtları" }).waitFor();
    assert.equal(requests.at(-1).get("page"), "2");
    for (const kind of ["CSV", "Excel"]) {
      const pending = page.waitForEvent("download");
      await page.getByRole("button", { name: kind, exact: true }).click();
      const file = await pending;
      assert.ok(
        file.suggestedFilename().endsWith(kind === "CSV" ? ".csv" : ".xlsx"),
      );
    }
    await page.evaluate(
      () =>
        (window.print = () => {
          window.printRequested = true;
        }),
    );
    await page
      .getByRole("button", { name: "Yazdır / PDF", exact: true })
      .click();
    await page.waitForFunction(() => window.printRequested);
    assert.equal(requests.at(-1).get("all"), "true");
    await page.emulateMedia({ media: "print" });
    assert.equal(await page.locator(".report-print").isVisible(), true);
    await page.pdf({
      path: path.resolve("../outputs/reports-print-test.pdf"),
      format: "A4",
    });
    await page.emulateMedia({ media: "screen" });
    await page.evaluate(() => dispatchEvent(new Event("afterprint")));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("tab", { name: "Ziyaretler", exact: true }).click();
    await page.getByRole("heading", { name: "Ziyaretler kayıtları" }).waitFor();
    await page.getByLabel("Saat", { exact: true }).selectOption("0");
    await page.getByRole("heading", { name: "Ziyaretler kayıtları" }).waitFor();
    assert.equal(requests.at(-1).get("hour"), "0");
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    await page.screenshot({
      path: path.resolve("../outputs/reports-mobile.png"),
      fullPage: true,
    });
    slow = true;
    await page
      .getByRole("button", { name: "Raporu yenile", exact: true })
      .click();
    await page
      .getByRole("status")
      .filter({ hasText: "Rapor hazırlanıyor" })
      .waitFor();
    await page.getByRole("heading", { name: "Ziyaretler kayıtları" }).waitFor();
    slow = false;
    failure = true;
    await page
      .getByRole("button", { name: "Raporu yenile", exact: true })
      .click();
    await page.getByRole("alert").waitFor();
    assert.equal(await page.locator(".report-metrics").count(), 0);
    failure = false;
    await page
      .getByRole("button", { name: "Tekrar dene", exact: true })
      .click();
    await page.getByRole("heading", { name: "Ziyaretler kayıtları" }).waitFor();
    await page.getByLabel("Başlangıç", { exact: true }).fill("2000-01-01");
    await page
      .getByText("Bu filtrelerle kayıt bulunamadı.", { exact: true })
      .waitFor();
    assert.equal(await page.locator(".report-line").count(), 0);
    assert.deepEqual(errors, []);
    console.log(
      "Reports desktop/mobile, graph filters, paging, loading/error/empty, CSV/XLSX downloads, print/PDF: passed. Fixtures never saved.",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
