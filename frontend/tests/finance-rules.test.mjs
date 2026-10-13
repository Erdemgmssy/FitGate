import test from "node:test";
import assert from "node:assert/strict";
import { financialRecords } from "../src/finance-rules.mjs";
import { installmentRows, cashBalance } from "../src/gym.mjs";

const db = {
  invoices: [{ id: "sale", memberId: "member", totalCents: 10001 }],
  payments: [
    {
      id: "p",
      invoiceId: "sale",
      actorId: 1,
      method: "pos",
      amountCents: 1001,
      at: "2026-10-13T09:00:00+03:00",
    },
  ],
  refunds: [
    {
      id: "r",
      paymentId: "p",
      actorId: 2,
      amountCents: 1,
      at: "2026-10-14T09:00:00+03:00",
    },
  ],
  installments: [
    {
      id: "old",
      invoiceId: "sale",
      archived: true,
      due: "2026-10-01",
      amountCents: 10001,
    },
    { id: "first", invoiceId: "sale", due: "2026-10-02", amountCents: 5001 },
    { id: "second", invoiceId: "sale", due: "2026-10-20", amountCents: 5000 },
  ],
};
test("finance filters select the actual payment date, method and actor", () => {
  assert.equal(
    financialRecords(db, {
      memberId: "member",
      from: "2026-10-13",
      to: "2026-10-13",
      actor: "1",
      method: "pos",
    }).length,
    1,
  );
  assert.equal(financialRecords(db, { actor: "2" }).length, 0);
  assert.equal(financialRecords(db, { memberId: "other" }).length, 0);
});
test("refund filtering uses refund date and refunding employee, not original collection date", () => {
  assert.equal(
    financialRecords(
      db,
      { from: "2026-10-14", actor: "2", method: "pos" },
      "refunds",
    ).length,
    1,
  );
  assert.equal(financialRecords(db, { to: "2026-10-13" }, "refunds").length, 0);
});
test("archived installment plans never double debt allocation", () => {
  const rows = installmentRows(db, db.invoices[0]);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].remaining, 4001);
  assert.equal(rows[1].remaining, 5000);
});
test("backdated cash collection belongs to its recording cash session", () => {
  const data = {
    ...db,
    payments: [
      {
        ...db.payments[0],
        method: "cash",
        at: "2026-10-01T09:00:00Z",
        recordedAt: "2026-10-13T09:00:00Z",
      },
    ],
    refunds: [],
    sales: [],
  };
  assert.equal(
    cashBalance(
      data,
      { openedAt: "2026-10-13T08:00:00Z", openingCents: 0 },
      new Date("2026-10-13T10:00:00Z"),
    ),
    1001,
  );
});
