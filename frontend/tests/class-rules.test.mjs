import test from "node:test";
import assert from "node:assert/strict";
import {
  turkeyDay,
  calendarDays,
  shiftPeriod,
  classState,
  classOccupancy,
  filteredClasses,
  localClassTime,
} from "../src/class-rules.mjs";
test("Turkey dates and midnight respect Europe/Istanbul", () => {
  assert.equal(turkeyDay("2026-10-13T22:30:00Z"), "2026-10-14");
  assert.equal(localClassTime("2026-10-13T22:30:00Z"), "2026-10-14T01:30");
});
test("calendar day week month and month boundaries", () => {
  assert.deepEqual(calendarDays("2026-10-13", "day"), ["2026-10-13"]);
  assert.equal(calendarDays("2026-10-13", "week")[0], "2026-10-12");
  assert.equal(calendarDays("2026-10-13", "month").length, 42);
  assert.equal(shiftPeriod("2026-01-31", "month", 1), "2026-02-01");
  assert.equal(shiftPeriod("2026-01-31", "month", -1), "2025-12-01");
});
test("past classes do not stay planned and cancellation preserved", () => {
  const row = { at: "2026-10-13T10:00:00Z", duration: 60 };
  assert.equal(classState(row, new Date("2026-10-13T09:00:00Z")), "planned");
  assert.equal(classState(row, new Date("2026-10-13T10:30:00Z")), "ongoing");
  assert.equal(classState(row, new Date("2026-10-13T11:00:00Z")), "completed");
  assert.equal(classState({ ...row, cancelled: true }), "cancelled");
  assert.equal(classState({ ...row, state: "notheld" }), "notheld");
});
test("occupancy excludes waitlist and cancelled but retains attendance history", () => {
  assert.equal(
    classOccupancy(
      "a",
      [
        "booked",
        "waiting",
        "attended",
        "late",
        "absent",
        "cancelled",
        "excused",
      ].map((status) => ({ classId: "a", status })),
    ),
    4,
  );
});
test("combined filters preserve and sort original classes", () => {
  const rows = [
    { id: 1, trainerId: "t", kind: "group", room: "A", at: "2026-10-15" },
    { id: 2, trainerId: "t", kind: "private", room: "A", at: "2026-10-13" },
  ];
  assert.deepEqual(
    filteredClasses(rows, { trainer: "t", kind: "private", room: "A" }).map(
      (r) => r.id,
    ),
    [2],
  );
  assert.deepEqual(
    filteredClasses(rows).map((r) => r.id),
    [2, 1],
  );
  assert.equal(rows[0].id, 1);
});
