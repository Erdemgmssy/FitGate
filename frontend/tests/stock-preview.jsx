import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { StockPage } from "../src/StockPage.jsx";
import { buildSeed } from "../src/gym.mjs";
import { cents } from "../src/stock-rules.mjs";
import "../src/styles.css";
const seed = buildSeed();
seed.stockPermissions = {
  manage: true,
  sell: true,
  discount: true,
  returns: true,
};
seed.stockSummary = null;
seed.cashSessions = [];
seed.suppliers = [
  {
    id: "s1",
    name: "Tedarik A",
    active: true,
    phone: "05321112233",
    email: "s@test.com",
    contact: "İstanbul",
  },
];
seed.products = [
  {
    id: "p1",
    name: "Su",
    code: "W",
    barcode: "8690001",
    category: "İçecek",
    price: 10.01,
    cost: 2,
    stock: 5,
    minimum: 2,
    supplierId: "s1",
    active: true,
    revision: 1,
    unit: "adet",
  },
  {
    id: "p2",
    name: "Protein Bar",
    code: "B",
    barcode: "8690002",
    category: "Gıda",
    price: 20,
    cost: 5,
    stock: 5,
    minimum: 2,
    supplierId: "s1",
    active: true,
    revision: 1,
    unit: "adet",
  },
];
seed.sales = [];
seed.stockMovements = [];
function Preview() {
  const [db, setDb] = useState(seed);
  return (
    <main className="page-content">
      <StockPage
        db={db}
        isAdmin
        run={async (type, payload) => {
          window.stockAction = { type, payload };
          if (type === "checkoutProducts") {
            let remaining = cents(payload.discount);
            const lines = payload.items.map((item, index) => {
              const p = db.products.find((p) => p.id === item.productId),
                subtotal = cents(p.price) * item.quantity,
                share = index === 0 ? remaining : 0;
              remaining -= share;
              return {
                id: "sale-" + index,
                checkoutId: "checkout-qa",
                number: "URN-QA",
                productId: p.id,
                productName: p.name,
                quantity: item.quantity,
                unitPriceCents: cents(p.price),
                discountCents: share,
                totalCents: subtotal - share,
                at: new Date().toISOString(),
                actor: "Admin QA",
                method: payload.method,
                memberId: payload.memberId,
                returnedQuantity: 0,
                refundedCents: 0,
                unit: "adet",
                returned: false,
              };
            });
            setDb((old) => ({
              ...old,
              sales: [...old.sales, ...lines],
              products: old.products.map((p) => ({
                ...p,
                stock:
                  p.stock -
                  (payload.items.find((i) => i.productId === p.id)?.quantity ||
                    0),
              })),
            }));
            return { ok: true, result: { checkoutId: "checkout-qa" } };
          }
          if (type === "returnSale")
            setDb((old) => ({
              ...old,
              sales: old.sales.map((s) =>
                s.id === payload.id
                  ? {
                      ...s,
                      returnedQuantity: Number(payload.quantity),
                      refundedCents: 1001,
                    }
                  : s,
              ),
            }));
          if (type === "saveProduct")
            setDb((old) => ({
              ...old,
              products: payload.id
                ? old.products.map((p) =>
                    p.id === payload.id
                      ? { ...payload, revision: p.revision + 1 }
                      : p,
                  )
                : [...old.products, { ...payload, id: "p3", revision: 1 }],
            }));
          return { ok: true, result: { id: "qa" } };
        }}
      />
    </main>
  );
}
createRoot(document.getElementById("root")).render(<Preview />);
