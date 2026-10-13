import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { ClassesPage } from "../src/ClassesPage.jsx";
import { buildSeed } from "../src/gym.mjs";
import { turkeyDay, shiftDay } from "../src/class-rules.mjs";
import "../src/styles.css";
const seed = buildSeed(),
  day = shiftDay(turkeyDay(), 1);
seed.classPermissions = { manage: true, book: true, attendance: true };
seed.employees = [
  { id: "trainer-1", name: "Mert Kaya", active: true, role: "trainer" },
];
seed.classes = [
  {
    id: "class-1",
    name: "Pilates",
    trainer: "Mert Kaya",
    trainerId: "trainer-1",
    room: "Stüdyo A",
    kind: "group",
    at: day + "T14:00:00+03:00",
    duration: 60,
    capacity: 10,
    cancelled: false,
    requireMembership: true,
    requireLesson: true,
    bookingMinutes: 30,
    cancelMinutes: 120,
    priceCents: 0,
    description: "Grup dersi",
    lateCancelConsumes: true,
    noShowConsumes: true,
  },
];
seed.bookings = [];
function Preview() {
  const [db, setDb] = useState(seed);
  return (
    <main className="page-content">
      <ClassesPage
        db={db}
        isAdmin
        run={async (type, payload) => {
          window.classAction = { type, payload };
          if (type === "saveClass")
            setDb((old) => ({
              ...old,
              classes: [
                ...old.classes,
                {
                  ...payload,
                  id: "new-class",
                  trainer: "Mert Kaya",
                  priceCents: Math.round(Number(payload.price) * 100),
                },
              ],
            }));
          if (type === "book")
            setDb((old) => ({
              ...old,
              bookings: [
                ...old.bookings,
                {
                  id: "booking-1",
                  classId: payload.classId,
                  memberId: payload.memberId,
                  status: "booked",
                  rightState: "reserved",
                  terms: { priceCents: 0 },
                },
              ],
            }));
          return { ok: true };
        }}
      />
    </main>
  );
}
createRoot(document.getElementById("root")).render(<Preview />);
