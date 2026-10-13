import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { PlansPage } from "../src/PlansPage.jsx";
import { buildSeed } from "../src/gym.mjs";
import "../src/styles.css";
const seed = buildSeed();
seed.plans = seed.plans.map((row) => ({
  ...row,
  kind: row.sessions == null ? "timed" : "hybrid",
  durationUnit: "day",
  durationValue: row.days,
  revision: 1,
  campaigns: [],
  freezeMin: 1,
  freezeMax: null,
  freezeLimit: null,
  dailyLimit: null,
  weeklyLimit: null,
  usedCount: 3,
}));
function Preview() {
  const [db, setDb] = useState(seed);
  return (
    <main className="page-content">
      <PlansPage
        db={db}
        run={async (type, payload) => {
          window.planAction = { type, payload };
          setDb((old) => ({
            ...old,
            plans: payload.id
              ? old.plans.map((row) =>
                  row.id === payload.id
                    ? { ...payload, revision: row.revision + 1 }
                    : row,
                )
              : [
                  ...old.plans,
                  { ...payload, id: "new-plan", revision: 1, usedCount: 0 },
                ],
          }));
          return { ok: true };
        }}
      />
    </main>
  );
}
createRoot(document.getElementById("root")).render(<Preview />);
