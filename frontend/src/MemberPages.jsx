import React, { useState, useEffect, useRef } from "react";
import { request } from "./api.mjs";
import { validateMember } from "./member-validation.mjs";
import { MembershipsTab, SubscriptionDialog } from "./MembershipsTab";
import { membershipEnd } from "./subscription-rules.mjs";
import { MemberPayments } from "./FinanceDetails";
import { saleAvailable, salePrice } from './plan-rules.mjs';
import {
  Search,
  Plus,
  Pencil,
  Snowflake,
  Play,
  Ban,
  CreditCard,
  RefreshCw,
  Save,
  RotateCcw,
} from "lucide-react";
import {
  currentSubscription,
  subscriptionStatus,
  memberDebt,
  invoiceDebt,
  paidCents,
  dayDiff,
  addDays,
} from "./gym.mjs";
import { dateKey, displayDate, displayTime, money } from "./attendance.mjs";
import {
  Badge,
  Button,
  Avatar,
  Empty,
  Table,
  Field,
  Dialog,
  ActionForm,
  ExportButtons,
  exportCsv,
  methods,
} from "./ui";


export function MemberForm({ db, member, onClose, run }) {
  const [photo, setPhoto] = useState(member?.photo || "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [photoReading, setPhotoReading] = useState(false);
  const [photoError, setPhotoError] = useState("");
  const photoReader = useRef(null);
  useEffect(() => () => photoReader.current?.abort(), []);
  const [planId, setPlanId] = useState("");
  const [start, setStart] = useState(dateKey());
  const plan = db.plans.find((item) => item.id === planId);
  return (
    <Dialog
      title={member ? "Üye bilgilerini düzenle" : "Yeni üye kaydı"}
      onClose={onClose}
    >
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (saving) return;
          if (photoReading || photoError) {
            setError(photoError || "Fotoğraf yükleniyor.");
            return;
          }
          const form = event.currentTarget;
          setError("");
          setSaving(true);
          try {
            const values = validateMember(
              Object.fromEntries(new FormData(form)),
              db.members,
              member?.id,
            );
            const result = await run(member ? "editMember" : "addMember", {
              ...values,
              photo,
              id: member?.id,
              consent: form.elements.consent?.checked,
              marketing: form.elements.marketing.checked,
            });
            if (result?.ok) onClose();
            else
              setError(
                result?.message || "Üye kaydedilemedi; bilgileri kontrol edin.",
              );
          } catch (err) {
            setError(err.message);
          } finally {
            setSaving(false);
          }
        }}
      >
        <div className="form-grid">
          <Field label="Ad soyad *">
            <input
              name="name"
              required
              defaultValue={member?.name}
              maxLength={120}
              autoComplete="name"
            />
          </Field>
          <Field label="Telefon *">
            <input
              name="phone"
              type="tel"
              required
              defaultValue={member?.phone}
              maxLength={30}
              autoComplete="tel"
            />
          </Field>
          <Field label="E-posta (isteğe bağlı)">
            <input
              name="email"
              type="email"
              maxLength={254}
              autoComplete="email"
              defaultValue={member?.email}
            />
          </Field>
          <Field label="Doğum tarihi (isteğe bağlı)">
            <input
              name="birthDate"
              type="date"
              max={dateKey()}
              defaultValue={member?.birthDate || ""}
            />
          </Field>
          <Field label="Acil iletişim kişisi (isteğe bağlı)">
            <input
              name="emergency"
              maxLength={200}
              defaultValue={member?.emergency}
            />
          </Field>
          <Field label="Acil iletişim telefonu (isteğe bağlı)">
            <input
              name="emergencyPhone"
              type="tel"
              maxLength={30}
              defaultValue={member?.emergencyPhone}
            />
          </Field>
          <Field label="Antrenör (isteğe bağlı)">
            <select name="trainer" defaultValue={member?.trainer || ""}>
              <option value="">Atanmadı</option>
              {db.employees
                .filter((item) => item.active)
                .map((item) => (
                  <option key={item.id}>{item.name}</option>
                ))}
            </select>
          </Field>
          <Field label="Üye fotoğrafı (isteğe bağlı)">
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(event) => {
                photoReader.current?.abort();
                setPhotoReading(false);
                setPhotoError("");
                const file = event.target.files[0];
                if (!file) return;
                if (
                  file.size > 500000 ||
                  !["image/png", "image/jpeg", "image/webp"].includes(file.type)
                ) {
                  setError("PNG/JPEG/WebP, en fazla 500 KB.");
                  setPhotoError("PNG/JPEG/WebP, en fazla 500 KB.");
                  return;
                }
                const reader = new FileReader();
                photoReader.current = reader;
                setPhotoReading(true);
                reader.onload = () => {
                  setPhoto(reader.result);
                  setPhotoReading(false);
                  setError("");
                };
                reader.onerror = () => {
                  setPhotoReading(false);
                  setPhotoError("Fotoğraf okunamadı.");
                  setError("Fotoğraf okunamadı.");
                };
                reader.readAsDataURL(file);
              }}
            />
          </Field>
          {member && (
            <Field label="Adres (isteğe bağlı)">
              <input
                name="address"
                maxLength={400}
                defaultValue={member.address}
              />
            </Field>
          )}
          <Field label="Açıklama (isteğe bağlı)">
            <textarea
              name="note"
              maxLength={4000}
              defaultValue={member?.note}
            />
          </Field>
          {!member && (
            <>
              <Field label="Üyelik paketi (isteğe bağlı)">
                <select
                  name="planId"
                  value={planId}
                  onChange={(event) => setPlanId(event.target.value)}
                >
                  <option value="">Paket seçilmedi</option>
                  {db.plans
                    .filter((item) => saleAvailable(item))
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} / {money(salePrice(item))}
                      </option>
                    ))}
                </select>
              </Field>
              {plan && (
                <>
                  <input type="hidden" name="planRevision" value={plan.revision || ''}/>
                  <Field label="Üyelik başlangıç tarihi">
                    <input
                      name="start"
                      type="date"
                      required
                      value={start}
                      onChange={(event) => setStart(event.target.value)}
                    />
                  </Field>
                  <Field label="Üyelik bitiş tarihi">
                    <input
                      key={`${start}-${planId}`}
                      name="end"
                      type={plan?.kind==='sessions'?'text':'date'}
                      disabled={plan?.kind==='sessions'}
                      readOnly
                      min={start}
                      required={plan?.kind!=='sessions'}
                      defaultValue={plan?.kind==='sessions'?'Bitiş tarihi yok':plan ? membershipEnd(plan, start) : ""}
                    />
                  </Field>
                  <Field label="İndirim (TL)">
                    <input
                      name="discount"
                      type="number"
                      min="0"
                      max={plan?.campaignDiscountCents>0?0:salePrice(plan)}
                      step="0.01"
                      defaultValue="0"
                    />
                  </Field>
                  <Field label="Taksit sayısı">
                    <input
                      name="installments"
                      type="number"
                      min="1"
                      max="12"
                      defaultValue="1"
                      required
                    />
                  </Field>
                  <Field label="Satış fiyatı"><input readOnly value={money(salePrice(plan))}/></Field>
                  <Field label="İlk ödeme (TL)">
                    <input
                      name="paid"
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue="0"
                    />
                  </Field>
                  <Field label="Ödeme yöntemi">
                    <select name="method">
                      {methods.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                </>
              )}
              <Field label="RFID kart UID (isteğe bağlı)">
                <input
                  name="uid"
                  maxLength={100}
                  pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,99}"
                  autoComplete="off"
                />
              </Field>
              <label className="check-field">
                <input name="consent" type="checkbox" required />
                Üye bilgilendirmesi yapıldı *
              </label>
            </>
          )}
          <label className="check-field">
            <input
              name="marketing"
              type="checkbox"
              defaultChecked={member?.marketing}
            />
            Pazarlama ileti izni
          </label>
        </div>
        {photo && (
          <img
            className="photo-preview"
            src={photo}
            alt="Üye fotoğrafı önizleme"
          />
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
            tone="primary"
            icon={Save}
            disabled={saving || photoReading || !!photoError}
          >
            {saving ? "Kaydediliyor..." : "Üyeyi kaydet"}
          </Button>
        </footer>
      </form>
    </Dialog>
  );
}

