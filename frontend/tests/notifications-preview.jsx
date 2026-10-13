import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { NotificationsPage } from "../src/NotificationsPage.jsx";
import "../src/styles.css";

const items = [
  {
    id: "info",
    message: "Yaklaşan Yoga dersi",
    severity: "info",
    type: "class",
    target: "classes",
    targetId: "class-1",
    at: "2026-10-13T10:00:00+03:00",
    status: "active",
    read: false,
  },
  {
    id: "critical",
    message: "Turnike RFID arızası",
    severity: "critical",
    type: "device",
    target: "devices",
    targetId: "device-1",
    at: "2026-10-12T10:00:00+03:00",
    status: "active",
    read: false,
  },
  {
    id: "warning",
    message: "Üyelik bitişi: " + "UzunÜyeAdı".repeat(20),
    severity: "warning",
    type: "membership",
    target: "members",
    targetId: "member-1",
    memberId: "member-1",
    at: "2026-10-13T08:00:00+03:00",
    status: "active",
    read: false,
  },
  {
    id: "resolved",
    message: "Bağlantı yeniden kuruldu",
    severity: "critical",
    type: "device",
    target: "devices",
    targetId: "device-1",
    at: "2026-10-11T08:00:00+03:00",
    status: "resolved",
    resolvedAt: "2026-10-13T08:00:00+03:00",
    resolution: "Güncel cihaz bildirimiyle düzeldiği doğrulandı.",
    read: true,
  },
];
function Preview() {
  const [notices, setNotices] = useState(items);
  window.failRead = false;
  return (
    <main style={{ padding: 20, maxWidth: 1400, margin: "auto" }}>
      <h1>Bildirimler</h1>
      <NotificationsPage
        db={{ source: "server", notificationItems: notices }}
        isAdmin={!location.search.includes("staff")}
        canCompose
        run={async (action, p) => {
          if (window.failRead) return { ok: false, message: "Bağlantı hatası" };
          if (action === "readNotice")
            setNotices((rows) =>
              rows.map((r) => (r.id === p.id ? { ...r, read: true } : r)),
            );
          window.lastAction = { action, p };
          return { ok: true };
        }}
        navigate={(page, memberId, targetId) => {
          window.navigation = { page, memberId, targetId };
        }}
      />
    </main>
  );
}
createRoot(document.getElementById("root")).render(<Preview />);
