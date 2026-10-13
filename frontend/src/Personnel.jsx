import React, { useEffect, useState } from "react";
import {
  Users,
  Clock,
  CalendarDays,
  UserPlus,
  Save,
  Pencil,
  Ban,
  IdCard,
  Play,
  Pause,
  LogOut,
  Check,
  X,
  Settings,
  Download,
  Send,
} from "lucide-react";
import {
  Button,
  IconButton,
  Table,
  Field,
  Dialog,
  Empty,
  Metric,
  Avatar,
  Badge,
  exportCsv,
} from "./ui";
import { durationLabel } from "./attendance.mjs";
import {
  roles,
  leaveStatuses,
  scheduleStatuses,
  trDay,
  trDate,
  trTime,
  inputTime,
  isoTime,
  plusDay,
  bounds,
  worked,
  scheduleWindow,
  calendarDays,
} from "./personnel-rules.mjs";

export function EmployeesPage({ db, user, run, isAdmin, selectedEmployeeId, onReports }) {
  const data = db.personnel || {
    plannedShifts: [],
    shiftBreaks: [],
    leaveRequests: [],
    leaveTypes: [],
    employeeCards: [],
    attendanceEvents: [],
    shiftMetrics: [],
    scheduleStatus: [],
    accounts: [],
    rolePolicies: [],
    permissions: {},
    rules: {},
  };
  const [tab, setTab] = useState(isAdmin ? "employees" : "attendance"),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState("all"),
    [role, setRole] = useState("all");
  const [employeeId, setEmployeeId] = useState("all"),
    [selected, setSelected] = useState(null),
    [modal, setModal] = useState(null),
    [now, setNow] = useState(new Date());
  const [day, setDay] = useState(trDay()),
    [period, setPeriod] = useState("month"),
    [calendarMode, setCalendarMode] = useState("week"),
    [includeSimulation, setIncludeSimulation] = useState(false),
    [scanUid, setScanUid] = useState(""),
    [scanResult, setScanResult] = useState(null),
    [busy, setBusy] = useState(false);
  useEffect(()=>{if(!selectedEmployeeId)return;const item=db.employees.find(e=>e.id===selectedEmployeeId);if(item){setSelected(item.id);setEmployeeId(item.id);if(isAdmin){setTab('employees');setQuery(item.name);}else{setTab('schedule');const next=data.plannedShifts.filter(s=>s.employeeId===item.id&&!s.cancelled&&s.kind==='work'&&new Date(s.start)>new Date()).sort((a,b)=>new Date(a.start)-new Date(b.start))[0];if(next){setDay(trDay(new Date(next.start)));setCalendarMode('day');}}}},[selectedEmployeeId]);
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 15000);
    return () => clearInterval(timer);
  }, []);
  const own = db.employees.find((row) => row.id === data.ownEmployeeId),
    employee = db.employees.find((row) => row.id === selected);
  const realShifts = db.shifts.filter((row) => !row.simulated),
    open =
      own && realShifts.find((row) => row.employeeId === own.id && !row.exit),
    metric = open && data.shiftMetrics.find((row) => row.id === open.id);
  const openPersonnelVisit =
    own &&
    (data.personnelVisits || []).find(
      (row) => row.employeeId === own.id && !row.exit,
    );
  const physicallyInside = Boolean(openPersonnelVisit);
  const pendingIntent =
    own?.passageIntent?.expiresAt && new Date(own.passageIntent.expiresAt) > now
      ? own.passageIntent.action
      : null;
  const plans = data.plannedShifts.filter((row) => !row.cancelled),
    today = trDay(now),
    todayPlans = plans.filter(
      (row) =>
        row.employeeId === own?.id &&
        row.kind === "work" &&
        new Date(row.start) < bounds(today).end &&
        new Date(row.end) > bounds(today).start,
    );
  const filtered = db.employees.filter(
    (row) =>
      (status === "all" || row.active === (status === "active")) &&
      (role === "all" || row.role === role) &&
      `${row.name} ${row.phone} ${row.email} ${row.jobTitle}`
        .toLocaleLowerCase("tr")
        .includes(query.toLocaleLowerCase("tr")),
  );
  const range = bounds(day, period);
  const rows = db.shifts
    .filter(
      (row) =>
        (employeeId === "all" || row.employeeId === employeeId) &&
        (includeSimulation || !row.simulated) &&
        new Date(row.entry) < range.end &&
        new Date(row.exit || now) >= range.start,
    )
    .sort((a, b) => b.entry.localeCompare(a.entry));
  const calendar = calendarDays(day, calendarMode);
  const names = (id) => db.employees.find((row) => row.id === id)?.name || "-";
  const times = (row) =>
    `${trDate(row.start)} ${trTime(row.start)} - ${trDate(row.end)} ${trTime(row.end)}`;
  const tabs = isAdmin
    ? [
        ["employees", "Personel listesi"],
        ["schedule", "Vardiyalar"],
        ["attendance", "Mesai takibi"],
        ["leave", "İzin yönetimi"],
        ["rules", "Kurallar ve yetkiler"],
      ]
    : [
        ["attendance", "Mesai geçmişim"],
        ["schedule", "Vardiyalarım"],
        ["leave", "İzinlerim"],
      ];
  async function perform(action, payload) {
    if (busy) return;
    setBusy(true);
    try {
      const result = await run(action, payload);
      setNow(new Date());
      if (result?.ok && result.result?.approved === false)
        return { ...result, ok: false, message: result.result.message };
      return result;
    } finally {
      setBusy(false);
    }
  }
  const total = (mode) =>
    own
      ? durationLabel(
          worked(db.shifts, data.shiftBreaks, own.id, bounds(today, mode), now),
        )
      : durationLabel(0);
  return (
    <section className="personnel-page">
      <div className="stat-row">
        {isAdmin ? (
          <>
            <Metric
              icon={Users}
              label="Toplam personel"
              value={db.employees.length}
            />
            <Metric
              icon={Users}
              label="Aktif personel"
              value={db.employees.filter((row) => row.active).length}
            />
            <Metric
              icon={Clock}
              label="Şu an mesaide"
              value={realShifts.filter((row) => !row.exit).length}
            />
            <Metric
              icon={CalendarDays}
              label="Bekleyen izin"
              value={
                data.leaveRequests.filter((row) => row.status === "pending")
                  .length
              }
            />
          </>
        ) : (
          <>
            <Metric
              icon={Clock}
              label="Mesai durumum"
              value={
                open
                  ? metric?.onBreak
                    ? "Mola"
                    : "Mesai başladı"
                  : "Başlamadı"
              }
            />
            <Metric icon={Clock} label="Bugünkü çalışma" value={total("day")} />
            <Metric
              icon={Clock}
              label="Haftalık çalışma"
              value={total("week")}
            />
            <Metric
              icon={CalendarDays}
              label="Bugünkü vardiyam"
              value={
                todayPlans.length
                  ? todayPlans
                      .map((row) => `${trTime(row.start)} - ${trTime(row.end)}`)
                      .join(" / ")
                  : "Vardiya yok"
              }
            />
          </>
        )}
      </div>
      {!isAdmin && !own && (
        <p className="form-error" role="alert">
          Bu hesap henüz bir personel kaydına bağlı değil. Yönetici personel
          detayından mevcut giriş hesabını eşleştirmeli.
        </p>
      )}
      {!isAdmin&&onReports&&<div className="button-group"><Button icon={Download} onClick={onReports}>Kendi mesai raporum</Button></div>}
      <div className="tabs" role="tablist" aria-label="Personel ve mesai">
        {tabs.map(([id, label]) => (
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
      {tab === "employees" && isAdmin && (
        <>
          <div className="filter-bar">
            <Field label="Personel ara">
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </Field>
            <Field label="Durum">
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="all">Tüm durumlar</option>
                <option value="active">Aktif</option>
                <option value="inactive">Pasif</option>
              </select>
            </Field>
            <Field label="Rol">
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="all">Tüm roller</option>
                {Object.entries(roles).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Button
              icon={UserPlus}
              tone="primary"
              onClick={() => setModal({ kind: "employee" })}
            >
              Yeni personel
            </Button>
          </div>
          <Table
            headers={[
              "Personel",
              "Görev / Rol",
              "İletişim",
              "Şube / Başlangıç",
              "Bugünkü mesai",
              "Durum",
              "İşlem",
            ]}
          >
            {filtered.map((row) => (
              <tr key={row.id}>
                <td>
                  <button
                    className="member-link"
                    onClick={() => setSelected(row.id)}
                  >
                    <Avatar member={row} size="small" />
                    <strong>{row.name}</strong>
                  </button>
                </td>
                <td>
                  {row.jobTitle || "-"}
                  <small>{roles[row.role]}</small>
                </td>
                <td>
                  {row.phone || "-"}
                  <small>{row.email || "-"}</small>
                </td>
                <td>
                  {db.branches[0]?.name}
                  <small>{trDate(row.startDate)}</small>
                </td>
                <td>
                  {durationLabel(
                    worked(
                      db.shifts,
                      data.shiftBreaks,
                      row.id,
                      bounds(today),
                      now,
                    ),
                  )}
                  <small>
                    {realShifts.some((s) => s.employeeId === row.id && !s.exit)
                      ? "Mesaide"
                      : "Açık mesai yok"}
                  </small>
                </td>
                <td>
                  <Badge status={row.active ? "active" : "inactive"} />
                </td>
                <td>
                  <IconButton
                    icon={Pencil}
                    label={`Düzenle: ${row.name}`}
                    onClick={() => setModal({ kind: "employee", record: row })}
                  />
                </td>
              </tr>
            ))}
          </Table>
          {!filtered.length && <Empty>Personel bulunmuyor.</Empty>}
          {employee && (
            <section className="personnel-detail">
              <div className="panel-header">
                <h2>{employee.name}</h2>
                <Button
                  icon={Pencil}
                  onClick={() =>
                    setModal({ kind: "employee", record: employee })
                  }
                >
                  Düzenle
                </Button>
              </div>
              <dl className="detail-grid">
                <div>
                  <dt>Giriş hesabı</dt>
                  <dd>
                    {data.accounts.find((row) => row.id === employee.userId)
                      ?.email || "Hesap bağlı değil"}
                  </dd>
                </div>
                <div>
                  <dt>Çalışan tipi</dt>
                  <dd>{employee.type === "hourly" ? "Saatlik" : "Sabit"}</dd>
                </div>
                <div>
                  <dt>Mesai kartı</dt>
                  <dd>{employee.card || "Kart yok"}</dd>
                </div>
                <div>
                  <dt>İşe başlangıç</dt>
                  <dd>{trDate(employee.startDate)}</dd>
                </div>
              </dl>
              <div className="filter-bar">
                <Button
                  icon={IdCard}
                  onClick={() => setModal({ kind: "card", record: employee })}
                >
                  Mesai kartı tanımla
                </Button>
                <Button
                  icon={Clock}
                  onClick={() => {
                    setEmployeeId(employee.id);
                    setTab("attendance");
                  }}
                >
                  Mesai geçmişi
                </Button>
                <Button
                  icon={Ban}
                  tone={employee.active ? "danger" : "secondary"}
                  onClick={() =>
                    setModal({ kind: "employeeStatus", record: employee })
                  }
                >
                  {employee.active ? "Pasife al" : "Aktifleştir"}
                </Button>
              </div>
              <Table headers={["Kart UID", "Durum", "İşlem"]}>
                {data.employeeCards
                  .filter((row) => row.employeeId === employee.id)
                  .map((row) => (
                    <tr key={row.id}>
                      <td>{row.uid}</td>
                      <td>
                        <Badge status={row.status} />
                      </td>
                      <td>
                        {row.status === "active" && (
                          <IconButton
                            icon={Ban}
                            label={`Kartı iptal et: ${row.uid}`}
                            onClick={() =>
                              setModal({ kind: "cancelCard", record: row })
                            }
                          />
                        )}
                      </td>
                    </tr>
                  ))}
              </Table>
            </section>
          )}
        </>
      )}
      {tab === "attendance" && (
        <>
          <div className="filter-bar">
            <Field label="Tarih">
              <input
                type="date"
                required
                value={day}
                onChange={(e) => e.target.value && setDay(e.target.value)}
              />
            </Field>
            <Field label="Dönem">
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              >
                <option value="day">Günlük</option>
                <option value="week">Haftalık</option>
                <option value="month">Aylık</option>
                <option value="period15">15 - 15 çalışma</option>
              </select>
            </Field>
            {isAdmin && (
              <EmployeeSelect
                employees={db.employees}
                value={employeeId}
                onChange={setEmployeeId}
                all
              />
            )}
            <label className="check-field">
              <input
                type="checkbox"
                checked={includeSimulation}
                onChange={(e) => setIncludeSimulation(e.target.checked)}
              />
              Simülasyonları göster
            </label>
            <IconButton
              icon={Download}
              label="Mesai CSV indir"
              onClick={() =>
                exportCsv(
                  "personel-mesai",
                  [
                    "Personel",
                    "Giriş",
                    "Çıkış",
                    "Süre",
                    "Geç kalma (dk)",
                    "Fazla mesai (dk)",
                    "Kaynak",
                  ],
                  rows.map((row) => {
                    const stat = data.shiftMetrics.find((s) => s.id === row.id);
                    return [
                      names(row.employeeId),
                      `${trDate(row.entry)} ${trTime(row.entry)}`,
                      row.exit
                        ? `${trDate(row.exit)} ${trTime(row.exit)}`
                        : "Eksik çıkış",
                      durationLabel(
                        worked(
                          [row],
                          data.shiftBreaks,
                          row.employeeId,
                          range,
                          now,
                          true,
                        ),
                      ),
                      stat?.lateMinutes ?? "",
                      stat?.overtimeMinutes ?? "",
                      row.simulated ? "SİMÜLASYON" : row.source,
                    ];
                  }),
                )
              }
            />
            {isAdmin && (
              <Button
                icon={Pencil}
                onClick={() => setModal({ kind: "presence" })}
              >
                Geçişi düzelt
              </Button>
            )}
            {data.permissions.manualAttendance && (
              <Button
                icon={Clock}
                disabled={!isAdmin && !own}
                onClick={() => setModal({ kind: "manual" })}
              >
                Manuel mesai
              </Button>
            )}
          </div>
          {!isAdmin && own && (
            <section className="personnel-self-summary">
              <h3>Mesai giriş-çıkış</h3>
              <p>
                İlk giriş:{" "}
                {trTime(
                  realShifts
                    .filter(
                      (s) =>
                        s.employeeId === own.id && trDay(s.entry) === today,
                    )
                    .sort((a, b) => a.entry.localeCompare(b.entry))[0]?.entry,
                )}{" "}
                · Son çıkış:{" "}
                {trTime(
                  realShifts
                    .filter(
                      (s) =>
                        s.employeeId === own.id &&
                        s.exit &&
                        trDay(s.exit) === today,
                    )
                    .sort((a, b) => b.exit.localeCompare(a.exit))[0]?.exit,
                )}{" "}
                · Aylık çalışma: {total("month")}
              </p>
              {data.permissions.attendanceBreak &&
                !data.permissions.manualAttendance &&
                open &&
                open.source !== "device" && (
                  <Button
                    icon={metric?.onBreak ? Play : Pause}
                    disabled={busy}
                    onClick={() =>
                      perform("attendanceBreak", {
                        direction: metric?.onBreak ? "end" : "start",
                      })
                    }
                  >
                    {metric?.onBreak ? "Molayı bitir" : "Mola başlat"}
                  </Button>
                )}
              {data.permissions.manualAttendance && <div className="button-group">
                <Button icon={Play} disabled={busy || Boolean(open)} onClick={()=>setModal({kind:'manual', operation:'start'})}>Manuel Mesai Başlat</Button>
                <Button icon={Pause} disabled={busy || !open || metric?.onBreak || !data.permissions.attendanceBreak} onClick={()=>setModal({kind:'manual', operation:'break'})}>Manuel Molaya Çık</Button>
                <Button icon={Play} disabled={busy || !open || !metric?.onBreak || !data.permissions.attendanceBreak} onClick={()=>setModal({kind:'manual', operation:'resume'})}>Manuel Moladan Dön</Button>
                <Button icon={LogOut} disabled={busy || !open} onClick={()=>setModal({kind:'manual', operation:'finish'})}>Manuel Mesai Bitir</Button>
              </div>}
              <div className="button-group">
                {!open && openPersonnelVisit?.entryEventId && (
                  <Button
                    icon={Play}
                    disabled={busy}
                    onClick={() =>
                      perform("physicalAttendanceIntent", { intent: "start" })
                    }
                  >
                    Mesaiyi başlat
                  </Button>
                )}
                {open &&
                  physicallyInside &&
                  data.permissions.attendanceBreak &&
                  !metric?.onBreak && (
                    <Button
                      icon={Pause}
                      disabled={busy}
                      onClick={() =>
                        perform("physicalAttendanceIntent", { intent: "break" })
                      }
                    >
                      Molaya çık
                    </Button>
                  )}
                {open && physicallyInside && (
                  <Button
                    icon={Check}
                    disabled={busy}
                    onClick={() =>
                      perform("physicalAttendanceIntent", { intent: "finish" })
                    }
                  >
                    Mesaiyi Bitir
                  </Button>
                )}
                {pendingIntent && (
                  <Button
                    icon={X}
                    disabled={busy}
                    onClick={() =>
                      perform("physicalAttendanceIntent", { intent: "cancel" })
                    }
                  >
                    Seçimi iptal et
                  </Button>
                )}
              </div>
              {pendingIntent && (
                <p role="status">
                  {pendingIntent === "finish" ? "Mesai bitişi" : "Mola"}:
                  fiziksel çıkış bekleniyor
                </p>
              )}
              <p className="member-note">
                {physicallyInside
                  ? openPersonnelVisit.entryEventId
                    ? "Doğrulanmış personel girişi: içeride"
                    : "Yönetici düzeltmesi: içeride"
                  : "Açık fiziksel personel ziyareti yok"}
              </p>
            </section>
          )}
          {data.simulationEnabled && data.permissions.simulateAttendance && (
            <section className="personnel-simulation">
              <h3>Kontrollü mesai simülasyonu</h3>
              <form
                className="scan-form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const response = await perform("simulateAttendance", {
                    uid: scanUid,
                    direction: "auto",
                  });
                  setScanResult(
                    response?.ok
                      ? response.result
                      : { approved: false, message: response?.message },
                  );
                }}
              >
                <Field label="Simülasyon kart UID">
                  <input
                    value={scanUid}
                    onChange={(e) => setScanUid(e.target.value)}
                    required
                    maxLength={100}
                  />
                </Field>
                <Button icon={IdCard} type="submit" disabled={busy}>
                  Kart okumayı simüle et
                </Button>
              </form>
              {scanResult && (
                <p
                  role="status"
                  className={
                    scanResult.approved ? "success-message" : "form-error"
                  }
                >
                  {scanResult.message}
                </p>
              )}
              <p className="member-note">
                Simülasyon kayıtları gerçek çalışma toplamlarından ve
                devamsızlık hesabından hariçtir.
              </p>
            </section>
          )}
          <Table
            headers={[
              "Personel",
              "Tarih / Giriş",
              "Çıkış",
              "Çalışma",
              "Vardiya",
              "Geç kalma",
              "Fazla mesai",
              "Durum / Kaynak",
              "İşlem",
            ]}
          >
            {rows.map((row) => {
              const stat = data.shiftMetrics.find((s) => s.id === row.id),
                plan = plans.find((p) => p.id === stat?.plannedId);
              return (
                <tr key={row.id}>
                  <td>{names(row.employeeId)}</td>
                  <td>
                    {trDate(row.entry)}
                    <small>{trTime(row.entry)}</small>
                  </td>
                  <td>
                    {row.exit
                      ? `${trDate(row.exit)} ${trTime(row.exit)}`
                      : "Çıkış yok"}
                  </td>
                  <td>
                    {durationLabel(
                      worked(
                        [row],
                        data.shiftBreaks,
                        row.employeeId,
                        range,
                        now,
                        true,
                      ),
                    )}
                  </td>
                  <td>
                    {plan
                      ? `${trTime(plan.start)} - ${trTime(plan.end)}`
                      : "Vardiya yok"}
                  </td>
                  <td>
                    {stat?.lateMinutes == null ? "-" : `${stat.lateMinutes} dk`}
                  </td>
                  <td>
                    {stat?.overtimeMinutes == null
                      ? "-"
                      : `${stat.overtimeMinutes} dk`}
                  </td>
                  <td>
                    {stat?.missingExit
                      ? "Eksik çıkış"
                      : stat?.onBreak
                        ? "Molada"
                        : row.exit
                          ? "Tamamlandı"
                          : "Devam ediyor"}
                    <small>
                      {row.simulated
                        ? "SİMÜLASYON"
                        : row.source === "device"
                          ? "Doğrulanmış cihaz"
                          : ["manual", "MANUAL_PERSONNEL"].includes(row.source)
                            ? "Manuel"
                            : "Eski kayıt"}
                    </small>
                    {row.reason && <small>{row.reason}</small>}
                  </td>
                  <td>
                    {isAdmin && (
                      <div className="button-group">
                        <IconButton
                          icon={Pencil}
                          label="Mesai düzelt"
                          onClick={() =>
                            setModal({ kind: "correct", record: row })
                          }
                        />
                        {!row.exit && data.permissions.attendanceBreak && (
                          <IconButton
                            icon={stat?.onBreak ? Play : Pause}
                            label={
                              stat?.onBreak ? "Molayı bitir" : "Mola başlat"
                            }
                            disabled={busy}
                            onClick={() =>
                              perform("attendanceBreak", {
                                employeeId: row.employeeId,
                                direction: stat?.onBreak ? "end" : "start",
                              })
                            }
                          />
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </Table>
          {!rows.length && <Empty>Bu dönemde mesai kaydı bulunmuyor.</Empty>}
          <h3 className="section-title">Vardiya uyarıları</h3>
          <Table headers={["Personel", "Vardiya", "Durum"]}>
            {plans
              .filter(
                (p) =>
                  (employeeId === "all" || p.employeeId === employeeId) &&
                  new Date(p.start) < range.end &&
                  new Date(p.end) > range.start,
              )
              .map((p) => {
                const state = data.scheduleStatus.find(
                  (s) => s.id === p.id,
                )?.status;
                return (
                  <tr key={p.id}>
                    <td>{names(p.employeeId)}</td>
                    <td>{times(p)}</td>
                    <td>{scheduleStatuses[state]}</td>
                  </tr>
                );
              })}
          </Table>
          <h3 className="section-title">Son mesai olayları</h3>
          <Table headers={["Zaman", "Personel", "Sonuç", "Kaynak / Cihaz"]}>
            {data.attendanceEvents.slice(0, 20).map((row) => (
              <tr key={row.id}>
                <td>
                  {trDate(row.occurredAt)}
                  <small>{trTime(row.occurredAt)}</small>
                </td>
                <td>{names(row.employeeId)}</td>
                <td>{row.message}</td>
                <td>
                  {row.source === "simulation"
                    ? "SİMÜLASYON"
                    : ["manual", "MANUAL_PERSONNEL"].includes(row.source)
                      ? "Manuel"
                      : "Doğrulanmış cihaz"}
                  <small>{row.actor || "-"}</small>
                  <small>{row.deviceId || "-"}</small>
                </td>
              </tr>
            ))}
          </Table>
        </>
      )}
      {tab === "schedule" && (
        <>
          <div className="filter-bar">
            <Field label="Takvim tarihi">
              <input
                type="date"
                required
                value={day}
                onChange={(e) => e.target.value && setDay(e.target.value)}
              />
            </Field>
            <Field label="Takvim görünümü">
              <select
                value={calendarMode}
                onChange={(e) => setCalendarMode(e.target.value)}
              >
                <option value="week">Haftalık</option>
                <option value="month">Aylık</option>
              </select>
            </Field>
            {isAdmin && (
              <>
                <EmployeeSelect
                  employees={db.employees}
                  value={employeeId}
                  onChange={setEmployeeId}
                  all
                />
                <Button
                  icon={CalendarDays}
                  tone="primary"
                  onClick={() => setModal({ kind: "schedule" })}
                >
                  Vardiya oluştur
                </Button>
              </>
            )}
          </div>
          <div className="personnel-calendar" aria-label="Vardiya takvimi">
            {calendar.map((date) => (
              <section
                key={date}
                className={`personnel-day ${date === today ? "today" : ""}`}
              >
                <h3>{trDate(date)}</h3>
                {plans
                  .filter(
                    (row) =>
                      (employeeId === "all" || row.employeeId === employeeId) &&
                      new Date(row.start) < bounds(date).end &&
                      new Date(row.end) > bounds(date).start,
                  )
                  .map((row) => (
                    <div key={row.id} className="personnel-slot">
                      <strong>{names(row.employeeId)}</strong>
                      <span>
                        {row.kind === "off"
                          ? "İzin günü"
                          : `${trTime(row.start)} - ${trTime(row.end)}`}
                      </span>
                      <small>
                        {
                          scheduleStatuses[
                            data.scheduleStatus.find((s) => s.id === row.id)
                              ?.status
                          ]
                        }
                      </small>
                      {isAdmin && (
                        <IconButton
                          icon={Ban}
                          label="Vardiyayı iptal et"
                          onClick={() =>
                            setModal({ kind: "cancelSchedule", record: row })
                          }
                        />
                      )}
                    </div>
                  ))}
              </section>
            ))}
          </div>
          <h3 className="section-title">Yaklaşan vardiyalar</h3>
          <Table headers={["Personel", "Başlangıç", "Bitiş", "Tür"]}>
            {plans
              .filter(
                (row) =>
                  new Date(row.end) >= now &&
                  (employeeId === "all" || row.employeeId === employeeId),
              )
              .sort((a, b) => a.start.localeCompare(b.start))
              .slice(0, 20)
              .map((row) => (
                <tr key={row.id}>
                  <td>{names(row.employeeId)}</td>
                  <td>
                    {trDate(row.start)} {trTime(row.start)}
                  </td>
                  <td>
                    {trDate(row.end)} {trTime(row.end)}
                  </td>
                  <td>{row.kind === "off" ? "İzin günü" : "Çalışma"}</td>
                </tr>
              ))}
          </Table>
        </>
      )}
      {tab === "leave" && (
        <>
          <div className="filter-bar">
            {isAdmin && (
              <EmployeeSelect
                employees={db.employees}
                value={employeeId}
                onChange={setEmployeeId}
                all
              />
            )}
            {data.permissions.requestLeave && (
              <Button
                icon={Send}
                tone="primary"
                disabled={
                  !data.leaveTypes.some((t) => t.active) || (!isAdmin && !own)
                }
                onClick={() => setModal({ kind: "leave" })}
              >
                İzin talebi
              </Button>
            )}
            {isAdmin && (
              <Button
                icon={Settings}
                onClick={() => setModal({ kind: "leaveType" })}
              >
                İzin türü ekle
              </Button>
            )}
          </div>
          {!data.leaveTypes.length && (
            <Empty>İzin türleri henüz tanımlanmamış.</Empty>
          )}
          <Table
            headers={[
              "Personel",
              "İzin türü",
              "Başlangıç / Bitiş",
              "Gerekçe",
              "Durum",
              "Karar",
              "İşlem",
            ]}
          >
            {data.leaveRequests
              .filter(
                (row) => employeeId === "all" || row.employeeId === employeeId,
              )
              .sort((a, b) => b.start.localeCompare(a.start))
              .map((row) => (
                <tr key={row.id}>
                  <td>{names(row.employeeId)}</td>
                  <td>
                    {data.leaveTypes.find((t) => t.id === row.typeId)?.name}
                  </td>
                  <td>
                    {trDate(row.start)}
                    <small>{trDate(row.end)}</small>
                  </td>
                  <td className="personnel-reason">{row.reason}</td>
                  <td>{leaveStatuses[row.status]}</td>
                  <td>
                    {row.reviewer || "-"}
                    <small>{row.reviewReason}</small>
                  </td>
                  <td>
                    {row.status === "pending" &&
                      (isAdmin ? (
                        <div className="button-group">
                          <IconButton
                            icon={Check}
                            label="İzni onayla"
                            onClick={() =>
                              setModal({
                                kind: "review",
                                record: row,
                                status: "approved",
                              })
                            }
                          />
                          <IconButton
                            icon={X}
                            label="İzni reddet"
                            onClick={() =>
                              setModal({
                                kind: "review",
                                record: row,
                                status: "rejected",
                              })
                            }
                          />
                        </div>
                      ) : (
                        <IconButton
                          icon={X}
                          label="Talebi geri çek"
                          disabled={busy}
                          onClick={() =>
                            perform("withdrawLeave", { id: row.id })
                          }
                        />
                      ))}
                  </td>
                </tr>
              ))}
          </Table>
          {!data.leaveRequests.length && (
            <Empty>İzin geçmişi bulunmuyor.</Empty>
          )}
          {isAdmin && (
            <>
              <h3 className="section-title">
                İzin türleri ve hak ediş kuralları
              </h3>
              <Table
                headers={[
                  "Tür",
                  "Yıllık hak",
                  "Asgari hizmet",
                  "Hesaplanan günler",
                  "Durum",
                  "İşlem",
                ]}
              >
                {data.leaveTypes.map((row) => (
                  <tr key={row.id}>
                    <td>{row.name}</td>
                    <td>
                      {row.annualDays == null
                        ? "Sınır tanımlı değil"
                        : `${row.annualDays} gün`}
                    </td>
                    <td>{row.serviceMonths} ay</td>
                    <td>{row.weekdays.length} gün / hafta</td>
                    <td>{row.active ? "Aktif" : "Pasif"}</td>
                    <td>
                      <IconButton
                        icon={Pencil}
                        label="İzin türünü düzenle"
                        onClick={() =>
                          setModal({ kind: "leaveType", record: row })
                        }
                      />
                    </td>
                  </tr>
                ))}
              </Table>
            </>
          )}
        </>
      )}
      {tab === "rules" && isAdmin && (
        <>
          <h3>Mesai kuralları</h3>
          <dl className="detail-grid">
            {[
              ["lateGraceMinutes", "Geç kalma toleransı (dk)"],
              ["overtimeGraceMinutes", "Fazla mesai toleransı (dk)"],
              ["missingExitHours", "Eksik çıkış uyarısı (saat)"],
              ["duplicateSeconds", "Tekrar okutma aralığı (sn)"],
            ].map(([key, label]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd>{data.rules[key]}</dd>
              </div>
            ))}
            <div>
              <dt>Molalar çalışma süresine dahil</dt>
              <dd>{data.rules.paidBreaks ? "Evet" : "Hayır"}</dd>
            </div>
          </dl>
          <Button icon={Settings} onClick={() => setModal({ kind: "rules" })}>
            Kuralları düzenle
          </Button>
          <h3 className="section-title">Rol bazlı kişisel mesai yetkileri</h3>
          <Table
            headers={[
              "Rol",
              "Manuel mesai",
              "İzin talebi",
              "Mola",
              "Simülasyon",
              "İşlem",
            ]}
          >
            {["staff", "trainer"].map((role) => {
              const rights = {
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
                memberManagement:role==='staff',
                cardManagement:role==='staff',
                collections:role==='staff',
                deviceRead:role==='staff',
                ...data.rolePolicies.find((p) => p.role === role)?.permissions,
              };
              return (
                <tr key={role}>
                  <td>{roles[role]}</td>
                  {[
                    "manualAttendance",
                    "requestLeave",
                    "attendanceBreak",
                    "simulateAttendance",
                  ].map((key) => (
                    <td key={key}>{rights[key] ? "İzinli" : "Kapalı"}</td>
                  ))}
                  <td>
                    <IconButton
                      icon={Pencil}
                      label={`Yetkileri düzenle: ${roles[role]}`}
                      onClick={() => setModal({ kind: "policy", role, rights })}
                    />
                  </td>
                </tr>
              );
            })}
          </Table>
          <p className="member-note">
            Kişisel yetkiler diğer personellerin kayıtlarına erişim sağlamaz.
            Personel yönetimi ve izin onayı yalnızca yöneticidedir.
          </p>
        </>
      )}
      {modal && (
        <PersonnelDialog
          key={modal.kind + (modal.record?.id || "")}
          modal={modal}
          db={db}
          data={data}
          own={own}
          isAdmin={isAdmin}
          run={perform}
          close={() => setModal(null)}
          onSelected={setSelected}
        />
      )}
    </section>
  );
}

function EmployeeSelect({ employees, value, onChange, all = false }) {
  return (
    <Field label="Personel">
      <select required value={value} onChange={(e) => onChange(e.target.value)}>
        {all && <option value="all">Tüm personeller</option>}
        {!all && <option value="">Personel seçin</option>}
        {employees.map((row) => (
          <option key={row.id} value={row.id}>
            {row.name}
          </option>
        ))}
      </select>
    </Field>
  );
}

function PersonnelDialog({
  modal,
  db,
  data,
  own,
  isAdmin,
  run,
  close,
  onSelected,
}) {
  const row = modal.record || {},
    kind = modal.kind;
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [photo, setPhoto] = useState(row.photo || ""),
    [createAccount, setCreateAccount] = useState(false),
    [emp, setEmp] = useState(own?.id || ""),
    [role, setRole] = useState(row.role || "staff");
  const titles = {
    employee: row.id ? "Personeli düzenle" : "Yeni personel",
    card: "Mesai kartı tanımla",
    cancelCard: "Mesai kartını iptal et",
    employeeStatus: row.active
      ? "Personeli pasife al"
      : "Personeli aktifleştir",
    schedule: "Vardiya oluştur",
    cancelSchedule: "Vardiyayı iptal et",
    manual: "Manuel mesai",
    correct: "Mesai kaydını düzelt",
    presence: "Personel geçişini düzelt",
    leave: "İzin talebi oluştur",
    leaveType: "İzin türü ve hak ediş",
    review: modal.status === "approved" ? "İzni onayla" : "İzni reddet",
    rules: "Mesai kuralları",
    policy: "Rol yetkilerini düzenle",
  };
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    let action,
      payload = { ...values };
    setBusy(true);
    setError("");
    try {
      if (kind === "employee") {
        action = "saveEmployee";
        payload = {
          ...values,
          id: row.id,
          role,
          photo,
          createAccount,
          active: form.elements.active.checked,
          branchId: db.branches[0]?.id,
        };
        if (!createAccount) delete payload.password;
      }
      if (kind === "card") {
        action = "assignEmployeeCard";
        payload = { employeeId: row.id, uid: values.uid };
      }
      if (kind === "cancelCard") {
        action = "employeeCardStatus";
        payload = { id: row.id, status: "cancelled" };
      }
      if (kind === "employeeStatus") {
        action = "saveEmployee";
        payload = { id: row.id, active: !row.active };
      }
      if (kind === "schedule") {
        action = "savePlannedShift";
        payload = {
          ...values,
          employeeId: emp,
          ...scheduleWindow(values.day, values.from, values.to),
          autoStart: form.elements.autoStart.checked,
          weekdays: new FormData(form).getAll("weekdays").map(Number),
        };
      }
      if (kind === "cancelSchedule") {
        action = "cancelPlannedShift";
        payload = { id: row.id, reason: values.reason };
      }
      if (kind === "manual") {
        action = "manualPersonnelOperation";
        payload = { ...values, confirmed: form.elements.confirmed.checked, employeeId: isAdmin ? emp : own.id };
      }
      if (kind === "presence") {
        action = "correctPersonnelPresence";
        payload = {
          employeeId: emp,
          deviceId: values.deviceId,
          direction: values.direction,
          reason: values.reason,
        };
      }
      if (kind === "correct") {
        action = "correctAttendance";
        payload = {
          id: row.id,
          entry: isoTime(values.entry),
          exit: values.exit ? isoTime(values.exit) : null,
          reason: values.reason,
        };
      }
      if (kind === "leave") {
        action = "requestLeave";
        payload = { ...values, employeeId: isAdmin ? emp : own.id };
      }
      if (kind === "leaveType") {
        action = "saveLeaveType";
        payload = {
          ...values,
          id: row.id,
          active: form.elements.active.checked,
          weekdays: new FormData(form).getAll("weekdays").map(Number),
        };
      }
      if (kind === "review") {
        action = "reviewLeave";
        payload = { id: row.id, status: modal.status, reason: values.reason };
      }
      if (kind === "rules") {
        action = "saveAttendanceRules";
        payload = { ...values, paidBreaks: form.elements.paidBreaks.checked };
      }
      if (kind === "policy") {
        action = "saveRolePolicy";
        payload = {
          role: modal.role,
          permissions: Object.fromEntries(
            [
              "manualAttendance",
              "manualVisits",
              "requestLeave",
              "attendanceBreak",
              "simulateAttendance",
              "classBooking",
              "classAttendance",
              "productSales",
              "productDiscount",
              "productReturns",
              "memberManagement",
              "cardManagement",
              "collections",
              "deviceRead",
            ].map((key) => [key, form.elements[key].checked]),
          ),
        };
      }
      const result = await run(action, payload);
      if (result?.ok) {
        if (kind === "employee") onSelected(result.result);
        close();
      } else setError(result?.message || "İşlem kaydedilemedi.");
    } catch (error) {
      setError(error.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={titles[kind]} onClose={close}>
      <form onSubmit={submit}>
        <div className="form-grid">
          {kind === "employee" && (
            <>
              <Field label="Ad soyad">
                <input
                  name="name"
                  required
                  maxLength={120}
                  defaultValue={row.name || ""}
                />
              </Field>
              <Field label="Telefon">
                <input name="phone" type="tel" defaultValue={row.phone || ""} />
              </Field>
              <Field label="E-posta">
                <input
                  name="email"
                  type="email"
                  maxLength={254}
                  defaultValue={row.email || ""}
                  required={createAccount}
                />
              </Field>
              <Field label="Görev">
                <input
                  name="jobTitle"
                  maxLength={120}
                  defaultValue={row.jobTitle || ""}
                />
              </Field>
              <Field label="Yetki rolü">
                <select
                  name="role"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                >
                  {Object.entries(roles).map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="İşe başlangıç tarihi">
                <input
                  name="startDate"
                  type="date"
                  defaultValue={row.startDate || trDay()}
                />
              </Field>
              <Field label="Şube">
                <input readOnly value={db.branches[0]?.name || ""} />
              </Field>
              <Field label="Çalışan tipi">
                <select name="type" defaultValue={row.type || "fixed"}>
                  <option value="fixed">Sabit</option>
                  <option value="hourly">Saatlik</option>
                </select>
              </Field>
              <Field label="Mesai kart UID (isteğe bağlı)">
                <input
                  name="card"
                  maxLength={100}
                  defaultValue={row.card || ""}
                />
              </Field>
              <Field label="Personel fotoğrafı">
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={async (e) => {
                    const file = e.target.files[0];
                    if (!file) return;
                    if (
                      file.size > 500000 ||
                      !["image/png", "image/jpeg", "image/webp"].includes(
                        file.type,
                      )
                    ) {
                      setError(
                        "Fotoğraf PNG/JPEG/WebP ve en fazla 500 KB olmalı.",
                      );
                      return;
                    }
                    const value = await new Promise((resolve, reject) => {
                      const reader = new FileReader();
                      reader.onload = () => resolve(reader.result);
                      reader.onerror = reject;
                      reader.readAsDataURL(file);
                    });
                    setPhoto(value);
                    setError("");
                  }}
                />
              </Field>
              {photo && (
                <img
                  className="avatar"
                  src={photo}
                  alt="Personel fotoğrafı önizleme"
                />
              )}
              {!row.userId && (
                <>
                  <label className="check-field">
                    <input
                      type="checkbox"
                      checked={createAccount}
                      onChange={(e) => setCreateAccount(e.target.checked)}
                    />
                    Giriş hesabı oluştur
                  </label>
                  {createAccount ? (
                    <Field label="Geçici şifre">
                      <input
                        name="password"
                        type="password"
                        autoComplete="new-password"
                        minLength={12}
                        maxLength={128}
                        required
                      />
                    </Field>
                  ) : (
                    <Field label="Mevcut giriş hesabı">
                      <select name="userId" defaultValue="">
                        <option value="">Hesap bağlama</option>
                        {data.accounts
                          .filter((u) => !u.linked && u.role === role)
                          .map((u) => (
                            <option key={u.id} value={u.id}>
                              {u.name} · {u.email}
                            </option>
                          ))}
                      </select>
                    </Field>
                  )}
                </>
              )}
              <label className="check-field">
                <input
                  name="active"
                  type="checkbox"
                  defaultChecked={row.active !== false}
                />
                Aktif personel
              </label>
            </>
          )}
          {kind === "presence" && (
            <>
              <EmployeeSelect
                employees={db.employees}
                value={emp}
                onChange={setEmp}
              />
              <Field label="Cihaz">
                <select name="deviceId" required>
                  {db.devices
                    .filter((item) => !item.simulated)
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Yön">
                <select name="direction">
                  <option value="exit">Eksik çıkışı kapat</option>
                  <option value="entry">Yönetici onaylı manuel giriş</option>
                </select>
              </Field>
              <Field label="Onay gerekçesi">
                <textarea name="reason" required maxLength={1500} />
              </Field>
            </>
          )}
          {kind === "card" && (
            <Field label="Mesai kart UID">
              <input name="uid" required maxLength={100} />
            </Field>
          )}
          {["cancelCard", "employeeStatus"].includes(kind) && (
            <p>
              {kind === "cancelCard"
                ? "Kart sonraki mesai okumalarında reddedilir. Eski mesai kayıtları korunur."
                : row.active
                  ? "Personel ve bağlı giriş hesabı pasif olur. Eski kayıtlar silinmez."
                  : "Personel ve bağlı giriş hesabı aktif olur."}
            </p>
          )}
          {kind === "schedule" && (
            <>
              <EmployeeSelect
                employees={db.employees.filter((e) => e.active)}
                value={emp}
                onChange={setEmp}
              />
              <Field label="Tarih">
                <input name="day" type="date" defaultValue={trDay()} required />
              </Field>
              <Field label="Başlangıç saati">
                <input name="from" type="time" required defaultValue="09:00" />
              </Field>
              <Field label="Bitiş saati">
                <input name="to" type="time" required defaultValue="18:00" />
              </Field>
              <Field label="Vardiya türü">
                <select name="kind">
                  <option value="work">Çalışma</option>
                  <option value="off">İzin günü</option>
                </select>
              </Field>
              <label className="check-field">
                <input type="checkbox" name="autoStart" defaultChecked />
                İlk doğrulanmış girişte mesaiyi otomatik başlat
              </label>
              <Field label="Planlanan mola (dk)">
                <input
                  name="breakMinutes"
                  type="number"
                  min="0"
                  max="1440"
                  defaultValue="0"
                  required
                />
              </Field>
              <Field label="Tekrar bitiş tarihi (isteğe bağlı)">
                <input name="repeatUntil" type="date" />
              </Field>
              <Weekdays values={[1, 2, 3, 4, 5]} />
              <p className="member-note">
                Bitiş saati başlangıçtan önceyse vardiya ertesi güne uzanır.
              </p>
            </>
          )}
          {kind === "manual" && (
            <>
              {isAdmin && (
                <EmployeeSelect
                  employees={db.employees}
                  value={emp}
                  onChange={setEmp}
                />
              )}
              <Field label="Mesai işlemi">
                <select name="operation" defaultValue={modal.operation || 'start'}>
                  <option value="start">Mesai başlat</option>
                  <option value="break">Molaya çık</option>
                  <option value="resume">Moladan dön</option>
                  <option value="finish">Mesai bitir</option>
                </select>
              </Field>
              <label className="check-field"><input name="confirmed" type="checkbox" required />Personelin mesai / mola işlemini doğruluyorum</label>
            </>
          )}
          {kind === "correct" && (
            <>
              <Field label="Giriş zamanı (Türkiye)">
                <input
                  name="entry"
                  type="datetime-local"
                  step="0.001"
                  defaultValue={inputTime(row.entry)}
                  required
                />
              </Field>
              <Field label="Çıkış zamanı (Türkiye)">
                <input
                  name="exit"
                  type="datetime-local"
                  step="0.001"
                  defaultValue={inputTime(row.exit)}
                />
              </Field>
            </>
          )}
          {kind === "leave" && (
            <>
              {isAdmin && (
                <EmployeeSelect
                  employees={db.employees.filter((e) => e.active)}
                  value={emp}
                  onChange={setEmp}
                />
              )}
              <Field label="İzin türü">
                <select name="typeId" required>
                  {data.leaveTypes
                    .filter((t) => t.active)
                    .map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="İzin başlangıç tarihi">
                <input
                  name="start"
                  type="date"
                  min={trDay()}
                  defaultValue={trDay()}
                  required
                />
              </Field>
              <Field label="İzin bitiş tarihi">
                <input
                  name="end"
                  type="date"
                  min={trDay()}
                  defaultValue={trDay()}
                  required
                />
              </Field>
            </>
          )}
          {kind === "leaveType" && (
            <>
              <Field label="İzin türü adı">
                <input
                  name="name"
                  maxLength={120}
                  defaultValue={row.name || ""}
                  required
                />
              </Field>
              <Field label="Yıllık gün hakkı (boşsa sınır yok)">
                <input
                  name="annualDays"
                  type="number"
                  min="0"
                  max="366"
                  defaultValue={row.annualDays ?? ""}
                />
              </Field>
              <Field label="Asgari hizmet süresi (ay)">
                <input
                  name="serviceMonths"
                  type="number"
                  min="0"
                  max="1200"
                  defaultValue={row.serviceMonths || 0}
                  required
                />
              </Field>
              <Weekdays values={row.weekdays || [0, 1, 2, 3, 4, 5, 6]} />
              <label className="check-field">
                <input
                  name="active"
                  type="checkbox"
                  defaultChecked={row.active !== false}
                />
                Aktif izin türü
              </label>
            </>
          )}
          {["manual", "correct", "leave", "review", "cancelSchedule"].includes(
            kind,
          ) && (
            <Field label="Gerekçe">
              <textarea name="reason" maxLength={1500} required />
            </Field>
          )}
          {kind === "rules" && (
            <>
              {[
                ["lateGraceMinutes", "Geç kalma toleransı (dk)"],
                ["overtimeGraceMinutes", "Fazla mesai toleransı (dk)"],
                ["missingExitHours", "Eksik çıkış uyarısı (saat)"],
                ["duplicateSeconds", "Tekrar okutma aralığı (sn)"],
              ].map(([key, label]) => (
                <Field key={key} label={label}>
                  <input
                    name={key}
                    type="number"
                    min={
                      ["missingExitHours", "duplicateSeconds"].includes(key)
                        ? 1
                        : 0
                    }
                    max={
                      key === "missingExitHours"
                        ? 168
                        : key === "duplicateSeconds"
                          ? 120
                          : 1440
                    }
                    defaultValue={data.rules[key]}
                    required
                  />
                </Field>
              ))}
              <label className="check-field">
                <input
                  name="paidBreaks"
                  type="checkbox"
                  defaultChecked={data.rules.paidBreaks}
                />
                Molaları çalışma süresine dahil et
              </label>
            </>
          )}
          {kind === "policy" &&
            Object.entries({
              manualAttendance: "Kendi manuel mesai işlemi",
              manualVisits: "Manuel üye giriş / çıkışı (resepsiyon)",
              requestLeave: "Kendi izin talebi",
              attendanceBreak: "Kendi mola işlemi",
              simulateAttendance: "Kontrollü simülasyon",
              classBooking: "Ders rezervasyonu (resepsiyon)",
              classAttendance: "Ders yoklaması (resepsiyon)",
              productSales: "Ürün satışı (resepsiyon)",
              productDiscount: "Ürün satışında indirim (resepsiyon)",
              productReturns: "Ürün iadesi (resepsiyon)",
              memberManagement:"Üye kayıtları (resepsiyon)",
              cardManagement:"Kart yönetimi (resepsiyon)",
              collections:"Tahsilat (resepsiyon)",
              deviceRead:"Cihaz durum bilgisi (resepsiyon)",
            }).map(([key, label]) => (
              <label key={key} className="check-field">
                <input
                  name={key}
                  type="checkbox"
                  defaultChecked={modal.rights[key]}
                  disabled={modal.role==='trainer'&&['manualVisits','memberManagement','cardManagement','collections','deviceRead'].includes(key)}
                />
                {label}
              </label>
            ))}
        </div>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <footer className="form-footer">
          <Button type="button" onClick={close}>
            Vazgeç
          </Button>
          <Button type="submit" tone="primary" icon={Save} disabled={busy}>
            {busy ? "Kaydediliyor..." : "Kaydet"}
          </Button>
        </footer>
      </form>
    </Dialog>
  );
}

function Weekdays({ values }) {
  return (
    <fieldset className="personnel-weekdays">
      <legend>Hesaplanan / tekrar eden günler</legend>
      {[
        "Pazar",
        "Pazartesi",
        "Salı",
        "Çarşamba",
        "Perşembe",
        "Cuma",
        "Cumartesi",
      ].map((label, id) => (
        <label className="check-field" key={id}>
          <input
            name="weekdays"
            type="checkbox"
            value={id}
            defaultChecked={values.includes(id)}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}
