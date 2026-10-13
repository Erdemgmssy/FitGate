import React, { useState, useRef, useEffect } from "react";
import {
  Plus,
  Pencil,
  Trash2,
  ShoppingCart,
  Package,
  AlertTriangle,
  Wallet,
  RotateCcw,
  Save,
  Printer,
  RefreshCw,
  Minus,
  History,
} from "lucide-react";
import {
  Button,
  IconButton,
  Field,
  Dialog,
  Table,
  Empty,
  Metric,
  Badge,
  methods,
} from "./ui";
import { money, displayDate, displayTime } from "./attendance.mjs";
import { CashPanel } from "./BusinessPages";
import {
  cents,
  cartTotal,
  productSearch,
  saleGroups,
  returnPreview,
  stockSummary,
} from "./stock-rules.mjs";
import { turkeyDay } from "./class-rules.mjs";

const movementNames = {
  opening: "Açılış",
  receipt: "Mal kabul",
  sale: "Satış",
  return: "İade",
  legacy_return: "Eski iade",
  loss: "Hasar / kayıp",
  adjustment: "Düzeltme",
  count: "Fiziksel sayım",
  cost_change: "Alış fiyatı",
};
const productDefaults = {
  name: "",
  code: "",
  barcode: "",
  category: "",
  description: "",
  price: "0",
  cost: "0",
  unit: "adet",
  stock: 0,
  minimum: 5,
  supplierId: "",
  image: "",
  active: true,
  expires: "",
};
export function StockPage({ db, run, isAdmin, focusedProductId }) {
  const [tab, setTab] = useState("checkout"),
    [query, setQuery] = useState(""),
    [active, setActive] = useState("all"),
    [category, setCategory] = useState(""),
    [supplierId, setSupplier] = useState(""),
    [movementKind, setMovementKind] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [dialog, setDialog] = useState(null);
  useEffect(()=>{if(!focusedProductId)return;const product=db.products.find(p=>p.id===focusedProductId);if(product){setTab('products');setQuery(product.name);}},[focusedProductId]);
  const rights = db.stockPermissions || {
    manage: isAdmin,
    sell: true,
    returns: isAdmin,
    discount: isAdmin,
  };
  const stats = db.stockSummary || stockSummary(db),
    products = productSearch(db.products, query).filter(
      (p) =>
        (active === "all" || (p.active !== false) === (active === "active")) &&
        (!category || p.category === category) &&
        (!supplierId || p.supplierId === supplierId),
    );
  const groups = saleGroups(db.sales).filter(
    (s) => (!from || turkeyDay(s.at) >= from) && (!to || turkeyDay(s.at) <= to),
  );
  const movements = db.stockMovements
    .filter(
      (m) =>
        (!supplierId || m.supplierId === supplierId) &&
        (!movementKind || m.kind === movementKind) &&
        (!from || turkeyDay(m.at) >= from) &&
        (!to || turkeyDay(m.at) <= to),
    )
    .slice()
    .reverse();
  const supplierName = (id) =>
    db.suppliers?.find((s) => s.id === id)?.name || "—";
  const save = async (type, payload) => {
    const result = await run(type, payload);
    if (result?.ok) setDialog(null);
    return result;
  };
  const history = (rows = movements) => (
    <Table
      headers={[
        "Tarih",
        "Ürün",
        "Tür",
        "Miktar",
        "Alış / iade",
        "Tedarikçi / mal kabul",
        "Gerekçe",
        "Personel",
      ]}
    >
      {rows.map((m) => (
        <tr key={m.id}>
          <td>
            {displayDate(m.at)}
            <small>{displayTime(m.at)}</small>
          </td>
          <td>{db.products.find((p) => p.id === m.productId)?.name}</td>
          <td>{movementNames[m.kind] || "Eski hareket"}</td>
          <td>
            {m.quantity > 0 ? "+" : ""}
            {m.quantity}
            {m.returnedUnits > 0 && (
              <small>
                {m.returnedUnits} ürün iade ·{" "}
                {m.restocked ? "Stoğa alındı" : "Satılamaz"}
              </small>
            )}
          </td>
          <td>
            {m.refundCents > 0
              ? money(m.refundCents / 100)
              : m.unitCostCents != null
                ? `${money(m.unitCostCents / 100)} / birim`
                : "—"}
          </td>
          <td>
            {supplierName(m.supplierId)}
            <small>{m.receivedCode}</small>
          </td>
          <td>{m.reason}</td>
          <td>{m.actor || "Eski kayıt: bilinmiyor"}</td>
        </tr>
      ))}
    </Table>
  );
  return (
    <section className="page-grid stock-page">
      <div className="stock-metrics">
        <Metric icon={Package} label="Ürün çeşidi" value={stats.productCount} />
        <Metric
          icon={AlertTriangle}
          label="Kritik stok"
          value={stats.criticalCount}
          tone="amber"
        />
        <Metric
          icon={Wallet}
          label={isAdmin?"Bugünkü net ürün satışı":"Bugünkü satışlarım"}
          value={money(stats.todayNetCents / 100)}
        />
        <Metric
          icon={Wallet}
          label={isAdmin?"Bu ay net ürün satışı":"Bu ay satışlarım"}
          value={money(stats.monthNetCents / 100)}
        />
        <Metric
          icon={Package}
          label="Tükenen ürünler"
          value={stats.emptyCount}
        />
        <Metric
          icon={RotateCcw}
          label="İade edilen ürün"
          value={stats.returnedUnits}
        />
      </div>
      <div
        className="stock-tabs"
        role="tablist"
        aria-label="Stok ve satış bölümleri"
      >
        {[
          ["checkout", "Hızlı Satış"],
          ["products", "Ürünler"],
          ["movements", "Stok Hareketleri"],
          ["suppliers", "Tedarikçiler"],
          ["history", "Satış Geçmişi"],
        ]
          .filter(([id]) => rights.manage || ['checkout','history'].includes(id))
          .map(([id, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={tab === id}
              onClick={() => {
                setTab(id);
                setQuery("");
                setSupplier("");
              }}
            >
              {label}
            </button>
          ))}
      </div>
      {tab === "checkout" && (
        <Checkout
          db={db}
          run={run}
          rights={rights}
          onReceipt={(id) => setDialog({ type: "receipt", id })}
        />
      )}
      {tab === "products" && (
        <>
          <div className="filter-bar">
            <Field label="Ürün ara">
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </Field>
            <Field label="Ürün durumu">
              <select
                value={active}
                onChange={(e) => setActive(e.target.value)}
              >
                <option value="all">Tümü</option>
                <option value="active">Aktif</option>
                <option value="inactive">Pasif</option>
              </select>
            </Field>
            <Field label="Kategori">
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">Tümü</option>
                {[...new Set(db.products.map((p) => p.category))]
                  .filter(Boolean)
                  .map((c) => (
                    <option key={c}>{c}</option>
                  ))}
              </select>
            </Field>
            {rights.manage && (
              <Button
                icon={Plus}
                tone="primary"
                onClick={() => setDialog({ type: "product" })}
              >
                Ürün ekle
              </Button>
            )}
          </div>
          <Table
            headers={[
              "Ürün",
              "Kategori / birim",
              "Fiyat",
              "Stok",
              "Tedarikçi",
              "Durum",
              "İşlem",
            ]}
          >
            {products.map((p) => (
              <tr key={p.id}>
                <td>
                  <div className="stock-product-name">
                    {p.image && <img src={p.image} alt={p.name} />}
                    <div>
                      <strong>{p.name}</strong>
                      <small>
                        {p.code} · {p.barcode || "Barkod yok"}
                      </small>
                    </div>
                  </div>
                </td>
                <td>
                  {p.category || "—"}
                  <small>{p.unit || "adet"}</small>
                </td>
                <td>
                  {money(p.price)}
                  {rights.manage && <small>Alış: {money(p.cost)}</small>}
                </td>
                <td>
                  <Badge status={p.stock <= p.minimum ? "rejected" : "active"}>
                    {p.stock}
                  </Badge>
                  <small>Kritik: {p.minimum}</small>
                </td>
                <td>
                  {supplierName(p.supplierId) === "—"
                    ? p.supplier || "—"
                    : supplierName(p.supplierId)}
                </td>
                <td>
                  <Badge status={p.active === false ? "inactive" : "active"} />
                  {p.expires && <small>SKT: {displayDate(p.expires)}</small>}
                </td>
                <td>
                  {rights.manage && (
                    <div className="button-group">
                      <IconButton
                        icon={Pencil}
                        label={`Ürünü düzenle: ${p.name}`}
                        onClick={() =>
                          setDialog({ type: "product", product: p })
                        }
                      />
                      <Button
                        icon={Plus}
                        onClick={() => setDialog({ type: "stock", product: p })}
                      >
                        Stok işlemi
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </Table>
          {!products.length && <Empty>Ürün bulunamadı.</Empty>}
        </>
      )}
      {["movements", "history"].includes(tab) && (
        <div className="filter-bar">
          <Field label="Başlangıç tarihi">
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </Field>
          <Field label="Bitiş tarihi">
            <input
              type="date"
              value={to}
              min={from}
              onChange={(e) => setTo(e.target.value)}
            />
          </Field>
          {tab === "movements" && (
            <>
              <Field label="Hareket türü">
                <select
                  value={movementKind}
                  onChange={(e) => setMovementKind(e.target.value)}
                >
                  <option value="">Tümü</option>
                  {Object.entries(movementNames).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value}
                    </option>
                  ))}
                </select>
              </Field>
              {rights.manage && (
                <Field label="Tedarikçi">
                  <select
                    value={supplierId}
                    onChange={(e) => setSupplier(e.target.value)}
                  >
                    <option value="">Tümü</option>
                    {(db.suppliers || []).map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
            </>
          )}
        </div>
      )}
      {tab === "movements" && (
        <>
          {history()}
          {!movements.length && <Empty>Stok hareketi yok.</Empty>}
        </>
      )}
      {tab === "suppliers" && rights.manage && (
        <>
          <div className="page-actions">
            <h2>Tedarikçiler</h2>
            <Button
              icon={Plus}
              tone="primary"
              onClick={() => setDialog({ type: "supplier" })}
            >
              Tedarikçi ekle
            </Button>
          </div>
          <Table
            headers={["Tedarikçi", "İletişim", "Ürünler", "Durum", "İşlem"]}
          >
            {(db.suppliers || []).map((s) => (
              <tr key={s.id}>
                <td>
                  <strong>{s.name}</strong>
                  <small>{s.contact}</small>
                </td>
                <td>
                  {s.phone || "—"}
                  <small>{s.email}</small>
                </td>
                <td>
                  {db.products
                    .filter((p) => p.supplierId === s.id)
                    .map((p) => p.name)
                    .join(", ") || "—"}
                </td>
                <td>
                  <Badge status={s.active ? "active" : "inactive"} />
                </td>
                <td>
                  <div className="button-group">
                    <IconButton
                      icon={Pencil}
                      label={`Tedarikçiyi düzenle: ${s.name}`}
                      onClick={() =>
                        setDialog({ type: "supplier", supplier: s })
                      }
                    />
                    <Button
                      icon={History}
                      onClick={() =>
                        setDialog({ type: "supplierHistory", supplier: s })
                      }
                    >
                      Alış geçmişi
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </Table>
          {!db.suppliers?.length && <Empty>Tedarikçi kaydı yok.</Empty>}
        </>
      )}
      {tab === "history" && (
        <>
          <Table
            headers={[
              "Satış / tarih",
              "Ürünler",
              "Müşteri",
              "Tutar / iade",
              "Yöntem",
              "Personel",
              "Durum",
              "İşlem",
            ]}
          >
            {groups.map((s) => (
              <tr key={s.id}>
                <td>
                  <button
                    className="text-button stock-sale-number"
                    onClick={() => setDialog({ type: "receipt", id: s.id })}
                  >
                    {s.number}
                  </button>
                  <small>
                    {displayDate(s.at)} {displayTime(s.at)}
                  </small>
                </td>
                <td>
                  {s.lines.map((l) => (
                    <div key={l.id}>
                      {l.productName} × {l.quantity}
                      <small>İade: {l.returnedQuantity || 0}</small>
                    </div>
                  ))}
                </td>
                <td>
                  {db.members.find((m) => m.id === s.memberId)?.name ||
                    "Misafir"}
                </td>
                <td>
                  {money(s.totalCents / 100)}
                  <small>İade: {money(s.refundCents / 100)}</small>
                </td>
                <td>
                  {methods.find((m) => m.value === s.method)?.label || s.method}
                </td>
                <td>{s.actor}</td>
                <td>
                  <Badge
                    status={
                      s.lines.every((l) => l.returned)
                        ? "cancelled"
                        : s.refundCents
                          ? "waiting"
                          : "active"
                    }
                  >
                    {s.lines.every((l) => l.returned)
                      ? "Tam iade"
                      : s.lines.some((l) => l.returnedQuantity > 0)
                        ? "Kısmi iade"
                        : "Satıldı"}
                  </Badge>
                </td>
                <td>
                  {rights.returns &&
                    s.lines
                      .filter((l) => l.returnedQuantity < l.quantity)
                      .map((l) => (
                        <Button
                          key={l.id}
                          icon={RotateCcw}
                          onClick={() => setDialog({ type: "return", sale: l })}
                        >
                          {l.productName} iade
                        </Button>
                      ))}
                </td>
              </tr>
            ))}
          </Table>
          {!groups.length && <Empty>Satış kaydı yok.</Empty>}
        </>
      )}
      {rights.manage && (
        <CashPanel
          db={db}
          run={run}
          session={db.cashSessions?.find((s) => !s.closedAt)}
        />
      )}
      {dialog?.type === "receipt" && (
        <SaleReceipt db={db} id={dialog.id} onClose={() => setDialog(null)} />
      )}
      {dialog?.type === "supplierHistory" && (
        <Dialog
          title={`${dialog.supplier.name} / Alış geçmişi`}
          onClose={() => setDialog(null)}
        >
          {history(
            db.stockMovements
              .filter((m) => m.supplierId === dialog.supplier.id)
              .slice()
              .reverse(),
          )}
        </Dialog>
      )}
      {dialog?.type === "product" && (
        <ProductDialog
          db={db}
          product={dialog.product}
          run={save}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === "supplier" && (
        <EditDialog
          title="Tedarikçi bilgileri"
          initial={{
            name: "",
            phone: "",
            email: "",
            contact: "",
            active: true,
            ...dialog.supplier,
          }}
          onClose={() => setDialog(null)}
          onSave={(form) => save("saveSupplier", form)}
        >
          {(form, set) => (
            <>
              <div className="form-grid">
                {[
                  ["name", "Tedarikçi adı", "text", true],
                  ["phone", "Telefon", "tel", false],
                  ["email", "E-posta", "email", false],
                  ["contact", "İletişim / adres", "textarea", false],
                ].map(([key, label, type, required]) => (
                  <Input
                    key={key}
                    name={key}
                    label={label}
                    type={type}
                    required={required}
                    form={form}
                    set={set}
                  />
                ))}
              </div>
              <CheckField
                label="Tedarikçi aktif"
                name="active"
                form={form}
                set={set}
              />
            </>
          )}
        </EditDialog>
      )}
      {dialog?.type === "stock" && (
        <StockDialog
          db={db}
          product={dialog.product}
          run={save}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === "return" && (
        <ReturnDialog
          sale={dialog.sale}
          run={save}
          onClose={() => setDialog(null)}
        />
      )}
    </section>
  );
}

function Checkout({ db, run, rights, onReceipt }) {
  const [query, setQuery] = useState(""),
    [cart, setCart] = useState([]),
    [memberId, setMember] = useState(""),
    [method, setMethod] = useState("cash"),
    [discount, setDiscount] = useState("0"),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const lock = useRef(false),
    scanner = useRef(null),
    products = productSearch(
      db.products.filter((p) => p.active !== false),
      query,
    );
  let totals = { subtotal: 0, total: 0 };
  try {
    totals = cartTotal(cart, discount);
  } catch {}
  const add = (product) => {
    if (!rights.sell || product.stock <= 0) return;
    setError("");
    setCart((old) => {
      const row = old.find((r) => r.productId === product.id);
      if (row && row.quantity >= product.stock) {
        setError("Stok sınırına ulaşıldı.");
        return old;
      }
      return row
        ? old.map((r) =>
            r.productId === product.id ? { ...r, quantity: r.quantity + 1 } : r,
          )
        : [
            ...old,
            {
              productId: product.id,
              name: product.name,
              quantity: 1,
              unitPriceCents: cents(product.price),
              revision: product.revision,
              unit: product.unit || "adet",
            },
          ];
    });
    setQuery("");
    scanner.current?.focus();
  };
  const quantity = (id, value) =>
    setCart((old) =>
      old.map((row) =>
        row.productId === id ? { ...row, quantity: Number(value) } : row,
      ),
    );
  return (
    <div className="stock-split">
      <div className="stock-catalog">
        <Field label="Ürün adı veya barkod">
          <input
            ref={scanner}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const product = db.products.find(
                  (p) =>
                    p.active !== false &&
                    (p.barcode === query.trim() || p.code === query.trim()),
                );
                if (product) add(product);
                else setError("Barkod / ürün kodu bulunamadı.");
              }
            }}
          />
        </Field>
        <Table headers={["Ürün", "Fiyat", "Stok", ""]}>
          {products.map((p) => (
            <tr key={p.id}>
              <td>
                <strong>{p.name}</strong>
                <small>{p.barcode || p.code}</small>
              </td>
              <td>{money(p.price)}</td>
              <td>
                <Badge status={p.stock <= p.minimum ? "rejected" : "active"}>
                  {p.stock} {p.unit || "adet"}
                </Badge>
              </td>
              <td>
                <IconButton
                  icon={Plus}
                  label={`Sepete ekle: ${p.name}`}
                  disabled={
                    busy ||
                    !rights.sell ||
                    p.stock <= 0 ||
                    (p.expires && p.expires < turkeyDay())
                  }
                  onClick={() => add(p)}
                />
              </td>
            </tr>
          ))}
        </Table>
        {!products.length && <Empty>Ürün bulunamadı.</Empty>}
      </div>
      <form
        className="stock-cart"
        onSubmit={async (e) => {
          e.preventDefault();
          if (lock.current) return;
          lock.current = true;
          setBusy(true);
          setError("");
          try {
            const amounts = cartTotal(cart, discount);
            if (!cart.length) throw Error("Sepete ürün ekleyin.");
            const result = await run("checkoutProducts", {
              items: cart.map((r) => ({
                productId: r.productId,
                quantity: r.quantity,
                revision: r.revision,
              })),
              memberId,
              method,
              discount: (amounts.discount / 100).toFixed(2),
              reason,
            });
            if (result?.ok) {
              setCart([]);
              setDiscount("0");
              setReason("");
              onReceipt(result.result.checkoutId);
            } else setError(result?.message || "Satış tamamlanamadı.");
          } catch (err) {
            setError(err.message);
          } finally {
            lock.current = false;
            setBusy(false);
          }
        }}
      >
        <fieldset disabled={busy} className="finance-fields">
          <div className="section-header">
            <h2>Satış sepeti</h2>
            <ShoppingCart size={19} />
          </div>
          {!cart.length && <Empty>Sepet boş.</Empty>}
          {cart.map((row) => (
            <div className="stock-cart-line" key={row.productId}>
              <div>
                <strong>{row.name}</strong>
                <small>
                  {money(row.unitPriceCents / 100)} / {row.unit}
                </small>
              </div>
              <div className="stock-stepper">
                <IconButton
                  icon={Minus}
                  label={`Azalt: ${row.name}`}
                  disabled={row.quantity <= 1}
                  onClick={(e) => {
                    e.preventDefault();
                    quantity(row.productId, row.quantity - 1);
                  }}
                  type="button"
                />
                <input
                  aria-label={`Miktar: ${row.name}`}
                  type="number"
                  required
                  min="1"
                  max={
                    db.products.find((p) => p.id === row.productId)?.stock || 1
                  }
                  step="1"
                  value={row.quantity}
                  onChange={(e) => quantity(row.productId, e.target.value)}
                />
                <IconButton
                  icon={Plus}
                  label={`Artır: ${row.name}`}
                  type="button"
                  onClick={() => quantity(row.productId, row.quantity + 1)}
                />
              </div>
              <strong>
                {money((row.unitPriceCents * row.quantity) / 100)}
              </strong>
              <IconButton
                type="button"
                icon={Trash2}
                label={`Sepetten çıkar: ${row.name}`}
                onClick={() =>
                  setCart((old) =>
                    old.filter((r) => r.productId !== row.productId),
                  )
                }
              />
            </div>
          ))}
          {cart.some(
            (r) =>
              r.revision !==
              db.products.find((p) => p.id === r.productId)?.revision,
          ) && (
            <Button
              type="button"
              icon={RefreshCw}
              onClick={() =>
                setCart((old) =>
                  old.map((r) => {
                    const p = db.products.find((p) => p.id === r.productId);
                    return p
                      ? {
                          ...r,
                          name: p.name,
                          revision: p.revision,
                          unitPriceCents: cents(p.price),
                        }
                      : r;
                  }),
                )
              }
            >
              Güncel fiyatları al
            </Button>
          )}
          <div className="form-grid">
            <Field label="Müşteri">
              <select
                value={memberId}
                onChange={(e) => setMember(e.target.value)}
              >
                <option value="">Misafir</option>
                {db.members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} · {m.number}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Ödeme yöntemi">
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                <option value="cash">Nakit</option>
                <option value="pos">Harici POS kaydı</option>
                <option value="bank">Havale / EFT</option>
              </select>
            </Field>
          </div>
          {rights.discount && (
            <>
              <Field label="İndirim (TL)">
                <input
                  type="number"
                  min="0"
                  step=".01"
                  max={totals.subtotal / 100}
                  value={discount}
                  onChange={(e) => setDiscount(e.target.value)}
                />
              </Field>
              {Number(discount) > 0 && (
                <Field label="İndirim gerekçesi">
                  <input
                    required
                    maxLength={1500}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </Field>
              )}
            </>
          )}
          <dl className="stock-totals">
            <div>
              <dt>Ara toplam</dt>
              <dd>{money(totals.subtotal / 100)}</dd>
            </div>
            <div>
              <dt>İndirim</dt>
              <dd>{money((totals.discount || 0) / 100)}</dd>
            </div>
            <div>
              <dt>Genel toplam</dt>
              <dd>{money(totals.total / 100)}</dd>
            </div>
          </dl>
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <div className="button-group">
            <Button
              type="button"
              icon={Trash2}
              disabled={!cart.length}
              onClick={() => {
                setCart([]);
                setDiscount("0");
                setReason("");
                setError("");
              }}
            >
              Sepeti iptal et
            </Button>
            <Button
              type="submit"
              tone="primary"
              icon={Wallet}
              disabled={!cart.length || busy || !rights.sell}
            >
              {busy ? "Kaydediliyor" : "Satışı tamamla"}
            </Button>
          </div>
        </fieldset>
      </form>
    </div>
  );
}

function EditDialog({ title, initial, onClose, onSave, children }) {
  const [form, setForm] = useState(initial),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    lock = useRef(false),
    set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  return (
    <Dialog title={title} onClose={() => !busy && onClose()}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (lock.current) return;
          lock.current = true;
          setBusy(true);
          setError("");
          try {
            const result = await onSave(form);
            if (!result?.ok)
              setError(result?.message || "İşlem tamamlanamadı.");
          } catch (err) {
            setError(err.message);
          } finally {
            setBusy(false);
            lock.current = false;
          }
        }}
      >
        <fieldset disabled={busy} className="finance-fields">
          {children(form, set)}
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <Button type="button" onClick={onClose}>
              Vazgeç
            </Button>
            <Button type="submit" tone="primary" icon={Save} disabled={busy}>
              Kaydet
            </Button>
          </div>
        </fieldset>
      </form>
    </Dialog>
  );
}
function Input({
  name,
  label,
  type = "text",
  required = false,
  form,
  set,
  min,
  max,
}) {
  return (
    <Field label={label}>
      {type === "textarea" ? (
        <textarea
          required={required}
          maxLength={600}
          value={form[name] ?? ""}
          onChange={(e) => set(name, e.target.value)}
        />
      ) : (
        <input
          required={required}
          type={type}
          min={min ?? (type === "number" ? 0 : undefined)}
          max={max}
          step={
            type === "number" && ["price", "cost"].includes(name)
              ? ".01"
              : type === "number"
                ? "1"
                : undefined
          }
          value={form[name] ?? ""}
          onChange={(e) => set(name, e.target.value)}
        />
      )}
    </Field>
  );
}
function CheckField({ name, label, form, set }) {
  return (
    <label className="check-field">
      <input
        type="checkbox"
        checked={form[name]}
        onChange={(e) => set(name, e.target.checked)}
      />
      {label}
    </label>
  );
}
function SupplierField({ db, form, set, required = false }) {
  return (
    <Field label="Tedarikçi">
      <select
        required={required}
        value={form.supplierId || ""}
        onChange={(e) => set("supplierId", e.target.value)}
      >
        <option value="">Tedarikçi seç</option>
        {(db.suppliers || [])
          .filter((s) => s.active || s.id === form.supplierId)
          .map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
      </select>
    </Field>
  );
}

function ProductDialog({ db, product, run, onClose }) {
  return (
    <EditDialog
      title={product ? "Ürünü düzenle" : "Ürün ekle"}
      initial={{ ...productDefaults, ...product }}
      onClose={onClose}
      onSave={(form) => {
        const payload = { ...form };
        if (product) delete payload.stock;
        return run("saveProduct", payload);
      }}
    >
      {(form, set) => (
        <>
          <div className="form-grid">
            {[
              ["name", "Ürün adı", "text", true],
              ["code", "Ürün kodu", "text", true],
              ["barcode", "Barkod", "text", false],
              ["category", "Kategori", "text", false],
              ["description", "Açıklama", "textarea", false],
              ["price", "Satış fiyatı (TL)", "number", true],
              ["cost", "Alış fiyatı (TL)", "number", true],
              ["unit", "Birim", "text", true],
              ...(!product ? [["stock", "Açılış stok", "number", true]] : []),
              ["minimum", "Kritik stok seviyesi", "number", true],
              ["expires", "Son kullanma tarihi (isteğe bağlı)", "date", false],
            ].map(([key, label, type, required]) => (
              <Input
                key={key}
                name={key}
                label={label}
                type={type}
                required={required}
                form={form}
                set={set}
              />
            ))}
            <SupplierField db={db} form={form} set={set} />
          </div>
          <Field label="Ürün görseli (isteğe bağlı)">
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                if (file.size > 500000) {
                  e.target.setCustomValidity("Görsel en fazla 500 KB olmalı.");
                  e.target.reportValidity();
                  return;
                }
                e.target.setCustomValidity("");
                const reader = new FileReader();
                reader.onload = () => set("image", reader.result);
                reader.readAsDataURL(file);
              }}
            />
          </Field>
          {form.image && (
            <div className="stock-image-preview">
              <img src={form.image} alt={form.name || "Ürün görseli"} />
              <IconButton
                type="button"
                icon={Trash2}
                label="Görseli kaldır"
                onClick={() => set("image", "")}
              />
            </div>
          )}
          <CheckField name="active" label="Ürün aktif" form={form} set={set} />
        </>
      )}
    </EditDialog>
  );
}

function StockDialog({ db, product, run, onClose }) {
  return (
    <EditDialog
      title={`${product.name} / Stok işlemi`}
      initial={{
        id: product.id,
        kind: "receipt",
        quantity: 1,
        count: product.stock,
        cost: product.cost,
        supplierId: product.supplierId || "",
        receivedCode: "",
        reason: "",
      }}
      onClose={onClose}
      onSave={(form) => run("stock", form)}
    >
      {(form, set) => (
        <>
          <p>
            Mevcut stok: {product.stock} {product.unit || "adet"}
          </p>
          <Field label="Stok işlem türü">
            <select
              value={form.kind}
              onChange={(e) => {
                set("kind", e.target.value);
                set("quantity", e.target.value === "loss" ? -1 : 1);
              }}
            >
              <option value="receipt">Tedarikçiden mal kabul</option>
              <option value="loss">Hasar / kayıp</option>
              <option value="adjustment">Manuel düzeltme</option>
              <option value="count">Fiziksel sayım</option>
            </select>
          </Field>
          <Input
            name={form.kind === "count" ? "count" : "quantity"}
            label={
              form.kind === "count" ? "Sayılan miktar" : "Stok değişimi (+ / -)"
            }
            type="number"
            min={
              form.kind === "loss" || form.kind === "adjustment" ? -100000 : 0
            }
            max={form.kind === "loss" ? -1 : 100000}
            required
            form={form}
            set={set}
          />
          {form.kind === "receipt" && (
            <>
              <SupplierField db={db} form={form} set={set} required />
              <Input
                name="receivedCode"
                label="Mal kabul / teslimat referansı"
                required
                form={form}
                set={set}
              />
              <Input
                name="cost"
                label="Birim alış fiyatı (TL)"
                type="number"
                required
                form={form}
                set={set}
              />
            </>
          )}
          <Input
            name="reason"
            label="İşlem gerekçesi"
            type="textarea"
            required
            form={form}
            set={set}
          />
        </>
      )}
    </EditDialog>
  );
}

function ReturnDialog({ sale, run, onClose }) {
  return (
    <EditDialog
      title={`${sale.productName} / Ürün iadesi`}
      initial={{ id: sale.id, quantity: 1, restock: true, reason: "" }}
      onClose={onClose}
      onSave={(form) => run("returnSale", form)}
    >
      {(form, set) => {
        let value = 0;
        try {
          value = returnPreview(sale, form.quantity);
        } catch {}
        return (
          <>
            <p>
              Satılan: {sale.quantity} · Daha önce iade:{" "}
              {sale.returnedQuantity || 0}
            </p>
            <Input
              name="quantity"
              label="İade miktarı"
              type="number"
              min={1}
              max={sale.quantity - (sale.returnedQuantity || 0)}
              required
              form={form}
              set={set}
            />
            <CheckField
              name="restock"
              label="Ürün satılabilir durumda, stoğa geri al"
              form={form}
              set={set}
            />
            <Input
              name="reason"
              label="İade gerekçesi"
              type="textarea"
              required
              form={form}
              set={set}
            />
            <strong>İade tutarı: {money(value / 100)}</strong>
          </>
        );
      }}
    </EditDialog>
  );
}

function SaleReceipt({ db, id, onClose }) {
  const sale = saleGroups(db.sales).find((s) => s.id === id);
  if (!sale)
    return (
      <Dialog title="Satış belgesi" onClose={onClose}>
        <Empty>Satış kaydı yükleniyor.</Empty>
      </Dialog>
    );
  return (
    <Dialog title="Ürün satış belgesi" onClose={onClose}>
      <div className="stock-receipt">
        <h2>FitGate</h2>
        <p>{sale.number}</p>
        <p>
          {displayDate(sale.at)} {displayTime(sale.at)}
        </p>
        <p>
          Müşteri:{" "}
          {db.members.find((m) => m.id === sale.memberId)?.name || "Misafir"} ·
          Personel: {sale.actor}
        </p>
        <Table headers={["Ürün", "Miktar", "Birim fiyat", "İndirim", "Tutar"]}>
          {sale.lines.map((l) => (
            <tr key={l.id}>
              <td>{l.productName}</td>
              <td>
                {l.quantity} {l.unit}
              </td>
              <td>{money(l.unitPriceCents / 100)}</td>
              <td>{money(l.discountCents / 100)}</td>
              <td>{money(l.totalCents / 100)}</td>
            </tr>
          ))}
        </Table>
        <p>
          Toplam: <strong>{money(sale.totalCents / 100)}</strong> · İade:{" "}
          {money(sale.refundCents / 100)}
        </p>
        <p>
          Ödeme:{" "}
          {sale.method === "pos"
            ? "Harici POS tahsilat kaydı"
            : methods.find((m) => m.value === sale.method)?.label}
        </p>
        <small>
          Bu belge resmi mali fatura veya e-Arşiv faturası değildir.
        </small>
      </div>
      <div className="dialog-actions">
        <Button type="button" icon={Printer} onClick={() => window.print()}>
          Yazdır
        </Button>
      </div>
    </Dialog>
  );
}
