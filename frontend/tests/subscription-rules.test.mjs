import test from "node:test";
import assert from "node:assert/strict";
import {
  subscriptionDays,
  sessionCounts,
  subscriptionGroup,
  orderSubscriptions,
  renewalStart,
  membershipEnd,
} from "../src/subscription-rules.mjs";

const sub = {
  id: "a",
  status: "active",
  start: "2026-10-01",
  end: "2026-10-30",
  remaining: 4,
  totalSessions: 5,
};
test("session snapshots and unlimited packages", () => {
  assert.deepEqual(sessionCounts({ ...sub, rules: { sessions: 99 } }), {
    total: 5,
    used: 1,
    remaining: 4,
  });
  assert.deepEqual(sessionCounts({ ...sub, remaining: null }), {
    total: null,
    used: null,
    remaining: null,
  });
});
test("inclusive days and cancelled validity", () => {
  assert.equal(subscriptionDays(sub, "2026-10-30"), 1);
  assert.equal(subscriptionDays(sub, "2026-10-31"), 0);
  assert.equal(
    subscriptionDays({ ...sub, status: "cancelled" }, "2026-10-01"),
    0,
  );
});
test("scheduled freeze pauses days and automatically ends", () => {
  const frozen = {
    ...sub,
    end: "2026-11-02",
    freezePeriods: [
      { start: "2026-10-10", end: "2026-10-13", plannedEnd: "2026-10-12" },
    ],
  };
  assert.equal(
    subscriptionDays(frozen, "2026-10-10"),
    subscriptionDays(frozen, "2026-10-12"),
  );
  assert.equal(subscriptionGroup(frozen, "2026-10-09"), "active");
  assert.equal(subscriptionGroup(frozen, "2026-10-10"), "frozen");
  assert.equal(subscriptionGroup(frozen, "2026-10-12"), "frozen");
  assert.equal(subscriptionGroup(frozen, "2026-10-13"), "active");
});
test("distinct historical categories", () => {
  assert.equal(subscriptionGroup(sub, "2026-09-30"), "pending");
  assert.equal(subscriptionGroup(sub, "2026-10-31"), "expired");
  assert.equal(
    subscriptionGroup({ ...sub, status: "cancelled" }, "2026-10-01"),
    "cancelled",
  );
});
test("stable ordering and renewal after all future packages", () => {
  const later = { ...sub, id: "b", end: "2026-12-30" };
  assert.deepEqual(
    orderSubscriptions([later, sub]).map((s) => s.id),
    ["a", "b"],
  );
  assert.equal(renewalStart([sub, later], "2026-10-01"), "2026-12-31");
  assert.equal(
    renewalStart([{ ...later, status: "cancelled" }], "2026-10-01"),
    "2026-10-01",
  );
});
test("calendar month package handles short months", () => {
  assert.equal(
    membershipEnd({ durationUnit: "month", durationValue: 1 }, "2026-01-31"),
    "2026-02-27",
  );
  assert.equal(
    membershipEnd({ durationUnit: "day", durationValue: 30 }, "2026-10-01"),
    "2026-10-30",
  );
});
