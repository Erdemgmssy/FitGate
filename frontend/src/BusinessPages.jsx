import React, { useEffect, useState } from "react";
import { request } from "./api.mjs";
import { financialRecords } from "./finance-rules.mjs";
import {
  PaymentDialog,
  InstallmentsDialog,
  ReceiptDialog,
} from "./FinanceDetails";
import {
  Plus,
  Wallet,
  CreditCard,
  Undo2,
  CalendarDays,
  Package,
  Bell,
  Check,
  Download,
  Pencil,
  Printer,
  Ban,
} from "lucide-react";
import {
  invoiceDebt,
  memberDebt,
  installmentRows,
  paidCents,
  automaticNotices,
  cashBalance,
} from "./gym.mjs";
import { dateKey, displayDate, displayTime, money } from "./attendance.mjs";
import {
  Badge,
  Button,
  Table,
  Empty,
  Metric,
  ActionForm,
  methods,
  ExportButtons,
  exportCsv,
  Field,
  IconButton,
} from "./ui";

export function FinancePage({ db, run, isAdmin, selectedMemberId, selectedInvoiceId, userId }) {
  if(!isAdmin&&db.memberDirectory?.length)db={...db,members:db.members.length?db.members:db.memberDirectory};
  const [memberId, setMemberId] = useState(selectedMemberId || "all"),
    [dialog, setDialog] = useState(null),
    [selectedInvoice, setSelectedInvoice] = useState(null);
  const [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [actor, setActor] = useState("all"),
    [method, setMethod] = useState("all"),
    [onlyDebt, setOnlyDebt] = useState(false),
    [exportError, setExportError] = useState(""),
    [exporting, setExporting] = useState(false);
  useEffect(() => setMemberId(selectedMemberId || "all"), [selectedMemberId]);
  useEffect(()=>{if(selectedInvoiceId)setSelectedInvoice(selectedInvoiceId);},[selectedInvoiceId]);
  const invoices = db.invoices.filter(
    (item) =>
      (memberId === "all" || item.memberId === memberId) &&
      (!onlyDebt || invoiceDebt(db, item) > 0),
  );
  const filters = { memberId, from, to, actor, method, onlyDebt };
  const payments = financialRecords(db, filters),
    refunds = financialRecords(db, filters, "refunds");
  const today = dateKey();
  const refunded = (payment) =>
    db.refunds
      .filter((item) => item.paymentId === payment.id)
      .reduce((sum, item) => sum + item.amountCents, 0);
  const selected =
    invoices.find((item) => item.id === selectedInvoice) || invoices[0];
  const memberName = (id) =>
    db.members.find((item) => item.id === id)?.name || "-";
  const cashSession = db.cashSessions?.find((item) => !item.closedAt);
  const metrics = db.finance;
  return (
    <section className="page-grid">
      {isAdmin && <CashPanel db={db} run={run} session={cashSession} />}
      <div className="filter-bar">
        <Field label="Üye">
          <select
            value={memberId}
            onChange={(event) => setMemberId(event.target.value)}
          >
            <option value="all">Tüm üyeler</option>
            {db.members.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Başlangıç">
          <input
            type="date"
            value={from}
            max={to || undefined}
            onChange={(e) => setFrom(e.target.value)}
          />
        </Field>
        <Field label="Bitiş">
          <input
            type="date"
            value={to}
            min={from || undefined}
            onChange={(e) => setTo(e.target.value)}
          />
        </Field>
        {isAdmin&&<Field label="Personel">
          <select value={actor} onChange={(e) => setActor(e.target.value)}>
            <option value="all">Tüm personeller</option>
            {Array.from(
              new Map(
                [...db.payments, ...db.refunds].map((row) => [
                  String(row.actorId),
                  row.actor,
                ]),
              ).entries(),
            ).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </Field>}
        <Field label="Yöntem">
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="all">Tüm yöntemler</option>
            {methods.map((row) => (
              <option key={row.value} value={row.value}>
                {row.value === "pos" ? "POS (harici)" : row.label}
              </option>
            ))}
          </select>
        </Field>
        <label className="check-field">
          <input
            type="checkbox"
            checked={onlyDebt}
            onChange={(e) => setOnlyDebt(e.target.checked)}
          />
          Yalnızca açık borçlar
        </label>
        <Button
          tone="primary"
          icon={Plus}
          disabled={!db.invoices.some((item) => invoiceDebt(db, item) > 0)}
          onClick={() => setDialog({ type: "collect" })}
        >
          Ödeme al
        </Button>
        {isAdmin && (
          <ExportButtons
            onExport={() =>
              exportCsv(
                "tahsilatlar",
                [
                  "No",
                  "Satış",
                  "Üye",
                  "Tarih",
                  "Yöntem",
                  "Tutar",
                  "İade",
                  "Personel",
                  "Açıklama",
                ],
                payments.map((item) => [
                  item.number,
                  db.invoices.find((row) => row.id === item.invoiceId)?.number,
                  memberName(
                    db.invoices.find((invoice) => invoice.id === item.invoiceId)
                      ?.memberId,
                  ),
                  item.at,
                  item.method,
                  item.amountCents / 100,
                  refunded(item) / 100,
                  item.actor,
                  item.note,
                ]),
              )
            }
          />
        )}
        {isAdmin && (
          <IconButton
            icon={Download}
            label="Excel indir"
            disabled={exporting}
            onClick={async () => {
              setExportError("");
              setExporting(true);
              try {
                const filters = new URLSearchParams();
                if (from) filters.set("from", from);
                if (to) filters.set("to", to);
                if (memberId !== "all") filters.set("memberId", memberId);
                if (actor !== "all") filters.set("actorId", actor);
                if (method !== "all") filters.set("method", method);
                if (onlyDebt) filters.set("onlyDebt", "true");
                const data = await request(`finance/export/?${filters}`),
                  bytes = Uint8Array.from(atob(data.base64), (c) =>
                    c.charCodeAt(0),
                  );
                const url = URL.createObjectURL(
                  new Blob([bytes], {
                    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  }),
                );
                const link = document.createElement("a");
                link.href = url;
                link.download = data.filename;
                link.click();
                URL.revokeObjectURL(url);
              } catch (error) {
                setExportError(error.message);
              } finally {
                setExporting(false);
              }
            }}
          />
        )}
      </div>
      {exportError && (
        <p role="alert" className="form-error">
          {exportError}
        </p>
      )}
      {isAdmin && (
        <div className="stat-row finance-metrics">
          <Metric
            icon={Wallet}
            label="Bugünkü tahsilat"
            value={metrics ? money(metrics.todayCents / 100) : "-"}
          />
          <Metric
            icon={CreditCard}
            label="Bu ayki tahsilat"
            value={metrics ? money(metrics.monthCents / 100) : "-"}
          />
          <Metric
            icon={Wallet}
            label="Toplam kalan alacak"
            value={metrics ? money(metrics.remainingCents / 100) : "-"}
            tone="amber"
          />
          <Metric
            icon={CalendarDays}
            label="Gecikmiş alacaklar"
            value={metrics ? money(metrics.overdueCents / 100) : "-"}
            tone="coral"
          />
          <Metric
            icon={CalendarDays}
            label="Bekleyen taksitler"
            value={metrics?.pendingInstallments ?? "-"}
          />
          <Metric
            icon={Undo2}
            label="İade edilen tutarlar"
            value={metrics ? money(metrics.refundedCents / 100) : "-"}
          />
        </div>
      )}
      <div className="section-header">
        <h2>Üyelik satışları ve borçlar</h2>
        <span>{invoices.length} satış</span>
      </div>
      {isAdmin && metrics && (
        <div className="stat-row three">
          <Metric
            icon={Wallet}
            label="Bu ay net üyelik tahsilatı"
            value={money((metrics.membershipMonthNetCents || 0) / 100)}
          />
          <Metric
            icon={Package}
            label="Bu ay net ürün satışı"
            value={money((metrics.productMonthNetCents || 0) / 100)}
          />
          <Metric
            icon={Package}
            label="Bugünkü net ürün satışı"
            value={money((metrics.productTodayNetCents || 0) / 100)}
          />
        </div>
      )}
      <Table
        headers={[
          "Satış no",
          "Üye",
          "Satış / İndirim",
          "Net tahsilat",
          "Kalan borç",
          "Durum",
        ]}
      >
        {invoices.map((invoice) => (
          <tr
            key={invoice.id}
            className={selected?.id === invoice.id ? "selected-table-row" : ""}
          >
            <td>
              <button
                className="text-button"
                onClick={() => setSelectedInvoice(invoice.id)}
              >
                {invoice.number}
              </button>
              <small>{displayDate(invoice.createdAt)}</small>
              <small>
                {db.subscriptions.find(
                  (row) => row.id === invoice.subscriptionId,
                )?.planName || invoice.description}
              </small>
            </td>
            <td>{memberName(invoice.memberId)}</td>
            <td>
              {money(invoice.totalCents / 100)}
              <small>İndirim: {money(invoice.discountCents / 100)}</small>
            </td>
            <td>{money(paidCents(db, invoice.id) / 100)}</td>
            <td>{money(invoiceDebt(db, invoice) / 100)}</td>
            <td>
              <Badge
                status={
                  invoice.status === "cancelled"
                    ? "cancelled"
                    : invoiceDebt(db, invoice) > 0
                      ? "pending"
                      : "active"
                }
              >
                {invoice.status === "cancelled"
                  ? "İptal"
                  : invoiceDebt(db, invoice) > 0
                    ? "Borçlu"
                    : "Ödendi"}
              </Badge>
            </td>
          </tr>
        ))}
      </Table>
      {!invoices.length && <Empty />}
      {selected && (
        <>
          <div className="section-header">
            <h2>{selected.number} / Taksit planı</h2>
            {isAdmin && selected.status !== "cancelled" && (
              <div className="button-group">
                <Button
                  icon={Pencil}
                  onClick={() => setDialog({ type: "plan", invoice: selected })}
                >
                  Taksit düzenle
                </Button>
                <IconButton
                  icon={Ban}
                  label="Satışı iptal et"
                  onClick={() =>
                    setDialog({ type: "cancelInvoice", invoice: selected })
                  }
                />
              </div>
            )}
          </div>
          <Table headers={["Vade", "Taksit", "Kalan", "Durum"]}>
            {installmentRows(db, selected).map((item) => (
              <tr key={item.id}>
                <td>{displayDate(item.due)}</td>
                <td>{money(item.amountCents / 100)}</td>
                <td>{money(item.remaining / 100)}</td>
                <td>
                  <Badge
                    status={
                      item.remaining === 0
                        ? "active"
                        : item.due < today
                          ? "rejected"
                          : "pending"
                    }
                  >
                    {item.remaining === 0
                      ? "Kapandı"
                      : item.due < today
                        ? "Gecikmiş"
                        : "Bekliyor"}
                  </Badge>
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
      <div className="section-header">
        <h2>Tahsilat geçmişi</h2>
      </div>
      <Table
        headers={[
          "Ödeme no",
          "Üye",
          "Tarih",
          "Yöntem",
          "Tutar / İade",
          "Personel",
          "İşlem",
        ]}
      >
        {payments
          .slice()
          .reverse()
          .map((payment) => (
            <tr key={payment.id}>
              <td>{payment.number}</td>
              <td>
                {memberName(
                  db.invoices.find((item) => item.id === payment.invoiceId)
                    ?.memberId,
                )}
              </td>
              <td>
                {displayDate(payment.at)}
                <small>{displayTime(payment.at)}</small>
              </td>
              <td>
                <Badge status={payment.method} />
              </td>
              <td>
                {money(payment.amountCents / 100)}
                <small>İade: {money(refunded(payment) / 100)}</small>
              </td>
              <td>{payment.actor}</td>
              <td>
                <IconButton
                  icon={Printer}
                  label="Tahsilat belgesini aç"
                  onClick={() => setDialog({ type: "receipt", payment })}
                />
                {isAdmin && (
                  <IconButton
                    icon={Pencil}
                    label="Ödeme bilgilerini düzelt"
                    onClick={() =>
                      setDialog({ type: "correctPayment", payment })
                    }
                  />
                )}
                {isAdmin && payment.amountCents > refunded(payment) && (
                  <Button
                    tone="danger"
                    icon={Undo2}
                    onClick={() => setDialog({ type: "refund", payment })}
                  >
                    İade
                  </Button>
                )}
              </td>
            </tr>
          ))}
      </Table>
      {!payments.length && <Empty />}
      <h3 className="section-title">İade geçmişi</h3>
      <Table headers={["Ödeme no", "Tarih", "Tutar", "Personel", "Gerekçe"]}>
        {refunds
          .slice()
          .reverse()
          .map((row) => (
            <tr key={row.id}>
              <td>{db.payments.find((p) => p.id === row.paymentId)?.number}</td>
              <td>
                {displayDate(row.at)} {displayTime(row.at)}
              </td>
              <td>{money(row.amountCents / 100)}</td>
              <td>{row.actor}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
      </Table>
      {selected &&
        db.installments.some(
          (row) => row.invoiceId === selected.id && row.archived,
        ) && (
          <details>
            <summary>Önceki taksit planları</summary>
            <Table headers={["Vade", "Tutar", "Durum"]}>
              {db.installments
                .filter((row) => row.invoiceId === selected.id && row.archived)
                .map((row) => (
                  <tr key={row.id}>
                    <td>{displayDate(row.due)}</td>
                    <td>{money(row.amountCents / 100)}</td>
                    <td>Arşiv</td>
                  </tr>
                ))}
            </Table>
          </details>
        )}
      {dialog &&
        ["collect", "refund", "correctPayment"].includes(dialog.type) && (
          <PaymentDialog
            key={dialog.type + dialog.payment?.id}
            db={db}
            run={run}
            dialog={dialog}
            selected={selected}
            onClose={() => setDialog(null)}
          />
        )}
      {dialog?.type === "plan" && (
        <InstallmentsDialog
          db={db}
          invoice={dialog.invoice}
          run={run}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === "receipt" && (
        <ReceiptDialog
          db={db}
          payment={dialog.payment}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === "cancelInvoice" && (
        <ActionForm
          title="Satış iptalini onayla"
          fields={[
            { name: "reason", label: "İptal gerekçesi", type: "textarea" },
            {
              name: "confirmed",
              label: "Satış iptalini onaylıyorum",
              type: "checkbox",
            },
          ]}
          onClose={() => setDialog(null)}
          onSave={(values) =>
            run("cancelInvoice", { invoiceId: dialog.invoice.id, ...values })
          }
        />
      )}
    </section>
  );
}

export function CashPanel({ db, run, session }) {
  const [dialog, setDialog] = useState(null);
  return (
    <section>
      <div className="overview-toolbar">
        <div>
          <h2>Nakit kasa</h2>
          <small>
            {session
              ? `Beklenen bakiye: ${money(cashBalance(db, session) / 100)}`
              : "Kapalı"}
          </small>
        </div>
        <Button onClick={() => setDialog(session ? "closeCash" : "openCash")}>
          {session ? "Kasa kapat" : "Kasa aç"}
        </Button>
      </div>
      {db.cashSessions?.some((item) => item.closedAt) && (
        <Table headers={["Açılış / Kapanış", "Beklenen", "Sayılan", "Fark"]}>
          {db.cashSessions
            .filter((item) => item.closedAt)
            .map((item) => (
              <tr key={item.id}>
                <td>
                  {displayDate(item.openedAt)} {displayTime(item.openedAt)}
                  <small>
                    {displayDate(item.closedAt)} {displayTime(item.closedAt)}
                  </small>
                </td>
                <td>{money(item.expectedCents / 100)}</td>
                <td>{money(item.countedCents / 100)}</td>
                <td>{money((item.countedCents - item.expectedCents) / 100)}</td>
              </tr>
            ))}
        </Table>
      )}
      {dialog && (
        <ActionForm
          title={dialog === "openCash" ? "Kasayı aç" : "Kasa sayımı ve kapanış"}
          fields={[
            {
              name: "amount",
              label:
                dialog === "openCash"
                  ? "Açılış tutarı (TL)"
                  : "Sayılan tutar (TL)",
              type: "number",
              min: 0,
              step: 0.01,
            },
            { name: "note", label: "Not", required: false },
          ]}
          onClose={() => setDialog(null)}
          onSave={(values) => run(dialog, values)}
        />
      )}
    </section>
  );
}

export { NotificationsPage } from './NotificationsPage';
