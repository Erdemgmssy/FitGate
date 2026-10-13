import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { CardManager } from "../src/MemberPages.jsx";
import { buildSeed, transact } from "../src/gym.mjs";
import "../src/styles.css";

function Preview() {
  const [db, setDb] = useState(() => {
    const fixture = buildSeed();
    fixture.devices = [];
    fixture.grants = [];
    fixture.cards = fixture.cards.filter((row) => row.id === "c1");
    fixture.visits = [
      {
        id: "old-visit",
        memberId: "m1",
        entry: "2026-10-01T09:00:00Z",
        exit: "2026-10-01T10:00:00Z",
      },
    ];
    fixture.members.find((row) => row.id === "m1").name = "Erdem";
    fixture.members.find((row) => row.id === "m2").name = "Yeni Üye";
    return fixture;
  });
  const [memberId, setMemberId] = useState("m1");
  window.cardsPreviewState = db;
  const run = async (action, payload) => {
    const result = transact(db, action, payload, {
      name: "QA Personel",
      role: "staff",
    });
    setDb(result.db);
    return { ok: true };
  };
  return (
    <main style={{ maxWidth: 900, margin: "24px auto", padding: 16 }}>
      <select
        aria-label="Üye"
        value={memberId}
        onChange={(event) => setMemberId(event.target.value)}
      >
        <option value="m1">Erdem</option>
        <option value="m2">Yeni Üye</option>
      </select>
      <CardManager
        key={memberId}
        member={db.members.find((row) => row.id === memberId)}
        db={db}
        run={run}
      />
    </main>
  );
}
createRoot(document.getElementById("root")).render(<Preview />);
