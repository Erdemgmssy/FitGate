import React, { useEffect, useState } from "react";
import { DoorOpen, Users, Activity, RefreshCw } from "lucide-react";
import { request } from "./api.mjs";
import { Button, Metric, Table, Badge, Empty } from "./ui";
import { displayDate, displayTime } from "./attendance.mjs";

export function RecentEntries({ navigate, hideMetrics = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true,
      inFlight = false;
    async function update() {
      if (inFlight || document.hidden) return;
      inFlight = true;
      try {
        const result = await request("access/recent-entries/");
        if (active) {
          setData(result);
          setError("");
        }
      } catch {
        if (active)
          setError(
            "Geçiş bağlantısı kesildi; gösterilen kayıtlar güncel olmayabilir.",
          );
      } finally {
        inFlight = false;
      }
    }
    update();
    const timer = setInterval(update, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [refresh]);
  return (
    <section className="page-grid">
      {!hideMetrics && (
        <div className="stat-row recent-stats">
          <Metric
            icon={Users}
            label="Şu an içeride"
            value={data?.inside ?? "—"}
          />
          <Metric
            icon={DoorOpen}
            label="Bugünkü girişler"
            value={data?.today ?? "—"}
          />
          <Metric
            icon={Activity}
            label="Son giriş"
            value={data?.entries[0] ? displayTime(data.entries[0].entry) : "—"}
            detail={data?.entries[0]?.name}
          />
        </div>
      )}
      <section className="panel recent-entries">
        <div className="panel-header">
          <h2>Son 10 giriş / çıkış</h2>
          <div className="button-group">
            <Button
              icon={RefreshCw}
              aria-label="Geçiş listesini yenile"
              onClick={() => setRefresh((v) => v + 1)}
            >
              Yenile
            </Button>
            <Button icon={Users} onClick={() => navigate("members")}>
              Üye yönetimi
            </Button>
          </div>
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {!data && !error && <Empty>Geçişler yükleniyor...</Empty>}
        {data && (
          <Table headers={["Üye", "İşlem", "Tarih / saat", "Geçiş noktası"]}>
            {data.movements.map((item) => (
              <tr key={item.id}>
                <td>
                  <button
                    className="member-link"
                    onClick={() => navigate("members", item.memberId)}
                  >
                    <span>
                      <strong>{item.name}</strong>
                      <small>{item.number}</small>
                    </span>
                  </button>
                </td>
                <td>
                  <Badge
                    status={item.direction === "entry" ? "active" : "inactive"}
                  >
                    {item.direction === "entry" ? "Giriş" : "Çıkış"}
                  </Badge>
                </td>
                <td>
                  {displayTime(item.at)}
                  <small>{displayDate(item.at)}</small>
                </td>
                <td>{item.device}</td>
              </tr>
            ))}
          </Table>
        )}
        {data && !data.movements.length && (
          <Empty>Henüz tamamlanmış giriş veya çıkış yok.</Empty>
        )}
      </section>
      <section className="panel recent-attempts">
        <div className="panel-header">
          <h2>Son 10 kart okutma</h2>
        </div>
        {data && (
          <Table headers={["Üye / kart", "İşlem", "Saat", "Sonuç", "Açıklama"]}>
            {data.attempts.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.name}</strong>
                  <small>{item.uid}</small>
                </td>
                <td>{item.direction === "entry" ? "Giriş" : "Çıkış"}</td>
                <td>
                  {displayTime(item.at)}
                  <small>{displayDate(item.at)}</small>
                </td>
                <td>
                  <Badge
                    status={
                      item.status === "confirmed"
                        ? "active"
                        : ["rejected", "expired"].includes(item.status)
                          ? "rejected"
                          : "pending"
                    }
                  >
                    {item.status === "confirmed"
                      ? "Tamamlandı"
                      : item.status === "expired"
                        ? "Tamamlanmadı"
                        : item.status === "rejected"
                          ? "Reddedildi"
                          : "Geçiş bekleniyor"}
                  </Badge>
                </td>
                <td>
                  {item.reason}
                  <small>{item.device}</small>
                </td>
              </tr>
            ))}
          </Table>
        )}
        {data && !data.attempts.length && <Empty>Henüz kart okutulmadı.</Empty>}
      </section>
    </section>
  );
}
