import React, { useState } from "react";
import { saleAvailable, salePrice } from "./plan-rules.mjs";
import { Snowflake, Play, Ban, RefreshCw, Save } from "lucide-react";
import {
  Table,
  Field,
  Badge,
  Button,
  IconButton,
  Dialog,
  Empty,
  methods,
} from "./ui";
import { dateKey, displayDate, money } from "./attendance.mjs";
import { addDays, dayDiff, subscriptionStatus } from "./gym.mjs";
import {
  subscriptionDays,
  sessionCounts,
  subscriptionGroup,
  orderSubscriptions,
  renewalStart,
  membershipEnd,
} from "./subscription-rules.mjs";

const groups = [
  ["all", "Tüm üyelikler"],
  ["active", "Aktif"],
  ["expired", "Süresi dolmuş"],
  ["frozen", "Dondurulmuş"],
  ["cancelled", "İptal edilmiş"],
  ["pending", "Gelecekte başlayacak"],
];

export function MembershipsTab({ subscriptions, freezes, isAdmin, onAction }) {
  const [group, setGroup] = useState("all");
  const today = dateKey();
  const rows = orderSubscriptions(subscriptions).filter(
    (sub) => group === "all" || subscriptionGroup(sub) === group,
  );
  const history = freezes
    .filter((row) => subscriptions.some((sub) => sub.id === row.subscriptionId))
    .slice()
    .sort((a, b) => b.start.localeCompare(a.start) || b.id.localeCompare(a.id));
  return (
    <section className="membership-tab">
      <div className="history-toolbar">
        <Field label="Üyelik durumu">
          <select
            value={group}
            onChange={(event) => setGroup(event.target.value)}
          >
            {groups.map(([id, label]) => (
              <option value={id} key={id}>
                {label} (
                {id === "all"
                  ? subscriptions.length
                  : subscriptions.filter((sub) => subscriptionGroup(sub) === id)
                      .length}
                )
              </option>
            ))}
          </select>
        </Field>
        <Button icon={RefreshCw} onClick={() => onAction("renew")}>
          Üyelik yenile
        </Button>
      </div>
      <p className="member-note">
        Geçiş önceliği: gün, saat ve seans koşulları uygun paketlerden bitişi en
        yakın olan; eşitlikte başlangıç, kayıt zamanı ve kayıt kimliği. Dondurma
        aralığında giriş kapalı, açık ziyaretin çıkışı serbest.
      </p>
      <Table
        headers={[
          "Paket",
          "Başlangıç / Bitiş",
          "Kalan gün",
          "Durum",
          "Satış fiyatı",
          "Toplam seans",
          "Kullanılan",
          "Kalan",
          "İşlem",
        ]}
      >
        {rows.map((sub) => {
          const sessions = sessionCounts(sub);
          const state = subscriptionStatus(sub);
          const pendingFreeze = (sub.freezePeriods || []).some(
            (period) =>
              !period.end || (period.end > today && period.end > period.start),
          );
          return (
            <tr key={sub.id}>
              <td>{sub.planName}</td>
              <td>
                {displayDate(sub.start)}
                <small>
                  {sub.end ? displayDate(sub.end) : "Bitiş tarihi yok"}
                </small>
              </td>
              <td>{subscriptionDays(sub) ?? "Süresiz"}</td>
              <td>
                <Badge status={state} />
              </td>
              <td>{money((sub.salePriceCents ?? sub.priceCents) / 100)}</td>
              {sub.remaining == null ? (
                <td colSpan={3}>Sınırsız</td>
              ) : (
                <>
                  <td>{sessions.total ?? "-"}</td>
                  <td>{sessions.used ?? "-"}</td>
                  <td>{sessions.remaining}</td>
                </>
              )}
              <td>
                {isAdmin && state !== "cancelled" && (
                  <div className="button-group">
                    {pendingFreeze || state === "frozen" ? (
                      <IconButton
                        icon={Play}
                        label={`Dondurmayı bitir: ${sub.planName}`}
                        onClick={() => onAction("resume", sub)}
                      />
                    ) : (
                      ["active", "ending", "pending"].includes(state) && (
                        <IconButton
                          icon={Snowflake}
                          label={`Dondur: ${sub.planName}`}
                          disabled={sub.rules.freezeDays <= sub.frozenDays}
                          onClick={() => onAction("freeze", sub)}
                        />
                      )
                    )}
                    <IconButton
                      icon={Ban}
                      label={`Sonlandır: ${sub.planName}`}
                      onClick={() => onAction("cancelSubscription", sub)}
                    />
                  </div>
                )}
              </td>
            </tr>
          );
        })}
      </Table>
      {!rows.length && <Empty>Bu durumda üyelik bulunmuyor.</Empty>}
      <h3 className="section-title">Dondurma geçmişi</h3>
      <Table
        headers={[
          "Paket",
          "Başlangıç",
          "Bitiş",
          "Durum",
          "Gerekçe",
          "Personel",
        ]}
      >
        {history.map((row) => (
          <tr key={row.id}>
            <td>
              {
                subscriptions.find((sub) => sub.id === row.subscriptionId)
                  ?.planName
              }
            </td>
            <td>{displayDate(row.start)}</td>
            <td>
              {row.end === row.start
                ? "-"
                : row.end
                  ? displayDate(addDays(row.end, -1))
                  : "Açık"}
              {row.plannedEnd && (
                <small>Planlanan: {displayDate(row.plannedEnd)}</small>
              )}
            </td>
            <td>
              {row.end === row.start
                ? "Vazgeçildi"
                : row.start > today
                  ? "Planlandı"
                  : row.end && row.end <= today
                    ? "Tamamlandı"
                    : "Devam ediyor"}
            </td>
            <td className="membership-reason">{row.reason}</td>
            <td>{row.actor}</td>
          </tr>
        ))}
      </Table>
      {!history.length && <Empty>Dondurma kaydı yok.</Empty>}
    </section>
  );
}

