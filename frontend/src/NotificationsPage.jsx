import React, { useState } from "react";
import {
  Bell,
  AlertTriangle,
  Info,
  Check,
  Plus,
  ArrowUpRight,
} from "lucide-react";
import { Button, Field, Empty, ActionForm } from "./ui";
import { automaticNotices } from "./gym.mjs";
import { displayDate, displayTime } from "./attendance.mjs";
import {
  filterNotices,
  noticeTypes,
  noticeSeverities,
} from "./notification-rules.mjs";
import "./notifications.css";
export function NotificationsPage({
  db,
  run,
  navigate,
  isAdmin,
  canCompose = true,
}) {
  const [filters, setFilters] = useState({
      read: "unread",
      type: "",
      severity: "",
      status: "active",
      from: "",
      to: "",
    }),
    [compose, setCompose] = useState(false),
    [busy, setBusy] = useState(null),
    [error, setError] = useState("");
  const notices = filterNotices(automaticNotices(db), filters);
  const change = (key, value) => setFilters((f) => ({ ...f, [key]: value }));
  async function read(item, open = false) {
    if (busy) return;
    setBusy(item.id);
    setError("");
    try {
      if (!item.read) {
        const result = await run("readNotice", { id: item.id });
        if (!result?.ok) {
          setError(result?.message || "Bildirim okundu olarak işaretlenemedi.");
          return;
        }
      }
      if (open) navigate(item.target, item.memberId, item.targetId);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }
  return (
    <section className="page-grid notifications-page">
      <div className="page-actions">
        <span>{notices.length} bildirim</span>
        {canCompose && (
          <Button icon={Plus} onClick={() => setCompose(true)}>
            Panel bildirimi oluştur
          </Button>
        )}
      </div>
      <div className="notification-filters">
        <Field label="Okunma durumu">
          <select
            value={filters.read}
            onChange={(e) => change("read", e.target.value)}
          >
            <option value="">Tümü</option>
            <option value="unread">Okunmadı</option>
            <option value="read">Okundu</option>
          </select>
        </Field>
        <Field label="Önem derecesi">
          <select
            value={filters.severity}
            onChange={(e) => change("severity", e.target.value)}
          >
            <option value="">Tümü</option>
            {Object.entries(noticeSeverities).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Bildirim türü">
          <select
            value={filters.type}
            onChange={(e) => change("type", e.target.value)}
          >
            <option value="">Tümü</option>
            {Object.entries(noticeTypes).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Bildirim durumu">
          <select
            value={filters.status}
            onChange={(e) => change("status", e.target.value)}
          >
            <option value="">Tümü</option>
            <option value="active">Aktif</option>
            <option value="resolved">Çözüldü</option>
            <option value="inactive">Pasif</option>
          </select>
        </Field>
        <Field label="Başlangıç">
          <input
            type="date"
            value={filters.from}
            max={filters.to || undefined}
            onChange={(e) => change("from", e.target.value)}
          />
        </Field>
        <Field label="Bitiş">
          <input
            type="date"
            value={filters.to}
            min={filters.from || undefined}
            onChange={(e) => change("to", e.target.value)}
          />
        </Field>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="notice-list">
        {notices.map((item) => {
          const severity = item.severity || "info",
            Icon =
              severity === "critical"
                ? AlertTriangle
                : severity === "warning"
                  ? Bell
                  : Info;
          return (
            <article
              className={`notice-row notice-${severity} ${item.read ? "is-read" : ""}`}
              key={item.id}
            >
              <div className="notice-icon">
                <Icon size={20} />
              </div>
              <div className="notice-content">
                {item.target ? (
                  <button
                    className="notice-title"
                    onClick={() => read(item, true)}
                    disabled={Boolean(busy)}
                  >
                    {item.message}
                  </button>
                ) : (
                  <strong>{item.message}</strong>
                )}
                <div className="notice-meta">
                  <span className={`notice-severity ${severity}`}>
                    {noticeSeverities[severity]}
                  </span>
                  <span>{noticeTypes[item.type] || noticeTypes.manual}</span>
                  <span>{item.read ? "Okundu" : "Okunmadı"}</span>
                  <span>
                    {item.at
                      ? `${displayDate(item.at)} ${displayTime(item.at)}`
                      : "Otomatik hatırlatma"}
                  </span>
                  {item.status === "resolved" && (
                    <span>
                      Çözüldü · {displayDate(item.resolvedAt)}{" "}
                      {displayTime(item.resolvedAt)}
                    </span>
                  )}
                  {item.status === "inactive" && <span>Pasif</span>}
                </div>
                {item.resolution && <small>{item.resolution}</small>}
              </div>
              <div className="button-group">
                {item.target && (
                  <Button
                    icon={ArrowUpRight}
                    onClick={() => read(item, true)}
                    disabled={Boolean(busy)}
                  >
                    İlgili kayıt
                  </Button>
                )}
                {!item.read && (
                  <Button
                    icon={Check}
                    onClick={() => read(item)}
                    disabled={Boolean(busy)}
                  >
                    Okundu
                  </Button>
                )}
              </div>
            </article>
          );
        })}
      </div>
      {!notices.length && <Empty>Bu filtrelerle bildirim bulunamadı.</Empty>}
      {compose && (
        <ActionForm
          title="Panel bildirimi"
          fields={[
            { name: "message", label: "Bildirim metni", type: "textarea" },
            {
              name: "severity",
              label: "Önem derecesi",
              options: Object.entries(noticeSeverities)
                .filter(([key]) => key !== "critical" || isAdmin)
                .map(([value, label]) => ({ value, label })),
            },
          ]}
          onClose={() => setCompose(false)}
          onSave={(values) => run("notice", values)}
        />
      )}
    </section>
  );
}