export function MembersPage({
  db,
  run,
  isAdmin,
  actorName,
  onAdd,
  selectedId,
  setSelectedId,
  navigate,
}) {
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState("all"),
    [packageId, setPackageId] = useState("all"),
    [debtOnly, setDebtOnly] = useState(false);
  const [edit, setEdit] = useState(false),
    [action, setAction] = useState(null),
    [tab, setTab] = useState("general"),
    [day, setDay] = useState(dateKey()),
    [allDays, setAllDays] = useState(false);
  const [actionSub, setActionSub] = useState(null);
  const [listPage, setListPage] = useState(1);
  const previousMembers = useRef(new Set(db.members.map((item) => item.id)));
  useEffect(() => {
    if (selectedId && !previousMembers.current.has(selectedId)) {
      setQuery("");
      setStatus("all");
      setPackageId("all");
      setDebtOnly(false);
      setListPage(1);
    }
    previousMembers.current = new Set(db.members.map((item) => item.id));
  }, [db.members, selectedId]);
  useEffect(() => setListPage(1), [query, status, packageId, debtOnly]);
  useEffect(() => {
    setTab("general");
    setAction(null);
    setActionSub(null);
    setDay(dateKey());
    setAllDays(false);
  }, [selectedId]);
  const member = db.members.find((item) => item.id === selectedId);
  const sub = member && currentSubscription(db, member.id);
  const state = (item) =>
    !item.active
      ? "inactive"
      : item.blocked
        ? "blocked"
        : subscriptionStatus(currentSubscription(db, item.id));
  const filtered = db.members.filter(
    (item) =>
      [item.name, item.phone, item.number]
        .join(" ")
        .toLocaleLowerCase("tr")
        .includes(query.toLocaleLowerCase("tr")) &&
      (status === "all" || state(item) === status) &&
      (packageId === "all" ||
        currentSubscription(db, item.id)?.planId === packageId) &&
      (!debtOnly || memberDebt(db, item.id) > 0),
  );
  const subscriptions = db.subscriptions.filter(
    (item) => item.memberId === member?.id,
  );
  const invoices = db.invoices.filter((item) => item.memberId === member?.id);
  const visits = db.visits.filter(
    (item) =>
      item.memberId === member?.id &&
      (allDays || dateKey(new Date(item.entry)) === day),
  );
  const attempts = db.attempts.filter(
    (item) =>
      item.memberId === member?.id &&
      (allDays || dateKey(new Date(item.at)) === day),
  );
  return (
    <section className="page-grid">
      <div className="filter-bar">
        <label className="search-box">
          <Search size={18} />
          <input
            aria-label="Üye ara"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ad, telefon veya üye numarası"
          />
        </label>
        <select
          aria-label="Üye durumu"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="all">Tüm durumlar</option>
          {[
            "active",
            "ending",
            "expired",
            "frozen",
            "inactive",
            "pending",
            "blocked",
            "none",
          ].map((item) => (
            <option key={item} value={item}>
              {
                {
                  active: "Aktif",
                  ending: "Bitiyor",
                  expired: "Süresi dolmuş",
                  frozen: "Dondurulmuş",
                  inactive: "Pasif",
                  pending: "Başlamamış",
                  blocked: "Engelli",
                  none: "Üyelik yok",
                }[item]
              }
            </option>
          ))}
        </select>
        <select
          aria-label="Paket filtresi"
          value={packageId}
          onChange={(event) => setPackageId(event.target.value)}
        >
          <option value="all">Tüm paketler</option>
          {db.plans.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <label className="check-field">
          <input
            type="checkbox"
            checked={debtOnly}
            onChange={(event) => setDebtOnly(event.target.checked)}
          />
          Borcu olanlar
        </label>
        {isAdmin && (
          <ExportButtons
            onExport={() =>
              exportCsv(
                "uyeler",
                ["Üye no", "Ad", "Telefon", "Durum", "Borç"],
                filtered.map((item) => [
                  item.number,
                  item.name,
                  item.phone,
                  state(item),
                  memberDebt(db, item.id) / 100,
                ]),
              )
            }
          />
        )}
      </div>
      <div className="member-workspace">
        <div className="member-directory">
          <Table headers={["Üye", "Paket / Tarihler", "Durum", "Borç"]}>
            {filtered.slice((listPage - 1) * 20, listPage * 20).map((item) => {
              const subscription = currentSubscription(db, item.id);
              return (
                <tr
                  key={item.id}
                  className={member?.id === item.id ? "selected-table-row" : ""}
                >
                  <td>
                    <button
                      className="member-link"
                      onClick={() => {
                        setSelectedId(item.id);
                        setTab("general");
                      }}
                    >
                      <Avatar member={item} size="small" />
                      <span>
                        <strong>{item.name}</strong>
                        <small>{item.number}</small>
                      </span>
                    </button>
                  </td>
                  <td>
                    {subscription?.planName || "-"}
                    <small>
                      {subscription
                        ? `${displayDate(subscription.start)} – ${displayDate(subscription.end)}`
                        : "-"}
                    </small>
                    <small>
                      {subscription
                        ? subscription.end ? `${Math.max(0, dayDiff(subscription.end, dateKey()))} gün kaldı` : 'Bitiş tarihi yok'
                        : ""}
                    </small>
                  </td>
                  <td>
                    <Badge status={state(item)} />
                  </td>
                  <td>{money(memberDebt(db, item.id) / 100)}</td>
                </tr>
              );
            })}
          </Table>
          {!filtered.length && <Empty>Aramaya uygun üye bulunamadı.</Empty>}
          <div className="filter-bar">
            <Button
              disabled={listPage === 1}
              onClick={() => setListPage(listPage - 1)}
            >
              Önceki
            </Button>
            <span>
              {filtered.length} üye · Sayfa {listPage} /{" "}
              {Math.max(1, Math.ceil(filtered.length / 20))}
            </span>
            <Button
              disabled={listPage * 20 >= filtered.length}
              onClick={() => setListPage(listPage + 1)}
            >
              Sonraki
            </Button>
          </div>
        </div>
        {member ? (
          <aside className="member-detail">
            <div className="profile-header">
              <Avatar member={member} />
              <div>
                <h2>{member.name}</h2>
                <small>
                  {member.number} · {member.phone}
                </small>
              </div>
              <Badge status={state(member)} />
            </div>
            <div className="button-group detail-actions">
              <Button icon={Pencil} onClick={() => setEdit(true)}>
                Düzenle
              </Button>
              <Button icon={RefreshCw} onClick={() => setAction("renew")}>
                Yenile
              </Button>
              <Button icon={CreditCard} onClick={() => navigate("payments")}>
                Ödeme al
              </Button>
            </div>
            <div className="tabs" role="tablist" aria-label="Üye detayları">
              {[
                ["general", "Bilgiler"],
                ["subscriptions", "Üyelikler"],
                ["payments", "Ödemeler"],
                ["visits", "Girişler"],
                ...(!isAdmin ? [["cards", "Kartlar"]] : []),
                ["history", "İşlemler"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  role="tab"
                  aria-selected={tab === id}
                  onClick={() => setTab(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab === "general" && (
              <>
                <dl className="detail-grid">
                  <Info
                    label="Üyelik başlangıcı"
                    value={sub ? displayDate(sub.start) : "-"}
                  />
                  <Info
                    label="Üyelik bitişi"
                    value={sub ? sub.end ? displayDate(sub.end) : 'Bitiş tarihi yok' : "-"}
                  />
                  <Info label="Paket" value={sub?.planName || "-"} />
                  <Info
                    label="Kalan borç"
                    value={money(memberDebt(db, member.id) / 100)}
                  />
                  <Info label="Antrenör" value={member.trainer || "Atanmadı"} />
                  <Info label="E-posta" value={member.email || "-"} />
                  <Info
                    label="Doğum tarihi"
                    value={
                      member.birthDate ? displayDate(member.birthDate) : "-"
                    }
                  />
                  <Info label="Acil iletişim" value={member.emergency || "-"} />
                  <Info
                    label="Acil iletişim telefonu"
                    value={member.emergencyPhone || "-"}
                  />
                  <Info
                    label="Kalan seans"
                    value={sub ? (sub.remaining ?? "Sınırsız") : "-"}
                  />
                </dl>
                <p className="member-note">
                  {member.note || "Not bulunmuyor."}
                </p>
                <label className="state-control">
                  <span>Üye aktif</span>
                  <input
                    type="checkbox"
                    checked={member.active}
                    onChange={(event) =>
                      run("editMember", {
                        id: member.id,
                        active: event.target.checked,
                      })
                    }
                  />
                </label>
                {isAdmin && (
                  <label className="state-control">
                    <span>Giriş engeli</span>
                    <input
                      type="checkbox"
                      checked={member.blocked}
                      onChange={(event) =>
                        run("editMember", {
                          id: member.id,
                          blocked: event.target.checked,
                        })
                      }
                    />
                  </label>
                )}
                <div className="button-group">
                  {isAdmin && sub && (
                    <>
                      {["active", "ending"].includes(
                        subscriptionStatus(sub),
                      ) && (
                        <Button
                          icon={Snowflake}
                          onClick={() => setAction("freeze")}
                        >
                          Dondur
                        </Button>
                      )}
                      {sub.status === "frozen" && (
                        <Button
                          icon={Play}
                          onClick={() => run("resume", { id: sub.id })}
                        >
                          Devam ettir
                        </Button>
                      )}
                      {sub.status !== "cancelled" && (
                        <Button
                          tone="danger"
                          icon={Ban}
                          onClick={() => setAction("cancelSubscription")}
                        >
                          Üyeliği sonlandır
                        </Button>
                      )}
                    </>
                  )}
                </div>
              </>
            )}
            {tab === "subscriptions" && <MembershipsTab key={member.id} subscriptions={subscriptions} freezes={db.freezes} isAdmin={isAdmin} onAction={(kind, target) => { setActionSub(target || null); setAction(kind); }} />}
            {tab === "payments" && (
              <MemberPayments db={db} member={member}/>
            )}
            {tab === "visits" && (
              <>
                <div className="history-toolbar">
                  <Field label="Tarih">
                    <input
                      type="date"
                      value={day}
                      disabled={allDays}
                      onChange={(event) => setDay(event.target.value)}
                    />
                  </Field>
                  <label className="check-field">
                    <input
                      type="checkbox"
                      checked={allDays}
                      onChange={(event) => setAllDays(event.target.checked)}
                    />
                    Tüm günler
                  </label>
                </div>
                <Table headers={["Tarih", "Giriş", "Çıkış", "Süre"]}>
                  {visits.map((item) => (
                    <tr key={item.id}>
                      <td>{displayDate(item.entry)}</td>
                      <td>{displayTime(item.entry)}</td>
                      <td>{item.exit ? displayTime(item.exit) : "İçeride"}</td>
                      <td>
                        {item.exit
                          ? `${Math.floor((new Date(item.exit) - new Date(item.entry)) / 60000)} dk`
                          : "-"}
                      </td>
                    </tr>
                  ))}
                </Table>
                <h3 className="section-title">Kart doğrulamaları</h3>
                <Table headers={["Saat", "Yön", "Sonuç"]}>
                  {attempts.map((item) => (
                    <tr key={item.id}>
                      <td>
                        {displayDate(item.at)}
                        <small>{displayTime(item.at)}</small>
                      </td>
                      <td>{item.direction === "entry" ? "Giriş" : "Çıkış"}</td>
                      <td>
                        <Badge status={item.status} />
                        <small>{item.reason}</small>
                      </td>
                    </tr>
                  ))}
                </Table>
                {!visits.length && !attempts.length && <Empty />}
              </>
            )}
            {tab === "cards" && !isAdmin && (
              <CardManager db={db} member={member} run={run} />
            )}
            {tab === "history" && (
              <>
                <Table headers={["Tarih", "Personel", "İşlem"]}>
                  {db.audit
                    .filter(
                      (item) =>
                        item.entityId === member.id ||
                        subscriptions.some((sub) => sub.id === item.entityId),
                    )
                    .slice()
                    .reverse()
                    .map((item) => (
                      <tr key={item.id}>
                        <td>
                          {displayDate(item.at)}
                          <small>{displayTime(item.at)}</small>
                        </td>
                        <td>{item.actor}</td>
                        <td>{actionLabels[item.type] || item.type}</td>
                      </tr>
                    ))}
                </Table>
                <Empty>Eski işlemler değiştirilemez.</Empty>
              </>
            )}
          </aside>
        ) : (
          <Empty>Üye detayını açmak için bir üye seçin.</Empty>
        )}
      </div>
      {edit && (
        <MemberForm
          db={db}
          member={member}
          run={run}
          onClose={() => setEdit(false)}
        />
      )}
      {action && <SubscriptionDialog key={action + (actionSub?.id || sub?.id || member.id)} kind={action} subscription={actionSub || sub} member={member} db={db} actorName={actorName} run={run} onClose={() => { setAction(null); setActionSub(null); }} />}
    </section>
  );
}
function Info({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
export const actionLabels = {
  addMember: "Üye kaydı",
  editMember: "Üye güncelleme",
  renew: "Üyelik satışı",
  freeze: "Üyelik dondurma",
  resume: "Üyelik devamı",
  cancelSubscription: "Üyelik iptali",
  collect: "Tahsilat",
  refund: "İade",
  savePlan: "Paket güncelleme",
  assignCard: "Kart atama",
  cardStatus: "Kart durumu",
  releaseCard: "Kart teslim alma",
  authorize: "Kart doğrulama",
  confirmPassage: "Fiziksel geçiş",
  sessionUsed: "Doğrulanmış girişte seans kullanımı",
  correctVisit: "Çıkış düzeltme",
  saveRates: "Fiyat / ücret güncelleme",
  saveClass: "Ders oluşturma",
  book: "Rezervasyon",
  bookingStatus: "Rezervasyon durumu",
  cancelClass: "Ders iptali",
  saveProduct: "Ürün oluşturma",
  sellProduct: "Ürün satışı",
  stock: "Stok düzeltme",
  returnSale: "Ürün iadesi",
  saveSettings: "Giriş politikası",
  deviceMode: "Cihaz bakım modu",
  notice: "Panel bildirimi",
  addEmployee: "Personel kaydı",
  scanEmployee: "Mesai okutma",
  correctShift: "Mesai düzeltme",
  employeeStatus: "Personel yetkisi",
  openCash: "Kasa açılışı",
  closeCash: "Kasa kapanışı",
};

export function CardManager({ db, member, run }) {
  const [card, setCard] = useState("");
  const [capture, setCapture] = useState(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const [returning, setReturning] = useState(null);
  const [deviceId, setDeviceId] = useState(
    db.devices.find((d) => d.code === "TRN-UNO-001")?.id ||
      db.devices.find((d) => !d.simulated)?.id ||
      "",
  );
  const captureRef = useRef(null);
  captureRef.current = capture;
  useEffect(() => {
    setCard("");
    setCapture(null);
    setError("");
    return () => {
      const item = captureRef.current;
      if (item && ["waiting", "captured"].includes(item.status))
        request(`cards/capture/${item.id}/`, { method: "DELETE" }).catch(
          () => {},
        );
    };
  }, [member.id]);
  useEffect(() => {
    if (!["waiting", "captured"].includes(capture?.status)) return;
    let active = true,
      busy = false;
    const timer = setInterval(async () => {
      if (
        capture.status === "captured" &&
        new Date(capture.expiresAt) <= new Date()
      ) {
        clearInterval(timer);
        return;
      }
      if (busy) return;
      busy = true;
      try {
        const item = await request(`cards/capture/${capture.id}/`);
        if (active) {
          setCapture(item);
          if (item.uid) setCard(item.uid);
          if (item.status === "expired")
            setError("Okutma süresi doldu. Yeniden başlatın.");
        }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        busy = false;
      }
    }, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [capture?.id, capture?.status]);
  async function beginCapture() {
    setStarting(true);
    setError("");
    setCard("");
    try {
      if (capture?.id)
        await request(`cards/capture/${capture.id}/`, { method: "DELETE" });
      setCapture(
        await request("cards/capture/", {
          method: "POST",
          body: JSON.stringify({ memberId: member.id, deviceId }),
        }),
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setStarting(false);
    }
  }
  return (
    <div className="form-block">
      <h3>Kart tanımlama</h3>
      <div className="inline-form">
        <select
          aria-label="Kart tanımlama okuyucusu"
          value={deviceId}
          disabled={starting || capture?.status === "waiting"}
          onChange={(event) => setDeviceId(event.target.value)}
        >
          {db.devices
            .filter((d) => !d.simulated)
            .map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
        </select>
        <Button
          icon={CreditCard}
          onClick={beginCapture}
          disabled={!deviceId || starting || capture?.status === "waiting"}
        >
          {starting ? "Bağlanıyor..." : "Kartı okut"}
        </Button>
        {capture?.status === "waiting" && (
          <Button
            onClick={async () => {
              try {
                setCapture(
                  await request(`cards/capture/${capture.id}/`, {
                    method: "DELETE",
                  }),
                );
              } catch (err) {
                setError(err.message);
              }
            }}
          >
            Vazgeç
          </Button>
        )}
      </div>
      {capture?.status === "waiting" && (
        <p role="status">Kart bekleniyor · Turnike açılmaz</p>
      )}
      {capture?.status === "captured" && (
        <p role="status">
          Kart okundu: <strong>{card}</strong> · {member.name}
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <form
        className="inline-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (
            (
              await run("assignCard", {
                memberId: member.id,
                uid: card,
                captureId:
                  capture?.status === "captured" ? capture.id : undefined,
              })
            )?.ok
          ) {
            setCard("");
            setCapture(null);
          }
        }}
      >
        <input
          aria-label="Kart UID"
          value={card}
          readOnly={
            capture?.status === "waiting" || capture?.status === "captured"
          }
          onChange={(event) => setCard(event.target.value)}
          placeholder="Kart UID"
          required
        />
        <Button
          type="submit"
          tone="primary"
          icon={CreditCard}
          disabled={!card || capture?.status === "waiting"}
        >
          Ata
        </Button>
      </form>
      {db.cards.some((item) => item.status === 'available' && !item.memberId) && (
        <Field label="Teslim alınan boş kartlar">
          <select aria-label="Boş kart seç" value="" disabled={!!capture && ['waiting','captured'].includes(capture.status)} onChange={(event) => setCard(event.target.value)}>
            <option value="">Kart seçin</option>
            {db.cards.filter((item) => item.status === 'available' && !item.memberId).map((item) => <option key={item.id} value={item.uid}>{item.uid}</option>)}
          </select>
        </Field>
      )}
      {db.cards
        .filter((item) => item.memberId === member.id)
        .map((item) => (
          <div className="card-record" key={item.id}>
            <div>
              <strong>{item.uid}</strong>
              <small>{displayDate(item.at)}</small>
            </div>
            <Badge status={item.status} />
            {['active','inactive','lost','cancelled'].includes(item.status) && (
              <Button icon={RotateCcw} onClick={() => setReturning(item)}>Kartı teslim al</Button>
            )}
            {["active", "inactive"].includes(item.status) && (
              <>
                <label className="check-field">
                  <input
                    type="checkbox"
                    aria-label={`${item.uid} aktif`}
                    checked={item.status === "active"}
                    onChange={(event) =>
                      run("cardStatus", {
                        id: item.id,
                        status: event.target.checked ? "active" : "inactive",
                      })
                    }
                  />
                  Aktif
                </label>
                <Button
                  tone="danger"
                  onClick={() =>
                    run("cardStatus", { id: item.id, status: "lost" })
                  }
                >
                  Kayıp
                </Button>
                <Button
                  tone="danger"
                  onClick={() =>
                    run("cardStatus", { id: item.id, status: "cancelled" })
                  }
                >
                  İptal
                </Button>
              </>
            )}
          </div>
        ))}
      {returning && (
        <ActionForm title="Kartı teslim al" fields={[{name:'confirmed',label:'Kart fiziksel olarak teslim alındı',type:'checkbox'}]} onClose={() => setReturning(null)} onSave={(values) => run('releaseCard',{id:returning.id,...values})}>
          <p><strong>{returning.uid}</strong> kartı {member.name} üzerinden kaldırılıp boş kartlara alınacak. Geçiş geçmişi korunacak.</p>
        </ActionForm>
      )}
    </div>
  );
}

export { PlansPage } from './PlansPage';
