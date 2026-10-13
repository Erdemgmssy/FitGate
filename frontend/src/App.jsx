import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Bell,
  CalendarDays,
  ChevronRight,
  CreditCard,
  DoorOpen,
  Dumbbell,
  Eye,
  EyeOff,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Plus,
  Settings,
  ShieldCheck,
  Users,
  Wallet,
  X,
  IdCard,
  Building2,
} from "lucide-react";
import {
  buildSeed,
  invoiceDebt,
  automaticNotices,
} from "./gym.mjs";
import { dateKey, displayDate, money } from "./attendance.mjs";
import { SettingsPage } from './SettingsPage';
import {panelPages} from './panel-navigation.mjs';
import {StaffQuickActions} from './StaffQuickActions';
import {
  Button,
  IconButton,
  Metric,
  Badge,
  Table,
  Empty,
  Field,
  Avatar,
} from "./ui";
import {
  MembersPage,
  MemberForm,
  PlansPage,
  CardManager,
} from "./MemberPages";
import {
  FinancePage,
  NotificationsPage,
} from "./BusinessPages";
import { StockPage } from "./StockPage";
import { ClassesPage } from "./ClassesPage";
import { ReportsPage } from "./ReportsPage";
import { AccessPage, ReceptionPage, DevicesPage } from "./AccessPages";
import { PricingSettings } from "./Employees";
import { EmployeesPage } from "./Personnel";
import { request, signIn, operation, pendingOperation, clearPendingOperation } from "./api.mjs";
import { RecentEntries } from "./RecentEntries";
import { SensorPage } from "./SensorPage";
import { AdminDashboard } from "./AdminDashboard";
import { Dialog } from "./ui";

