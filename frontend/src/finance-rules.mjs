import { dateKey } from "./attendance.mjs";
import { invoiceDebt } from "./gym.mjs";

export function financialRecords(db, filters = {}, type = "payments") {
  const {
    memberId = "all",
    from = "",
    to = "",
    actor = "all",
    method = "all",
    onlyDebt = false,
  } = filters;
  const invoiceIds = new Set(
    db.invoices
      .filter(
        (row) =>
          (memberId === "all" || row.memberId === memberId) &&
          (!onlyDebt || invoiceDebt(db, row) > 0),
      )
      .map((row) => row.id),
  );
  return db[type].filter((row) => {
    const payment =
      type === "refunds"
        ? db.payments.find((p) => p.id === row.paymentId)
        : row;
    const day = dateKey(new Date(row.at));
    return (
      payment &&
      invoiceIds.has(payment.invoiceId) &&
      (!from || day >= from) &&
      (!to || day <= to) &&
      (actor === "all" || String(row.actorId) === actor) &&
      (method === "all" || payment.method === method)
    );
  });
}
