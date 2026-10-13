import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  DoorOpen,
  Radio,
  Wrench,
  Check,
  X,
  Download,
} from "lucide-react";
import { dateKey, displayDate, displayTime } from "./attendance.mjs";
import ManualAccessPanel from './ManualAccessPanel';
import {
  Button,
  Badge,
  Table,
  Empty,
  Field,
  ActionForm,
  Avatar,
  ExportButtons,
  exportCsv,
} from "./ui";

export function ReceptionPage({ db, run, isAdmin = false }) {
  const [mode, setMode] = useState('automatic');
  const [card, setCard] = useState(""),
    [deviceId, setDeviceId] = useState(
      db.devices.find((item) => !item.simulated && ['access','mixed'].includes(item.purpose))?.id || db.devices.find((item) => item.simulated)?.id || "",
    ),
    [direction, setDirection] = useState("entry"),
    [simulatedResult, setResult] = useState(null);
  const device=db.devices.find(item=>item.id===deviceId),simulating=Boolean(device?.simulated&&(db.personnel?.simulationEnabled||db.source!=='server'));
  const latest=db.attempts.filter(row=>row.deviceId===deviceId).slice().sort((a,b)=>new Date(b.at)-new Date(a.at))[0];
  const observedGrant=latest&&db.grants.find(row=>row.attemptId===latest.id);
  const result=device?.simulated?simulatedResult:latest?{approved:['granted','confirmed'].includes(latest.status),memberId:latest.memberId,grantId:observedGrant?.id,reason:latest.reason,direction:latest.direction}:null;
  const member = db.members.find((item) => item.id === result?.memberId);
  const grant = db.grants.find((item) => item.id === result?.grantId);
  const expired =
    grant && !grant.confirmed && new Date(grant.expiresAt) <= new Date();
  const scan = async (event) => {
    event.preventDefault();
    const response = await run("authorize", { uid: card, deviceId, direction });
    if (response?.ok) {
      setResult(response.result);
      setCard("");
    }
  };
  return (
    <>
    <div className="segmented" aria-label="Terminal işlem modu">
      <button aria-pressed={mode==='automatic'} onClick={()=>setMode('automatic')}>Otomatik RFID Modu</button>
      <button aria-pressed={mode==='manual'} onClick={()=>setMode('manual')}>Manuel İşlem Modu</button>
    </div>
    {mode==='manual' ? <ManualAccessPanel db={db} run={run} isAdmin={isAdmin} /> : <section className="terminal">
      <div className="terminal-toolbar">
        <Field label="Giriş noktası">
          <select
            value={deviceId}
            onChange={(event) => setDeviceId(event.target.value)}
          >
            {db.devices
              .filter((item) => ['access','mixed'].includes(item.purpose)||item.simulated)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </select>
        </Field>
        {simulating&&<div className="segmented">
          {[
            ["entry", "Giriş"],
            ["exit", "Çıkış"],
          ].map(([value, label]) => (
            <button
              key={value}
              aria-pressed={direction === value}
              onClick={() => {
                setDirection(value);
                setResult(null);
              }}
            >
              {label}
            </button>
          ))}
        </div>}
        <Badge
          status={db.devices.find((item) => item.id === deviceId)?.status}
        />
      </div>
      <div
        className={`terminal-result ${result?.approved ? "approved" : result ? "denied" : ""}`}
      >
        {member ? (
          <Avatar member={member} />
        ) : (
          <div className="terminal-icon">
            <Radio size={44} />
          </div>
        )}
        <h2>
          {result
            ? result.approved
              ? grant?.confirmed
                ? "Geçiş tamamlandı"
                : expired
                  ? "Geçiş izni süresi doldu"
                  : "Geçiş izni verildi"
              : "Giriş reddedildi"
            : "Kartınızı okutunuz"}
        </h2>
        <p>{member?.name || "FitGate giriş kontrol terminali"}</p>
        {result?.reason && <strong>{result.reason}</strong>}
        {result?.approved && !grant?.confirmed && (
          <div className="sensor-confirm">
            <span>
              {expired ? "Kartı yeniden okutun" : "Fiziksel geçiş bekleniyor"}
            </span>
            {simulating&&<Button
              tone="primary"
              icon={Check}
              disabled={expired}
              onClick={async () => {
                if ((await run("confirmPassage", { id: result.grantId }))?.ok)
                  setResult({ ...result });
              }}
            >
              Sensör onayını simüle et
            </Button>}
          </div>
        )}
      </div>
      {simulating&&<form className="terminal-scan" onSubmit={scan}>
        <Field label="Üye kart UID">
          <input
            autoFocus
            required
            autoComplete="off"
            value={card}
            onChange={(event) => setCard(event.target.value)}
            placeholder="RFID-12004"
          />
        </Field>
        <Button type="submit" icon={ShieldCheck} tone="primary">
          Kartı doğrula
        </Button>
      </form>}
    </section>}
    </>
  );
}

export function AccessPage({ db, run, isAdmin }) {
  const [tab, setTab] = useState("inside"),
    [day, setDay] = useState(dateKey()),
    [all, setAll] = useState(false),
    [deviceId, setDeviceId] = useState("all"),
    [direction, setDirection] = useState("all"),
    [query, setQuery] = useState(""),
    [correct, setCorrect] = useState(null),
    [policy, setPolicy] = useState(false);
  const memberName = (id) =>
    db.members.find((item) => item.id === id)?.name || "Bilinmeyen kart";
  const deviceName = (id) =>
    db.devices.find((item) => item.id === id)?.name || "-";
  const attempts = db.attempts.filter(
    (item) =>
      (all || dateKey(new Date(item.at)) === day) &&
      (deviceId === "all" || item.deviceId === deviceId) &&
      (direction === "all" || item.direction === direction) &&
      memberName(item.memberId)
        .toLocaleLowerCase("tr")
        .includes(query.toLocaleLowerCase("tr")) &&
      (tab !== "rejected" || item.status === "rejected"),
  );
  const visits = db.visits.filter(
    (item) =>
      !item.exit &&
      (tab !== "missing" || new Date() - new Date(item.entry) > 12 * 3600000) &&
      (deviceId === "all" || item.deviceId === deviceId) &&
      memberName(item.memberId)
        .toLocaleLowerCase("tr")
        .includes(query.toLocaleLowerCase("tr")),
  );
  return (
    <section className="page-grid">
      <div className="tabs" role="tablist" aria-label="Geçiş kayıtları">
        {[
          ["inside", "İçeridekiler"],
          ["all", "Tüm geçişler"],
          ["rejected", "Reddedilenler"],
          ["missing", "Eksik çıkışlar"],
          ["manual", "Manuel işlemler"],
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
      {tab !== 'manual' && <div className="filter-bar">
        {isAdmin && (
          <Button icon={Wrench} onClick={() => setPolicy(true)}>
            Giriş politikası
          </Button>
        )}
        <input
          className="search-input"
          aria-label="Geçişlerde üye ara"
          placeholder="Üye ara"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Field label="Tarih">
          <input
            type="date"
            value={day}
            disabled={all}
            onChange={(event) => setDay(event.target.value)}
          />
        </Field>
        <label className="check-field">
          <input
            type="checkbox"
            checked={all}
            onChange={(event) => setAll(event.target.checked)}
          />
          Tüm tarihler
        </label>
        <select
          aria-label="Cihaz filtresi"
          value={deviceId}
          onChange={(event) => setDeviceId(event.target.value)}
        >
          <option value="all">Tüm cihazlar</option>
          {db.devices.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Geçiş yönü"
          value={direction}
          onChange={(event) => setDirection(event.target.value)}
        >
          <option value="all">Tüm yönler</option>
          <option value="entry">Giriş</option>
          <option value="exit">Çıkış</option>
        </select>
        {isAdmin && (
          <ExportButtons
            onExport={() =>
              exportCsv(
                "gecisler",
                ["Üye", "Tarih", "Yön", "Durum", "Neden"],
                attempts.map((item) => [
                  memberName(item.memberId),
                  item.at,
                  item.direction,
                  item.status,
                  item.reason,
                ]),
              )
            }
          />
        )}
      </div>}
      {["inside", "missing"].includes(tab) ? (
        <>
          <Table
            headers={[
              "Üye",
              "Giriş zamanı",
              "İçerideki süre",
              "Cihaz",
              "İşlem",
            ]}
          >
            {visits.map((item) => (
              <tr key={item.id}>
                <td>{memberName(item.memberId)}</td>
                <td>
                  {displayDate(item.entry)}
                  <small>{displayTime(item.entry)}</small>
                </td>
                <td>
                  {Math.max(
                    0,
                    Math.floor((new Date() - new Date(item.entry)) / 60000),
                  )}{" "}
                  dk
                </td>
                <td>{deviceName(item.deviceId)}</td>
                <td>
                  {isAdmin && (
                    <Button onClick={() => setCorrect(item)}>
                      Çıkışı düzelt
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </Table>
          {!visits.length && <Empty />}
        </>
      ) : tab === "manual" ? (
        <ManualAccessPanel db={db} run={run} isAdmin={isAdmin} />
      ) : (
        <>
          <Table
            headers={["Üye / Kart", "Tarih", "Yön", "Cihaz", "Sonuç", "Neden"]}
          >
            {attempts
              .slice()
              .reverse()
              .map((item) => (
                <tr key={item.id}>
                  <td>
                    {memberName(item.memberId)}
                    <small>{item.card}</small>
                  </td>
                  <td>
                    {displayDate(item.at)}
                    <small>{displayTime(item.at)}</small>
                  </td>
                  <td>{item.direction === "entry" ? "Giriş" : "Çıkış"}</td>
                  <td>{deviceName(item.deviceId)}</td>
                  <td>
                    <Badge status={item.status} />
                  </td>
                  <td>{item.reason}</td>
                </tr>
              ))}
          </Table>
          {!attempts.length && <Empty />}
        </>
      )}
      {policy && (
        <ActionForm
          title="Giriş politikası"
          initial={db.settings}
          fields={[
            {
              name: "capacity",
              label: "Salon kapasitesi",
              type: "number",
              min: 1,
            },
            {
              name: "debtBlock",
              label: "Borcu olan üyeye giriş engeli",
              type: "checkbox",
              required: false,
            },
          ]}
          onClose={() => setPolicy(false)}
          onSave={(values) => run("saveSettings", values)}
        />
      )}
      {correct && (
        <ActionForm
          title="Manuel çıkış düzeltmesi"
          fields={[
            { name: "reason", label: "Düzeltme gerekçesi", type: "textarea" },
          ]}
          onClose={() => setCorrect(null)}
          onSave={(values) =>
            run("correctVisit", { ...values, id: correct.id })
          }
        />
      )}
    </section>
  );
}

export function DevicesPage({ db, run, selectedDeviceId }) {
  const [selected, setSelected] = useState(null);
  const [diagnostic, setDiagnostic] = useState(null);
  useEffect(()=>{if(selectedDeviceId && db.devices.some(d=>d.id===selectedDeviceId))setSelected(selectedDeviceId);},[selectedDeviceId]);
  return (
    <section className="page-grid">
      <div className="page-actions">
        <Badge
          status={
            db.devices.some(
              (item) => !item.simulated && item.status === "online",
            )
              ? "online"
              : "offline"
          }
        >
          {
            db.devices.filter(
              (item) => !item.simulated && item.status === "online",
            ).length
          }{" "}
          gerçek cihaz çevrimiçi
        </Badge>
      </div>
      <div className="device-grid">
        {db.devices.map((item) => (
          <article className="device-item" key={item.id}>
            <div className="panel-header">
              <div className="device-symbol">
                <DoorOpen size={24} />
              </div>
              <Badge status={item.simulated ? "pending" : item.status}>
                {item.simulated
                  ? "Simülasyon"
                  : item.status === "online"
                    ? "Çevrimiçi"
                    : "Çevrimdışı"}
              </Badge>
            </div>
            <h2>{item.name}</h2>
            <p>
              {item.code} · {item.model}
            </p>
            {item.telemetry?.validationMode === 'single_sensor_prototype' && (
              <p role="note">Tek sensör prototipi: algılama tam fiziksel geçiş kanıtı değildir. Gerçek turnike güvenliği için kullanılmamalıdır.</p>
            )}
            <dl className="detail-grid">
              <div>
                <dt>Son bağlantı</dt>
                <dd>
                  {item.lastSeen
                    ? `${displayDate(item.lastSeen)} ${displayTime(item.lastSeen)}`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Sensör</dt>
                <dd>
                  {item.status !== "online" || item.simulated
                    ? "Veri yok"
                    : item.sensor === "ready"
                      ? "Hazır"
                      : item.sensor === "fault"
                        ? "Ölçüm hatası"
                        : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>{item.telemetry?.validationMode === 'single_sensor_prototype' ? 'Kayıtlı prototip olayı' : 'Doğrulanmış geçiş'}</dt>
                <dd>
                  {
                    db.attempts.filter(
                      (attempt) =>
                        attempt.deviceId === item.id &&
                        attempt.status === "confirmed" &&
                        dateKey(new Date(attempt.at)) === dateKey(),
                    ).length
                  }
                </dd>
              </div>
              <div>
                <dt>Mod</dt>
                <dd>
                  {item.mode === "auto"
                    ? "Otomatik"
                    : item.mode === "maintenance"
                      ? "Bakım"
                      : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>USB portu</dt>
                <dd>{item.telemetry?.port || "Veri yok"}</dd>
              </div>
              <div>
                <dt>Firmware</dt>
                <dd>
                  {item.status === "online" && !item.simulated
                    ? item.telemetry?.firmware || "Veri yok"
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Son kart olayı</dt>
                <dd>{item.telemetry?.lastScanUid || "Veri yok"}</dd>
              </div>
              <div>
                <dt>LCD son komut</dt>
                <dd>
                  {item.status === "online" && !item.simulated
                    ? `${item.telemetry?.lcdTop || "Veri yok"} / ${item.telemetry?.lcdBottom || ""}`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Buzzer / LED komutu</dt>
                <dd>
                  {item.status === "online" &&
                  !item.simulated &&
                  typeof item.telemetry?.buzzer === "boolean"
                    ? `${item.telemetry.buzzer ? "Buzzer açık" : "Buzzer kapalı"} / ${item.telemetry.led ? "LED açık" : "LED kapalı"}`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Son giriş</dt>
                <dd>
                  {item.lastEntryAt
                    ? `${displayDate(item.lastEntryAt)} ${displayTime(item.lastEntryAt)}`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Son çıkış</dt>
                <dd>
                  {item.lastExitAt
                    ? `${displayDate(item.lastExitAt)} ${displayTime(item.lastExitAt)}`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Son personel işlemi</dt>
                <dd>{item.lastAttendance || "Veri yok"}</dd>
              </div>
              <div>
                <dt>Bağlantı denemesi</dt>
                <dd>
                  {item.simulated
                    ? "Simülasyon"
                    : item.telemetry?.connection === "retrying"
                      ? "Yeniden bağlanıyor"
                      : item.status === "online"
                        ? "Bağlı"
                        : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>RFID okuyucu</dt>
                <dd>
                  {item.status !== "online" || item.simulated
                    ? "Veri yok"
                    : item.telemetry?.rfid === "ready"
                      ? "Yanıt veriyor"
                      : item.telemetry?.rfid === "fault"
                        ? "Yanıt alınamıyor"
                        : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Servo komutu</dt>
                <dd>
                  {item.status !== "online" || item.simulated
                    ? "Veri yok"
                    : item.telemetry?.servo === "open"
                      ? "Açık"
                      : item.telemetry?.servo === "closed"
                        ? "Kapalı"
                        : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Dış sensör</dt>
                <dd>
                  {item.status === "online" &&
                  !item.simulated &&
                  item.telemetryAt &&
                  Date.now() - new Date(item.telemetryAt) < 5000
                    ? item.telemetry?.outsideCm == null
                      ? "Geçerli ölçüm yok"
                      : `${item.telemetry.outsideCm} cm`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>İç sensör</dt>
                <dd>
                  {item.status === "online" &&
                  !item.simulated &&
                  item.telemetryAt &&
                  Date.now() - new Date(item.telemetryAt) < 5000
                    ? item.telemetry?.insideCm == null
                      ? "Geçerli ölçüm yok"
                      : `${item.telemetry.insideCm} cm`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Son RFID okuma</dt>
                <dd>
                  {item.lastRfidAt
                    ? `${displayDate(item.lastRfidAt)} ${displayTime(item.lastRfidAt)}`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>{item.telemetry?.validationMode === 'single_sensor_prototype' ? 'Ziyaretten belirlenen yön' : 'Algılanan yön'}</dt>
                <dd>
                  {item.status !== "online" ||
                  item.simulated ||
                  !item.telemetry?.progressAt ||
                  Date.now() - new Date(item.telemetry.progressAt) > 15000
                    ? "Veri yok"
                    : {
                        entry: "Giriş algılandı",
                        exit: "Çıkış algılandı",
                        none: "Henüz algılanmadı",
                      }[item.telemetry.detectedDirection] || "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Geçiş durumu</dt>
                <dd>
                  {item.status !== "online" ||
                  item.simulated ||
                  !item.telemetry?.progressAt ||
                  Date.now() - new Date(item.telemetry.progressAt) > 15000
                    ? "Veri yok"
                    : {
                        idle: "Kart bekleniyor",
                        authorizing: "Yetki kontrolü",
                        waiting_first: item.telemetry?.validationMode === 'single_sensor_prototype' ? 'Herhangi bir sensör bekleniyor' : "İlk sensör bekleniyor",
                        detected: "İkinci sensör bekleniyor",
                        waiting_clear: "İki sensörün boşalması bekleniyor",
                        completed: "Fiziksel geçiş tamamlandı",
                        prototype_triggered: "Tek sensör olayı; güvenli kapanma bekleniyor",
                        fault: "Geçiş durduruldu",
                      }[item.telemetry.passageState] || "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>{item.lastPassageValidationMode === 'single_sensor_prototype' ? 'Son prototip olayı' : 'Son fiziksel geçiş'}</dt>
                <dd>
                  {item.lastPassageAt
                    ? `${displayDate(item.lastPassageAt)} ${displayTime(item.lastPassageAt)}`
                    : "Veri yok"}
                </dd>
              </div>
              <div>
                <dt>Son uyarı / hata</dt>
                <dd>{item.lastError || "Kayıt yok"}</dd>
              </div>
              <div>
                <dt>Kullanım amacı</dt>
                <dd>
                  <select
                    aria-label={`${item.name} kullanım amacı`}
                    value={item.purpose || "access"}
                    onChange={(event) =>
                      run("devicePurpose", {
                        id: item.id,
                        purpose: event.target.value,
                      })
                    }
                  >
                    <option value="mixed">Üye ve personel turnike</option>
                    <option value="access">Üye turnike geçişi</option>
                    <option value="attendance">Sadece personel turnike</option>
                  </select>
                </dd>
              </div>
              {item.purpose === "mixed" && (
                <div>
                  <dt>Kart bağlamı</dt>
                  <dd>
                    <select
                      aria-label={`${item.name} kart bağlamı`}
                      value={item.credentialContext || "auto"}
                      onChange={(event) =>
                        run("devicePurpose", {
                          id: item.id,
                          purpose: "mixed",
                          credentialContext: event.target.value,
                        })
                      }
                    >
                      <option value="auto">Kart türünü otomatik belirle</option>
                      <option value="member">Üye profili</option>
                      <option value="employee">Personel profili</option>
                    </select>
                  </dd>
                </div>
              )}
            </dl>
            <div className="button-group">
              <Button
                icon={Wrench}
                onClick={() =>
                  run("deviceMode", {
                    id: item.id,
                    mode: item.mode === "auto" ? "maintenance" : "auto",
                  })
                }
              >
                {item.mode === "auto" ? "Bakım modu" : "Otomatik mod"}
              </Button>
              <Button onClick={() => setSelected(item.id)}>Olay geçmişi</Button>
              {!item.simulated && (
                <Button icon={Wrench} onClick={() => setDiagnostic(item)}>
                  Donanım testi
                </Button>
              )}
            </div>
          </article>
        ))}
      </div>
      {diagnostic && (
        <ActionForm
          title="Kontrollü donanım testi"
          fields={[
            {
              name: "action",
              label: "Test",
              options: [
                { value: "lcd", label: "LCD mesaj testi" },
                { value: "indicators", label: "Buzzer ve LED testi" },
                { value: "servo", label: "Servo aç/kapat komut testi" },
              ],
            },
            {
              name: "confirmed",
              label:
                "Servo hareket alanı güvenli, uygun besleme ve bağımsız fiziksel emniyet hazır",
              type: "checkbox",
            },
          ]}
          onClose={() => setDiagnostic(null)}
          onSave={(values) =>
            run("queueDeviceDiagnostic", { deviceId: diagnostic.id, ...values })
          }
        />
      )}
      {(db.deviceCommands || []).length > 0 && (
        <Table headers={["Cihaz", "Tanılama", "Durum", "Sonuç"]}>
          {db.deviceCommands
            .slice()
            .reverse()
            .slice(0, 10)
            .map((row) => (
              <tr key={row.id}>
                <td>
                  {
                    db.devices.find((device) => device.id === row.deviceId)
                      ?.name
                  }
                </td>
                <td>{row.action}</td>
                <td>
                  {["queued", "sent"].includes(row.status) &&
                  new Date(row.expiresAt) < new Date()
                    ? "Süre doldu"
                    : {
                        queued: "Kuyrukta",
                        sent: "Cihaz sonucu bekleniyor",
                        complete: "Komut tamamlandı",
                        failed: "Başarısız",
                        expired: "Süre doldu",
                      }[row.status] || row.status}
                </td>
                <td>{row.result || "—"}</td>
              </tr>
            ))}
        </Table>
      )}
      {selected && (
        <>
          <div className="section-header">
            <h2>Cihaz olayları</h2>
          </div>
          <Table headers={["Zaman", "Olay", "Personel"]}>
            {db.deviceEvents
              .filter((item) => item.deviceId === selected)
              .map((item) => (
                <tr key={item.id}>
                  <td>
                    {displayDate(item.at)} {displayTime(item.at)}
                  </td>
                  <td>{item.message}</td>
                  <td>{item.actor}</td>
                </tr>
              ))}
          </Table>
        </>
      )}
    </section>
  );
}
