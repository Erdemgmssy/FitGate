import test from "node:test";
import assert from "node:assert/strict";
import {
  bounds,
  worked,
  scheduleWindow,
  trDay,
  calendarDays,
  inputTime,
  isoTime,
} from "../src/personnel-rules.mjs";

test('correction inputs retain seconds and milliseconds',()=>{
  const value='2026-10-12T21:34:12.345Z';
  assert.equal(isoTime(inputTime(value)),value);
});

test("overnight shift uses Turkey time and next day", () => {
  assert.deepEqual(scheduleWindow("2026-10-12", "22:00", "06:00"), {
    start: "2026-10-12T19:00:00.000Z",
    end: "2026-10-13T03:00:00.000Z",
  });
  assert.equal(trDay("2026-10-12T22:00:00Z"), "2026-10-13");
});
test("day week month and 15-to-15 bounds", () => {
  assert.equal(
    bounds("2026-10-12", "week").start.toISOString(),
    "2026-10-11T21:00:00.000Z",
  );
  assert.equal(
    bounds("2026-10-12", "period15").start.toISOString(),
    "2026-09-14T21:00:00.000Z",
  );
  assert.equal(calendarDays("2026-02-15", "month").length, 28);
  assert.equal(calendarDays("2026-10-12", "week").length, 7);
});
test('15-to-15 clips previous-night work, subtracts unpaid break and excludes simulation',()=>{
  const shifts=[{id:'night',employeeId:'own',entry:'2026-09-14T22:00:00+03:00',exit:'2026-09-15T06:00:00+03:00'}, {id:'sim',employeeId:'own',entry:'2026-09-16T09:00:00+03:00',exit:'2026-09-16T10:00:00+03:00',simulated:true},{id:'other',employeeId:'other',entry:'2026-09-15T09:00:00+03:00',exit:'2026-09-15T17:00:00+03:00'}];
  const pauses=[{shiftId:'night',start:'2026-09-15T00:00:00+03:00',end:'2026-09-15T00:30:00+03:00',paid:false},{shiftId:'night',start:'2026-09-15T02:00:00+03:00',end:'2026-09-15T02:30:00+03:00',paid:true}];
  assert.equal(worked(shifts,pauses,'own',bounds('2026-10-13','period15'),new Date('2026-10-13T12:00:00+03:00')),5.5*3600000);
});
test("breaks are clipped at midnight and paid breaks remain working time", () => {
  const shifts = [
    {
      id: "s",
      employeeId: "e",
      entry: "2026-10-12T22:00:00+03:00",
      exit: "2026-10-13T06:00:00+03:00",
    },
  ];
  const breaks = [
    {
      shiftId: "s",
      start: "2026-10-12T23:45:00+03:00",
      end: "2026-10-13T00:15:00+03:00",
      paid: false,
    },
  ];
  assert.equal(
    worked(shifts, breaks, "e", bounds("2026-10-13"), new Date("2026-10-14")),
    5.75 * 3600000,
  );
  assert.equal(
    worked(
      shifts,
      breaks.map((p) => ({ ...p, paid: true })),
      "e",
      bounds("2026-10-13"),
      new Date("2026-10-14"),
    ),
    6 * 3600000,
  );
});
test("simulated work is excluded by default and other employees stay separate", () => {
  const rows = [
    {
      id: "s",
      employeeId: "e",
      entry: "2026-10-12T09:00:00+03:00",
      exit: "2026-10-12T17:00:00+03:00",
      simulated: true,
    },
  ];
  assert.equal(
    worked(rows, [], "e", bounds("2026-10-12"), new Date("2026-10-13")),
    0,
  );
  assert.equal(
    worked(rows, [], "e", bounds("2026-10-12"), new Date("2026-10-13"), true),
    8 * 3600000,
  );
  assert.equal(
    worked(
      rows,
      [],
      "other",
      bounds("2026-10-12"),
      new Date("2026-10-13"),
      true,
    ),
    0,
  );
});
