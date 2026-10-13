import React, { useState, useRef } from "react";
import {
  Plus,
  Pencil,
  Search,
  Eye,
  Ban,
  Check,
  Save,
  Trash2,
} from "lucide-react";
import { Button, IconButton, Field, Dialog, Badge, Table, Empty } from "./ui";
import { money, displayDate } from "./attendance.mjs";
import {
  planTypes,
  durationUnits,
  planKind,
  planDuration,
  salePrice,
} from "./plan-rules.mjs";

const defaults = {
  name: "",
  description: "",
  kind: "timed",
  price: "0",
  durationValue: 1,
  durationUnit: "month",
  sessions: null,
  from: "06:00",
  to: "23:00",
  weekdays: [0, 1, 2, 3, 4, 5, 6],
  freezeDays: 0,
  freezeMin: 1,
  freezeMax: null,
  freezeLimit: null,
  dailyLimit: null,
  weeklyLimit: null,
  saleStart: "",
  saleEnd: "",
  active: true,
  campaigns: [],
  lessonTypes: ["group"],
  lessonSessions: null,
};

export function PlansPage({ db, run }) {
  const [search, setSearch] = useState(""),
    [active, setActive] = useState("all"),
    [kind, setKind] = useState("all"),
    [dialog, setDialog] = useState(null);
  const plans = db.plans.filter(
    (row) =>
      (row.name + " " + row.description)
        .toLocaleLowerCase("tr")
        .includes(search.toLocaleLowerCase("tr")) &&
      (active === "all" || row.active === (active === "active")) &&
      (kind === "all" || planKind(row) === kind),
  );
  return (
    <section className="page-grid">
      <div className="filter-bar">
        <Field label="Paket ara">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </Field>
        <Field label="Durum">
          <select value={active} onChange={(e) => setActive(e.target.value)}>
            <option value="all">Tümü</option>
            <option value="active">Aktif</option>
            <option value="inactive">Pasif</option>
          </select>
        </Field>
        <Field label="Paket türü">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="all">Tüm türler</option>
            {Object.entries(planTypes).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <span>{plans.length} paket</span>
        <Button
          icon={Plus}
          tone="primary"
          onClick={() => setDialog({ type: "edit", plan: defaults })}
        >
          Paket oluştur
        </Button>
      </div>
      <div className="plan-grid">
        {plans.map((plan) => (
          <article className="plan-item" key={plan.id}>
            <div className="panel-header">
              <h2>{plan.name}</h2>
              <Badge status={plan.active ? "active" : "inactive"} />
            </div>
            <small>
              {planTypes[planKind(plan)]} · Sürüm {plan.revision || 1}
            </small>
            <strong className="plan-price">{money(salePrice(plan))}</strong>
            {plan.campaignDiscountCents > 0 && (
              <p>
                <del>{money(plan.price)}</del> · {plan.appliedCampaign?.name}
              </p>
            )}
            <p>{plan.description}</p>
            <dl>
              <Row label="Süre" value={planDuration(plan)} />
              <Row label="Seans" value={plan.sessions ?? "Sınırsız"} />
              <Row
                label="Ders hakkı"
                value={
                  (plan.lessonTypes || []).length
                    ? (plan.lessonSessions ?? "Sınırsız")
                    : "Yok"
                }
              />
              <Row label="Saatler" value={`${plan.from} - ${plan.to}`} />
              <Row
                label="Giriş limiti"
                value={`Günlük ${plan.dailyLimit || "-"} / Haftalık ${plan.weeklyLimit || "-"}`}
              />
              <Row label="Dondurma" value={`${plan.freezeDays} gün`} />
              <Row
                label="Satış dönemi"
                value={`${plan.saleStart ? displayDate(plan.saleStart) : "Başlangıç sınırı yok"} / ${plan.saleEnd ? displayDate(plan.saleEnd) : "Bitiş sınırı yok"}`}
              />
            </dl>
            <div className="button-group">
              <Button
                icon={Pencil}
                onClick={() => setDialog({ type: "edit", plan })}
              >
                Düzenle
              </Button>
              <IconButton
                icon={Eye}
                label="Paket detayları"
                onClick={() => setDialog({ type: "detail", plan })}
              />
              <IconButton
                icon={plan.active ? Ban : Check}
                label={plan.active ? "Paketi pasife al" : "Paketi aktifleştir"}
                onClick={() => setDialog({ type: "status", plan })}
              />
            </div>
          </article>
        ))}
      </div>
      {!plans.length && <Empty />}
      {dialog?.type === "edit" && (
        <PlanForm
          key={dialog.plan.id || "new"}
          plan={dialog.plan}
          run={run}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === "detail" && (
        <Dialog
          title={`${dialog.plan.name} / Paket detayları`}
          onClose={() => setDialog(null)}
        >
          <dl className="receipt-details">
            <Row label="Süre" value={planDuration(dialog.plan)} />
            <Row label="Normal fiyat" value={money(dialog.plan.price)} />
            <Row label="Güncel fiyat" value={money(salePrice(dialog.plan))} />
            <Row label="Kullanılan üyelik" value={dialog.plan.usedCount || 0} />
            <Row
              label="Günler"
              value={dialog.plan.weekdays
                .map(
                  (day) =>
                    ["Paz", "Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"][day],
                )
                .join(", ")}
            />
            <Row
              label="Dondurma"
              value={
                dialog.plan.freezeDays
                  ? `${dialog.plan.freezeMin || 1} - ${dialog.plan.freezeMax || dialog.plan.freezeDays} gün / ${dialog.plan.freezeLimit || "Sayı sınırı yok"}`
                  : "Dondurma hakkı yok"
              }
            />
          </dl>
          <h3>Kampanyalar</h3>
          <Table
            headers={["Kampanya", "İndirim", "Başlangıç", "Bitiş", "Durum"]}
          >
            {(dialog.plan.campaigns || []).map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td>
                <td>
                  {row.type === "percent" ? `%${row.value}` : money(row.value)}
                </td>
                <td>{displayDate(row.start)}</td>
                <td>{displayDate(row.end)}</td>
                <td>
                  <Badge status={row.active ? "active" : "inactive"} />
                </td>
              </tr>
            ))}
          </Table>
        </Dialog>
      )}
      {dialog?.type === "status" && (
        <Dialog
          title={dialog.plan.active ? "Paketi pasife al" : "Paketi aktifleştir"}
          onClose={() => setDialog(null)}
        >
          <p>
            {dialog.plan.name} · {dialog.plan.usedCount || 0} üyelikte
            kullanıldı.
          </p>
          <p>Mevcut satış ve üyelik sözleşmeleri değişmeyecek.</p>
          <Button
            icon={Check}
            tone="primary"
            onClick={async () => {
              if (
                (
                  await run("savePlan", {
                    ...dialog.plan,
                    kind: planKind(dialog.plan),
                    active: !dialog.plan.active,
                    confirmed: true,
                  })
                )?.ok
              )
                setDialog(null);
            }}
          >
            Onayla
          </Button>
        </Dialog>
      )}
    </section>
  );
}
function Row({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
function PlanForm({ plan, run, onClose }) {
  const [form, setForm] = useState({
      ...defaults,
      ...plan,
      kind: planKind(plan),
      durationValue: plan.durationValue || plan.days || 1,
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const lock = useRef(false),
    set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  const fields = [
    ["name", "Paket adı", "text", true],
    ["description", "Açıklama", "textarea", false],
    ["price", "Satış fiyatı (TL)", "number", true],
    ["lessonSessions", "Ders hakkı (boş: sınırsız)", "number", false],
    ...(form.kind === "sessions"
      ? []
      : [["durationValue", "Süre değeri", "number", true]]),
    ...(form.kind === "timed"
      ? []
      : [["sessions", "Toplam seans hakkı", "number", true]]),
    ["dailyLimit", "Günlük giriş sınırı (isteğe bağlı)", "number", false],
    ["weeklyLimit", "Haftalık giriş sınırı (isteğe bağlı)", "number", false],
    ["from", "Geçerli giriş başlangıcı", "time", true],
    ["to", "Geçerli giriş bitişi", "time", true],
    ["freezeDays", "Toplam dondurma hakkı (gün)", "number", true],
    ...(Number(form.freezeDays) > 0
      ? [
          ["freezeMin", "Minimum dondurma (gün)", "number", true],
          ["freezeMax", "Bir seferde maksimum (gün)", "number", false],
          ["freezeLimit", "Dondurma sayısı limiti", "number", false],
        ]
      : []),
    ["saleStart", "Satışa sunulma tarihi", "date", false],
    ["saleEnd", "Satıştan kaldırılma tarihi", "date", false],
  ];
  const campaign = (index, key, value) =>
    set(
      "campaigns",
      form.campaigns.map((row, i) =>
        i === index ? { ...row, [key]: value } : row,
      ),
    );
  return (
    <Dialog
      title={plan.id ? "Paketi düzenle" : "Paket oluştur"}
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (lock.current) return;
          lock.current = true;
          setBusy(true);
          setError("");
          const payload = {
            ...form,
            confirmed,
            weekdays: form.weekdays,
            durationValue: form.kind === "sessions" ? 0 : form.durationValue,
            sessions: form.kind === "timed" ? null : Number(form.sessions),
            freezeMax: Number(form.freezeDays) ? form.freezeMax : null,
            freezeLimit: Number(form.freezeDays) ? form.freezeLimit : null,
          };
          for (const key of [
            "dailyLimit",
            "weeklyLimit",
            "freezeMax",
            "freezeLimit",
          ])
            payload[key] = payload[key] === "" ? null : payload[key];
          try {
            const result = await run("savePlan", payload);
            if (result?.ok) onClose();
            else setError(result?.message || "Paket kaydedilemedi.");
          } catch (err) {
            setError(err.message);
          } finally {
            lock.current = false;
            setBusy(false);
          }
        }}
      >
        <fieldset disabled={busy} className="finance-fields">
          <div className="lesson-checks">
            {[
              ["group", "Grup derslerine erişim"],
              ["private", "Özel derslere erişim"],
            ].map(([kind, label]) => (
              <label key={kind}>
                <input
                  type="checkbox"
                  checked={form.lessonTypes.includes(kind)}
                  onChange={(e) =>
                    set(
                      "lessonTypes",
                      e.target.checked
                        ? [...form.lessonTypes, kind]
                        : form.lessonTypes.filter((t) => t !== kind),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
          <div className="form-grid">
            <Field label="Paket türü">
              <select
                value={form.kind}
                onChange={(e) => set("kind", e.target.value)}
              >
                {Object.entries(planTypes).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            {form.kind !== "sessions" && (
              <Field label="Süre birimi">
                <select
                  value={form.durationUnit}
                  onChange={(e) => set("durationUnit", e.target.value)}
                >
                  {Object.entries(durationUnits).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {fields.map(([key, label, type, required]) => (
              <Field key={key} label={label}>
                {type === "textarea" ? (
                  <textarea
                    value={form[key] || ""}
                    maxLength="600"
                    onChange={(e) => set(key, e.target.value)}
                  />
                ) : (
                  <input
                    name={key}
                    type={type}
                    value={form[key] ?? ""}
                    required={required}
                    min={
                      type === "number"
                        ? ["price", "freezeDays"].includes(key)
                          ? 0
                          : 1
                        : undefined
                    }
                    step={
                      key === "price"
                        ? "0.01"
                        : type === "number"
                          ? 1
                          : undefined
                    }
                    maxLength={key === "name" ? 120 : undefined}
                    onChange={(e) => set(key, e.target.value)}
                  />
                )}
              </Field>
            ))}
          </div>
          <fieldset className="weekday-picker">
            <legend>Geçerli giriş günleri</legend>
            {["Paz", "Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"].map(
              (label, i) => (
                <label key={i}>
                  <input
                    type="checkbox"
                    checked={form.weekdays.includes(i)}
                    onChange={(e) =>
                      set(
                        "weekdays",
                        e.target.checked
                          ? [...form.weekdays, i]
                          : form.weekdays.filter((day) => day !== i),
                      )
                    }
                  />
                  {label}
                </label>
              ),
            )}
          </fieldset>
          <label className="check-field">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => set("active", e.target.checked)}
            />
            Paket aktif
          </label>
          <div className="section-header">
            <h3>Kampanyalar</h3>
            <Button
              type="button"
              icon={Plus}
              onClick={() =>
                set("campaigns", [
                  ...form.campaigns,
                  {
                    id: crypto.randomUUID(),
                    name: "",
                    type: "percent",
                    value: "10",
                    start: "",
                    end: "",
                    active: true,
                  },
                ])
              }
            >
              Kampanya ekle
            </Button>
          </div>
          {form.campaigns.map((row, i) => (
            <fieldset className="plan-campaign" key={row.id}>
              <legend>Kampanya {i + 1}</legend>
              <div className="form-grid">
                <Field label={`Kampanya ${i + 1} adı`}>
                  <input
                    required
                    maxLength="120"
                    value={row.name}
                    onChange={(e) => campaign(i, "name", e.target.value)}
                  />
                </Field>
                <Field label={`Kampanya ${i + 1} indirim türü`}>
                  <select
                    value={row.type}
                    onChange={(e) => campaign(i, "type", e.target.value)}
                  >
                    <option value="percent">Yüzde</option>
                    <option value="amount">Tutar (TL)</option>
                  </select>
                </Field>
                <Field label={`Kampanya ${i + 1} değeri`}>
                  <input
                    required
                    type="number"
                    min="0.01"
                    step="0.01"
                    max={row.type === "percent" ? 100 : undefined}
                    value={row.value}
                    onChange={(e) => campaign(i, "value", e.target.value)}
                  />
                </Field>
                <Field label={`Kampanya ${i + 1} başlangıcı`}>
                  <input
                    required
                    type="date"
                    value={row.start}
                    onChange={(e) => campaign(i, "start", e.target.value)}
                  />
                </Field>
                <Field label={`Kampanya ${i + 1} bitişi`}>
                  <input
                    required
                    type="date"
                    min={row.start}
                    value={row.end}
                    onChange={(e) => campaign(i, "end", e.target.value)}
                  />
                </Field>
              </div>
              <div className="button-group">
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={row.active}
                    onChange={(e) => campaign(i, "active", e.target.checked)}
                  />
                  Kampanya aktif
                </label>
                <IconButton
                  type="button"
                  icon={Trash2}
                  label={`Kampanya ${i + 1} kaldır`}
                  onClick={() =>
                    set(
                      "campaigns",
                      form.campaigns.filter((_, index) => index !== i),
                    )
                  }
                />
              </div>
            </fieldset>
          ))}
          {plan.id && (
            <label className="check-field">
              <input
                required
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              Fiyat ve koşul değişikliklerini onaylıyorum
            </label>
          )}
        </fieldset>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <Button icon={Save} tone="primary" disabled={busy}>
            Kaydet
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
