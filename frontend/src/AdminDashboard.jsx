import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Bell,
  CalendarDays,
  CreditCard,
  DoorOpen,
  IdCard,
  Plus,
  RefreshCw,
  Search,
  Users,
  Wallet,
  Radio,
} from "lucide-react";
import { request } from "./api.mjs";
import { dateKey, displayDate, displayTime, money } from "./attendance.mjs";
import { Badge, Button, Dialog, Empty, Field, Metric, Table } from "./ui";

function InsideList({ rows, navigate, now, limit }) {
  const [search, setSearch] = useState("");
  const filtered = rows.filter((row) =>
    `${row.name} ${row.number}`
      .toLocaleLowerCase("tr-TR")
      .includes(search.toLocaleLowerCase("tr-TR")),
  );
  return (
    <>
      <div className="dash-search">
        <Search size={16} />
        <input
          aria-label="İçerideki üyeleri ara"
          placeholder="Üye adı veya numarası"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <Table headers={["Üye", "Giriş", "Süre"]}>
        {filtered.slice(0, limit || filtered.length).map((row) => {
          const minutes = Math.max(
            0,
            Math.floor((now - new Date(row.entry).getTime()) / 60000),
          );
          return (
            <tr key={row.id}>
              <td>
                <button
                  className="member-link"
                  onClick={() => navigate("members", row.memberId)}
                >
                  <span>
                    <strong>{row.name}</strong>
                    <small>{row.number}</small>
                  </span>
                </button>
              </td>
              <td>
                {displayTime(row.entry)}
                <small>{displayDate(row.entry)}</small>
              </td>
              <td>
                {Math.floor(minutes / 60)} sa {minutes % 60} dk
              </td>
            </tr>
          );
        })}
      </Table>
      {!filtered.length && (
        <Empty>
          {search ? "Aramaya uygun üye yok." : "Şu an salonda üye yok."}
        </Empty>
      )}
    </>
  );
}

function AttentionList({ rows, navigate }) {
  return (
    <div className="dash-attention-list">
      {rows.map((row) => (
        <button
          key={row.id}
          className={`attention-row ${row.severity}`}
          onClick={() => navigate(row.target, row.memberId)}
        >
          <span className="attention-marker" />
          <span>{row.message}</span>
          <ArrowUpRight size={15} />
        </button>
      ))}
    </div>
  );
}

function measurement(value) {
  return typeof value === "number" &&
    Number.isFinite(value) &&
    value >= 2 &&
    value <= 340
    ? `${value} cm`
    : "Veri yok";
}

function deviceDistance(row, key, now) {
  const at = new Date(row.measurements?.at).getTime();
  if (
    row.simulated ||
    row.controller !== "online" ||
    !Number.isFinite(at) ||
    now - at >= 4000 ||
    now < at
  )
    return "Veri yok";
  return measurement(row.measurements?.[key]);
}

