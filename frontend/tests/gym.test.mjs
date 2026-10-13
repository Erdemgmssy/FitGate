import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSeed,
  transact,
  currentSubscription,
  subscriptionStatus,
  invoiceDebt,
  installmentRows,
  paidCents,
  addMonths,
  cents,
  cashBalance,
} from "../src/gym.mjs";
import {
  payrollPeriod,
  workedMilliseconds,
  earnedAmount,
} from "../src/attendance.mjs";
const now = new Date("2026-10-10T12:00:00+03:00");
const admin = { name: "Admin", role: "admin" },
  staff = { name: "Staff", role: "staff" };
const run = (db, type, payload, user = admin, time = now) =>
  transact(db, type, payload, user, time);

test("replacing inactive card revokes it; discarded card cannot reactivate", () => {
  let db = run(
    buildSeed(now),
    "cardStatus",
    { id: "c1", status: "inactive" },
    staff,
  ).db;
  db = run(db, "assignCard", { memberId: "m1", uid: "RFID-NEW" }, staff).db;
  assert.equal(db.cards.find((item) => item.id === "c1").status, "cancelled");
  assert.throws(() =>
    run(db, "cardStatus", { id: "c1", status: "active" }, staff),
  );
  assert.equal(
    db.cards.filter(
      (item) => item.memberId === "m1" && item.status === "active",
    ).length,
    1,
  );
});

test("returned cards are unassigned, reusable and keep former visits", () => {
  let db = buildSeed(now);
  db.visits = db.visits.filter((item) => item.memberId !== "m1");
  db.grants = [];
  db.visits.push({
    id: "closed-old",
    memberId: "m1",
    entry: "2026-10-01T09:00:00Z",
    exit: "2026-10-01T10:00:00Z",
  });
  const oldUid = db.cards.find((item) => item.id === "c1").uid;
  db = run(db, "releaseCard", { id: "c1", confirmed: true }, staff).db;
  assert.equal(db.cards.find((item) => item.id === "c1").memberId, null);
  assert.equal(db.cards.find((item) => item.id === "c1").status, "available");
  assert.throws(() =>
    run(db, "cardStatus", { id: "c1", status: "active" }, staff),
  );
  db = run(db, "assignCard", { memberId: "m2", uid: oldUid }, staff).db;
  assert.equal(db.cards.find((item) => item.id === "c1").memberId, "m2");
  assert.equal(db.cards.filter((item) => item.uid === oldUid).length, 1);
  assert.equal(
    db.visits.find((item) => item.id === "closed-old").memberId,
    "m1",
  );
  assert.ok(db.audit.some((item) => item.type === "releaseCard"));
});

test("card return needs possession confirmation and a closed visit", () => {
  const db = buildSeed(now);
  assert.throws(() => run(db, "releaseCard", { id: "c1" }, staff));
  db.visits.push({
    id: "open-old",
    memberId: "m1",
    entry: now.toISOString(),
    exit: null,
  });
  assert.throws(() =>
    run(db, "releaseCard", { id: "c1", confirmed: true }, staff),
  );
});

test("cash opening, collections and counted closing snapshot", () => {
  let db = run(
    buildSeed(now),
    "openCash",
    { amount: 100 },
    admin,
    new Date(now.getTime() - 1000),
  ).db;
  assert.throws(() => run(db, "openCash", { amount: 0 }));
  db = run(db, "collect", {
    invoiceId: "inv2",
    amount: 100,
    method: "cash",
  }).db;
  assert.equal(cashBalance(db, db.cashSessions[0], now), 20000);
  db = run(db, "closeCash", { amount: 195, note: "Sayım" }).db;
  assert.equal(db.cashSessions[0].expectedCents, 20000);
  assert.equal(db.cashSessions[0].countedCents, 19500);
});

