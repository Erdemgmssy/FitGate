import test from "node:test";
import assert from "node:assert/strict";
import { cashBalance } from "../src/gym.mjs";
import {
  cents,
  cartTotal,
  productSearch,
  saleGroups,
  returnPreview,
  stockSummary,
} from "../src/stock-rules.mjs";
test("exact cents and discounts, no fractional cent or overdiscount", () => {
  assert.equal(cents("10.01"), 1001);
  assert.equal(cents("0.1"), 10);
  assert.equal(cents("9999999999.99"), 999999999999);
  assert.deepEqual(
    cartTotal(
      [
        { unitPriceCents: 1001, quantity: 2 },
        { unitPriceCents: 2000, quantity: 1 },
      ],
      "1.01",
    ),
    { subtotal: 4002, discount: 101, total: 3901 },
  );
  for (const value of ["1.001", "NaN", "-1"]) assert.throws(() => cents(value));
  assert.throws(() => cartTotal([{ unitPriceCents: 1, quantity: 1 }], "1"));
});
test("search barcode code and Turkish names", () => {
  const rows = [
    { id: 1, name: "İçecek", code: "W", barcode: "869123", category: "Su" },
  ];
  assert.equal(productSearch(rows, "869123").length, 1);
  assert.equal(productSearch(rows, "içecek").length, 1);
  assert.equal(productSearch(rows, "w").length, 1);
  assert.equal(productSearch(rows, "bad").length, 0);
});
test("checkout groups line items once and partial returns aggregate", () => {
  const rows = [
    {
      id: "1",
      checkoutId: "group",
      number: "N",
      at: "2026-10-13T10:00:00Z",
      totalCents: 1001,
      refundedCents: 500,
    },
    {
      id: "2",
      checkoutId: "group",
      at: "2026-10-13T10:00:00Z",
      totalCents: 2000,
      refundedCents: 0,
    },
  ];
  const result = saleGroups(rows);
  assert.equal(result.length, 1);
  assert.equal(result[0].lines.length, 2);
  assert.equal(result[0].totalCents, 3001);
  assert.equal(result[0].refundCents, 500);
});
test("partial return cumulative rounding totals match discounted sale", () => {
  const sale = {
    quantity: 3,
    totalCents: 2902,
    returnedQuantity: 0,
    refundedCents: 0,
  };
  assert.equal(returnPreview(sale, 1), 967);
  assert.equal(
    returnPreview({ ...sale, returnedQuantity: 2, refundedCents: 1934 }, 1),
    968,
  );
  assert.throws(() =>
    returnPreview({ ...sale, returnedQuantity: 3, refundedCents: 2902 }, 1),
  );
});
test("daily and monthly product net use return date and no double income", () => {
  const db = {
    products: [
      { active: true, stock: 0, minimum: 2 },
      { active: true, stock: 1, minimum: 2 },
    ],
    sales: [{ at: "2026-10-12T10:00:00Z", totalCents: 3001 }],
    stockMovements: [
      { at: "2026-10-13T10:00:00Z", returnedUnits: 1, refundCents: 1001 },
    ],
  };
  const value = stockSummary(db, new Date("2026-10-13T10:30:00Z"));
  assert.equal(value.todayNetCents, -1001);
  assert.equal(value.monthNetCents, 2000);
  assert.equal(value.emptyCount, 1);
  assert.equal(value.criticalCount, 1);
});
test("cash returns come from the event ledger, not duplicated full-return flags", () => {
  const at = "2026-10-13T10:00:00Z",
    db = {
      payments: [{ amountCents: 2000, method: "cash", at }],
      refunds: [],
      sales: [
        {
          totalCents: 3000,
          method: "cash",
          at,
          returned: true,
          returnedAt: at,
        },
      ],
      stockMovements: [{ refundCents: 500, method: "cash", at }],
    };
  assert.equal(
    cashBalance(
      db,
      { openingCents: 0, openedAt: "2026-10-13T00:00:00Z" },
      new Date("2026-10-13T12:00:00Z"),
    ),
    4500,
  );
});
