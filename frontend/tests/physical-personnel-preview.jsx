import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { EmployeesPage } from "../src/Personnel.jsx";
import "../src/styles.css";

function Preview() {
  const [db, setDb] = useState(window.personnelFixture);
  window.setPersonnelFixture = setDb;
  return <main className="main-content"><EmployeesPage db={db} user={{id: "worker", role: "staff"}} isAdmin={false} run={async (action, payload) => {
    window.personnelAction = {action, payload};
    if (action === "physicalAttendanceIntent") {
      setDb(previous => ({...previous, employees: previous.employees.map(row => ({...row, passageIntent: payload.intent === "cancel" ? {} : {action: payload.intent, expiresAt: new Date(Date.now() + 900000).toISOString()}}))}));
    }
    return {ok: true};
  }} /></main>;
}

createRoot(document.getElementById("root")).render(<Preview />);
