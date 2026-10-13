import React, { useState, useEffect } from "react";
import {
  Save,
  X,
  Pencil,
  KeyRound,
  Lock,
  ArrowUpRight,
  Building2,
  Clock,
  Wallet,
  Users,
  ShieldCheck,
  DoorOpen,
  Bell,
  Database,
} from "lucide-react";
import { Button, Field, Dialog, Table, Empty, Badge } from "./ui";
import { PricingSettings } from "./Employees";
import { displayDate, displayTime } from "./attendance.mjs";
import "./settings.css";

const sections = [
  ["profile", "Salon Bilgileri", Building2],
  ["opening", "Çalışma Saatleri", Clock],
  ["pricing", "Fiyatlandırma", Wallet],
  ["accounts", "Kullanıcı ve Rol Yönetimi", Users],
  ["security", "Güvenlik", ShieldCheck],
  ["devices", "Cihaz Yapılandırması", DoorOpen],
  ["notifications", "Bildirim Tercihleri", Bell],
  ["data", "Veri ve Yedekleme", Database],
];
const roles = { admin: "Admin", staff: "Resepsiyon", trainer: "Antrenör" };
const permissionLabels = {
  memberManagement: "Üye kayıtları",
  cardManagement: "Kart yönetimi",
  collections: "Tahsilat",
  deviceRead: "Cihaz durum bilgisi",
  classBooking: "Ders kaydı",
  classAttendance: "Ders yoklaması",
  productSales: "Ürün satışı",
  productDiscount: "Ürün indirimi",
  productReturns: "Ürün iadesi",
  manualAttendance: "Manuel mesai",
  manualVisits: "Manuel üye giriş / çıkışı (resepsiyon)",
  requestLeave: "İzin talebi",
  attendanceBreak: "Mola",
  simulateAttendance: "Mesai simülasyonu",
};
const noticeLabels = {
  membership: "Üyelik bitişi",
  payment: "Gecikmiş ödeme",
  stock: "Kritik stok",
  class: "Yaklaşan ders",
  shift: "Personel vardiyası",
  device: "Cihaz bağlantı hataları",
};

