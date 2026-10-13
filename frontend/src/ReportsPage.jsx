import React, { useEffect, useState } from "react";
import {
  BarChart3,
  Download,
  Printer,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import {
  Button,
  IconButton,
  Field,
  Metric,
  Table,
  Empty,
  Badge,
  labels,
} from "./ui";
import { request } from "./api.mjs";
import {
  period,
  cleanFilters,
  query,
  chartFilter,
  reportTypes,
  reportLabels,
} from "./report-rules.mjs";
import "./reports.css";

const trNumber = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const tl = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
});
function format(value, kind = "text") {
  if (value == null || value === "") return "—";
  if (kind === "money") return tl.format(value / 100);
  if (kind === "boolean") return value ? "Evet" : "Hayır";
  if (kind === "date") return value.slice(0, 10).split("-").reverse().join(".");
  if (kind === "datetime")
    return new Date(value).toLocaleString("tr-TR", {
      timeZone: "Europe/Istanbul",
      dateStyle: "short",
      timeStyle: "short",
    });
  if (["hours", "minutes", "percent", "decimal", "count"].includes(kind))
    return (
      trNumber.format(value) +
      (kind === "percent"
        ? "%"
        : kind === "hours"
          ? " sa"
          : kind === "minutes"
            ? " dk"
            : "")
    );
  return labels[value] || reportLabels[value] || String(value);
}
function ReportTable({ table }) {
  return (
    <>
      <Table headers={table.columns.map((c) => c.label)}>
        {table.rows.map((row, index) => (
          <tr key={index}>
            {row.map((value, i) => (
              <td key={i}>
                {typeof value === "string" && value.startsWith("{") ? (
                  <details>
                    <summary>İşlem ayrıntısı</summary>
                    <pre>{value}</pre>
                  </details>
                ) : (
                  format(value, table.columns[i].format)
                )}
              </td>
            ))}
          </tr>
        ))}
      </Table>
      {!table.rows.length && <Empty>Bu filtrelerle kayıt bulunamadı.</Empty>}
    </>
  );
}
function Connections({ devices }) {
  return (
    <section className="report-data">
      <h2>Güncel cihaz bağlantıları</h2>
      <Table headers={["Cihaz", "Tür", "Durum", "Son bağlantı"]}>
        {devices.map((d) => (
          <tr key={d.code}>
            <td>{d.code}</td>
            <td>{d.simulated ? "Simülasyon" : "Gerçek cihaz"}</td>
            <td>
              <Badge status={d.status} />
            </td>
            <td>{format(d.lastSeen, "datetime")}</td>
          </tr>
        ))}
      </Table>
      {!devices.length && <Empty>Kayıt bulunamadı.</Empty>}
    </section>
  );
}
function Graph({ graph, onFilter }) {
  const points = graph.points,
    max = Math.max(1, ...points.map((p) => Math.abs(p.value)));
  const names = (p) =>
    p.filter?.weekday != null
      ? [
          "Pazar",
          "Pazartesi",
          "Salı",
          "Çarşamba",
          "Perşembe",
          "Cuma",
          "Cumartesi",
        ][Number(p.label)]
      : p.filter?.hour != null
        ? `${String(p.label).padStart(2, "0")}:00`
        : format(p.label);
  const minValue = Math.min(0, ...points.map((p) => p.value)),
    maxValue = Math.max(1, ...points.map((p) => p.value)),
    span = maxValue - minValue;
  const position = (p, i) => [
    40 + (points.length === 1 ? 240 : (i * 480) / (points.length - 1)),
    180 - ((p.value - minValue) * 155) / span,
  ];
  return (
    <section className="report-chart">
      <h2>{graph.title}</h2>
      {!points.length ? (
        <Empty>Bu dönemde grafik verisi yok.</Empty>
      ) : graph.type === "line" ? (
        <>
          <svg
            viewBox="0 0 560 205"
            role="img"
            aria-label={graph.title}
            className="report-line"
          >
            <line
              x1="40"
              x2="520"
              y1={180 - ((0 - minValue) * 155) / span}
              y2={180 - ((0 - minValue) * 155) / span}
              stroke="#d9dfe4"
            />
            <text x="40" y="14">
              {format(maxValue, graph.format)}
            </text>
            <polyline
              fill="none"
              stroke="#16866c"
              strokeWidth="3"
              points={points.map((p, i) => position(p, i).join(",")).join(" ")}
            />
            {points.map((p, i) => {
              const [x, y] = position(p, i);
              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r="5"
                  fill="#16866c"
                  tabIndex={p.filter ? 0 : -1}
                  aria-label={`${names(p)}: ${format(p.value, graph.format)}`}
                  style={{ cursor: p.filter ? "pointer" : "default" }}
                  onClick={() => p.filter && onFilter(p.filter)}
                  onKeyDown={(e) => {
                    if (p.filter && ["Enter", " "].includes(e.key)) {
                      e.preventDefault();
                      onFilter(p.filter);
                    }
                  }}
                >
                  <title>
                    {names(p)}: {format(p.value, graph.format)}
                  </title>
                </circle>
              );
            })}
          </svg>
          <div className="report-point-list">
            {points.map((p, i) => (
              <button
                key={i}
                disabled={!p.filter}
                title={`${names(p)}: ${format(p.value, graph.format)}`}
                onClick={() => onFilter(p.filter)}
              >
                {names(p)}
                <strong>{format(p.value, graph.format)}</strong>
              </button>
            ))}
          </div>
        </>
      ) : graph.type === "bar" ? (
        <div className="report-columns">
          {points.map((p, i) => (
            <button
              key={i}
              disabled={!p.filter}
              onClick={() => onFilter(p.filter)}
              title={`${names(p)}: ${format(p.value, graph.format)}`}
            >
              <strong>{format(p.value, graph.format)}</strong>
              <span
                className={`report-column-space ${minValue < 0 ? "signed" : ""}`}
              >
                <span
                  className={`report-column-fill ${p.value < 0 ? "negative" : ""}`}
                  style={{
                    height: `${(Math.abs(p.value) / max) * (minValue < 0 ? 50 : 100)}%`,
                    bottom: p.value < 0 ? "auto" : minValue < 0 ? "50%" : "0",
                    top: p.value < 0 ? "50%" : "auto",
                  }}
                />
              </span>
              <span className="report-column-label">{names(p)}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className={`report-bars ${graph.type}`}>
          {points.map((p, i) => (
            <button
              key={i}
              disabled={!p.filter}
              onClick={() => onFilter(p.filter)}
              title={`${names(p)}: ${format(p.value, graph.format)}`}
            >
              <span>{names(p)}</span>
              <span className="report-track">
                <span
                  className={`report-fill ${p.value < 0 ? "negative" : ""}`}
                  style={{ width: `${(Math.abs(p.value) / max) * 100}%` }}
                />
              </span>
              <strong>{format(p.value, graph.format)}</strong>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
function download(file) {
  const bytes = Uint8Array.from(atob(file.base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes]));
  const a = document.createElement("a");
  a.href = url;
  a.download = file.filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const scopeLabels = {
  period: "Seçili dönem",
  asof: "Dönem sonu (bugüne kadar)",
  current: "Güncel kayıt",
  previous: "Önceki eşit uzunlukta dönem",
  lastDay: "Son gün · seçili dönem içinde",
  lastWeek: "Son 7 gün · seçili dönem içinde",
  lastMonth: "Son takvim ayı · seçili dönem içinde",
};
export function ReportsPage({ user }) {
  const admin = user.role === "admin";
  const [options, setOptions] = useState(null),
    [filters, setFilters] = useState({
      ...period("month"),
      tab: admin ? "overview" : "personnel",
      page: 1,
      pageSize: 50,
      granularity: "day",
    }),
    [data, setData] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [exporting, setExporting] = useState(false),
    [preset, setPreset] = useState("month"),
    [reload, setReload] = useState(0),
    [printData, setPrintData] = useState(null);
  useEffect(() => {
    let active = true;
    request("reports/options/")
      .then((o) => {
        if (active) setOptions(o);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [reload]);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError("");
    setData(null);
    request(`reports/?${query(filters)}`, { signal: controller.signal })
      .then((r) => {
        if (!controller.signal.aborted) setData(r);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [filters, reload]);
  useEffect(() => {
    if (!printData) return;
    document.body.classList.add("printing-report");
    const timer = setTimeout(() => window.print(), 100);
    const cleanup = () => {
      document.body.classList.remove("printing-report");
      setPrintData(null);
    };
    window.addEventListener("afterprint", cleanup);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("afterprint", cleanup);
      document.body.classList.remove("printing-report");
    };
  }, [printData]);
  const update = (key, value) => {
    setFilters((f) => ({ ...f, [key]: value, page: 1 }));
    if (["from", "to"].includes(key)) setPreset("custom");
  };
  const tab = filters.tab,
    customType = ["devices", "audit"].includes(tab);
  async function output(kind) {
    setExporting(true);
    setError("");
    try {
      if (kind === "print")
        setPrintData(
          await request(`reports/?${query({ ...filters, all: "true" })}`),
        );
      else
        download(
          await request(
            `reports/export/?${query({ ...filters, format: kind })}`,
          ),
        );
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  }
  return (
    <section className="page-grid reports-page">
      <div className="tabs report-tabs" role="tablist" aria-label="Rapor türü">
        {Object.entries(
          options?.tabs || {
            [filters.tab]: admin ? "Genel özet" : "Personel ve mesai",
          },
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setFilters((f) => cleanFilters(id, f, admin))}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="report-filters">
        <Field label="Dönem">
          <select
            value={preset}
            onChange={(e) => {
              setPreset(e.target.value);
              if (e.target.value !== "custom")
                setFilters((f) => ({
                  ...f,
                  ...period(e.target.value),
                  page: 1,
                }));
            }}
          >
            {[
              ["today", "Bugün"],
              ["yesterday", "Dün"],
              ["week", "Son 7 gün"],
              ["month", "Bu ay"],
              ["previousMonth", "Geçen ay"],
              ["custom", "Özel aralık"],
            ].map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Başlangıç">
          <input
            type="date"
            value={filters.from}
            max={filters.to}
            onChange={(e) => {
              if (e.target.value) update("from", e.target.value);
            }}
          />
        </Field>
        <Field label="Bitiş">
          <input
            type="date"
            value={filters.to}
            min={filters.from}
            onChange={(e) => {
              if (e.target.value) update("to", e.target.value);
            }}
          />
        </Field>
        <Field label="Şube">
          <select
            value={filters.branch || options?.branches[0]?.id || ""}
            onChange={(e) => update("branch", e.target.value)}
          >
            {options?.branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </Field>
        {admin && tab !== "visits" && (
          <Field label={tab === "classes" ? "Antrenör" : "Personel"}>
            <select
              value={filters.person || ""}
              onChange={(e) => update("person", e.target.value)}
            >
              <option value="">Tümü</option>
              {options?.people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {["overview", "finance", "members", "visits", "classes"].includes(
          tab,
        ) && (
          <Field label="Paket">
            <select
              value={filters.planId || ""}
              onChange={(e) => update("planId", e.target.value)}
            >
              <option value="">Tümü</option>
              {options?.plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {["overview", "finance", "stock"].includes(tab) && (
          <Field label="Ürün kategorisi">
            <select
              value={filters.category || ""}
              onChange={(e) => update("category", e.target.value)}
            >
              <option value="">Tümü</option>
              {options?.categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
        )}
        {tab !== "overview" && (
          <Field label="İşlem türü">
            {customType ? (
              <input
                value={filters.type || ""}
                onChange={(e) => update("type", e.target.value)}
                list={`report-${tab}-types`}
                placeholder="Tümü"
              />
            ) : (
              <select
                value={filters.type || ""}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    type: e.target.value,
                    method: [
                      "debt",
                      "overdue",
                      "movements",
                      "critical",
                      "empty",
                    ].includes(e.target.value)
                      ? ""
                      : f.method,
                    page: 1,
                  }))
                }
              >
                <option value="">Tümü</option>
                {reportTypes[tab]?.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}
        {customType && (
          <datalist id={`report-${tab}-types`}>
            {data?.charts
              .flatMap((g) => g.points)
              .filter((p) => p.filter?.type)
              .map((p, i) => (
                <option key={i} value={p.filter.type} />
              ))}
          </datalist>
        )}
        {["overview", "finance", "stock"].includes(tab) &&
          !["debt", "overdue", "movements", "critical", "empty"].includes(
            filters.type,
          ) && (
            <Field label="Ödeme yöntemi">
              <select
                value={filters.method || ""}
                onChange={(e) => update("method", e.target.value)}
              >
                <option value="">Tümü</option>
                {["cash", "pos", "bank", "mixed"].map((v) => (
                  <option key={v} value={v}>
                    {labels[v]}
                  </option>
                ))}
              </select>
            </Field>
          )}
        <Field label="Grafik dönemi">
          <select
            value={filters.granularity}
            onChange={(e) => update("granularity", e.target.value)}
          >
            <option value="day">Günlük</option>
            <option value="week">Haftalık</option>
            <option value="month">Aylık</option>
          </select>
        </Field>
        {tab === "visits" && (
          <>
            <Field label="Saat">
              <select
                value={filters.hour ?? ""}
                onChange={(e) => update("hour", e.target.value)}
              >
                <option value="">Tümü</option>
                {Array.from({ length: 24 }, (_, h) => (
                  <option key={h} value={h}>
                    {h}:00
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Haftanın günü">
              <select
                value={filters.weekday ?? ""}
                onChange={(e) => update("weekday", e.target.value)}
              >
                <option value="">Tümü</option>
                {[
                  "Pazar",
                  "Pazartesi",
                  "Salı",
                  "Çarşamba",
                  "Perşembe",
                  "Cuma",
                  "Cumartesi",
                ].map((d, i) => (
                  <option key={i} value={i}>
                    {d}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}
      </div>
      <div className="report-actions">
        <span>
          {data?.context.branchName || options?.branches[0]?.name} ·{" "}
          {format(filters.from, "date")} – {format(filters.to, "date")} ·
          Türkiye saati
        </span>
        <div>
          <IconButton
            icon={RefreshCw}
            label="Raporu yenile"
            onClick={() => setReload((r) => r + 1)}
            disabled={busy}
          />
          <Button
            icon={Download}
            onClick={() => output("csv")}
            disabled={!data || exporting}
          >
            CSV
          </Button>
          <Button
            icon={Download}
            onClick={() => output("xlsx")}
            disabled={!data || exporting}
          >
            Excel
          </Button>
          <IconButton
            icon={Printer}
            label="Yazdır / PDF"
            onClick={() => output("print")}
            disabled={!data || exporting}
          />
        </div>
      </div>
      {error && (
        <div className="report-error" role="alert">
          {error}
          <Button icon={RefreshCw} onClick={() => setReload((r) => r + 1)}>
            Tekrar dene
          </Button>
        </div>
      )}
      {busy && (
        <div className="report-loading" role="status">
          Rapor hazırlanıyor…
        </div>
      )}
      {exporting && <p role="status">Dosya hazırlanıyor…</p>}
      {data && (
        <>
          <div className="report-metrics">
            {data.metrics.map((m) => (
              <Metric
                key={m.key}
                icon={BarChart3}
                label={m.label}
                value={format(m.value, m.format)}
                detail={scopeLabels[m.scope] || m.scope}
              />
            ))}
          </div>
          <div className="report-charts">
            {data.charts.map((g, i) => (
              <Graph
                key={i}
                graph={g}
                onFilter={(selected) => {
                  setPreset(selected?.date ? "custom" : preset);
                  setFilters((f) => chartFilter(f, selected));
                }}
              />
            ))}
          </div>
          <section className="report-data">
            <div className="section-heading">
              <h2>{data.title} kayıtları</h2>
              <span>{data.table.count.toLocaleString("tr-TR")} kayıt</span>
            </div>
            <ReportTable table={data.table} />
          </section>
          <div className="report-pager">
            <Field label="Sayfa başına">
              <select
                value={filters.pageSize}
                onChange={(e) => update("pageSize", Number(e.target.value))}
              >
                {[25, 50, 100, 200].map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>
            <div>
              <IconButton
                icon={ChevronLeft}
                label="Önceki sayfa"
                disabled={filters.page <= 1}
                onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
              />
              <span>
                {filters.page} /{" "}
                {Math.max(
                  1,
                  Math.ceil(
                    Math.max(data.table.count, data.commands?.count || 0) /
                      filters.pageSize,
                  ),
                )}
              </span>
              <IconButton
                icon={ChevronRight}
                label="Sonraki sayfa"
                disabled={
                  filters.page * filters.pageSize >=
                  Math.max(data.table.count, data.commands?.count || 0)
                }
                onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
              />
            </div>
          </div>
          {data.connections && <Connections devices={data.connections} />}
          {data.commands && (
            <section className="report-data">
              <h2>Tanılama talepleri · {data.commands.count} kayıt</h2>
              <ReportTable table={data.commands} />
            </section>
          )}
          <details className="report-methodology">
            <summary>Hesaplama kapsamı</summary>
            {data.definitions.map((d, i) => (
              <p key={i}>{d}</p>
            ))}
            <p>
              Üretildi: {format(data.context.generatedAt, "datetime")} · Dönem
              sonu: {format(data.context.asOf, "datetime")}
            </p>
          </details>
        </>
      )}
      {printData && (
        <div className="report-print">
          <h1>FitGate · {printData.title}</h1>
          <p>
            {printData.context.branchName} ·{" "}
            {format(printData.context.from, "date")} –{" "}
            {format(printData.context.to, "date")} · Europe/Istanbul
          </p>
          <p>
            Filtreler:{" "}
            {Object.entries(filters)
              .filter(([k, v]) => v && !["page", "pageSize"].includes(k))
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ")}
          </p>
          <Table headers={["Gösterge", "Değer", "Kapsam"]}>
            {printData.metrics.map((m) => (
              <tr key={m.key}>
                <td>{m.label}</td>
                <td>{format(m.value, m.format)}</td>
                <td>{scopeLabels[m.scope]}</td>
              </tr>
            ))}
          </Table>
          <ReportTable table={printData.table} />
          {printData.commands && <ReportTable table={printData.commands} />}
          {printData.connections && (
            <Connections devices={printData.connections} />
          )}
          <div>
            {printData.definitions.map((d, i) => (
              <p key={i}>{d}</p>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