test("calendar month-end and future/expired subscription status", () => {
  assert.equal(addMonths("2026-01-31", 1), "2026-02-28");
  assert.equal(
    subscriptionStatus(
      { status: "active", start: "2026-11-01", end: "2026-11-30" },
      "2026-10-10",
    ),
    "pending",
  );
  assert.equal(
    subscriptionStatus(
      { status: "active", start: "2026-09-01", end: "2026-10-09" },
      "2026-10-10",
    ),
    "expired",
  );
});
test("partial collections allocate oldest installments; overpayments rollback", () => {
  const db = buildSeed(now),
    invoice = db.invoices[1];
  assert.equal(invoiceDebt(db, invoice), 220000);
  const next = run(db, "collect", {
    invoiceId: invoice.id,
    amount: 200,
    method: "cash",
  }).db;
  assert.equal(invoiceDebt(next, invoice), 200000);
  assert.equal(installmentRows(next, invoice)[0].remaining, 200000);
  assert.throws(() =>
    run(db, "collect", { invoiceId: invoice.id, amount: 9999, method: "cash" }),
  );
  assert.equal(db.payments.length, 3);
});
test("refund caps and membership cancellation preserves invoice debt", () => {
  const db = buildSeed(now),
    payment = db.payments[0];
  const next = run(db, "refund", {
    paymentId: payment.id,
    amount: 100,
    reason: "Düzeltme",
  }).db;
  assert.equal(paidCents(next, payment.invoiceId), payment.amountCents - 10000);
  assert.throws(() =>
    run(next, "refund", {
      paymentId: payment.id,
      amount: 2000,
      reason: "Fazla",
    }),
  );
  const cancelled = run(next, "cancelSubscription", {
    id: "sub1",
    reason: "İptal",
    confirmed: true,
  }).db;
  assert.equal(
    invoiceDebt(cancelled, cancelled.invoices[0]),
    invoiceDebt(next, next.invoices[0]),
  );
  assert.deepEqual(cancelled.payments, next.payments);
});
test("member duplicate check and cent-safe installment splits", () => {
  const db = buildSeed(now);
  assert.throws(() =>
    run(db, "addMember", {
      name: "Test",
      phone: "05321112233",
      consent: true,
      planId: "p1",
    }),
  );
  const next = run(db, "addMember", {
    name: "Test Üye",
    phone: "05551112233",
    consent: true,
    planId: "p1",
    installments: 7,
    discount: 0.01,
    paid: 0,
    start: "2026-10-10",
  }).db;
  const invoice = next.invoices.at(-1);
  assert.equal(
    next.installments
      .filter((item) => item.invoiceId === invoice.id)
      .reduce((sum, item) => sum + item.amountCents, 0),
    119999,
  );
  assert.equal(db.members.length, 4);
});
test("sales snapshot prices/rules and freeze preserve remaining days", () => {
  const db = buildSeed(now),
    sub = structuredClone(db.subscriptions[0]);
  const updated = run(db, "savePlan", {
    ...db.plans[0],
    price: 9999,
    days: 1,
  }).db;
  assert.equal(updated.subscriptions[0].priceCents, sub.priceCents);
  assert.equal(updated.subscriptions[0].rules.days, sub.rules.days);
  const frozen = run(db, "freeze", { id: "sub1", reason: "İzin" }).db;
  const resumed = run(
    frozen,
    "resume",
    { id: "sub1" },
    admin,
    new Date("2026-10-13T12:00:00+03:00"),
  ).db;
  assert.equal(resumed.subscriptions[0].end, "2026-11-27");
  assert.equal(resumed.subscriptions[0].frozenDays, 3);
});
test("authorization is not physical passage; one confirmation consumes one session", () => {
  let db = buildSeed(now);
  db.subscriptions.find((item) => item.memberId === "m3").remaining = 10;
  const authorized = run(
    db,
    "authorize",
    { uid: "RFID-12004", deviceId: "d1", direction: "entry" },
    staff,
  );
  assert.equal(authorized.result.approved, true);
  assert.equal(authorized.db.visits.length, db.visits.length);
  assert.equal(
    authorized.db.subscriptions.find((item) => item.memberId === "m3")
      .remaining,
    10,
  );
  const confirmed = run(
    authorized.db,
    "confirmPassage",
    { id: authorized.result.grantId },
    staff,
    new Date(now.getTime() + 1000),
  );
  assert.equal(confirmed.db.visits.length, db.visits.length + 1);
  assert.equal(
    confirmed.db.subscriptions.find((item) => item.memberId === "m3").remaining,
    9,
  );
  assert.throws(() =>
    run(
      confirmed.db,
      "confirmPassage",
      { id: authorized.result.grantId },
      staff,
    ),
  );
});
test("expired permission, lost cards, capacity and expired membership reject", () => {
  const db = buildSeed(now);
  for (const payload of [
    { uid: "UNKNOWN", deviceId: "d1", direction: "entry" },
    { uid: "RFID-77561", deviceId: "d1", direction: "entry" },
    { uid: "RFID-12004", deviceId: "d2", direction: "entry" },
  ])
    assert.equal(run(db, "authorize", payload, staff).result.approved, false);
  db.settings.capacity = 1;
  assert.equal(
    run(
      db,
      "authorize",
      { uid: "RFID-12004", deviceId: "d1", direction: "entry" },
      staff,
    ).result.approved,
    false,
  );
  db.settings.capacity = 100;
  const granted = run(
    db,
    "authorize",
    { uid: "RFID-12004", deviceId: "d1", direction: "entry" },
    staff,
  );
  assert.throws(() =>
    run(
      granted.db,
      "confirmPassage",
      { id: granted.result.grantId },
      staff,
      new Date(now.getTime() + 31000),
    ),
  );
});
test("exit allowed for expired member with open visit; duplicate exit rejected", () => {
  const db = buildSeed(now);
  db.visits.push({
    id: "expired",
    memberId: "m4",
    entry: "2026-10-10T10:00:00",
    exit: null,
  });
  const granted = run(
    db,
    "authorize",
    { uid: "RFID-77561", deviceId: "d1", direction: "exit" },
    staff,
  );
  assert.equal(granted.result.approved, true);
  assert.ok(
    run(
      granted.db,
      "confirmPassage",
      { id: granted.result.grantId },
      staff,
    ).db.visits.find((item) => item.id === "expired").exit,
  );
});
test("staff cannot alter rates/refund/devices; admin can assign member cards", () => {
  const db = buildSeed(now);
  for (const action of ["saveRates", "refund", "deviceMode", "correctShift"])
    assert.throws(() => run(db, action, {}, staff));
  const assigned = run(
    db,
    "assignCard",
    { memberId: "m1", uid: "TEST" },
    admin,
  );
  assert.equal(
    assigned.db.cards.find((card) => card.uid === "TEST").memberId,
    "m1",
  );
});
test("class waitlist promotion and duplicate booking", () => {
  let db = buildSeed(now);
  db = run(db, "book", { classId: "cl1", memberId: "m2" }, staff).db;
  const waiting = run(db, "book", { classId: "cl1", memberId: "m3" }, staff);
  assert.equal(waiting.result, "waiting");
  assert.throws(() =>
    run(waiting.db, "book", { classId: "cl1", memberId: "m3" }, staff),
  );
  const cancelled = run(
    waiting.db,
    "bookingStatus",
    { id: "bk1", status: "cancelled" },
    staff,
  ).db;
  assert.equal(
    cancelled.bookings.find((item) => item.memberId === "m3").status,
    "booked",
  );
});
test("stock cannot go negative and returns are idempotent", () => {
  const db = buildSeed(now);
  assert.throws(() =>
    run(
      db,
      "sellProduct",
      { productId: "pr2", quantity: 5, method: "cash" },
      staff,
    ),
  );
  const sale = run(
    db,
    "sellProduct",
    { productId: "pr2", quantity: 2, method: "cash" },
    staff,
  ).db;
  assert.equal(sale.products[1].stock, 2);
  const returned = run(sale, "returnSale", {
    id: sale.sales[0].id,
    reason: "İade",
  }).db;
  assert.equal(returned.products[1].stock, 4);
  assert.throws(() =>
    run(returned, "returnSale", { id: sale.sales[0].id, reason: "Tekrar" }),
  );
});
test("15th payroll boundaries and historical rate changes", () => {
  const period = payrollPeriod("2026-09"),
    shifts = [
      {
        employeeId: "e",
        entry: "2026-09-14T23:00:00",
        exit: "2026-09-15T02:00:00",
      },
      {
        employeeId: "e",
        entry: "2026-10-14T23:00:00",
        exit: "2026-10-15T03:00:00",
      },
    ];
  const future = new Date("2026-11-01T00:00:00");
  assert.equal(
    workedMilliseconds(shifts, "e", period.start, period.end, future),
    3 * 3600000,
  );
  const rates = [
    { employeeId: "e", effectiveAt: "2020-01-01T00:00:00", rate: 100 },
    { employeeId: "e", effectiveAt: "2026-10-01T00:00:00", rate: 200 },
  ];
  assert.equal(
    earnedAmount(shifts, "e", rates, period.start, period.end, future),
    400,
  );
});
