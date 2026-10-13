import { turkeyDay } from "./class-rules.mjs";
export function cents(value) {
  const match = /^(\d{1,10})(?:\.(\d{1,2}))?$/.exec(String(value ?? 0));
  if (!match) throw new Error("Tutar en fazla iki ondalık hane içermeli.");
  return Number(match[1]) * 100 + Number((match[2] || "").padEnd(2, "0"));
}
export function cartTotal(cart, discount = "0") {
  const subtotal = cart.reduce(
      (sum, row) => sum + row.unitPriceCents * row.quantity,
      0,
    ),
    reduction = cents(discount || 0);
  if (!Number.isSafeInteger(subtotal) || reduction > subtotal)
    throw new Error("İndirim satış toplamını aşamaz.");
  return { subtotal, discount: reduction, total: subtotal - reduction };
}
export function productSearch(products, query = "") {
  const value = query.trim().toLocaleLowerCase("tr");
  return products.filter((row) =>
    (row.name + " " + row.code + " " + row.barcode + " " + row.category)
      .toLocaleLowerCase("tr")
      .includes(value),
  );
}
export function saleGroups(sales) {
  const groups = new Map();
  for (const sale of sales) {
    const key = sale.checkoutId || sale.id;
    const group = groups.get(key) || {
      id: key,
      number: sale.number || sale.id,
      at: sale.at,
      method: sale.method,
      memberId: sale.memberId,
      actor: sale.actor,
      lines: [],
      totalCents: 0,
      refundCents: 0,
    };
    group.lines.push(sale);
    group.totalCents += sale.totalCents;
    group.refundCents +=
      sale.refundedCents ?? (sale.returned ? sale.totalCents : 0);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => new Date(b.at) - new Date(a.at));
}
export function returnPreview(sale, quantity) {
  const returned = sale.returnedQuantity ?? (sale.returned ? sale.quantity : 0),
    refunded = sale.refundedCents ?? (sale.returned ? sale.totalCents : 0);
  if (
    !Number.isInteger(Number(quantity)) ||
    quantity < 1 ||
    Number(quantity) + returned > sale.quantity
  )
    throw new Error("İade miktarı geçersiz.");
  return (
    Math.floor(
      (sale.totalCents * (returned + Number(quantity))) / sale.quantity,
    ) - refunded
  );
}
export function stockSummary(db, now = new Date()) {
  const today = turkeyDay(now),
    month = today.slice(0, 7),
    returns = db.stockMovements.filter((r) => r.returnedUnits > 0);
  const net = (prefix) =>
    db.sales
      .filter((r) => turkeyDay(r.at).startsWith(prefix))
      .reduce((s, r) => s + r.totalCents, 0) -
    returns
      .filter((r) => turkeyDay(r.at).startsWith(prefix))
      .reduce((s, r) => s + r.refundCents, 0);
  return {
    productCount: db.products.length,
    criticalCount: db.products.filter(
      (p) => p.active !== false && p.stock > 0 && p.stock <= p.minimum,
    ).length,
    emptyCount: db.products.filter((p) => p.active !== false && p.stock === 0)
      .length,
    todayNetCents: net(today),
    monthNetCents: net(month),
    returnedUnits: returns.reduce((s, r) => s + r.returnedUnits, 0),
  };
}
