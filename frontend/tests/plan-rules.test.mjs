import test from "node:test";
import assert from "node:assert/strict";
import {
  planKind,
  planDuration,
  saleAvailable,
  salePrice,
} from "../src/plan-rules.mjs";
import {
  membershipEnd,
  subscriptionDays,
  orderSubscriptions,
  renewalStart,
} from "../src/subscription-rules.mjs";
import {
  subscriptionStatus,
  currentSubscription,
  automaticNotices,
} from "../src/gym.mjs";
test("calendar months differ from fixed days and weeks use seven days", () => {
  assert.equal(
    membershipEnd({ durationUnit: "month", durationValue: 3 }, "2026-02-01"),
    "2026-04-30",
  );
  assert.equal(
    membershipEnd({ durationUnit: "day", durationValue: 90 }, "2026-02-01"),
    "2026-05-01",
  );
  assert.equal(
    membershipEnd({ durationUnit: "week", durationValue: 2 }, "2026-01-01"),
    "2026-01-14",
  );
});
test("pure session packages have no duration, end or expiring notice", () => {
  const plan = { kind: "sessions", sessions: 10 };
  assert.equal(membershipEnd(plan, "2026-01-01"), "");
  assert.equal(planDuration(plan), "Bitiş tarihi yok");
  const sub = {
    id: "s",
    memberId: "m",
    start: "2026-01-01",
    end: null,
    status: "active",
  };
  assert.equal(subscriptionStatus(sub, "2026-10-13"), "active");
  assert.equal(subscriptionDays(sub), null);
  assert.equal(
    automaticNotices({
      members: [{ id: "m" }],
      subscriptions: [sub],
      notices: [],
      invoices: [],
      installments: [],
      devices: [],
      products: [],
    }).length,
    0,
  );
});
test("finite packages sort before indefinite packages without breaking renewal", () => {
  const list = [
    { id: "a", start: "2026-01-01", end: null, status: "active" },
    { id: "b", start: "2026-01-01", end: "2026-10-20", status: "active" },
  ];
  assert.equal(orderSubscriptions(list)[0].id, "b");
  assert.equal(renewalStart(list, "2026-10-13"), "2026-10-21");
});
test("sales windows are inclusive and do not redefine historical subscriptions", () => {
  const plan = { active: true, saleStart: "2026-10-13", saleEnd: "2026-10-20" };
  assert.equal(saleAvailable(plan, "2026-10-13"), true);
  assert.equal(saleAvailable(plan, "2026-10-21"), false);
  assert.equal(saleAvailable({ ...plan, active: false }, "2026-10-13"), false);
});
test("display uses exact server campaign price and legacy type interpretation", () => {
  assert.equal(salePrice({ price: 100.01, effectivePriceCents: 5000 }), 50);
  assert.equal(planKind({ sessions: 5 }), "hybrid");
  assert.equal(
    planDuration({ durationUnit: "month", durationValue: 3 }),
    "3 takvim ayı",
  );
});
