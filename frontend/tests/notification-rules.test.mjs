import test from "node:test";
import assert from "node:assert/strict";
import { filterNotices } from "../src/notification-rules.mjs";
import { automaticNotices } from "../src/gym.mjs";
const rows = [
  {
    id: "i",
    severity: "info",
    type: "class",
    read: true,
    at: "2026-10-12T21:00:00Z",
    status: "active",
  },
  {
    id: "c",
    severity: "critical",
    type: "device",
    read: false,
    at: "2026-10-12T20:59:00Z",
    status: "active",
  },
  {
    id: "r",
    severity: "warning",
    type: "stock",
    read: false,
    at: "2026-10-12T18:00:00Z",
    status: "resolved",
  },
];
test("Severity/read/type/status filters and immutable ordering", () => {
  assert.deepEqual(
    filterNotices(rows, { status: "active" }).map((n) => n.id),
    ["c", "i"],
  );
  assert.deepEqual(
    filterNotices(rows, { read: "read" }).map((n) => n.id),
    ["i"],
  );
  assert.equal(
    filterNotices(rows, { type: "stock", status: "resolved" }).length,
    1,
  );
  assert.equal(rows[0].id, "i");
});
test("Turkey day filters include midnight and both boundaries", () => {
  assert.deepEqual(
    filterNotices(rows, { from: "2026-10-13", to: "2026-10-13" }).map(
      (n) => n.id,
    ),
    ["i"],
  );
});
test("Server notifications are authoritative, no duplicate browser synthesis", () => {
  const db = {
    source: "server",
    notificationItems: rows,
    notices: rows,
    members: [{}],
    devices: [{}],
  };
  assert.equal(automaticNotices(db), rows);
});
