import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { FinancePage } from "../src/BusinessPages.jsx";
import { MemberPayments } from "../src/FinanceDetails.jsx";
import { buildSeed } from "../src/gym.mjs";
import "../src/styles.css";
const fixture = buildSeed();
fixture.finance = {
  todayCents: 10001,
  monthCents: 50001,
  remainingCents: 20001,
  overdueCents: 10001,
  pendingInstallments: 2,
  refundedCents: 501,
};
fixture.payments.forEach((row) => {
  row.actorId = 1;
  row.recordedAt = row.at;
});
function Preview() {
  const [db, setDb] = useState(fixture);
  if (window.financeMember)
    return (
      <main className="page-content">
        <MemberPayments db={db} member={db.members[0]} />
      </main>
    );
  return (
    <main className="page-content">
      <FinancePage
        db={db}
        isAdmin={window.financeAdmin !== false}
        run={async (type, payload) => {
          window.financeAction = { type, payload };
          if (type === "collect")
            setDb((old) => ({
              ...old,
              payments: [
                ...old.payments,
                {
                  ...payload,
                  id: "qa-payment",
                  number: "QA-NEW",
                  amountCents: Math.round(Number(payload.amount) * 100),
                  actor: "QA staff",
                  actorId: 1,
                  recordedAt: payload.at,
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