const pages = [
  {
    id: "sensors",
    label: "Sensör ölçümleri",
    icon: Activity,
    roles: ["admin", "staff"],
    group: "OPERASYON",
  },
  {
    id: "dashboard",
    label: "Genel bakış",
    icon: LayoutDashboard,
    roles: ["admin", "staff"],
    group: "YÖNETİM",
  },
  {
    id: "members",
    label: "Üye yönetimi",
    icon: Users,
    roles: ["admin", "staff"],
    group: "YÖNETİM",
  },
  {
    id: "plans",
    label: "Üyelik paketleri",
    icon: Package,
    roles: ["admin"],
    group: "YÖNETİM",
  },
  {
    id: "payments",
    label: "Ödemeler",
    icon: Wallet,
    roles: ["admin", "staff"],
    group: "YÖNETİM",
  },
  {
    id: "access",
    label: "Giriş / çıkış",
    icon: DoorOpen,
    roles: ["admin", "staff"],
    group: "OPERASYON",
  },
  {
    id: "cards",
    label: "Kart yönetimi",
    icon: IdCard,
    roles: ["staff"],
    group: "OPERASYON",
  },
  {
    id: "reception",
    label: "Giriş terminali",
    icon: ShieldCheck,
    roles: ["staff"],
    group: "OPERASYON",
  },
  {
    id: "employees",
    label: "Personel ve mesai",
    icon: Users,
    roles: ["admin", "staff", "trainer"],
    group: "OPERASYON",
  },
  {
    id: "classes",
    label: "Ders ve randevular",
    icon: CalendarDays,
    roles: ["admin", "staff", "trainer"],
    group: "OPERASYON",
  },
  {
    id: "stock",
    label: "Stok ve satış",
    icon: Package,
    roles: ["admin", "staff"],
    group: "OPERASYON",
  },
  {
    id: "devices",
    label: "Cihaz durumu",
    icon: Activity,
    roles: ["admin"],
    group: "OPERASYON",
  },
  {
    id: "reports",
    label: "Raporlar",
    icon: BarChart3,
    roles: ["admin", "staff", "trainer"],
    group: "SİSTEM",
  },
  {
    id: "notifications",
    label: "Bildirimler",
    icon: Bell,
    roles: ["admin", "staff", "trainer"],
    group: "SİSTEM",
  },
  {
    id: "settings",
    label: "Ayarlar",
    icon: Settings,
    roles: ["admin"],
    group: "SİSTEM",
  },
];
export default function App() {
  const [db, setDb] = useState(buildSeed),
    dbRef = useRef(db),
    [user, setUser] = useState(null),
    [page, setPage] = useState("dashboard"),
    [selectedId, setSelectedId] = useState(null),
    [noticeTarget, setNoticeTarget] = useState(null),
    [add, setAdd] = useState(false),
    [toast, setToast] = useState(null),
    [navOpen, setNavOpen] = useState(false),
    [, setClock] = useState(0);
  const busy = useRef(false);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [dashboardMeta, setDashboardMeta] = useState(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [cardAssignmentOpen, setCardAssignmentOpen] = useState(false);
  const [pending, setPending] = useState(
    false,
  );
  const adopt = (data) => {
    dbRef.current = data;
    setDb(data);
    setConnected(true);
  };
  useEffect(()=>{const expired=()=>{setUser(null);setDb(buildSeed());setConnected(false);setAdd(false);setProfileOpen(false);setCardAssignmentOpen(false);};window.addEventListener('fitgate-session-expired',expired);return()=>window.removeEventListener('fitgate-session-expired',expired);},[]);
  useEffect(() => {
    request("auth/me/")
      .then(async ({ user: account }) => {
        adopt((await request("state/")).db);
        setUser(account);
        setPage(account.role === "trainer" ? "employees" : "dashboard");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!user) return;
    if (page === "reports") return;
    if (user.role === "admin" && page === "dashboard") return;
    let polling=false, active=true;
    const controller=new AbortController();
    const timer = setInterval(async () => {
      if (busy.current || polling || document.hidden) return;
      polling=true;
      try {
        const data = await request("state/",{signal:controller.signal});
        if (active && !busy.current) adopt(data.db);
      } catch (error) {
        if (!active) return;
        setConnected(false);
        if(error.status===401){setUser(null);setDb(buildSeed());setAdd(false);setProfileOpen(false);setCardAssignmentOpen(false);}
      } finally {polling=false;}
    }, ['devices','employees','members','cards','access'].includes(page) ? 3000 : 15000);
    return () => {active=false;controller.abort();clearInterval(timer);};
  }, [user, page]);
  useEffect(() => {
    const timer = setInterval(() => setClock((value) => value + 1), 30000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(timer);
  }, [toast]);
  const accessible = panelPages(pages,user,db.personnel?.permissions || user?.personnelPermissions);
  const visible = accessible.filter(item=>item.menu);
  useEffect(()=>setPending(Boolean(user&&pendingOperation(user.id))),[user?.id]);
  useEffect(()=>{if(user&&!accessible.some(item=>item.id===page))setPage(user.role==='trainer'?'employees':'dashboard');},[user?.id,user?.role,page,accessible.map(item=>item.id).join(',')]);
  const navigate = (id, memberId, targetId) => {
    if (!accessible.some((item) => item.id === id)) return;
    setPage(id);
    setNavOpen(false);
    setNoticeTarget(targetId ? {page:id,id:targetId} : null);
    if (memberId) setSelectedId(memberId);
  };
  const run = async (type, payload) => {
    if (busy.current) return { ok: false };
    busy.current = true;
    try {
      const response = await operation(type, payload,user.id);
      adopt(response.db);
      if(type==='changePassword'||type==='manageAccount'&&Number(payload.id)===user.id){setUser(null);setDb(buildSeed());}
      if (type === "addMember") {
        setSelectedId(response.result);
        setPage("members");
      }
      if (
        !["authorize", "confirmPassage", "scanEmployee", "simulateAttendance", "manualAttendance", "readNotice"].includes(
          type,
        )
      )
        setToast({ ok: true, message: "İşlem kaydedildi." });
      return { ok: true, result: response.result };
    } catch (error) {
      if(error.status===401){setUser(null);setDb(buildSeed());setAdd(false);}
      setToast({
        ok: false,
        message:
          error.name === "QuotaExceededError"
            ? "Tarayıcı depolama alanı dolu; işlem kaydedilemedi."
            : error.message,
      });
      return { ok: false, message: error.message };
    } finally {
      busy.current = false;
      setPending(Boolean(pendingOperation(user.id)));
    }
  };
  const isAdmin = user?.role === "admin",
    current = accessible.find((item) => item.id === page) || visible[0];
  if (loading)
    return <main className="login-page">Oturum kontrol ediliyor...</main>;
  if (!user)
    return (
      <LoginPage
        onLogin={async (email, password) => {
          const { user: account } = await signIn(email, password);
          adopt((await request("state/")).db);
          setUser(account);
          setPage(account.role === "trainer" ? "employees" : "dashboard");
        }}
      />
    );
  const notices = automaticNotices(db).filter(
    (item) =>
      !item.read &&
      (item.status || 'active') === 'active' &&
      (isAdmin || !["devices", "stock", "payments"].includes(item.target)),
  );
  const openAdd = () => {
    navigate("members");
    setAdd(true);
  };
  const dashboardActive = isAdmin && page === "dashboard";
  const unreadCount =
    dashboardActive && dashboardMeta ? dashboardMeta.unread : notices.length;
  return (
    <div className="app-shell">
      <aside className={`sidebar ${navOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Dumbbell size={24} />
          </div>
          <div>
            <strong>
              FitGate<span className="brand-dot">.</span>
            </strong>
            <span>SALON YÖNETİMİ</span>
          </div>
        </div>
        <div className="workspace-label">
          <Building2 size={16} />
          <span>Merkez spor salonu</span>
        </div>
        <nav className="nav-list" aria-label="Ana menü">
          {(user.role==='staff'?["GÜNLÜK OPERASYON"]:["YÖNETİM", "OPERASYON", "SİSTEM"]).map((group) => (
            <React.Fragment key={group}>
              <span className="nav-heading">{group}</span>
              {visible
                .filter((item) => item.group === group)
                .map((item) => (
                  <button
                    key={item.id}
                    className={`nav-item ${page === item.id ? "active" : ""}`}
                    title={item.label}
                    aria-label={item.label}
                    aria-current={page === item.id ? "page" : undefined}
                    onClick={() => navigate(item.id)}
                  >
                    <item.icon size={18} />
                    <span>{item.label}</span>
                    {item.id === "notifications" && unreadCount > 0 && (
                      <b className="nav-count">{unreadCount}</b>
                    )}
                  </button>
                ))}
            </React.Fragment>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="connection-dot" />
          <span>
            {connected ? "Sunucu bağlantısı" : "Bağlantı kesildi"}
          </span>
          <small>
            {connected ? "Merkezi kayıt" : "İşlemler sunucu onayı gerektirir"}
          </small>
        </div>
      </aside>
      {navOpen && (
        <button
          className="nav-scrim"
          aria-label="Menüyü kapat"
          onClick={() => setNavOpen(false)}
        />
      )}
      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            <IconButton
              icon={Menu}
              label="Menüyü aç"
              onClick={() => setNavOpen((current) => !current)}
            />
            <span>
              {dashboardActive && dashboardMeta
                ? dashboardMeta.branch
                : db.branches[0]?.name || "Şube"}
            </span>
            <ChevronRight size={14} />
            <strong>{current.label}</strong>
          </div>
          <div className="topbar-actions">
            <span className="notification-control">
              <IconButton
                icon={Bell}
                label={`Bildirimler (${unreadCount})`}
                onClick={() =>
                  dashboardActive
                    ? document.getElementById("dashboard-attention")?.focus()
                    : navigate("notifications")
                }
              />
              {dashboardActive && unreadCount > 0 && (
                <span className="notification-count">{unreadCount}</span>
              )}
            </span>
            <div className="account">
              {dashboardActive ? (
                <button
                  className="profile-control"
                  onClick={() => setProfileOpen(true)}
                  aria-label="Profilimi görüntüle"
                >
                  <strong>{user.name}</strong>
                  <span>Admin</span>
                </button>
              ) : (
                <>
                  <strong>{user.name}</strong>
                  <span>{isAdmin ? "Salon sahibi" : user.role === "trainer" ? "Antrenör" : "Resepsiyon"}</span>
                </>
              )}
            </div>
            <IconButton
              icon={LogOut}
              label="Çıkış yap"
              onClick={async () => {
                try {
                  await request("auth/logout/", { method: "POST" });
                } catch (error) {
                  setToast({ ok: false, message: error.message });
                  return;
                }
                setUser(null);
                setAdd(false);
                setNavOpen(false);
                setToast(null);
                setProfileOpen(false);
                setCardAssignmentOpen(false);
                setDashboardMeta(null);
              }}
            />
          </div>
        </header>
        <div className="page-heading">
          <div>
            <span className="eyebrow">
              {isAdmin ? "Yönetim çalışma alanı" : "Günlük operasyon"}
            </span>
            <h1>{current.label}</h1>
          </div>
          {page === "members" && (
            <Button tone="primary" icon={Plus} onClick={openAdd}>
              Yeni üye
            </Button>
          )}
        </div>
        <div className="page-content">
          {accessible.some(item=>item.id===page)?<>
          {page === "sensors" && (
            <>
              <SensorPage />
              <RecentEntries navigate={navigate} hideMetrics />
            </>
          )}
          {pending && (
            <div className="filter-bar" role="alert">
              <span>Son işlemin sonucu doğrulanamadı.</span>
              <Button
                onClick={async () => {
                  const saved=pendingOperation(user.id);if(!saved)return;
                  try{const result=await request(`actions/status/${saved.key}/`);if(result.status==='completed'){clearPendingOperation(user.id);setPending(false);adopt((await request('state/')).db);setToast({ok:true,message:'İşlem kaydı doğrulandı.'});}else setToast({ok:false,message:'Henüz işlem kaydı bulunamadı. Aynı formdaki isteği tekrar gönderin.'});}catch(error){setToast({ok:false,message:error.message});}
                }}
              >
                Son işlemi doğrula
              </Button>
            </div>
          )}
          {page === "dashboard" && isAdmin && (
            <AdminDashboard
              user={user}
              navigate={navigate}
              onAdd={openAdd}
              onAssignCard={async () => {
                try {
                  adopt((await request("state/")).db);
                  setCardAssignmentOpen(true);
                } catch (error) {
                  setToast({ ok: false, message: error.message });
                }
              }}
              onMeta={setDashboardMeta}
              onConnection={setConnected}
            />
          )}
          {page === "dashboard" && !isAdmin && (
            <><StaffQuickActions db={db} navigate={navigate}/><RecentEntries navigate={navigate} /></>
          )}
          {page === "members" && (
            <MembersPage
              db={db}
              run={run}
              isAdmin={isAdmin}
              onAdd={openAdd}
              actorName={user.name}
              selectedId={selectedId || db.members[0]?.id}
              setSelectedId={setSelectedId}
              navigate={navigate}
            />
          )}
          {page === "plans" && isAdmin && <PlansPage db={db} run={run} />}
          {page === "payments" && (
            <FinancePage
              db={db}
              userId={user.id}
              run={run}
              isAdmin={isAdmin}
              selectedMemberId={selectedId}
              selectedInvoiceId={noticeTarget?.page==='payments' ? noticeTarget.id : null}
            />
          )}
          {page === "access" && (
            <>
              {isAdmin&&<div className="button-group"><Button icon={ShieldCheck} onClick={()=>navigate('reception')}>Giriş terminali</Button><Button icon={IdCard} onClick={()=>navigate('cards')}>RFID kart işlemleri</Button></div>}
              <RecentEntries navigate={navigate} hideMetrics />
              <AccessPage db={db} run={run} isAdmin={isAdmin} />
            </>
          )}
          {page === "cards" && <CardsPage db={db} run={run} />}
          {page === "reception" && (
            <><ReceptionPage db={db} run={run} isAdmin={isAdmin} /><RecentEntries navigate={navigate} hideMetrics/></>
          )}
          {page === "employees" && (
            <EmployeesPage
              db={db}
              user={user}
              selectedEmployeeId={noticeTarget?.page==='employees' ? noticeTarget.id : null}
              onReports={()=>navigate('reports')}
              run={run}
              isAdmin={isAdmin}
            />
          )}
          {page === "classes" && (
            <ClassesPage db={db} run={run} isAdmin={isAdmin} selectedClassId={noticeTarget?.page==='classes' ? noticeTarget.id : null} />
          )}
          {page === "stock" && (
            <StockPage db={db} run={run} isAdmin={isAdmin} focusedProductId={noticeTarget?.page==='stock' ? noticeTarget.id : null} />
          )}
          {page === "devices" && isAdmin && <DevicesPage db={db} run={run} selectedDeviceId={noticeTarget?.page==='devices' ? noticeTarget.id : null} />}
          {page === "reports" && <ReportsPage user={user} />}
          {page === "notifications" && (
            <NotificationsPage
              db={db}
              run={run}
              navigate={navigate}
              isAdmin={isAdmin}
              canCompose={user.role!=='trainer'}
            />
          )}
          {page === "settings" && isAdmin && (
            <SettingsPage db={db} user={user} run={run} navigate={navigate}/>
          )}
          </>:<Empty>Bu sayfa için erişim yetkiniz yok.</Empty>}
        </div>
      </main>
      {add && <MemberForm db={db} run={run} onClose={() => setAdd(false)} />}
      {profileOpen && (
        <Dialog title="Yönetici profili" onClose={() => setProfileOpen(false)}>
          <dl className="dash-profile">
            <dt>Ad soyad</dt>
            <dd>{user.name}</dd>
            <dt>Rol</dt>
            <dd>Admin</dd>
            <dt>Şube</dt>
            <dd>{db.branches[0]?.name}</dd>
          </dl>
        </Dialog>
      )}
      {cardAssignmentOpen && (
        <Dialog
          title="RFID Kart Tanımla"
          onClose={() => setCardAssignmentOpen(false)}
        >
          <CardsPage db={db} run={run} />
        </Dialog>
      )}
      {toast && (
        <div
          className={`toast ${toast.ok ? "success" : "error"}`}
          role={toast.ok ? "status" : "alert"}
        >
          <span>{toast.message}</span>
          <IconButton
            icon={X}
            label="Uyarıyı kapat"
            onClick={() => setToast(null)}
          />
        </div>
      )}
    </div>
  );
}
function LoginPage({ onLogin }) {
  const [visible, setVisible] = useState(false),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  return (
    <main className="login-page">
      <div className="login-brand">
        <div className="brand-mark">
          <Dumbbell size={27} />
        </div>
        <strong>
          FitGate<span>.</span>
        </strong>
      </div>
      <form
        className="login-form"
        onSubmit={async (event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          setSaving(true);
          try {
            await onLogin(
              form.get("email").trim().toLowerCase(),
              form.get("password"),
            );
          } catch (error) {
            setError(error.message);
          } finally {
            setSaving(false);
          }
        }}
      >
        <span className="eyebrow">SALON YÖNETİMİ</span>
        <h1>Hoş geldiniz</h1>
        <p className="login-subtitle">Çalışma alanınıza giriş yapın.</p>
        <Field label="E-posta">
          <input
            name="email"
            type="email"
            required
            autoComplete="username"
            placeholder="ornek@salon.com"
            onChange={() => setError("")}
          />
        </Field>
        <Field label="Şifre">
          <div className="password-input">
            <input
              name="password"
              type={visible ? "text" : "password"}
              required
              autoComplete="current-password"
              placeholder="Şifreniz"
              onChange={() => setError("")}
            />
            <IconButton
              icon={visible ? EyeOff : Eye}
              label={visible ? "Şifreyi gizle" : "Şifreyi göster"}
              type="button"
              onClick={() => setVisible((current) => !current)}
            />
          </div>
        </Field>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <Button
          type="submit"
          tone="primary"
          icon={ArrowUpRight}
          disabled={saving}
        >
          {saving ? "Giriş yapılıyor..." : "Giriş yap"}
        </Button>
      </form>
      <span className="login-footer">Üyelik · Finans · Operasyon</span>
    </main>
  );
}
function CardsPage({ db, run }) {
  if(!db.members.length&&db.memberDirectory)db={...db,members:db.memberDirectory};
  const [memberId, setMemberId] = useState(db.members[0]?.id);
  const member = db.members.find((item) => item.id === memberId);
  return (
    <section className="page-grid">
      {!db.members.length && (
        <Empty>Kart tanımlamak için önce bir üye ekleyin.</Empty>
      )}
      <Field label="Üye">
        <select
          value={memberId}
          onChange={(event) => setMemberId(event.target.value)}
        >
          {db.members.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} / {item.number}
            </option>
          ))}
        </select>
      </Field>
      {member && (
        <CardManager key={member.id} db={db} member={member} run={run} />
      )}
    </section>
  );
}
