import React from "react";
import { createRoot } from "react-dom/client";
import { DevicesPage } from "../src/AccessPages.jsx";
import "../src/styles.css";

createRoot(document.getElementById("root")).render(
  <main className="main-content">
    <DevicesPage
      db={window.deviceFixture}
      run={(action, payload) => {
        window.deviceAction = { action, payload };
        return Promise.resolve({ ok: true });
      }}
    />
  </main>,
);
