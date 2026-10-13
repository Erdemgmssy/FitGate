import React, { useEffect, useRef, useState } from "react";
import { Radio, RefreshCw, Pause, Play, Clock3 } from "lucide-react";
import { request } from "./api.mjs";
import { Button, Badge, Field, Empty, Table } from "./ui";

function time(value) {
  return value
    ? new Date(value).toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";
}
function distanceState(cm, stale) {
  if (stale) return { label: "Eski ölçüm", tone: "inactive" };
  if (cm == null) return { label: "Ölçüm yok", tone: "rejected" };
  if (cm < 20) return { label: "Yakın alan", tone: "ending" };
  return { label: "Uzak alan", tone: "active" };
}
function Sensor({ title, pins, cm, stale, paused }) {
  const state = distanceState(cm, stale);
  return (
    <section className={`sensor-reading ${state.tone}`}>
      <header>
        <div>
          <h2>{title}</h2>
          <span>{pins}</span>
        </div>
        <Radio size={23} />
      </header>
      <div className="sensor-value">
        <strong>{cm == null ? "—" : cm}</strong>
        <span>cm</span>
      </div>
      <Badge status={paused ? "inactive" : state.tone}>
        {paused ? "Duraklatıldı" : state.label}
      </Badge>
      <meter aria-label={`${title} mesafe`} min="0" max="340" value={cm ?? 0} />
      <div className="sensor-scale">
        <span>0 cm</span>
        <span>20 cm</span>
        <span>340 cm</span>
      </div>
    </section>
  );
}
export function SensorPage() {
  const [data, setData] = useState(null),
    [selected, setSelected] = useState("");
  const [error, setError] = useState(""),
    [paused, setPaused] = useState(false),
    [refresh, setRefresh] = useState(0);
  const [history, setHistory] = useState([]);
  const historyDevice = useRef(null);
  useEffect(() => {
    if (paused) return;
    let active = true,
      busy = false;
    async function update() {
      if (busy || document.hidden) return;
      busy = true;
      try {
        const next = await request("sensors/measurements/");
        if (active) {
          setData(next);
          setError("");
        }
      } catch {
        if (active)
          setError(
            "Ölçüm bağlantısı kesildi. Son değerler güncel olmayabilir.",
          );
      } finally {
        busy = false;
      }
    }
    update();
    const timer = setInterval(update, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [paused, refresh]);
  const device =
    data?.devices.find((d) => d.id === selected) ||
    data?.devices.find((d) => d.code === "TRN-UNO-001") ||
    data?.devices[0];
  useEffect(() => {
    if (!device) return;
    const changed = historyDevice.current !== device.id;
    historyDevice.current = device.id;
    setHistory((old) => {
      const list = changed ? [] : old;
      if (
        !device.measuredAt ||
        list.some((row) => row.at === device.measuredAt)
      )
        return list;
      return [
        {
          at: device.measuredAt,
          outside: device.outsideCm,
          inside: device.insideCm,
        },
        ...list,
      ].slice(0, 30);
    });
  }, [device?.id, device?.measuredAt]);
  const stale = !!error || !device?.online || device?.stale;
  return (
    <section className="page-grid">
      <div className="filter-bar sensor-toolbar">
        <Field label="Okuyucu">
          <select
            value={device?.id || ""}
            onChange={(e) => setSelected(e.target.value)}
          >
            {data?.devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </Field>
        <Badge status={paused ? "inactive" : stale ? "offline" : "online"}>
          {paused ? "Duraklatıldı" : stale ? "Veri güncel değil" : "Canlı"}
        </Badge>
        <Button icon={paused ? Play : Pause} onClick={() => setPaused(!paused)}>
          {paused ? "Sürdür" : "Duraklat"}
        </Button>
        <Button
          icon={RefreshCw}
          disabled={paused}
          onClick={() => setRefresh((v) => v + 1)}
        >
          Yenile
        </Button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <Empty>Ölçümler yükleniyor...</Empty>}
      {data && !device && <Empty>Tanımlı USB okuyucu yok.</Empty>}
      {device && (
        <>
          <div className="sensor-readings">
            <Sensor
              title="Dış sensör · Giriş"
              pins="TRIG D2 · ECHO D3"
              cm={device.outsideCm}
              stale={stale}
              paused={paused}
            />
            <Sensor
              title="İç sensör · Çıkış"
              pins="TRIG D4 · ECHO D5"
              cm={device.insideCm}
              stale={stale}
              paused={paused}
            />
          </div>
          <div className="sensor-update">
            <Clock3 size={16} />
            <span>Son ölçüm: {time(device.measuredAt)}</span>
            <Badge status={device.online ? "online" : "offline"} />
            <span>Yakın: &lt;20 cm · Uzak: ≥20 cm</span>
          </div>
          <section className="sensor-history">
            <div className="panel-header">
              <h2>Son ölçümler</h2>
              <span>{history.length} / 30</span>
            </div>
            <Table headers={["Saat", "Dış sensör", "İç sensör"]}>
              {history.map((row) => (
                <tr key={row.at}>
                  <td>{time(row.at)}</td>
                  <td>
                    {row.outside == null ? "Ölçüm yok" : `${row.outside} cm`}
                  </td>
                  <td>
                    {row.inside == null ? "Ölçüm yok" : `${row.inside} cm`}
                  </td>
                </tr>
              ))}
            </Table>
            {!history.length && <Empty>Henüz ölçüm ulaşmadı.</Empty>}
          </section>
        </>
      )}
    </section>
  );
}
