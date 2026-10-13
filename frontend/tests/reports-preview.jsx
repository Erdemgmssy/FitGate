import React from "react";
import { createRoot } from "react-dom/client";
import { ReportsPage } from "../src/ReportsPage.jsx";
import "../src/styles.css";
createRoot(document.getElementById("root")).render(
  <main className="page-content">
    <ReportsPage
      user={{
        role: new URLSearchParams(location.search).get("role") || "admin",
      }}
    />
  </main>,
);
