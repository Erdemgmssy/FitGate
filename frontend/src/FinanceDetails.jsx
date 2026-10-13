import React, { useRef, useState } from "react";
import { Plus, Save, Printer, Trash2 } from "lucide-react";
import {
  Dialog,
  Field,
  Button,
  IconButton,
  Table,
  Empty,
  Badge,
  methods,
} from "./ui";
import { money, displayDate, displayTime, dateKey } from "./attendance.mjs";
import { inputTime, isoTime } from "./personnel-rules.mjs";
import { invoiceDebt, installmentRows, paidCents, addMonths } from "./gym.mjs";

export function PaymentDialog({ db, run, dialog, onClose, selected }) {
  const open = db.invoices.filter((row) => invoiceDebt(db, row) > 0);
  const members = db.members.filter((row) =>
    open.some((sale) => sale.memberId === row.id),
  );
  const [memberId, setMemberId] = useState(
    members.some((row) => row.id === selected?.memberId)
      ? selected.memberId
      : members[0]?.id || "",
  );
  const initialSale =
    open.find((row) => row.id === selected?.id) ||
    open.find((row) => row.memberId === memberId);
  const [invoiceId, setInvoiceId] = useState(initialSale?.id || "");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const locked = useRef(false);
  const payment = dialog.payment,
    type = dialog.type;
  const refund = db.refunds
    .filter((row) => row.paymentId === payment?.id)
    .reduce((sum, row) => sum + row.amountCents, 0);
  async function submit(event) {
    event.preventDefault();
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget),
        payload = Object.fromEntries(form);
      if (type === "collect") payload.invoiceId = invoiceId;
      else payload.paymentId = payment.id;
      if (payload.at) payload.at = isoTime(payload.at);
      const result = await run(type, payload);
      if (result?.ok) onClose();
      else setError(result?.message || "İşlem tamamlanamadı.");
    } catch (err) {
      setError(err.message);
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return (
    <Dialog
      title={
        {
          collect: "Tahsilat kaydı",
          refund: "Gerekçeli ödeme iadesi",
          correctPayment: "Ödeme bilgilerini düzelt",
        }[type]
      }
      onClose={() => !busy && onClose()}
    >
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="finance-fields">
          <div className="form-grid">
            {type === "collect" && (
              <>
                <Field label="Üye">
                  <select
                    value={memberId}
                    onChange={(e) => {
                      setMemberId(e.target.value);
                      setInvoiceId(
                        open.find((row) => row.memberId === e.target.value)
                          ?.id || "",
                      );
                    }}
                  >
                    {members.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.name} / {row.number}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Ödemenin uygulanacağı satış">
                  <select
                    required
                    value={invoiceId}
                    onChange={(e) => setInvoiceId(e.target.value)}
                  >
                    {open
                      .filter((row) => row.memberId === memberId)
                      .map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.number} /{" "}
                          {db.subscriptions.find(
                            (s) => s.id === row.subscriptionId,
                          )?.planName || row.description}{" "}
                          / {money(invoiceDebt(db, row) / 100)}
                        </option>
                      ))}
                  </select>
                </Field>
              </>
            )}
            {type !== "correctPayment" && (
              <Field
                label={
                  type === "refund" ? "İade tutarı (TL)" : "Ödenen tutar (TL)"
                }
              >
                <input
                  required
                  name="amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  max={
                    (type === "refund"
                      ? payment.amountCents - refund
                      : invoiceDebt(
                          db,
                          open.find((row) => row.id === invoiceId) || {
                            totalCents: 0,
                          },
                        )) / 100
                  }
                  defaultValue={
                    type === "refund"
                      ? ((payment.amountCents - refund) / 100).toFixed(2)
                      : ""
                  }
                />
              </Field>
            )}
            {type !== "refund" && (
              <>
                <Field label="Ödeme yöntemi">
                  <select
                    name="method"
                    defaultValue={payment?.method || "cash"}
                  >
                    {methods.map((row) => (
                      <option key={row.value} value={row.value}>
                        {row.value === "pos"
                          ? "POS (harici tahsilat)"
                          : row.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Ödeme tarihi (Türkiye saati)">
                  <input
                    required
                    name="at"
                    type="datetime-local"
                    step="0.001"
                    defaultValue={inputTime(
                      payment?.at || new Date().toISOString(),
                    )}
                  />
                </Field>
                <Field label="Açıklama / belge referansı">
                  <textarea
                    name="note"
                    maxLength="600"
                    defaultValue={payment?.note || ""}
                  />
                </Field>
              </>
            )}
            {type !== "collect" && (
              <Field label="İşlem gerekçesi">
                <textarea
                  required
                  minLength="3"
                  maxLength="1500"
                  name="reason"
                />
              </Field>
            )}
          </div>
        </fieldset>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <Button icon={Save} tone="primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function InstallmentsDialog({ db, invoice, run, onClose }) {
  const current = installmentRows(db, invoice);
  const [rows, setRows] = useState(
    current.map((row) => ({
      due: row.due,
      amount: (row.amountCents / 100).toFixed(2),
    })),
  );
  const [count, setCount] = useState(current.length || 1),
    [first, setFirst] = useState(dateKey()),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const locked = useRef(false);
  const update = (index, key, value) =>
    setRows((previous) =>
      previous.map((row, i) => (i === index ? { ...row, [key]: value } : row)),
    );
  return (
    <Dialog
      title={`${invoice.number} / Taksit planını düzenle`}
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (locked.current) return;
          locked.current = true;
          setBusy(true);
          setError("");
          try {
            const reason = new FormData(e.currentTarget).get("reason");
            const result = await run("saveInstallments", {
              invoiceId: invoice.id,
              rows,
              reason,
            });
            if (result?.ok) onClose();
            else setError(result?.message || "Plan kaydedilemedi.");
          } finally {
            locked.current = false;
            setBusy(false);
          }
        }}
      >
        <fieldset disabled={busy} className="finance-fields">
          <p>
            {invoice.number} · Satış: {money(invoice.totalCents / 100)} ·
            Tahsilat: {money(paidCents(db, invoice.id) / 100)}
          </p>
          <div className="filter-bar">
            <Field label="Taksit sayısı">
              <input
                type="number"
                min="1"
                max="36"
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </Field>
            <Field label="İlk vade">
              <input
                type="date"
                required
                value={first}
                onChange={(e) => setFirst(e.target.value)}
              />
            </Field>
            <Button
              type="button"
              icon={Plus}
              onClick={() => {
                if (
                  !Number.isInteger(count) ||
                  count < 1 ||
                  count > 36 ||
                  !first
                )
                  return;
                const whole = Math.floor(invoice.totalCents / count),
                  rest = invoice.totalCents % count;
                setRows(
                  Array.from({ length: count }, (_, i) => ({
                    due: addMonths(first, i),
                    amount: ((whole + (i < rest ? 1 : 0)) / 100).toFixed(2),
                  })),
                );
              }}
            >
              Plan oluştur
            </Button>
          </div>
          <Table headers={["Vade", "Tutar (TL)", "İşlem"]}>
            {rows.map((row, index) => (
              <tr key={index}>
                <td>
                  <input
                    aria-label={`Vade ${index + 1}`}
                    required
                    type="date"
                    value={row.due}
                    onChange={(e) => update(index, "due", e.target.value)}
                  />
                </td>
                <td>
                  <input
                    aria-label={`Tutar ${index + 1}`}
                    required
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={row.amount}
                    onChange={(e) => update(index, "amount", e.target.value)}
                  />
                </td>
                <td>
                  <IconButton
                    type="button"
                    icon={Trash2}
                    label={`Taksit ${index + 1} sil`}
                    onClick={() =>
                      setRows((previous) =>
                        previous.filter((_, i) => i !== index),
                      )
                    }
                  />
                </td>
              </tr>
            ))}
          </Table>
          <Field label="Plan değişikliği gerekçesi">
            <textarea name="reason" required minLength="3" maxLength="1500" />
          </Field>
        </fieldset>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <Button icon={Save} tone="primary" disabled={busy || !rows.length}>
            Kaydet
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function ReceiptDialog({ db, payment, onClose }) {
  const invoice = db.invoices.find((row) => row.id === payment.invoiceId),
    member = db.members.find((row) => row.id === invoice?.memberId);
  const refunds = db.refunds.filter((row) => row.paymentId === payment.id);
  return (
    <Dialog title="Tahsilat belgesi" onClose={onClose}>
      <article className="receipt-document">
        <h2>FitGate · Tahsilat belgesi</h2>
        <p>{db.branches?.[0]?.name}</p>
        <dl className="receipt-details">
          {[
            ["İşlem no", payment.number],
            ["Satış no", invoice?.number],
            ["Üye", `${member?.name || "-"} / ${member?.number || "-"}`],
            ["Tarih", `${displayDate(payment.at)} ${displayTime(payment.at)}`],
            [
              "Yöntem",
              methods.find((row) => row.value === payment.method)?.label,
            ],
            ["Tutar", money(payment.amountCents / 100)],
            ["Personel", payment.actor],
            ["Açıklama", payment.note || "-"],
          ].map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        {refunds.length > 0 && (
          <p>
            İade edilen:{" "}
            {money(
              refunds.reduce((sum, row) => sum + row.amountCents, 0) / 100,
            )}
          </p>
        )}
        <p>Bu belge resmi mali fatura veya e-Arşiv faturası değildir.</p>
        {payment.method === "pos" && (
          <p>Harici POS ile alınan ödemenin kayıt belgesidir.</p>
        )}
      </article>
      <div className="modal-actions">
        <Button icon={Printer} onClick={() => window.print()}>
          Yazdır
        </Button>
      </div>
    </Dialog>
  );
}

export function MemberPayments({ db, member }) {
  const invoices = db.invoices.filter((row) => row.memberId === member.id),
    ids = new Set(invoices.map((row) => row.id));
  const payments = db.payments.filter((row) => ids.has(row.invoiceId)),
    [receipt, setReceipt] = useState(null);
  return (
    <>
      <Table headers={["Satış no / Paket", "Satış tutarı", "Tahsilat", "Borç"]}>
        {invoices.map((row) => (
          <tr key={row.id}>
            <td>
              {row.number}
              <small>
                {db.subscriptions.find((s) => s.id === row.subscriptionId)
                  ?.planName || row.description}
              </small>
            </td>
            <td>{money(row.totalCents / 100)}</td>
            <td>{money(paidCents(db, row.id) / 100)}</td>
            <td>{money(invoiceDebt(db, row) / 100)}</td>
          </tr>
        ))}
      </Table>
      {!invoices.length && <Empty />}
      <h3 className="section-title">Tahsilat ve iade geçmişi</h3>
      <Table
        headers={[
          "İşlem / Satış",
          "Tarih",
          "Yöntem",
          "Tutar",
          "Personel",
          "Belge",
        ]}
      >
        {payments
          .slice()
          .reverse()
          .map((row) => (
            <React.Fragment key={row.id}>
              <tr>
                <td>
                  {row.number}
                  <small>
                    {invoices.find((i) => i.id === row.invoiceId)?.number}
                  </small>
                </td>
                <td>
                  {displayDate(row.at)} {displayTime(row.at)}
                </td>
                <td>
                  <Badge status={row.method} />
                </td>
                <td>{money(row.amountCents / 100)}</td>
                <td>
                  {row.actor}
                  <small>{row.note}</small>
                </td>
                <td>
                  <IconButton
                    icon={Printer}
                    label="Tahsilat belgesini aç"
                    onClick={() => setReceipt(row)}
                  />
                </td>
              </tr>
              {db.refunds
                .filter((r) => r.paymentId === row.id)
                .map((r) => (
                  <tr key={r.id}>
                    <td>İade</td>
                    <td>
                      {displayDate(r.at)} {displayTime(r.at)}
                    </td>
                    <td>
                      <Badge status={row.method} />
                    </td>
                    <td>-{money(r.amountCents / 100)}</td>
                    <td>
                      {r.actor}
                      <small>{r.reason}</small>
                    </td>
                    <td />
                  </tr>
                ))}
            </React.Fragment>
          ))}
      </Table>
      <h3 className="section-title">Taksitler</h3>
      <Table headers={["Satış", "Vade", "Taksit", "Kalan", "Durum"]}>
        {invoices.flatMap((invoice) =>
          installmentRows(db, invoice).map((row) => (
            <tr key={row.id}>
              <td>{invoice.number}</td>
              <td>{displayDate(row.due)}</td>
              <td>{money(row.amountCents / 100)}</td>
              <td>{money(row.remaining / 100)}</td>
              <td>
                {row.remaining === 0
                  ? "Kapandı"
                  : row.due < dateKey()
                    ? "Gecikmiş"
                    : "Bekliyor"}
              </td>
            </tr>
          )),
        )}
      </Table>
      {db.installments.some(
        (row) => ids.has(row.invoiceId) && row.archived,
      ) && (
        <details>
          <summary>Önceki taksit planları</summary>
          <Table headers={["Satış", "Vade", "Tutar", "Durum"]}>
            {db.installments
              .filter((row) => ids.has(row.invoiceId) && row.archived)
              .map((row) => (
                <tr key={row.id}>
                  <td>
                    {
                      invoices.find((invoice) => invoice.id === row.invoiceId)
                        ?.number
                    }
                  </td>
                  <td>{displayDate(row.due)}</td>
                  <td>{money(row.amountCents / 100)}</td>
                  <td>Arşiv</td>
                </tr>
              ))}
          </Table>
        </details>
      )}
      {receipt && (
        <ReceiptDialog
          db={db}
          payment={receipt}
          onClose={() => setReceipt(null)}
        />
      )}
    </>
  );
}
