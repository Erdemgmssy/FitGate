import test from "node:test";
import assert from "node:assert/strict";
import {
  turkeyDay,
  shiftDay,
  period,
  cleanFilters,
  query,
  chartFilter,
} from "../src/report-rules.mjs";
test("Turkey boundaries and leap month presets", () => {
  assert.equal(turkeyDay(new Date("2026-10-12T21:00:00Z")), "2026-10-13");
  assert.deepEqual(period("previousMonth", "2024-03-04"), {
    from: "2024-02-01",
    to: "2024-02-29",
  });
  assert.deepEqual(period("week", "2026-01-02"), {
    from: "2025-12-27",
    to: "2026-01-02",
  });
  assert.equal(shiftDay("2026-01-01", -1), "2025-12-31");
});
test("Changing reports removes incompatible filters and staff attribution", () => {
  const filters = cleanFilters("visits", {
    planId: "p",
    person: "u:1",
    method: "cash",
    category: "Drink",
    type: "debt",
  });
  assert.equal(filters.person, "");
  assert.equal(filters.method, "");
  assert.equal(filters.category, "");
  assert.equal(filters.planId, "p");
  assert.equal(filters.type, "");
  assert.equal(
    cleanFilters("personnel", { person: "u:1", planId: "p" }, false).person,
    "",
  );
});
test("Query keeps zero hour/weekday and removes empty filters", () => {
  assert.equal(
    query({ hour: 0, weekday: 0, type: "", person: null }),
    "hour=0&weekday=0",
  );
});
test("Graph date filters clip selected week/month and cross December safely", () => {
  assert.deepEqual(
    chartFilter(
      { from: "2026-12-15", to: "2026-12-27", granularity: "month" },
      { date: "2026-12-01" },
    ),
    { from: "2026-12-15", to: "2026-12-27", granularity: "month", page: 1 },
  );
  assert.equal(
    chartFilter(
      { from: "2026-10-01", to: "2026-10-13", granularity: "week" },
      { date: "2026-10-12" },
    ).to,
    "2026-10-13",
  );
  assert.equal(chartFilter({ page: 2 }, { hour: "0" }).hour, "0");
});