export function SettingsForm({
  initial,
  onSave,
  children,
  title = "Değişiklikleri onayla",
}) {
  const [draft, setDraft] = useState(initial),
    [base, setBase] = useState(JSON.stringify(initial)),
    [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(null);
  const incoming = JSON.stringify(initial),
    dirty = JSON.stringify(draft) !== base;
  useEffect(() => {
    if (!dirty) {
      setDraft(initial);
      setBase(incoming);
    }
  }, [incoming]);
  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await onSave({ ...draft, confirmed: true });
      if (result?.ok) {
        setBase(JSON.stringify(draft));
        setConfirm(false);
        setMessage({ ok: true, text: "Değişiklikler kaydedildi." });
      } else
        setMessage({
          ok: false,
          text: result?.message || "İşlem tamamlanamadı.",
        });
    } catch (e) {
      setMessage({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      className="settings-form"
      onSubmit={(e) => {
        e.preventDefault();
        setMessage(null);
        setConfirm(true);
      }}
    >
      {children(draft, (update) => {
        setDraft((old) =>
          typeof update === "function" ? update(old) : { ...old, ...update },
        );
        setMessage(null);
      })}
      {message && (
        <p
          role={message.ok ? "status" : "alert"}
          className={message.ok ? "success-message" : "form-error"}
        >
          {message.text}
        </p>
      )}
      <div className="button-group settings-save">
        <Button
          type="submit"
          icon={Save}
          tone="primary"
          disabled={!dirty || busy}
        >
          Kaydet
        </Button>
        <Button
          type="button"
          icon={X}
          disabled={!dirty || busy}
          onClick={() => {
            setDraft(initial);
            setBase(incoming);
            setMessage(null);
          }}
        >
          İptal
        </Button>
      </div>
      {confirm && (
        <Dialog title={title} onClose={() => !busy && setConfirm(false)}>
          <p>Bu değişiklik denetim günlüğüne kaydedilecek.</p>
          {message && !message.ok && (
            <p role="alert" className="form-error">
              {message.text}
            </p>
          )}
          <div className="button-group">
            <Button
              type="button"
              icon={Save}
              tone="primary"
              disabled={busy}
              onClick={save}
            >
              Onayla ve kaydet
            </Button>
            <Button
              type="button"
              icon={X}
              disabled={busy}
              onClick={() => setConfirm(false)}
            >
              Vazgeç
            </Button>
          </div>
        </Dialog>
      )}
    </form>
  );
}
export function SettingsPage({ db, user, run, navigate }) {
  const [deviceEdit, setDeviceEdit] = useState(null);
  const [tab, setTab] = useState("profile"),
    [account, setAccount] = useState(null),
    [policyRole, setPolicyRole] = useState("staff"),
    [photoError, setPhotoError] = useState("");
  const settings = db.systemSettings,
    accounts = db.personnel?.accounts || [],
    policies = db.personnel?.rolePolicies || [];
  if (!settings)
    return <Empty>Ayarlar verisi alınamadı. Bağlantıyı kontrol edin.</Empty>;
  const accountForm = account && {
    id: account.row.id,
    operation: account.operation,
    role: account.row.role,
    active: account.row.active,
    reason: "",
    ...(account.operation === "resetPassword" ? { password: "" } : {}),
  };
  const policy = policies.find((p) => p.role === policyRole)?.permissions || {};
  const defaults = {
    manualAttendance: false,
    manualVisits: false,
    requestLeave: true,
    attendanceBreak: true,
    simulateAttendance: false,
    classBooking: true,
    classAttendance: true,
    productSales: true,
    productDiscount: false,
    productReturns: false,
    memberManagement: policyRole === "staff",
    cardManagement: policyRole === "staff",
    collections: policyRole === "staff",
    deviceRead: policyRole === "staff",
  };
  return (
    <section className="page-grid settings-page">
      <nav className="settings-tabs" aria-label="Ayar bölümleri">
        {sections.map(([key, label, Icon]) => (
          <button
            key={key}
            type="button"
            aria-current={tab === key ? "page" : undefined}
            onClick={() => {
              setTab(key);
              setPhotoError("");
            }}
          >
            <Icon size={17} />
            {label}
          </button>
        ))}
      </nav>
      <div className="settings-body">
        <h2>{sections.find((s) => s[0] === tab)[1]}</h2>
        {tab === "profile" && (
          <SettingsForm
            initial={settings.profile}
            onSave={(p) => run("saveBranchProfile", p)}
          >
            {(d, set) => (
              <>
                <div className="form-grid">
                  <Field label="Salon adı">
                    <input
                      value={d.name}
                      required
                      maxLength={120}
                      onChange={(e) => set({ name: e.target.value })}
                    />
                  </Field>
                  <Field label="Telefon">
                    <input
                      type="tel"
                      value={d.phone}
                      onChange={(e) => set({ phone: e.target.value })}
                    />
                  </Field>
                  <Field label="E-posta">
                    <input
                      type="email"
                      value={d.email}
                      onChange={(e) => set({ email: e.target.value })}
                    />
                  </Field>
                  <Field label="Adres">
                    <textarea
                      value={d.address}
                      maxLength={600}
                      onChange={(e) => set({ address: e.target.value })}
                    />
                  </Field>
                  <Field label="Logo">
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={(e) => {
                        const file = e.target.files[0];
                        if (!file) return;
                        if (
                          file.size > 500000 ||
                          !["image/png", "image/jpeg", "image/webp"].includes(
                            file.type,
                          )
                        ) {
                          setPhotoError(
                            "PNG, JPEG veya WebP; en fazla 500 KB.",
                          );
                          return;
                        }
                        const reader = new FileReader();
                        reader.onload = () => {
                          set({ logo: reader.result });
                          setPhotoError("");
                        };
                        reader.readAsDataURL(file);
                      }}
                    />
                  </Field>
                </div>
                {d.logo && (
                  <div className="settings-logo">
                    <img src={d.logo} alt="Salon logosu" />
                    <Button
                      type="button"
                      icon={X}
                      onClick={() => set({ logo: "" })}
                    >
                      Logoyu kaldır
                    </Button>
                  </div>
                )}
                {photoError && (
                  <p role="alert" className="form-error">
                    {photoError}
                  </p>
                )}
              </>
            )}
          </SettingsForm>
        )}
        {tab === "opening" && (
          <SettingsForm
            initial={settings.opening}
            onSave={(p) => run("saveOpeningHours", p)}
          >
            {(d, set) => (
              <>
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={d.enforced}
                    onChange={(e) => set({ enforced: e.target.checked })}
                  />
                  Girişlerde salon çalışma takvimini uygula
                </label>
                <div className="form-grid">
                  <Field label="Açılış saati">
                    <input
                      type="time"
                      required
                      value={d.from}
                      onChange={(e) => set({ from: e.target.value })}
                    />
                  </Field>
                  <Field label="Kapanış saati">
                    <input
                      type="time"
                      required
                      value={d.to}
                      onChange={(e) => set({ to: e.target.value })}
                    />
                  </Field>
                </div>
                <fieldset className="settings-days">
                  <legend>Çalışma günleri</legend>
                  {[
                    "Pazar",
                    "Pazartesi",
                    "Salı",
                    "Çarşamba",
                    "Perşembe",
                    "Cuma",
                    "Cumartesi",
                  ].map((label, i) => (
                    <label className="check-field" key={i}>
                      <input
                        type="checkbox"
                        checked={d.days.includes(i)}
                        onChange={(e) =>
                          set({
                            days: e.target.checked
                              ? [...d.days, i].sort()
                              : d.days.filter((day) => day !== i),
                          })
                        }
                      />
                      {label}
                    </label>
                  ))}
                </fieldset>
                <Field label="Resmi tatil ve özel kapanış tarihleri">
                  <textarea
                    placeholder="2026-10-29"
                    value={d.closures.join("\n")}
                    onChange={(e) =>
                      set({
                        closures: e.target.value.split("\n").filter(Boolean),
                      })
                    }
                  />
                </Field>
                <p className="member-note">
                  Her satırda YYYY-AA-GG biçiminde bir tarih. Takvim yalnızca
                  yeni üye girişlerine uygulanır; açık ziyaretlerin çıkışı
                  engellenmez.
                </p>
              </>
            )}
          </SettingsForm>
        )}
        {tab === "pricing" && (
          <PricingSettings
            plans={db.plans}
            employees={db.employees}
            onSave={(plans, rates, confirmed) =>
              run("saveRates", { plans, rates, confirmed })
            }
          />
        )}
        {tab === "accounts" && (
          <>
            <Table headers={["Kullanıcı", "Rol", "Durum", "İşlemler"]}>
              {accounts.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.name}</strong>
                    <small>{row.email}</small>
                  </td>
                  <td>{roles[row.role]}</td>
                  <td>
                    <Badge status={row.active ? "active" : "inactive"} />
                  </td>
                  <td>
                    <div className="button-group">
                      <Button
                        icon={Pencil}
                        onClick={() => setAccount({ row, operation: "update" })}
                      >
                        Düzenle / kilitle
                      </Button>
                      <Button
                        icon={KeyRound}
                        onClick={() =>
                          setAccount({ row, operation: "resetPassword" })
                        }
                      >
                        Parola sıfırla
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
            <h3>Rol izinleri</h3>
            <Field label="Yetki rolü">
              <select
                value={policyRole}
                onChange={(e) => setPolicyRole(e.target.value)}
              >
                <option value="staff">Resepsiyon</option>
                <option value="trainer">Antrenör</option>
              </select>
            </Field>
            <SettingsForm
              key={policyRole}
              initial={{
                role: policyRole,
                permissions: { ...defaults, ...policy },
              }}
              onSave={(p) => run("saveRolePolicy", p)}
              title="Rol izinlerini değiştir"
            >
              {(d, set) => (
                <>
                  <div className="settings-permissions">
                    {Object.entries(permissionLabels).map(([key, label]) => (
                      <label className="check-field" key={key}>
                        <input
                          type="checkbox"
                          checked={Boolean(d.permissions[key])}
                          disabled={
                            policyRole === "trainer" &&
                            [
                              "manualVisits",
                              "memberManagement",
                              "cardManagement",
                              "collections",
                              "deviceRead",
                            ].includes(key)
                          }
                          onChange={(e) =>
                            set({
                              permissions: {
                                ...d.permissions,
                                [key]: e.target.checked,
                              },
                            })
                          }
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                  <p className="member-note">
                    İzin değişikliğinde ilgili rolün oturumları kapatılır. Üye
                    tahsilat iadesi, personel yönetimi ve cihaz yapılandırması
                    yalnızca admin yetkisindedir.
                  </p>
                </>
              )}
            </SettingsForm>
          </>
        )}
        {tab === "security" && (
          <>
            <dl className="settings-summary">
              <dt>Parola güvenliği</dt>
              <dd>{settings.security.hash}</dd>
              <dt>Erişim oturumu</dt>
              <dd>{settings.security.accessMinutes} dakika</dd>
              <dt>Yenileme oturumu</dt>
              <dd>{settings.security.refreshHours} saat</dd>
              <dt>Giriş koruması</dt>
              <dd>
                Hesap: {settings.security.loginAccountLimit}, IP:{" "}
                {settings.security.loginIpLimit} başarısız deneme;{" "}
                {settings.security.lockMinutes} dakika bekleme
              </dd>
              <dt>Güvenli çerezler</dt>
              <dd>
                {settings.security.secureCookies
                  ? "Etkin"
                  : "Yerel geliştirme; HTTPS dağıtımı gerekli"}
              </dd>
            </dl>
            <h3>Parolamı değiştir</h3>
            <SettingsForm
              initial={{ currentPassword: "", password: "" }}
              onSave={(p) => run("changePassword", p)}
              title="Parolayı değiştir ve oturumları kapat"
            >
              {(d, set) => (
                <div className="form-grid">
                  <Field label="Mevcut parola">
                    <input
                      type="password"
                      required
                      autoComplete="current-password"
                      value={d.currentPassword}
                      onChange={(e) => set({ currentPassword: e.target.value })}
                    />
                  </Field>
                  <Field label="Yeni parola">
                    <input
                      type="password"
                      required
                      minLength={12}
                      maxLength={128}
                      autoComplete="new-password"
                      value={d.password}
                      onChange={(e) => set({ password: e.target.value })}
                    />
                  </Field>
                </div>
              )}
            </SettingsForm>
          </>
        )}
        {tab === "devices" && (
          <>
            <Table
              headers={["Cihaz", "Şube", "Amaç", "Bağlantı", "Port", "İşlem"]}
            >
              {db.devices.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td>{db.branches[0]?.name}</td>
                  <td>
                    {
                      { access: "Üye", attendance: "Personel", mixed: "Karma" }[
                        row.purpose
                      ]
                    }
                  </td>
                  <td>
                    {row.simulated
                      ? "Simülasyon"
                      : !row.enabled
                        ? "Devre dışı"
                        : row.lastSeen &&
                            Date.now() - new Date(row.lastSeen) < 60000
                          ? "Çevrimiçi"
                          : "Çevrimdışı"}
                  </td>
                  <td>{row.telemetry?.port || "Veri yok"}</td>
                  <td>
                    <Button icon={Pencil} onClick={() => setDeviceEdit(row)}>
                      Adı düzenle
                    </Button>
                    <Button
                      icon={ArrowUpRight}
                      onClick={() => navigate("devices", null, row.id)}
                    >
                      Cihazı yönet
                    </Button>
                  </td>
                </tr>
              ))}
            </Table>
            <p className="member-note">
              COM portu cihazın bağlı olduğu bilgisayardaki USB Bridge
              yapılandırmasından gelir; web panelinden değiştirilmez. Hata
              uyarıları Bildirim Tercihleri bölümündedir.
            </p>
          </>
        )}
        {tab === "notifications" && (
          <SettingsForm
            initial={settings.notifications}
            onSave={(p) => run("saveNotificationPreferences", p)}
          >
            {(d, set) => (
              <>
                <Field label="Üyelik bitişinden kaç gün önce">
                  <input
                    type="number"
                    min={0}
                    max={90}
                    required
                    value={d.membershipDays}
                    onChange={(e) =>
                      set({ membershipDays: Number(e.target.value) })
                    }
                  />
                </Field>
                <div className="settings-notice-preferences">
                  {Object.entries(noticeLabels).map(([key, label]) => (
                    <div key={key}>
                      <label className="check-field">
                        <input
                          type="checkbox"
                          checked={d.enabled[key]}
                          onChange={(e) =>
                            set({
                              enabled: {
                                ...d.enabled,
                                [key]: e.target.checked,
                              },
                            })
                          }
                        />
                        {label}
                      </label>
                      <div className="button-group">
                        {(key === "membership"
                          ? ["admin", "staff"]
                          : ["class", "shift"].includes(key)
                            ? ["admin", "staff", "trainer"]
                            : ["admin"]
                        ).map((role) => (
                          <label className="check-field" key={role}>
                            <input
                              type="checkbox"
                              aria-label={`${label}: ${roles[role]}`}
                              checked={d.roles[key].includes(role)}
                              onChange={(e) =>
                                set({
                                  roles: {
                                    ...d.roles,
                                    [key]: e.target.checked
                                      ? [...d.roles[key], role]
                                      : d.roles[key].filter((r) => r !== role),
                                  },
                                })
                              }
                            />
                            {roles[role]}
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </SettingsForm>
        )}
        {tab === "data" && (
          <>
            <dl className="settings-summary">
              <dt>Veritabanı</dt>
              <dd>
                {settings.data.database === "connected"
                  ? "PostgreSQL bağlantısı doğrulandı"
                  : "Bağlantı hatası"}
              </dd>
              <dt>Son başarılı yedek</dt>
              <dd>
                {settings.data.lastSuccessfulAt
                  ? `${displayDate(settings.data.lastSuccessfulAt)} ${displayTime(settings.data.lastSuccessfulAt)}`
                  : "Doğrulanmış yedek yok"}
              </dd>
              <dt>Son durum</dt>
              <dd>
                {settings.data.latest?.status === "success"
                  ? "Başarılı"
                  : settings.data.latest?.status === "failed"
                    ? "Başarısız"
                    : "Veri yok"}
              </dd>
            </dl>
            {settings.data.latest?.error && (
              <p role="alert" className="form-error">
                {settings.data.latest.error}
              </p>
            )}
            <Table
              headers={[
                "Tarih",
                "Durum",
                "Arşiv kontrolü",
                "Ayrı ortam geri yükleme",
                "Hata",
              ]}
            >
              {settings.data.history.map((row) => (
                <tr key={row.id}>
                  <td>
                    {displayDate(row.at)} {displayTime(row.at)}
                  </td>
                  <td>{row.status === "success" ? "Başarılı" : "Başarısız"}</td>
                  <td>{row.verified ? "Doğrulandı" : "Doğrulanmadı"}</td>
                  <td>{row.restoreVerified ? "Doğrulandı" : "Yapılmadı"}</td>
                  <td>{row.error || "—"}</td>
                </tr>
              ))}
            </Table>
            {!settings.data.history.length && (
              <Empty>Yedek geçmişi bulunamadı.</Empty>
            )}
          </>
        )}
      </div>
      {deviceEdit && (
        <Dialog title="Cihaz adını düzenle" onClose={() => setDeviceEdit(null)}>
          <SettingsForm
            initial={{ id: deviceEdit.id, name: deviceEdit.name }}
            onSave={async (p) => {
              const result = await run("saveDeviceName", p);
              if (result?.ok) setDeviceEdit(null);
              return result;
            }}
          >
            {(d, set) => (
              <Field label="Cihaz adı">
                <input
                  required
                  maxLength={120}
                  value={d.name}
                  onChange={(e) => set({ name: e.target.value })}
                />
              </Field>
            )}
          </SettingsForm>
        </Dialog>
      )}
      {account && (
        <Dialog
          title={
            account.operation === "resetPassword"
              ? "Yetkili parola sıfırlama"
              : "Kullanıcı hesabı"
          }
          onClose={() => setAccount(null)}
        >
          <SettingsForm
            initial={accountForm}
            onSave={async (p) => {
              const result = await run("manageAccount", p);
              if (result?.ok) setAccount(null);
              return result;
            }}
            title="Hesap değişikliğini onayla"
          >
            {(d, set) => (
              <>
                <strong>
                  {account.row.name} · {account.row.email}
                </strong>
                {account.operation === "resetPassword" ? (
                  <Field label="Yeni parola">
                    <input
                      type="password"
                      required
                      minLength={12}
                      maxLength={128}
                      autoComplete="new-password"
                      value={d.password}
                      onChange={(e) => set({ password: e.target.value })}
                    />
                  </Field>
                ) : (
                  <>
                    <Field label="Kullanıcı rolü">
                      <select
                        value={d.role}
                        onChange={(e) => set({ role: e.target.value })}
                      >
                        {Object.entries(roles).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <label className="check-field">
                      <input
                        type="checkbox"
                        checked={d.active}
                        onChange={(e) => set({ active: e.target.checked })}
                      />
                      Hesap aktif; kapatıldığında giriş kilitlenir
                    </label>
                  </>
                )}
                <Field label="İşlem gerekçesi">
                  <textarea
                    required
                    minLength={3}
                    maxLength={600}
                    value={d.reason}
                    onChange={(e) => set({ reason: e.target.value })}
                  />
                </Field>
              </>
            )}
          </SettingsForm>
        </Dialog>
      )}
    </section>
  );
}
