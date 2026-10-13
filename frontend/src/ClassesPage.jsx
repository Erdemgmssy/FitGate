import React, { useState, useEffect, useRef } from "react";
import {
  Plus,
  Pencil,
  Ban,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Check,
  Clock,
  Bell,
  Users,
  Save,
  History,
} from "lucide-react";
import {
  Button,
  IconButton,
  Field,
  Dialog,
  Table,
  Badge,
  Empty,
  Metric,
} from "./ui";
import { money, displayDate, displayTime } from "./attendance.mjs";
import {
  classStates,
  attendanceStates,
  turkeyDay,
  shiftPeriod,
  calendarDays,
  classState,
  classOccupancy,
  filteredClasses,
  localClassTime,
} from "./class-rules.mjs";

export function ClassesPage({ db, run, isAdmin, selectedClassId }) {
  const [day, setDay] = useState(turkeyDay()),
    [mode, setMode] = useState("week"),
    [filter, setFilter] = useState({ trainer: "", kind: "", room: "" }),
    [dialog, setDialog] = useState(null),
    [selectedId, setSelected] = useState(null),
    [historyMember, setHistoryMember] = useState(null),
    [now, setNow] = useState(new Date());
  useEffect(()=>{if(!selectedClassId)return;const cls=db.classes.find(c=>c.id===selectedClassId);if(cls){setSelected(cls.id);setDay(turkeyDay(new Date(cls.at)));setMode('day');}},[selectedClassId]);
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(id);
  }, []);
  const rights = db.classPermissions || {
    manage: isAdmin,
    book: true,
    attendance: true,
  };
  const classes = filteredClasses(db.classes, filter),
    days = calendarDays(day, mode),
    selected = db.classes.find((c) => c.id === selectedId),
    bookings = db.bookings.filter((b) => b.classId === selectedId);
  const upcoming = classes
    .filter((c) => classState(c, now) === "planned")
    .slice(0, 10);
  const today = turkeyDay(now),
    active = db.classes.filter(
      (c) =>
        turkeyDay(c.at) === today &&
        !["cancelled", "notheld"].includes(classState(c, now)),
    );
  const seats = active.reduce(
      (sum, c) => sum + classOccupancy(c.id, db.bookings),
      0,
    ),
    capacity = active.reduce((sum, c) => sum + c.capacity, 0);
  const action = async (type, payload) => {
    const result = await run(type, payload);
    if (result?.ok) {
      setDialog(null);
      if (type === "saveClass" && result.result?.id)
        setSelected(result.result.id);
    }
    return result;
  };
  return (
    <section className="page-grid lessons-page">
      <div className="metrics-grid">
        <Metric
          label="Bugünkü dersler"
          value={active.length}
          icon={CalendarDays}
        />
        <Metric
          label="Rezervasyonlar"
          value={db.bookings.filter((b) => b.status === "booked").length}
          icon={Users}
        />
        <Metric
          label="Bekleme listesi"
          value={db.bookings.filter((b) => b.status === "waiting").length}
          icon={Clock}
        />
        <Metric
          label="Bugünkü doluluk"
          value={capacity ? `${Math.round((seats / capacity) * 100)}%` : "—"}
          icon={Check}
        />
      </div>
      <div className="filter-bar">
        <Button
          icon={History}
          onClick={() => setHistoryMember(db.members[0]?.id || "")}
        >
          Rezervasyon geçmişi
        </Button>
        <Field label="Antrenör">
          <select
            value={filter.trainer}
            onChange={(e) => setFilter({ ...filter, trainer: e.target.value })}
          >
            <option value="">Tümü</option>
            {[
              ...new Map(
                db.classes
                  .filter((c) => c.trainerId)
                  .map((c) => [c.trainerId, c.trainer]),
              ).entries(),
            ].map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ders türü">
          <select
            value={filter.kind}
            onChange={(e) => setFilter({ ...filter, kind: e.target.value })}
          >
            <option value="">Tümü</option>
            <option value="group">Grup dersi</option>
            <option value="private">Özel ders</option>
          </select>
        </Field>
        <Field label="Salon / stüdyo">
          <select
            value={filter.room}
            onChange={(e) => setFilter({ ...filter, room: e.target.value })}
          >
            <option value="">Tümü</option>
            {[...new Set(db.classes.map((c) => c.room))].map((room) => (
              <option key={room}>{room}</option>
            ))}
          </select>
        </Field>
        {rights.book && (
          <Button icon={Bell} onClick={() => run("classReminders", {})}>
            Hatırlatmaları oluştur
          </Button>
        )}
        {rights.manage && (
          <Button
            icon={Plus}
            tone="primary"
            onClick={() => setDialog({ type: "saveClass" })}
          >
            Ders oluştur
          </Button>
        )}
        {rights.manage && (
          <Button
            icon={Plus}
            onClick={() => setDialog({ type: "saveClass", kind: "private" })}
          >
            Özel ders oluştur
          </Button>
        )}
      </div>
      <div className="lesson-calendar-bar">
        <div className="button-group">
          <IconButton
            label="Önceki dönem"
            icon={ChevronLeft}
            onClick={() => setDay(shiftPeriod(day, mode, -1))}
          />
          <Field label="Takvim tarihi">
            <input
              type="date"
              value={day}
              onChange={(e) => e.target.value && setDay(e.target.value)}
            />
          </Field>
          <IconButton
            label="Sonraki dönem"
            icon={ChevronRight}
            onClick={() => setDay(shiftPeriod(day, mode, 1))}
          />
          <Button onClick={() => setDay(today)}>Bugün</Button>
        </div>
        <div className="segmented" role="group" aria-label="Takvim görünümü">
          {[
            ["day", "Gün"],
            ["week", "Hafta"],
            ["month", "Ay"],
          ].map(([id, label]) => (
            <Button
              key={id}
              tone={mode === id ? "primary" : "default"}
              onClick={() => setMode(id)}
              aria-pressed={mode === id}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>
      <div className={`lesson-calendar lesson-view-${mode}`}>
        {days.map((date) => (
          <div
            className={`lesson-day ${date === today ? "is-today" : ""} ${mode === "month" && !date.startsWith(day.slice(0, 7)) ? "muted-day" : ""}`}
            key={date}
          >
            <div className="lesson-day-heading">
              <strong>
                {new Date(date + "T12:00:00Z").toLocaleDateString("tr-TR", {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                  timeZone: "Europe/Istanbul",
                })}
              </strong>
            </div>
            {classes
              .filter((c) => turkeyDay(c.at) === date)
              .map((c) => (
                <button
                  className={`lesson-event ${classState(c, now)}`}
                  key={c.id}
                  onClick={() => setSelected(c.id)}
                  aria-label={`${c.name} ${displayTime(c.at)} detayları`}
                >
                  <strong>
                    {displayTime(c.at)} · {c.name}
                  </strong>
                  <span>{c.trainer}</span>
                  <small>
                    {classStates[classState(c, now)]} ·{" "}
                    {classOccupancy(c.id, db.bookings)}/{c.capacity}
                  </small>
                </button>
              ))}
          </div>
        ))}
      </div>
      {!classes.length && <Empty>Henüz ders planlanmadı.</Empty>}
      <div className="section-header">
        <h2>Yaklaşan dersler</h2>
        <span>{upcoming.length} ders</span>
      </div>
      <Table
        headers={["Ders", "Antrenör / salon", "Tarih", "Kontenjan", "İşlem"]}
      >
        {upcoming.map((c) => (
          <tr key={c.id}>
            <td>
              <strong>{c.name}</strong>
              <small className="cell-note">
                {c.kind === "private" ? "Özel ders" : "Grup dersi"}
                {c.seriesId ? " · Haftalık seri" : ""}
              </small>
            </td>
            <td>
              {c.trainer}
              <small className="cell-note">{c.room}</small>
            </td>
            <td>
              {displayDate(c.at)} · {displayTime(c.at)}
            </td>
            <td>
              {classOccupancy(c.id, db.bookings)} / {c.capacity}
            </td>
            <td>
              <Button onClick={() => setSelected(c.id)}>Detaylar</Button>
            </td>
          </tr>
        ))}
      </Table>
      {!upcoming.length && <Empty>Yaklaşan ders yok.</Empty>}
      {selected && (
        <>
          <div className="section-header">
            <div>
              <h2>{selected.name} / Katılımcılar</h2>
              <p>
                {selected.trainer} · {selected.room} ·{" "}
                {displayDate(selected.at)} {displayTime(selected.at)} ·{" "}
                {classStates[classState(selected, now)]}
              </p>
            </div>
            <div className="button-group">
              {rights.book && classState(selected, now) === "planned" && (
                <Button
                  icon={Plus}
                  tone="primary"
                  onClick={() =>
                    setDialog({ type: "book", classId: selected.id })
                  }
                >
                  Rezervasyon ekle
                </Button>
              )}
              {rights.manage && classState(selected, now) === "planned" && (
                <>
                  <IconButton
                    label="Dersi düzenle"
                    icon={Pencil}
                    onClick={() =>
                      setDialog({ type: "saveClass", item: selected })
                    }
                  />
                  <IconButton
                    label="Dersi iptal et"
                    icon={Ban}
                    onClick={() =>
                      setDialog({ type: "cancelClass", id: selected.id })
                    }
                  />
                </>
              )}
              {rights.manage &&
                ["ongoing", "completed"].includes(
                  classState(selected, now),
                ) && (
                  <Button
                    tone="danger"
                    onClick={() =>
                      setDialog({ type: "classOutcome", id: selected.id })
                    }
                  >
                    Yapılmadı
                  </Button>
                )}
            </div>
          </div>
          <p>{selected.description}</p>
          <div className="lesson-terms">
            <span>
              {selected.requireMembership
                ? "Üyelik gerekli"
                : "Üyelik zorunlu değil"}
            </span>
            <span>
              {selected.requireLesson
                ? "Ders hakkı gerekli"
                : "Ders hakkı tüketilmez"}
            </span>
            <span>İptal sınırı: {selected.cancelMinutes} dk</span>
            <span>Ücret: {money((selected.priceCents || 0) / 100)}</span>
            <span>
              Geç iptal:{" "}
              {selected.lateCancelConsumes ? "Hak tüketir" : "Hak iade"}
            </span>
            <span>
              Gelmedi: {selected.noShowConsumes ? "Hak tüketir" : "Hak iade"}
            </span>
          </div>
          <Table
            headers={[
              "Üye",
              "Katılım",
              "Ders hakkı",
              "Satış / ücret",
              "Açıklama",
              "İşlem",
            ]}
          >
            {bookings.map((b) => (
              <tr key={b.id}>
                <td>
                  <button
                    className="text-button"
                    onClick={() => setHistoryMember(b.memberId)}
                  >
                    {db.members.find((m) => m.id === b.memberId)?.name || "Üye"}
                  </button>
                </td>
                <td>
                  <Badge status={b.status}>{attendanceStates[b.status]}</Badge>
                </td>
                <td>
                  {{
                    none: "—",
                    reserved: "Ayrıldı",
                    consumed: "Kullanıldı",
                    released: "İade edildi",
                  }[b.rightState] || "—"}
                </td>
                <td>
                  {b.invoiceId
                    ? db.invoices.find((i) => i.id === b.invoiceId)?.number
                    : "—"}
                  {b.terms && (
                    <small className="cell-note">
                      {money((b.terms.priceCents || 0) / 100)}
                    </small>
                  )}
                </td>
                <td>{b.reason || "—"}</td>
                <td>
                  {(["booked", "attended", "late", "absent"].includes(
                    b.status,
                  ) ||
                    (b.status === "excused" && b.attendanceRecorded)) &&
                    rights.attendance &&
                    ["ongoing", "completed"].includes(
                      classState(selected, now),
                    ) && (
                      <Button
                        icon={Check}
                        onClick={() =>
                          setDialog({
                            type: "bookingStatus",
                            id: b.id,
                            attendance: true,
                            status: b.status,
                          })
                        }
                      >
                        Yoklama
                      </Button>
                    )}
                  {["booked", "waiting"].includes(b.status) &&
                    rights.book &&
                    classState(selected, now) === "planned" && (
                      <IconButton
                        label="Rezervasyonu iptal et"
                        icon={Ban}
                        onClick={() =>
                          setDialog({ type: "bookingStatus", id: b.id })
                        }
                      />
                    )}
                </td>
              </tr>
            ))}
          </Table>
          {!bookings.length && <Empty>Bu dersin rezervasyonu yok.</Empty>}
        </>
      )}
      {dialog?.type === "saveClass" && (
        <ClassForm
          db={db}
          item={dialog.item}
          kind={dialog.kind}
          onClose={() => setDialog(null)}
          run={action}
        />
      )}
      {historyMember !== null && (
        <Dialog
          title="Üye rezervasyon geçmişi"
          onClose={() => setHistoryMember(null)}
        >
          <Field label="Üye">
            <select
              value={historyMember}
              onChange={(e) => setHistoryMember(e.target.value)}
            >
              <option value="">Üye seç</option>
              {db.members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} · {m.number}
                </option>
              ))}
            </select>
          </Field>
          <Table headers={["Ders", "Tarih", "Katılım", "Ders hakkı"]}>
            {db.bookings
              .filter((b) => b.memberId === historyMember)
              .sort((a, b) => new Date(b.at) - new Date(a.at))
              .map((b) => {
                const c = db.classes.find((c) => c.id === b.classId);
                return (
                  <tr key={b.id}>
                    <td>{c?.name || b.terms?.className}</td>
                    <td>
                      {c ? `${displayDate(c.at)} ${displayTime(c.at)}` : "—"}
                    </td>
                    <td>{attendanceStates[b.status]}</td>
                    <td>
                      {{
                        reserved: "Ayrıldı",
                        consumed: "Kullanıldı",
                        released: "İade edildi",
                        none: "—",
                      }[b.rightState] || "—"}
                    </td>
                  </tr>
                );
              })}
          </Table>
          {!db.bookings.some((b) => b.memberId === historyMember) && (
            <Empty>Rezervasyon geçmişi yok.</Empty>
          )}
        </Dialog>
      )}
      {dialog && dialog.type !== "saveClass" && (
        <BookingDialog
          db={db}
          dialog={dialog}
          run={action}
          onClose={() => setDialog(null)}
        />
      )}
    </section>
  );
}