export function SubscriptionDialog({
  kind,
  subscription,
  member,
  db,
  actorName,
  run,
  onClose,
}) {
  const renew = kind === "renew";
  const [planId, setPlanId] = useState(
    db.plans.find((plan) => saleAvailable(plan))?.id || "",
  );
  const [start, setStart] = useState(
    renew
      ? renewalStart(
          db.subscriptions.filter((sub) => sub.memberId === member.id),
        )
      : dateKey() > subscription.start
        ? dateKey()
        : subscription.start,
  );
  const [end, setEnd] = useState(
    addDays(start, (subscription?.rules?.freezeMin || 1) - 1),
  );
  const [discount, setDiscount] = useState("0");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const plan = db.plans.find((plan) => plan.id === planId);
  const title = renew
    ? "Üyelik yenile"
    : kind === "freeze"
      ? "Üyeliği dondur"
      : kind === "resume"
        ? "Dondurmayı bitir"
        : "Üyeliği sonlandır";
  return (
    <Dialog title={title} onClose={onClose}>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (saving) return;
          const form = event.currentTarget;
          const values = Object.fromEntries(new FormData(form));
          setSaving(true);
          setError("");
          try {
            const payload = renew
              ? { ...values, memberId: member.id }
              : {
                  id: subscription.id,
                  ...(kind === "freeze"
                    ? { start, end, reason: values.reason }
                    : kind === "cancelSubscription"
                      ? {
                          reason: values.reason,
                          confirmed: form.elements.confirmed.checked,
                        }
                      : {}),
                };
            const result = await run(kind, payload);
            if (result?.ok) onClose();
            else setError(result?.message || "İşlem kaydedilemedi.");
          } catch (err) {
            setError(err.message);
          } finally {
            setSaving(false);
          }
        }}
      >
        <div className="form-grid">
          {renew ? (
            <>
              <Field label="Paket">
                <select
                  name="planId"
                  value={planId}
                  required
                  onChange={(event) => setPlanId(event.target.value)}
                >
                  <option value="" disabled>
                    Paket seçin
                  </option>
                  {db.plans
                    .filter((plan) => saleAvailable(plan))
                    .map((plan) => (
                      <option key={plan.id} value={plan.id}>
                        {plan.name} / {money(salePrice(plan))}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Başlangıç">
                <input
                  name="start"
                  type="date"
                  required
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                />
              </Field>
              <Field label="Bitiş">
                <input
                  type={plan?.kind === "sessions" ? "text" : "date"}
                  readOnly
                  value={
                    plan?.kind === "sessions"
                      ? "Bitiş tarihi yok"
                      : plan
                        ? membershipEnd(plan, start)
                        : ""
                  }
                />
              </Field>
              <Field label="İndirim (TL)">
                <input
                  name="discount"
                  type="number"
                  min="0"
                  max={plan?.campaignDiscountCents > 0 ? 0 : salePrice(plan)}
                  step="0.01"
                  value={discount}
                  onChange={(event) => setDiscount(event.target.value)}
                />
              </Field>
              <input
                type="hidden"
                name="planRevision"
                value={plan?.revision || ""}
              />
              <Field label="Satış fiyatı">
                <input
                  readOnly
                  value={money(Math.max(0, salePrice(plan) - Number(discount)))}
                />
              </Field>
              <Field label="Taksit sayısı">
                <input
                  name="installments"
                  type="number"
                  min="1"
                  max="12"
                  required
                  defaultValue="1"
                />
              </Field>
              <Field label="İlk ödeme (TL)">
                <input
                  name="paid"
                  type="number"
                  min="0"
                  max={Math.max(0, salePrice(plan) - Number(discount))}
                  step="0.01"
                  defaultValue="0"
                />
              </Field>
              <Field label="Ödeme yöntemi">
                <select name="method">
                  {methods.map((method) => (
                    <option key={method.value} value={method.value}>
                      {method.label}
                    </option>
                  ))}
                </select>
              </Field>
            </>
          ) : (
            <>
              <Field label="Paket">
                <input readOnly value={subscription.planName} />
              </Field>
              <Field label="İşlemi yapan personel">
                <input readOnly value={actorName} />
              </Field>
              {kind === "freeze" && (
                <>
                  <Field label="Dondurma başlangıç tarihi">
                    <input
                      type="date"
                      required
                      min={
                        dateKey() > subscription.start
                          ? dateKey()
                          : subscription.start
                      }
                      max={subscription.end}
                      value={start}
                      onChange={(event) => setStart(event.target.value)}
                    />
                  </Field>
                  <Field label="Dondurma bitiş tarihi">
                    <input
                      type="date"
                      required
                      min={
                        start
                          ? addDays(
                              start,
                              (subscription.rules.freezeMin || 1) - 1,
                            )
                          : start
                      }
                      max={
                        start
                          ? addDays(
                              start,
                              Math.max(
                                0,
                                Math.min(
                                  subscription.rules.freezeDays -
                                    subscription.frozenDays,
                                  subscription.rules.freezeMax ||
                                    subscription.rules.freezeDays,
                                ) - 1,
                              ),
                            )
                          : undefined
                      }
                      value={end}
                      onChange={(event) => setEnd(event.target.value)}
                    />
                  </Field>
                  <Field label="Dondurma günü">
                    <input
                      readOnly
                      value={
                        start && end ? Math.max(0, dayDiff(end, start) + 1) : 0
                      }
                    />
                  </Field>
                  <Field label="Kalan dondurma hakkı">
                    <input
                      readOnly
                      value={Math.max(
                        0,
                        subscription.rules.freezeDays - subscription.frozenDays,
                      )}
                    />
                  </Field>
                </>
              )}
              {kind !== "resume" && (
                <Field
                  label={
                    kind === "freeze"
                      ? "Dondurma nedeni"
                      : "Sonlandırma gerekçesi"
                  }
                >
                  <textarea name="reason" maxLength={1500} required />
                </Field>
              )}
            </>
          )}
        </div>
        {kind === "cancelSubscription" && (
          <>
            <p className="member-note">
              Üyelik giriş yetkisi sona erer. Geçmiş ödemeler ve mevcut borç
              kayıtları korunur.
            </p>
            <label className="check-field">
              <input name="confirmed" type="checkbox" required />
              Üyelik sonlandırmasını onaylıyorum
            </label>
          </>
        )}
        {kind === "resume" && (
          <p className="member-note">
            Kullanılmayan dondurma günleri paket hakkına geri döner; üyelik
            bitişi buna göre düzeltilir.
          </p>
        )}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <footer className="form-footer">
          <Button type="button" onClick={onClose}>
            Vazgeç
          </Button>
          <Button
            type="submit"
            icon={Save}
            tone={kind === "cancelSubscription" ? "danger" : "primary"}
            disabled={saving || (renew && !plan)}
          >
            {saving
              ? "Kaydediliyor..."
              : kind === "cancelSubscription"
                ? "Üyeliği sonlandır"
                : "Kaydet"}
          </Button>
        </footer>
      </form>
    </Dialog>
  );
}
