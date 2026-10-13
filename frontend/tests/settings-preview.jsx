import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { SettingsPage } from "../src/SettingsPage";
import { buildSeed } from "../src/gym.mjs";
import "../src/styles.css";
const seed = buildSeed();
seed.branches = [{ id: "b1", name: "FitGate Salon" }];
seed.devices = [
  {
    id: "d1",
    name: "Ana Turnike",
    enabled: true,
    simulated: false,
    purpose: "mixed",
    lastSeen: null,
    telemetry: { port: "COM6" },
  },
  {
    id: "d2",
    name: "Test",
    enabled: true,
    simulated: true,
    purpose: "access",
    telemetry: {},
  },
];
seed.personnel = {
  rolePolicies: [],
  accounts: [
    {
      id: 1,
      name: "Salon Sahibi",
      email: "owner@gym.test",
      role: "admin",
      active: true,
    },
    {
      id: 2,
      name: "Resepsiyon",
      email: "staff@gym.test",
      role: "staff",
      active: true,
    },
  ],
};
seed.systemSettings = {
  profile: {
    name: "FitGate Salon",
    phone: "05321112233",
    email: "info@gym.test",
    address: "İstanbul",
    logo: "",
  },
  opening: {
    enforced: false,
    from: "06:00",
    to: "23:00",
    days: [0, 1, 2, 3, 4, 5, 6],
    closures: [],
  },
  notifications: {
    membershipDays: 7,
    enabled: {
      membership: true,
      payment: true,
      stock: true,
      class: true,
      shift: true,
      device: true,
    },
    roles: {
      membership: ["admin", "staff"],
      payment: ["admin"],
      stock: ["admin"],
      class: ["admin", "staff", "trainer"],
      shift: ["admin", "staff", "trainer"],
      device: ["admin"],
    },
  },
  security: {
    hash: "Argon2",
    accessMinutes: 15,
    refreshHours: 8,
    secureCookies: false,
    loginAccountLimit: 5,
    loginIpLimit: 25,
    lockMinutes: 15,
  },
  data: {
    database: "connected",
    lastSuccessfulAt: "2026-10-13T13:28:42Z",
    latest: { status: "success" },
    history: [
      {
        id: "backup1",
        at: "2026-10-13T13:28:42Z",
        status: "success",
        verified: true,
        restoreVerified: true,
        error: null,
      },
    ],
  },
};
function Preview() {
  const [db, setDb] = useState(seed);
  window.settingsDb = db;
  return (
    <main style={{ padding: 20, maxWidth: 1400, margin: "auto" }}>
      <h1>Ayarlar</h1>
      <SettingsPage
        db={db}
        user={{ id: 1, role: "admin" }}
        navigate={(...args) => (window.destination = args)}
        run={async (action, p) => {
          window.settingsAction = { action, p };
          if (window.failSettings)
            return { ok: false, message: "Doğrulama hatası" };
          const mapping = {
            saveBranchProfile: "profile",
            saveOpeningHours: "opening",
            saveNotificationPreferences: "notifications",
          };
          if (mapping[action]) {
            const { confirmed, ...value } = p;
            setDb((old) => ({
              ...old,
              systemSettings: {
                ...old.systemSettings,
                [mapping[action]]: value,
              },
            }));
          }
          return { ok: true };
        }}
      />
    </main>
  );
}
createRoot(document.getElementById("root")).render(<Preview />);