function ClassForm({ db, item, kind, onClose, run }) {
  const [form, setForm] = useState({
    name: "",
    description: "",
    kind: kind || "group",
    trainerId: "",
    room: "",
    at: "",
    duration: 60,
    capacity: kind === "private" ? 1 : 10,
    price: "0",
    bookingMinutes: 0,
    cancelMinutes: 120,
    requireMembership: true,
    requireLesson: false,
    lateCancelConsumes: true,
    noShowConsumes: true,
    repeatCount: 1,
    scope: "single",
    ...item,
    ...(item
      ? { at: localClassTime(item.at), price: String(item.priceCents / 100) }
      : {}),
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    lock = useRef(false),
    set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  return (
    <Dialog
      title={item ? "Dersi düzenle" : "Ders / randevu oluştur"}
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (lock.current) return;
          lock.current = true;
          setBusy(true);
          setError("");
          try {
            const result = await run("saveClass", {
              ...form,
              at: form.at + ":00+03:00",
              capacity: form.kind === "private" ? 1 : form.capacity,
            });
            if (!result?.ok) setError(result?.message || "Ders kaydedilemedi.");
          } catch (err) {
            setError(err.message);
          } finally {
            lock.current = false;
            setBusy(false);
          }
        }}
      >
        <fieldset className="finance-fields" disabled={busy}>
          <div className="form-grid">
            <Field label="Ders adı">
              <input
                required
                maxLength={120}
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </Field>
            <Field label="Ders türü">
              <select
                value={form.kind}
                onChange={(e) => {
                  set("kind", e.target.value);
                  if (e.target.value === "private") set("capacity", 1);
                }}
              >
                <option value="group">Grup dersi</option>
                <option value="private">Özel ders (birebir)</option>
              </select>
            </Field>
            <Field label="Antrenör">
              <select
                required
                value={form.trainerId || ""}
                onChange={(e) => set("trainerId", e.target.value)}
              >
                <option value="">Antrenör seç</option>
                {db.employees
                  .filter((e) => e.active && e.role === "trainer")
                  .map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="Salon / stüdyo">
              <input
                required
                maxLength={100}
                value={form.room}
                onChange={(e) => set("room", e.target.value)}
              />
            </Field>
            <Field label="Başlangıç (Türkiye saati)">
              <input
                type="datetime-local"
                required
                value={form.at}
                onChange={(e) => set("at", e.target.value)}
              />
            </Field>
            <Field label="Bitiş (Türkiye saati)">
              <input
                type="datetime-local"
                readOnly
                value={
                  form.at && Number(form.duration) > 0
                    ? localClassTime(
                        new Date(
                          new Date(form.at + ":00+03:00").getTime() +
                            Number(form.duration) * 60000,
                        ),
                      )
                    : ""
                }
              />
            </Field>
            {[
              ["duration", "Süre (dakika)", 1, 1440],
              ...(form.kind === "private"
                ? []
                : [["capacity", "Kontenjan", 1, 10000]]),
              ["price", "Ders ücreti (TL)", 0, 9999999999],
              ["bookingMinutes", "Rezervasyon kapanışı (dk önce)", 0, 10080],
              ["cancelMinutes", "Ücretsiz iptal sınırı (dk önce)", 0, 10080],
            ].map(([key, label, min, max]) => (
              <Field key={key} label={label}>
                <input
                  required
                  type="number"
                  min={min}
                  max={max}
                  step={key === "price" ? ".01" : "1"}
                  value={form[key]}
                  onChange={(e) => set(key, e.target.value)}
                />
              </Field>
            ))}
            {!item && (
              <Field label="Haftalık tekrar sayısı">
                <input
                  type="number"
                  min="1"
                  max="52"
                  value={form.repeatCount}
                  onChange={(e) => set("repeatCount", e.target.value)}
                />
              </Field>
            )}
            {item?.seriesId && (
              <Field label="Düzenleme kapsamı">
                <select
                  value={form.scope}
                  onChange={(e) => set("scope", e.target.value)}
                >
                  <option value="single">Yalnızca bu ders</option>
                  <option value="future">Bu ve sonraki dersler</option>
                </select>
              </Field>
            )}
            <Field label="Açıklama">
              <textarea
                maxLength={600}
                value={form.description}
                onChange={(e) => set("description", e.target.value)}
              />
            </Field>
          </div>
          <div className="lesson-checks">
            {[
              ["requireMembership", "Geçerli üyelik gerekli"],
              ["requireLesson", "Paketten ders hakkı ayır"],
              ["lateCancelConsumes", "Geç iptal ders hakkını tüketir"],
              ["noShowConsumes", "Gelmedi ders hakkını tüketir"],
            ].map(([key, label]) => (
              <label key={key}>
                <input
                  type="checkbox"
                  checked={form[key]}
                  onChange={(e) => {
                    set(key, e.target.checked);
                    if (key === "requireLesson" && e.target.checked)
                      set("requireMembership", true);
                    if (key === "requireMembership" && !e.target.checked)
                      set("requireLesson", false);
                  }}
                />
                {label}
              </label>
            ))}
          </div>
          {error && (
            <p role="alert" className="error-text">
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

function BookingDialog({ db, dialog, run, onClose }) {
  const [search, setSearch] = useState(""),
    [memberId, setMember] = useState(""),
    [status, setStatus] = useState(
      dialog.attendance ? "attended" : "cancelled",
    ),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    lock = useRef(false);
  const booking = dialog.type === "book";
  const members = db.members.filter(
    (m) =>
      m.active &&
      (m.name + " " + m.number + " " + m.phone)
        .toLocaleLowerCase("tr")
        .includes(search.toLocaleLowerCase("tr")),
  );
  return (
    <Dialog
      title={
        booking
          ? "Rezervasyon ekle"
          : dialog.attendance
            ? "Katılım / yoklama"
            : dialog.type === "bookingStatus"
              ? "Rezervasyonu iptal et"
              : "Dersi kapat"
      }
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (lock.current) return;
          lock.current = true;
          setBusy(true);
          setError("");
          try {
            const result = await run(dialog.type, {
              id: dialog.id,
              classId: dialog.classId,
              memberId,
              status,
              reason,
            });
            if (!result?.ok)
              setError(result?.message || "İşlem kaydedilemedi.");
          } catch (err) {
            setError(err.message);
          } finally {
            lock.current = false;
            setBusy(false);
          }
        }}
      >
        <fieldset className="finance-fields" disabled={busy}>
          {booking ? (
            <>
              <Field label="Üye ara">
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </Field>
              <Field label="Üye">
                <select
                  required
                  value={memberId}
                  onChange={(e) => setMember(e.target.value)}
                >
                  <option value="">Üye seç</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} · {m.number}
                    </option>
                  ))}
                </select>
              </Field>
            </>
          ) : (
            <>
              {dialog.type === "bookingStatus" && (
                <Field label="Katılım durumu">
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    {(dialog.attendance
                      ? ["booked", "attended", "late", "absent", "excused"]
                      : ["cancelled", "excused"]
                    ).map((s) => (
                      <option key={s} value={s}>
                        {attendanceStates[s]}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              <Field label="İşlem gerekçesi">
                <textarea
                  required
                  maxLength={1500}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
            </>
          )}
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <Button type="button" onClick={onClose}>
              Vazgeç
            </Button>
            <Button icon={Check} type="submit" tone="primary" disabled={busy}>
              {booking ? "Rezervasyon oluştur" : "Onayla"}
            </Button>
          </div>
        </fieldset>
      </form>
    </Dialog>
  );
}