export function AdminDashboard({
  user,
  navigate,
  onAdd,
  onAssignCard,
  onMeta,
  onConnection,
}) {
  const [day, setDay] = useState(dateKey()),
    [branch, setBranch] = useState(user.branchId);
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [refresh, setRefresh] = useState(0);
  const [showInside, setShowInside] = useState(false),
    [now, setNow] = useState(Date.now());
  const [showAttention, setShowAttention] = useState(false);
  const clock = useRef({ server: Date.now(), sampled: performance.now() });
  useEffect(() => {
    const timer = setInterval(
      () =>
        setNow(
          clock.current.server + performance.now() - clock.current.sampled,
        ),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let active = true,
      busy = false,
      controller;
    async function update() {
      if (busy || document.hidden) return;
      busy = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      try {
        const result = await request(
          `admin/dashboard/?date=${day}&branch=${branch}`,
          { signal: controller.signal },
        );
        if (active) {
          setData(result);
          setError("");
          setNow(new Date(result.serverTime).getTime());
          clock.current = {
            server: new Date(result.serverTime).getTime(),
            sampled: performance.now(),
          };
          onMeta({ unread: result.unread, branch: result.branch.name });
          onConnection(true);
        }
      } catch (failure) {
        if (active) {
          setError(
            failure.name === "AbortError"
              ? "Sunucu yanıtı zaman aşımına uğradı."
              : failure.message || "Sunucu bağlantısı kesildi.",
          );
          onConnection(false);
        }
      } finally {
        clearTimeout(timeout);
        busy = false;
      }
    }
    update();
    const timer = setInterval(update, 3000);
    document.addEventListener("visibilitychange", update);
    return () => {
      active = false;
      controller?.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", update);
    };
  }, [day, branch, refresh, onMeta, onConnection]);
  const current = data?.date === day && data?.branch.id === branch;
  const metrics = current ? data.metrics : null;
  const chartMax = Math.max(1, ...(data?.hourly || []).map((row) => row.count));
  const chartHasData = data?.hourly.some((row) => row.count > 0);
  const chartTicks = [...new Set([chartMax, Math.floor(chartMax / 2), 0])];
  const metricRows = metrics
    ? [
        [
          Users,
          "Toplam üye",
          metrics.members,
          `${metrics.activeMembers} aktif üye`,
          "members",
        ],
        [
          DoorOpen,
          "Şu an salonda",
          metrics.inside,
          `${metrics.capacity} kişi kapasite · %${metrics.capacity ? Math.round((metrics.inside / metrics.capacity) * 100) : 0}`,
          "inside",
        ],
        [
          Activity,
          day === dateKey() ? "Bugünkü Girişler" : "Seçili Gün Girişleri",
          metrics.entries + (metrics.manualEntries || 0),
          `${metrics.entries} fiziksel · ${metrics.manualEntries || 0} manuel · ${metrics.rejectedEntries} reddedilen`,
          "access",
        ],
        [
          CalendarDays,
          "Bitecek üyelikler",
          metrics.ending,
          "Önümüzdeki 7 gün · canlı",
          "members",
        ],
        [
          Wallet,
          "Günlük tahsilat",
          money(metrics.dailyCents / 100),
          displayDate(day),
          "payments",
        ],
        [
          Wallet,
          "7 günlük tahsilat",
          money(metrics.weeklyCents / 100),
          "Seçili gün dahil son 7 gün",
          "payments",
        ],
        [
          CreditCard,
          "Aylık tahsilat",
          money(metrics.monthlyCents / 100),
          "Seçili ay · net tahsilat",
          "payments",
        ],
        [
          Wallet,
          "Bekleyen alacak",
          money(metrics.debtCents / 100),
          "Güncel tahsil edilmemiş bakiye",
          "payments",
        ],
      ]
    : [];
  return (
    <section
      className="admin-dashboard page-grid"
      aria-busy={!current && !error}
    >
      <div className="overview-toolbar">
        <div
          className={`dash-connection ${error ? "offline" : ""}`}
          role="status"
        >
          <span className="connection-dot" />
          {error
            ? "Sunucu bağlantısı kesildi"
            : data
              ? "Sunucu bağlı"
              : "Sunucuya bağlanıyor"}
          {data && <small>Son güncelleme {displayTime(data.serverTime)}</small>}
        </div>
        <div className="button-group">
          <Field label="Şube">
            <select value={branch} onChange={(e) => setBranch(e.target.value)}>
              {(
                data?.branches || [{ id: user.branchId, name: "Yetkili şube" }]
              ).map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Tarih">
            <input
              type="date"
              value={day}
              onChange={(e) => {
                if (e.target.value) setDay(e.target.value);
              }}
            />
          </Field>
          <Button
            icon={RefreshCw}
            aria-label="Dashboard'u yenile"
            onClick={() => setRefresh((v) => v + 1)}
          >
            Yenile
          </Button>
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}{" "}
          {data
            ? "Son veriler gösteriliyor; güncel olmayabilir."
            : "Dashboard verileri alınamadı."}
        </p>
      )}
      {!current && !error && <Empty>Salon özeti yükleniyor...</Empty>}
      {current && (
        <>
          <div className="dash-metrics">
            {metricRows.map(([icon, label, value, detail, target], i) => (
              <button
                className="dash-metric-button"
                key={label}
                onClick={() =>
                  target === "inside" ? setShowInside(true) : navigate(target)
                }
              >
                <Metric
                  icon={icon}
                  label={label}
                  value={value}
                  detail={detail}
                  tone={
                    ["", "green", "blue", "amber", "", "", "green", "coral"][i]
                  }
                />
              </button>
            ))}
          </div>
          <div className="quick-actions dash-actions">
            <Button icon={Plus} tone="primary" onClick={onAdd}>
              Yeni üye ekle
            </Button>
            <Button icon={CalendarDays} onClick={() => navigate("members")}>
              Üyelik sat / yenile
            </Button>
            <Button icon={Wallet} onClick={() => navigate("payments")}>
              Ödeme al
            </Button>
            <Button icon={IdCard} onClick={onAssignCard}>
              RFID Kart Tanımla
            </Button>
            <Button icon={DoorOpen} onClick={() => navigate("access")}>
              Giriş-çıkış kayıtları
            </Button>
          </div>
          <div className="dashboard-grid dash-top-grid">
            <section className="chart-section">
              <div className="section-header">
                <div>
                  <h2>Giriş yoğunluğu</h2>
                  <small>
                    {displayDate(day)} · doğrulanmış fiziksel girişler
                  </small>
                </div>
                <Badge status="active">{metrics.entries} giriş</Badge>
              </div>
              {chartHasData ? (
                <div
                  className="dash-chart"
                  role="img"
                  aria-label="Saatlere göre doğrulanmış fiziksel girişler"
                >
                  <div className="dash-chart-axis">
                    {chartTicks.map((value) => (
                      <span key={value}>{value}</span>
                    ))}
                  </div>
                  <div
                    className="hour-chart"
                    style={{
                      gridTemplateColumns: `repeat(${data.hourly.length}, minmax(20px, 1fr))`,
                    }}
                  >
                    {data.hourly.map((row) => (
                      <button
                        key={row.hour}
                        title={`${String(row.hour).padStart(2, "0")}:00 · ${row.count} giriş`}
                        aria-label={`${row.hour}:00, ${row.count} giriş`}
                        onClick={() => navigate("access")}
                      >
                        <span className="bar-value">{row.count || ""}</span>
                        <span className="chart-track">
                          <span
                            className="chart-bar"
                            style={{
                              height: `${(row.count / chartMax) * 100}%`,
                            }}
                          />
                        </span>
                        <small>{String(row.hour).padStart(2, "0")}</small>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="dash-chart-empty">
                  <Empty>Seçili tarihte doğrulanmış giriş yok.</Empty>
                </div>
              )}
            </section>
            <section
              className="attention-section"
              id="dashboard-attention"
              tabIndex={-1}
            >
              <div className="section-header">
                <h2>Dikkat gerektirenler</h2>
                <Bell size={18} />
              </div>
              <AttentionList
                rows={data.attention.slice(0, 5)}
                navigate={navigate}
              />
              {!data.attention.length && (
                <Empty>Müdahale gerektiren durum yok.</Empty>
              )}
              <Button
                icon={ArrowUpRight}
                onClick={() => setShowAttention(true)}
              >
                Tüm Bildirimleri Gör
              </Button>
            </section>
          </div>
          <div className="dashboard-grid dash-bottom-grid">
            <section>
              <div className="section-header">
                <div>
                  <h2>Son 10 geçiş işlemi</h2>
                  <small>{displayDate(day)}</small>
                </div>
                <Button icon={ArrowUpRight} onClick={() => navigate("access")}>
                  Tüm kayıtlar
                </Button>
              </div>
              <Table headers={["Üye", "İşlem", "Saat", "Cihaz", "Sonuç"]}>
                {data.events.map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.memberId ? (
                        <button
                          className="member-link"
                          onClick={() => navigate("members", row.memberId)}
                        >
                          <span>
                            <strong>{row.name}</strong>
                            <small>{row.number}</small>
                          </span>
                        </button>
                      ) : (
                        <>
                          <strong>{row.name}</strong>
                          <small>{row.number}</small>
                        </>
                      )}
                    </td>
                    <td>
                      {row.direction === "entry" ? "Giriş" : "Çıkış"}
                      <small>{row.kind === 'prototype' ? 'Tek sensör prototipi' : row.kind === 'manual' ? 'Manuel işlem' : row.kind === 'correction' ? 'Admin düzeltmesi' : 'Fiziksel geçiş'}</small>
                    </td>
                    <td>{displayTime(row.at)}</td>
                    <td>{row.device}</td>
                    <td>
                      <Badge status="confirmed">Tamamlandı</Badge>
                    </td>
                  </tr>
                ))}
              </Table>
              {!data.events.length && (
                <Empty>Seçili tarihte geçiş kaydı yok.</Empty>
              )}
            </section>
            <section>
              <div className="section-header">
                <h2>Şu an içeride</h2>
                <Badge status="active">{metrics.inside} kişi</Badge>
              </div>
              <InsideList
                rows={data.inside}
                navigate={navigate}
                now={now}
                limit={6}
              />
              <Button icon={Users} onClick={() => setShowInside(true)}>
                Tümünü görüntüle ({metrics.inside})
              </Button>
            </section>
          </div>
          <section className="dash-devices">
            <div className="section-header">
              <h2>Cihaz durumu</h2>
              <Button icon={Radio} onClick={() => navigate("devices")}>
                Cihazları görüntüle
              </Button>
            </div>
            <Table
              headers={[
                "Cihaz",
                "RFID okuyucu",
                "Servo turnike",
                "Mesafe sensörleri",
                "Son haberleşme",
                "Durum",
              ]}
            >
              {data.devices.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.name}</strong>
                    <small>{row.code}</small>
                  </td>
                  <td>
                    {row.rfid === "online" &&
                    !row.simulated &&
                    row.controller === "online"
                      ? "Doğrulandı"
                      : "Veri yok"}
                  </td>
                  <td>
                    {row.servo === "online" &&
                    !row.simulated &&
                    row.controller === "online"
                      ? "Doğrulandı"
                      : "Veri yok"}
                  </td>
                  <td>
                    <span>Dış: {deviceDistance(row, "outsideCm", now)}</span>
                    <small>İç: {deviceDistance(row, "insideCm", now)}</small>
                  </td>
                  <td>
                    {row.lastSeen ? (
                      <>
                        {displayTime(row.lastSeen)}
                        <small>{displayDate(row.lastSeen)}</small>
                      </>
                    ) : (
                      "Henüz haberleşme yok"
                    )}
                  </td>
                  <td>
                    <Badge
                      status={
                        row.state === "online"
                          ? "online"
                          : row.state === "fault"
                            ? "rejected"
                            : "inactive"
                      }
                    >
                      {
                        {
                          online: "Aktif",
                          offline: "Çevrimdışı",
                          fault: "Hatalı",
                          simulated: "Simülasyon",
                          disabled: "Devre dışı",
                          unknown: "Doğrulanmadı",
                        }[row.state]
                      }
                    </Badge>
                  </td>
                </tr>
              ))}
            </Table>
            {!data.devices.length && <Empty>Tanımlı cihaz yok.</Empty>}
          </section>
        </>
      )}
      {showInside && data && (
        <Dialog
          title={`İçerideki üyeler (${data.inside.length})`}
          onClose={() => setShowInside(false)}
        >
          <InsideList
            rows={data.inside}
            now={now}
            navigate={(...args) => {
              setShowInside(false);
              navigate(...args);
            }}
          />
        </Dialog>
      )}
      {showAttention && data && (
        <Dialog title="Tüm Bildirimler" onClose={() => setShowAttention(false)}>
          <AttentionList
            rows={data.attention}
            navigate={(...args) => {
              setShowAttention(false);
              navigate(...args);
            }}
          />
          {!data.attention.length && (
            <Empty>Müdahale gerektiren durum yok.</Empty>
          )}
        </Dialog>
      )}
    </section>
  );
}
