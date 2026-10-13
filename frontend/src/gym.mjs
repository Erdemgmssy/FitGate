import { dateKey } from "./attendance.mjs";
export const uid = () => crypto.randomUUID();
export const cents = (value) => Math.round(Number(value) * 100);
export const dayDiff = (from, to) =>
  Math.round(
    (Date.UTC(...from.split("-").map((n, i) => Number(n) - (i === 1 ? 1 : 0))) -
      Date.UTC(...to.split("-").map((n, i) => Number(n) - (i === 1 ? 1 : 0)))) /
      86400000,
  );
export function addDays(day, count) {
  const date = new Date(`${day}T12:00:00`);
  date.setDate(date.getDate() + count);
  return dateKey(date);
}
export function addMonths(day, count) {
  const date = new Date(`${day}T12:00:00`);
  const targetDay = date.getDate();
  date.setDate(1);
  date.setMonth(date.getMonth() + count);
  date.setDate(
    Math.min(
      targetDay,
      new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate(),
    ),
  );
  return dateKey(date);
}
export function subscriptionStatus(sub, today = dateKey()) {
  if (!sub) return "none";
  if (sub.status === "cancelled") return sub.status;
  if (sub.start > today) return "pending";
  if (
    sub.freezePeriods?.some(
      (period) => period.start <= today && (!period.end || today < period.end),
    ) ||
    sub.legacyFrozen ||
    (sub.status === "frozen" && !Array.isArray(sub.freezePeriods))
  )
    return "frozen";
  if (!sub.end) return "active";
  if (sub.end < today) return "expired";
  return dayDiff(sub.end, today) <= 7 ? "ending" : "active";
}
export function currentSubscription(db, memberId, today = dateKey()) {
  const list = db.subscriptions
    .filter((sub) => sub.memberId === memberId)
    .slice()
    .sort(
      (a, b) =>
        (a.end || "9999-12-31").localeCompare(b.end || "9999-12-31") ||
        a.start.localeCompare(b.start) ||
        (a.createdAt || "").localeCompare(b.createdAt || "") ||
        a.id.localeCompare(b.id),
    );
  return (
    list.find((sub) =>
      ["active", "ending", "frozen"].includes(subscriptionStatus(sub, today)),
    ) ||
    list.find((sub) => subscriptionStatus(sub, today) === "pending") ||
    list.at(-1)
  );
}
export function paidCents(db, invoiceId) {
  const invoice=db.invoices.find(row=>row.id===invoiceId);
  if(db.source==='server'&&Number.isSafeInteger(invoice?.netPaidCents))return invoice.netPaidCents;
  return db.payments
    .filter((payment) => payment.invoiceId === invoiceId)
    .reduce(
      (sum, payment) =>
        sum +
        payment.amountCents -
        db.refunds
          .filter((refund) => refund.paymentId === payment.id)
          .reduce((a, refund) => a + refund.amountCents, 0),
      0,
    );
}
export const invoiceDebt = (db, invoice) =>
  invoice.status === "cancelled"
    ? 0
    : Math.max(0, invoice.totalCents - paidCents(db, invoice.id));
export const memberDebt = (db, memberId) =>
  db.invoices
    .filter((invoice) => invoice.memberId === memberId)
    .reduce((sum, invoice) => sum + invoiceDebt(db, invoice), 0);
export function installmentRows(db, invoice) {
  let paid = paidCents(db, invoice.id);
  return db.installments
    .filter((item) => item.invoiceId === invoice.id && !item.archived)
    .sort((a, b) => a.due.localeCompare(b.due))
    .map((item) => {
      const allocated = Math.min(item.amountCents, Math.max(0, paid));
      paid -= allocated;
      return {
        ...item,
        remaining:
          invoice.status === "cancelled" ? 0 : item.amountCents - allocated,
      };
    });
}
export function buildSeed(now = new Date()) {
  const today = dateKey(now),
    yesterday = addDays(today, -1);
  const members = [
    {
      id: "m1",
      number: "GYM-000001",
      name: "Ayşe Yılmaz",
      phone: "0532 111 22 33",
      email: "ayse@example.com",
      active: true,
      blocked: false,
      trainer: "Mert Kaya",
      note: "",
      photo: "",
      createdAt: `${today}T08:00:00`,
      branchId: "b1",
      consent: true,
    },
    {
      id: "m2",
      number: "GYM-000002",
      name: "Mehmet Demir",
      phone: "0544 987 65 43",
      email: "",
      active: true,
      blocked: false,
      trainer: "Elif Arslan",
      note: "",
      photo: "",
      createdAt: `${yesterday}T08:00:00`,
      branchId: "b1",
      consent: true,
    },
    {
      id: "m3",
      number: "GYM-000003",
      name: "Zeynep Acar",
      phone: "0555 333 77 88",
      email: "",
      active: true,
      blocked: false,
      trainer: "Mert Kaya",
      note: "",
      photo: "",
      createdAt: `${yesterday}T08:00:00`,
      branchId: "b1",
      consent: true,
    },
    {
      id: "m4",
      number: "GYM-000004",
      name: "Can Özkan",
      phone: "0537 222 10 10",
      email: "",
      active: true,
      blocked: false,
      trainer: "",
      note: "",
      photo: "",
      createdAt: `${yesterday}T08:00:00`,
      branchId: "b1",
      consent: true,
    },
  ];
  const plans = [
    {
      id: "p1",
      name: "Standart Aylık",
      days: 30,
      price: 1200,
      active: true,
      sessions: null,
      from: "06:00",
      to: "23:00",
      weekdays: [0, 1, 2, 3, 4, 5, 6],
      freezeDays: 14,
      description: "Fitness alanı",
    },
    {
      id: "p2",
      name: "3 Aylık",
      days: 90,
      price: 3200,
      active: true,
      sessions: null,
      from: "06:00",
      to: "23:00",
      weekdays: [0, 1, 2, 3, 4, 5, 6],
      freezeDays: 30,
      description: "Fitness ve grup dersleri",
    },
    {
      id: "p3",
      name: "6 Aylık",
      days: 180,
      price: 5900,
      active: true,
      sessions: null,
      from: "06:00",
      to: "23:00",
      weekdays: [0, 1, 2, 3, 4, 5, 6],
      freezeDays: 30,
      description: "Uzun dönem üyelik",
    },
    {
      id: "p4",
      name: "10 Seans",
      days: 90,
      price: 2000,
      active: true,
      sessions: 10,
      from: "06:00",
      to: "23:00",
      weekdays: [0, 1, 2, 3, 4, 5, 6],
      freezeDays: 0,
      description: "10 doğrulanmış giriş",
    },
  ];
  const subscriptions = members.map((member, index) => ({
    id: `sub${index + 1}`,
    memberId: member.id,
    planId: plans[index % 3].id,
    planName: plans[index % 3].name,
    start: addDays(today, -20),
    end: addDays(today, [45, 5, 90, -3][index]),
    status: "active",
    priceCents: cents(plans[index % 3].price),
    remaining: null,
    rules: structuredClone(plans[index % 3]),
    frozenAt: null,
    frozenDays: 0,
  }));
  const invoices = subscriptions.map((sub, index) => ({
    id: `inv${index + 1}`,
    number: `SAT-00000${index + 1}`,
    memberId: sub.memberId,
    subscriptionId: sub.id,
    totalCents: sub.priceCents,
    discountCents: 0,
    status: "open",
    createdAt: `${today}T08:00:00`,
  }));
  const payments = invoices.slice(0, 3).map((invoice, index) => ({
    id: `pay${index + 1}`,
    number: `ODM-00000${index + 1}`,
    invoiceId: invoice.id,
    amountCents: index === 1 ? 100000 : invoice.totalCents,
    method: index === 0 ? "cash" : "pos",
    actor: "Salon Yönetimi",
    at: `${today}T08:30:00`,
    note: "Açılış demo kaydı",
  }));
  return {
    version: 2,
    members,
    plans,
    subscriptions,
    invoices,
    payments,
    refunds: [],
    freezes: [],
    installments: invoices.map((invoice, index) => ({
      id: `ins${index + 1}`,
      invoiceId: invoice.id,
      due: addDays(today, index === 1 ? -2 : 5),
      amountCents: invoice.totalCents,
    })),
    cards: members.map((member, index) => ({
      id: `c${index + 1}`,
      uid: ["RFID-82913", "RFID-44019", "RFID-12004", "RFID-77561"][index],
      memberId: member.id,
      status: "active",
      at: now.toISOString(),
    })),
    visits: [
      {
        id: "v1",
        memberId: "m1",
        entry: `${today}T09:00:00`,
        exit: null,
        deviceId: "d1",
        method: "RFID",
      },
      {
        id: "v2",
        memberId: "m3",
        entry: `${yesterday}T16:00:00`,
        exit: `${yesterday}T17:15:00`,
        deviceId: "d1",
        method: "RFID",
      },
    ],
    attempts: [
      {
        id: "a1",
        memberId: "m1",
        card: "RFID-82913",
        at: `${today}T09:00:00`,
        direction: "entry",
        deviceId: "d1",
        status: "confirmed",
        reason: "Geçiş tamamlandı",
      },
      {
        id: "a2",
        memberId: "m4",
        card: "RFID-77561",
        at: `${today}T09:10:00`,
        direction: "entry",
        deviceId: "d1",
        status: "rejected",
        reason: "Üyelik süresi dolmuş",
      },
    ],
    grants: [],
    devices: [
      {
        id: "d1",
        code: "TRN-001",
        name: "Ana giriş",
        branchId: "b1",
        status: "online",
        direction: "both",
        sensor: "normal",
        mode: "auto",
        model: "Turnike kontrolcüsü",
        lastSeen: now.toISOString(),
      },
      {
        id: "d2",
        code: "TRN-002",
        name: "Yan giriş",
        branchId: "b1",
        status: "offline",
        direction: "both",
        sensor: "unknown",
        mode: "auto",
        model: "Turnike kontrolcüsü",
        lastSeen: `${yesterday}T20:00:00`,
      },
    ],
    deviceEvents: [],
    branches: [{ id: "b1", name: "Merkez" }],
    classes: [
      {
        id: "cl1",
        name: "Pilates",
        trainer: "Elif Arslan",
        room: "Stüdyo A",
        at: `${addDays(today, 1)}T18:00:00`,
        duration: 60,
        capacity: 2,
        cancelled: false,
        branchId: "b1",
      },
      {
        id: "cl2",
        name: "Kişisel Antrenman",
        trainer: "Mert Kaya",
        room: "Fitness",
        at: `${addDays(today, 1)}T10:00:00`,
        duration: 60,
        capacity: 1,
        cancelled: false,
        branchId: "b1",
      },
    ],
    bookings: [
      {
        id: "bk1",
        classId: "cl1",
        memberId: "m1",
        status: "booked",
        at: now.toISOString(),
      },
    ],
    products: [
      {
        id: "pr1",
        code: "SU-001",
        barcode: "869000000001",
        name: "Su 500 ml",
        category: "İçecek",
        price: 20,
        cost: 8,
        stock: 48,
        minimum: 10,
        supplier: "Merkez dağıtım",
      },
      {
        id: "pr2",
        code: "PRT-001",
        barcode: "869000000002",
        name: "Protein içeceği",
        category: "İçecek",
        price: 95,
        cost: 55,
        stock: 4,
        minimum: 5,
        supplier: "Spor beslenme",
      },
    ],
    sales: [],
    stockMovements: [],
    notices: [],
    readNotices: [],
    audit: [],
    settings: { capacity: 100, debtBlock: false },
    employees: [
      {
        id: "e1",
        name: "Mert Kaya",
        type: "fixed",
        card: "STAFF-1001",
        hourlyRate: 0,
        role: "trainer",
        active: true,
      },
      {
        id: "e2",
        name: "Elif Arslan",
        type: "hourly",
        card: "STAFF-1002",
        hourlyRate: 180,
        role: "staff",
        active: true,
      },
    ],
    rates: [
      {
        id: "r1",
        employeeId: "e2",
        effectiveAt: "2020-01-01T00:00:00",
        rate: 180,
      },
    ],
    shifts: [
      {
        id: "s1",
        employeeId: "e2",
        entry: `${dateKey(new Date(now.getFullYear(), now.getMonth() - (now.getDate() < 15 ? 1 : 0), 15))}T10:00:00`,
        exit: `${dateKey(new Date(now.getFullYear(), now.getMonth() - (now.getDate() < 15 ? 1 : 0), 15))}T16:30:00`,
      },
    ],
  };
}

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}
function sellSubscription(db, memberId, payload, now) {
  const plan = db.plans.find((item) => item.id === payload.planId);
  requireValue(plan?.active, "Satışa açık bir paket seçin.");
  const start = payload.start || dateKey(now),
    end = payload.end || addDays(start, plan.days - 1);
  requireValue(
    /^\d{4}-\d{2}-\d{2}$/.test(start) && end >= start,
    "Üyelik tarihlerini kontrol edin.",
  );
  const discountCents = cents(payload.discount || 0);
  requireValue(
    discountCents >= 0 && discountCents <= cents(plan.price),
    "İndirim paket fiyatını aşamaz.",
  );
  const sub = {
    id: uid(),
    memberId,
    planId: plan.id,
    planName: plan.name,
    start,
    end,
    status: "active",
    rules: structuredClone(plan),
    priceCents: cents(plan.price),
    remaining: plan.sessions,
    frozenAt: null,
    frozenDays: 0,
  };
  db.subscriptions.push(sub);
  const invoice = {
    id: uid(),
    number: `SAT-${String(db.invoices.length + 1).padStart(6, "0")}`,
    memberId,
    subscriptionId: sub.id,
    totalCents: sub.priceCents - discountCents,
    discountCents,
    status: "open",
    createdAt: now.toISOString(),
  };
  db.invoices.push(invoice);
  const count = Number(payload.installments || 1);
  requireValue(
    Number.isInteger(count) && count >= 1 && count <= 12,
    "Taksit sayısı 1–12 olmalı.",
  );
  for (let index = 0; index < count; index++)
    db.installments.push({
      id: uid(),
      invoiceId: invoice.id,
      due: addMonths(start, index),
      amountCents:
        Math.floor(invoice.totalCents / count) +
        (index < invoice.totalCents % count ? 1 : 0),
    });
  if (Number(payload.paid) > 0)
    collect(
      db,
      {
        invoiceId: invoice.id,
        amount: payload.paid,
        method: payload.method || "cash",
      },
      now,
      payload.actor,
    );
  return sub;
}
function collect(db, payload, now, actor) {
  const invoice = db.invoices.find((item) => item.id === payload.invoiceId),
    amountCents = cents(payload.amount);
  requireValue(
    invoice && invoice.status !== "cancelled",
    "Geçerli bir satış seçin.",
  );
  requireValue(
    Number.isFinite(amountCents) &&
      amountCents > 0 &&
      amountCents <= invoiceDebt(db, invoice),
    "Ödeme sıfırdan büyük ve kalan borçtan küçük veya eşit olmalı.",
  );
  requireValue(
    ["cash", "pos", "bank", "mixed"].includes(payload.method),
    "Ödeme yöntemi geçersiz.",
  );
  db.payments.push({
    id: uid(),
    number: `ODM-${String(db.payments.length + 1).padStart(6, "0")}`,
    invoiceId: invoice.id,
    amountCents,
    method: payload.method,
    note: payload.note || "",
    at: now.toISOString(),
    actor,
  });
}
const adminActions = [
  "savePlan",
  "freeze",
  "resume",
  "cancelSubscription",
  "refund",
  "saveProduct",
  "stock",
  "returnSale",
  "saveClass",
  "cancelClass",
  "saveSettings",
  "deviceMode",
  "correctVisit",
  "addEmployee",
  "employeeStatus",
  "saveRates",
  "correctShift",
  "openCash",
  "closeCash",
];
export function transact(source, type, payload, user, now = new Date()) {
  requireValue(
    user && ["admin", "staff"].includes(user.role),
    "Geçerli bir oturum gerekiyor.",
  );
  requireValue(
    user && (user.role === "admin" || !adminActions.includes(type)),
    "Bu işlem için yönetici yetkisi gerekiyor.",
  );
  const db = structuredClone(source),
    actor = user.name,
    today = dateKey(now);
  let result = null;
  if (type === "addMember") {
    requireValue(
      payload.name?.trim() && payload.phone?.replace(/\D/g, "").length >= 10,
      "Ad soyad ve geçerli telefon zorunlu.",
    );
    requireValue(
      !db.members.some(
        (member) =>
          member.phone.replace(/\D/g, "") === payload.phone.replace(/\D/g, ""),
      ),
      "Bu telefonla kayıtlı bir üye var.",
    );
    requireValue(payload.consent, "Bilgilendirme kaydı gerekli.");
    const member = {
      ...payload,
      id: uid(),
      number: `GYM-${String(db.members.length + 1).padStart(6, "0")}`,
      active: true,
      blocked: false,
      createdAt: now.toISOString(),
      createdBy: actor,
      branchId: "b1",
    };
    db.members.push(member);
    sellSubscription(db, member.id, { ...payload, actor }, now);
    result = member.id;
  } else if (type === "editMember") {
    const member = db.members.find((item) => item.id === payload.id);
    requireValue(member, "Üye bulunamadı.");
    if (payload.phone)
      requireValue(
        !db.members.some(
          (item) =>
            item.id !== member.id &&
            item.phone.replace(/\D/g, "") === payload.phone.replace(/\D/g, ""),
        ),
        "Telefon başka bir üyeye ait.",
      );
    const allowed = [
      "name",
      "phone",
      "email",
      "photo",
      "note",
      "trainer",
      "active",
      "emergency",
      "address",
      "marketing",
    ];
    if (user.role === "admin") allowed.push("blocked");
    for (const key of allowed) if (key in payload) member[key] = payload[key];
  } else if (type === "renew") {
    requireValue(
      db.members.some((item) => item.id === payload.memberId),
      "Üye bulunamadı.",
    );
    result = sellSubscription(
      db,
      payload.memberId,
      { ...payload, actor },
      now,
    ).id;
  } else if (["freeze", "resume", "cancelSubscription"].includes(type)) {
    const sub = db.subscriptions.find((item) => item.id === payload.id);
    requireValue(sub, "Üyelik bulunamadı.");
    if (type === "freeze") {
      requireValue(
        ["active", "ending"].includes(subscriptionStatus(sub, today)),
        "Yalnız geçerli üyelik dondurulabilir.",
      );
      requireValue(
        sub.rules.freezeDays > sub.frozenDays,
        "Paketin dondurma hakkı kalmadı.",
      );
      sub.status = "frozen";
      sub.frozenAt = today;
      db.freezes.push({
        id: uid(),
        subscriptionId: sub.id,
        start: today,
        end: null,
        reason: payload.reason || "",
        actor,
      });
    } else if (type === "resume") {
      requireValue(sub.status === "frozen", "Üyelik dondurulmamış.");
      const days = Math.min(
        dayDiff(today, sub.frozenAt),
        sub.rules.freezeDays - sub.frozenDays,
      );
      sub.end = addDays(sub.end, days);
      sub.frozenDays += days;
      sub.status = "active";
      sub.frozenAt = null;
      db.freezes.find(
        (item) => item.subscriptionId === sub.id && !item.end,
      ).end = today;
    } else {
      requireValue(payload.reason?.trim(), "İptal gerekçesi zorunlu.");
      requireValue(payload.confirmed === true, "İptal onayı zorunlu.");
      sub.status = "cancelled";
    }
  } else if (type === "collect") collect(db, payload, now, actor);
  else if (type === "refund") {
    const payment = db.payments.find((item) => item.id === payload.paymentId);
    const refundable =
      payment?.amountCents -
      db.refunds
        .filter((item) => item.paymentId === payload.paymentId)
        .reduce((sum, item) => sum + item.amountCents, 0);
    const amountCents = cents(payload.amount);
    requireValue(
      payment &&
        amountCents > 0 &&
        amountCents <= refundable &&
        payload.reason?.trim(),
      "İade tutarı veya gerekçesi geçersiz.",
    );
    db.refunds.push({
      id: uid(),
      paymentId: payment.id,
      amountCents,
      reason: payload.reason,
      actor,
      at: now.toISOString(),
    });
  } else if (type === "savePlan") {
    requireValue(
      payload.name?.trim() &&
        Number.isInteger(Number(payload.days)) &&
        Number(payload.days) > 0 &&
        Number(payload.price) >= 0,
      "Paket adı, süre ve fiyatı kontrol edin.",
    );
    requireValue(
      payload.from < payload.to && payload.weekdays?.length,
      "Paket saatlerini ve günlerini kontrol edin.",
    );
    requireValue(
      payload.sessions === null ||
        (Number.isInteger(Number(payload.sessions)) &&
          Number(payload.sessions) > 0),
      "Seans sayısı pozitif tam sayı olmalı.",
    );
    const plan = {
      ...payload,
      days: Number(payload.days),
      price: Number(payload.price),
      freezeDays: Number(payload.freezeDays || 0),
      sessions: payload.sessions === null ? null : Number(payload.sessions),
      id: payload.id || uid(),
    };
    const index = db.plans.findIndex((item) => item.id === plan.id);
    if (index < 0) db.plans.push(plan);
    else db.plans[index] = plan;
  } else if (type === "assignCard") {
    requireValue(
      ["admin", "staff"].includes(user.role),
      "Kart yönetimi yetkisi gerekli.",
    );
    const cardUid = payload.uid.trim().toUpperCase();
    const existing = db.cards.find((item) => item.uid === cardUid);
    requireValue(
      db.members.some((item) => item.id === payload.memberId),
      "Üye bulunamadı.",
    );
    requireValue(
      cardUid &&
        (!existing ||
          (existing.status === "available" && !existing.memberId)) &&
        !db.employees.some((item) => item.card === cardUid) &&
        !(db.employeeCards || []).some((item) => item.uid === cardUid),
      "Kart atanmış veya kullanıma kapalı. Önce teslim alın.",
    );
    db.cards
      .filter(
        (item) =>
          item.memberId === payload.memberId &&
          ["active", "inactive"].includes(item.status),
      )
      .forEach((item) => {
        item.status = "cancelled";
      });
    const assigned = {
      id: existing?.id || uid(),
      uid: cardUid,
      memberId: payload.memberId,
      status: "active",
      at: now.toISOString(),
    };
    if (existing) Object.assign(existing, assigned);
    else db.cards.push(assigned);
  } else if (type === "releaseCard") {
    requireValue(
      ["admin", "staff"].includes(user.role),
      "Kart yönetimi yetkisi gerekli.",
    );
    const card = db.cards.find((item) => item.id === payload.id);
    requireValue(
      payload.confirmed === true,
      "Kartın fiziksel olarak teslim alındığını onaylayın.",
    );
    requireValue(
      card?.memberId &&
        ["active", "inactive", "lost", "cancelled"].includes(card.status),
      "Kart zaten boş veya teslim alınamaz.",
    );
    requireValue(
      !db.visits.some((item) => item.memberId === card.memberId && !item.exit),
      "Üyenin açık ziyareti var. Önce çıkışı tamamlayın.",
    );
    requireValue(
      !db.grants.some(
        (item) =>
          item.memberId === card.memberId &&
          !item.confirmed &&
          new Date(item.expiresAt) > now,
      ),
      "Bekleyen geçiş izni var.",
    );
    card.memberId = null;
    card.status = "available";
    card.at = now.toISOString();
  } else if (type === "cardStatus") {
    requireValue(
      ["admin", "staff"].includes(user.role),
      "Kart yönetimi yetkisi gerekli.",
    );
    const card = db.cards.find((item) => item.id === payload.id);
    requireValue(
      card &&
        ["active", "inactive", "lost", "cancelled"].includes(payload.status),
      "Kart durumu geçersiz.",
    );
    requireValue(
      ["active", "inactive"].includes(card.status),
      "İptal edilmiş kart yeniden kullanılamaz.",
    );
    requireValue(
      payload.status !== "active" ||
        !db.cards.some(
          (item) =>
            item.id !== card.id &&
            item.memberId === card.memberId &&
            item.status === "active",
        ),
      "Üyenin zaten aktif bir kartı var.",
    );
    card.status = payload.status;
  } else if (type === "authorize") {
    requireValue(
      ["entry", "exit"].includes(payload.direction),
      "Geçiş yönü geçersiz.",
    );
    requireValue(
      user.role === "staff",
      "Kart okutma resepsiyon hesabından yapılır.",
    );
    const card = db.cards.find(
        (item) => item.uid === payload.uid.trim().toUpperCase(),
      ),
      member = db.members.find((item) => item.id === card?.memberId);
    const device = db.devices.find((item) => item.id === payload.deviceId),
      sub = currentSubscription(db, member?.id, today);
    const inside = db.visits.some(
      (item) => item.memberId === member?.id && !item.exit,
    );
    let reason = "";
    const pending = db.grants.some(
      (item) =>
        item.memberId === member?.id &&
        !item.confirmed &&
        new Date(item.expiresAt) > now,
    );
    const recent = db.attempts.findLast(
      (item) =>
        item.card === payload.uid.trim().toUpperCase() &&
        now - new Date(item.at) < 10000,
    );
    if (!device || device.status !== "online" || device.mode !== "auto")
      reason = "Cihaz çevrimdışı veya bakımda";
    else if (!card) reason = "Kart tanımsız";
    else if (card.status !== "active")
      reason = "Kart pasif, kayıp veya iptal edilmiş";
    else if (pending || recent) reason = "Tekrar okutma / bekleyen geçiş";
    else if (payload.direction === "exit") {
      if (!inside) reason = "Açık giriş kaydı bulunamadı";
    } else if (!member.active || member.blocked)
      reason = "Üye pasif veya giriş engeli var";
    else if (!["active", "ending"].includes(subscriptionStatus(sub, today)))
      reason = "Üyelik geçerli değil";
    else if (inside) reason = "Üye zaten içeride";
    else if (sub.remaining !== null && sub.remaining <= 0)
      reason = "Seans hakkı kalmadı";
    else if (
      !sub.rules.weekdays.includes(now.getDay()) ||
      now.toTimeString().slice(0, 5) < sub.rules.from ||
      now.toTimeString().slice(0, 5) >= sub.rules.to
    )
      reason = "Paket gün / saat kısıtlaması";
    else if (db.settings.debtBlock && memberDebt(db, member.id) > 0)
      reason = "Ödeme borcu nedeniyle giriş engeli";
    else if (
      db.visits.filter((item) => !item.exit).length +
        db.grants.filter(
          (item) =>
            item.direction === "entry" &&
            !item.confirmed &&
            new Date(item.expiresAt) > now,
        ).length >=
      db.settings.capacity
    )
      reason = "Salon kapasitesi dolu";
    const attempt = {
      id: uid(),
      memberId: member?.id || null,
      card: payload.uid.trim().toUpperCase(),
      at: now.toISOString(),
      deviceId: payload.deviceId,
      direction: payload.direction,
      status: reason ? "rejected" : "granted",
      reason: reason || "Sensör onayı bekleniyor",
    };
    db.attempts.push(attempt);
    if (!reason) {
      const grant = {
        id: uid(),
        attemptId: attempt.id,
        memberId: member.id,
        subscriptionId: sub?.id,
        deviceId: device.id,
        direction: payload.direction,
        confirmed: false,
        expiresAt: new Date(now.getTime() + 30000).toISOString(),
      };
      db.grants.push(grant);
      result = { approved: true, grantId: grant.id, memberId: member.id };
    } else result = { approved: false, reason, memberId: member?.id };
  } else if (type === "confirmPassage") {
    requireValue(
      user.role === "staff",
      "Geçiş onayı resepsiyon hesabından yapılır.",
    );
    const grant = db.grants.find((item) => item.id === payload.id);
    requireValue(
      grant && !grant.confirmed && new Date(grant.expiresAt) > now,
      "İzin kullanılmış veya süresi dolmuş.",
    );
    const visit = db.visits.find(
      (item) => item.memberId === grant.memberId && !item.exit,
    );
    const device = db.devices.find((item) => item.id === grant.deviceId);
    requireValue(
      device?.status === "online" && device.mode === "auto",
      "Cihaz kullanıma hazır değil.",
    );
    if (grant.direction === "exit") {
      requireValue(visit, "Açık ziyaret bulunamadı.");
      visit.exit = now.toISOString();
    } else {
      requireValue(!visit, "Üye zaten içeride.");
      const sub = db.subscriptions.find(
        (item) => item.id === grant.subscriptionId,
      );
      requireValue(
        ["active", "ending"].includes(subscriptionStatus(sub, today)) &&
          (sub.remaining === null || sub.remaining > 0),
        "Üyelik veya seans hakkı geçersiz.",
      );
      db.visits.push({
        id: uid(),
        memberId: grant.memberId,
        entry: now.toISOString(),
        exit: null,
        deviceId: grant.deviceId,
        method: "RFID",
      });
      if (sub.remaining !== null) sub.remaining--;
    }
    grant.confirmed = true;
    const attempt = db.attempts.find((item) => item.id === grant.attemptId);
    attempt.status = "confirmed";
    attempt.reason = "Fiziksel geçiş tamamlandı";
  } else if (type === "correctVisit") {
    const visit = db.visits.find((item) => item.id === payload.id);
    requireValue(
      visit && !visit.exit && payload.reason?.trim(),
      "Açık ziyaret ve gerekçe gerekli.",
    );
    visit.exit = now.toISOString();
    visit.correctionReason = payload.reason;
  } else if (type === "saveClass") {
    requireValue(
      payload.room?.trim() &&
        Number.isInteger(Number(payload.duration)) &&
        Number(payload.duration) > 0,
      "Salon ve ders süresi gerekli.",
    );
    requireValue(
      payload.name?.trim() &&
        payload.trainer?.trim() &&
        Number(payload.capacity) >= 1 &&
        Number.isInteger(Number(payload.capacity)) &&
        new Date(payload.at) > now,
      "Ders adı, antrenör, gelecek tarih ve kontenjan gerekli.",
    );
    const end =
      new Date(payload.at).getTime() + Number(payload.duration) * 60000;
    requireValue(
      !db.classes.some(
        (item) =>
          !item.cancelled &&
          (item.trainer === payload.trainer || item.room === payload.room) &&
          new Date(item.at).getTime() < end &&
          new Date(item.at).getTime() + item.duration * 60000 >
            new Date(payload.at).getTime(),
      ),
      "Antrenör veya salon bu saatte dolu.",
    );
    db.classes.push({
      ...payload,
      id: uid(),
      capacity: Number(payload.capacity),
      duration: Number(payload.duration),
      branchId: "b1",
      cancelled: false,
    });
  } else if (type === "book") {
    const cls = db.classes.find((item) => item.id === payload.classId),
      sub = currentSubscription(db, payload.memberId, today),
      member = db.members.find((item) => item.id === payload.memberId);
    requireValue(
      cls &&
        !cls.cancelled &&
        new Date(cls.at) > now &&
        member?.active &&
        !member.blocked &&
        ["active", "ending"].includes(
          subscriptionStatus(sub, dateKey(new Date(cls.at))),
        ),
      "Ders veya üyenin üyeliği uygun değil.",
    );
    requireValue(
      !db.bookings.some(
        (item) =>
          item.classId === cls.id &&
          item.memberId === payload.memberId &&
          item.status !== "cancelled",
      ),
      "Üye bu derse zaten kayıtlı.",
    );
    const full =
      db.bookings.filter(
        (item) =>
          item.classId === cls.id &&
          ["booked", "attended"].includes(item.status),
      ).length >= cls.capacity;
    const booking = {
      id: uid(),
      ...payload,
      status: full ? "waiting" : "booked",
      at: now.toISOString(),
    };
    db.bookings.push(booking);
    result = booking.status;
  } else if (type === "bookingStatus") {
    const booking = db.bookings.find((item) => item.id === payload.id);
    requireValue(booking, "Rezervasyon bulunamadı.");
    requireValue(
      ["cancelled", "attended"].includes(payload.status),
      "Rezervasyon durumu geçersiz.",
    );
    requireValue(
      payload.status !== "attended" || booking.status === "booked",
      "Yalnız onaylı rezervasyona katılım işlenir.",
    );
    const previous = booking.status;
    booking.status = payload.status;
    if (payload.status === "cancelled" && previous === "booked") {
      const next = db.bookings
        .filter(
          (item) =>
            item.classId === booking.classId && item.status === "waiting",
        )
        .sort((a, b) => a.at.localeCompare(b.at))[0];
      if (next) next.status = "booked";
    }
  } else if (type === "cancelClass") {
    const cls = db.classes.find((item) => item.id === payload.id);
    requireValue(cls, "Ders bulunamadı.");
    cls.cancelled = true;
    db.bookings
      .filter((item) => item.classId === cls.id)
      .forEach((item) => {
        item.status = "cancelled";
      });
  } else if (type === "saveProduct") {
    requireValue(
      Number.isFinite(Number(payload.cost)) &&
        Number(payload.cost) >= 0 &&
        Number.isInteger(Number(payload.minimum)) &&
        Number(payload.minimum) >= 0,
      "Alış fiyatı veya minimum stok geçersiz.",
    );
    requireValue(
      !payload.barcode ||
        !db.products.some((item) => item.barcode === payload.barcode),
      "Barkod başka bir ürüne ait.",
    );
    requireValue(
      payload.name?.trim() &&
        payload.code?.trim() &&
        Number(payload.price) >= 0 &&
        Number.isInteger(Number(payload.stock)) &&
        Number(payload.stock) >= 0,
      "Ürün alanlarını kontrol edin.",
    );
    requireValue(
      !db.products.some((item) => item.code === payload.code),
      "Ürün kodu kullanılıyor.",
    );
    const product = {
      ...payload,
      id: uid(),
      price: Number(payload.price),
      cost: Number(payload.cost),
      stock: Number(payload.stock),
      minimum: Number(payload.minimum),
    };
    db.products.push(product);
    db.stockMovements.push({
      id: uid(),
      productId: product.id,
      quantity: product.stock,
      reason: "Açılış",
      at: now.toISOString(),
    });
  } else if (type === "stock") {
    const product = db.products.find((item) => item.id === payload.id);
    const quantity = Number(payload.quantity);
    requireValue(
      product &&
        Number.isInteger(quantity) &&
        quantity !== 0 &&
        product.stock + quantity >= 0 &&
        payload.reason?.trim(),
      "Stok miktarı veya gerekçe geçersiz.",
    );
    product.stock += quantity;
    db.stockMovements.push({
      id: uid(),
      productId: product.id,
      quantity,
      reason: payload.reason,
      at: now.toISOString(),
    });
  } else if (type === "sellProduct") {
    requireValue(
      ["cash", "pos", "bank", "mixed"].includes(payload.method),
      "Ödeme yöntemi geçersiz.",
    );
    const product = db.products.find((item) => item.id === payload.productId),
      quantity = Number(payload.quantity);
    requireValue(
      product &&
        Number.isInteger(quantity) &&
        quantity > 0 &&
        quantity <= product.stock,
      "Stok yetersiz veya miktar geçersiz.",
    );
    product.stock -= quantity;
    db.sales.push({
      id: uid(),
      ...payload,
      quantity,
      totalCents: cents(product.price) * quantity,
      productName: product.name,
      at: now.toISOString(),
      actor,
      returned: false,
    });
    db.stockMovements.push({
      id: uid(),
      productId: product.id,
      quantity: -quantity,
      reason: "Satış",
      at: now.toISOString(),
    });
  } else if (type === "returnSale") {
    const sale = db.sales.find((item) => item.id === payload.id);
    requireValue(
      sale && !sale.returned && payload.reason?.trim(),
      "Satış veya iade gerekçesi geçersiz.",
    );
    sale.returned = true;
    sale.returnedAt = now.toISOString();
    db.products.find((item) => item.id === sale.productId).stock +=
      sale.quantity;
    db.stockMovements.push({
      id: uid(),
      productId: sale.productId,
      quantity: sale.quantity,
      reason: payload.reason,
      at: now.toISOString(),
    });
  } else if (type === "saveSettings") {
    requireValue(
      Number.isInteger(Number(payload.capacity)) &&
        Number(payload.capacity) > 0,
      "Kapasite pozitif tam sayı olmalı.",
    );
    db.settings = {
      ...db.settings,
      ...payload,
      capacity: Number(payload.capacity),
    };
  } else if (type === "deviceMode") {
    const device = db.devices.find((item) => item.id === payload.id);
    requireValue(
      device && ["auto", "maintenance"].includes(payload.mode),
      "Cihaz bulunamadı.",
    );
    device.mode = payload.mode;
    db.deviceEvents.push({
      id: uid(),
      deviceId: device.id,
      at: now.toISOString(),
      message: `Mod: ${payload.mode}`,
      actor,
    });
  } else if (type === "notice") {
    requireValue(payload.message?.trim(), "Bildirim metni gerekli.");
    db.notices.push({
      id: uid(),
      message: payload.message,
      at: now.toISOString(),
      actor,
      channel: "panel",
    });
  } else if (type === "readNotice") {
    if (!db.readNotices.includes(payload.id)) db.readNotices.push(payload.id);
  } else if (type === "addEmployee") {
    const card = payload.card.trim().toUpperCase();
    requireValue(
      payload.name?.trim() &&
        card &&
        !db.cards.some((item) => item.uid === card) &&
        !db.employees.some((item) => item.card === card),
      "Çalışan adı veya kartı geçersiz / kullanılıyor.",
    );
    const employee = {
      ...payload,
      id: uid(),
      card,
      hourlyRate: Number(payload.hourlyRate),
      role: payload.role || "staff",
      active: true,
    };
    db.employees.push(employee);
    if (employee.type === "hourly")
      db.rates.push({
        id: uid(),
        employeeId: employee.id,
        effectiveAt: now.toISOString(),
        rate: employee.hourlyRate,
      });
  } else if (type === "employeeStatus") {
    const employee = db.employees.find((item) => item.id === payload.id);
    requireValue(employee, "Çalışan bulunamadı.");
    requireValue(
      !payload.role || ["staff", "trainer"].includes(payload.role),
      "Görev rolü geçersiz.",
    );
    employee.active = payload.active;
    employee.role = payload.role || employee.role;
  } else if (type === "scanEmployee") {
    requireValue(
      user.role === "staff",
      "Mesai okutma çalışan ekranından yapılır.",
    );
    const employee = db.employees.find(
      (item) => item.card === payload.uid.trim().toUpperCase(),
    );
    requireValue(employee?.active, "Çalışan kartı bulunamadı veya pasif.");
    const employeeShifts = db.shifts.filter(
        (item) => item.employeeId === employee.id,
      ),
      last = employeeShifts.at(-1);
    requireValue(
      !last || now - new Date(last.exit || last.entry) >= 10000,
      "Tekrar okuma algılandı. 10 saniye bekleyin.",
    );
    const open = employeeShifts.find((item) => !item.exit);
    if (open) open.exit = now.toISOString();
    else
      db.shifts.push({
        id: uid(),
        employeeId: employee.id,
        entry: now.toISOString(),
        exit: null,
      });
    result = `${employee.name}: Mesai ${open ? "çıkışı" : "girişi"} kaydedildi.`;
  } else if (type === "correctShift") {
    const shift = db.shifts.find((item) => item.id === payload.id);
    requireValue(
      shift &&
        payload.reason?.trim() &&
        new Date(payload.exit) > new Date(shift.entry) &&
        new Date(payload.exit) <= now,
      "Çıkış zamanı ve gerekçeyi kontrol edin.",
    );
    requireValue(
      !db.shifts.some(
        (item) =>
          item.id !== shift.id &&
          item.employeeId === shift.employeeId &&
          new Date(item.entry) < new Date(payload.exit) &&
          new Date(item.exit || now) > new Date(shift.entry),
      ),
      "Düzeltme başka bir mesaiyle çakışıyor.",
    );
    shift.exit = new Date(payload.exit).toISOString();
    shift.reason = payload.reason;
  } else if (type === "saveRates") {
    for (const plan of payload.plans) {
      requireValue(
        Number(plan.price) >= 0 && Number.isFinite(Number(plan.price)),
        "Fiyat geçersiz.",
      );
      db.plans.find((item) => item.id === plan.id).price = Number(plan.price);
    }
    for (const employee of db.employees.filter(
      (item) => item.type === "hourly",
    )) {
      const rate = Number(payload.rates[employee.id] ?? employee.hourlyRate);
      requireValue(
        rate >= 0 && Number.isFinite(rate),
        "Saatlik ücret geçersiz.",
      );
      if (rate !== employee.hourlyRate) {
        employee.hourlyRate = rate;
        db.rates.push({
          id: uid(),
          employeeId: employee.id,
          effectiveAt: now.toISOString(),
          rate,
        });
      }
    }
  } else if (type === "openCash") {
    db.cashSessions ||= [];
    requireValue(
      !db.cashSessions.some((item) => !item.closedAt),
      "Kasa zaten açık.",
    );
    const openingCents = cents(payload.amount);
    requireValue(
      Number.isFinite(openingCents) && openingCents >= 0,
      "Açılış tutarı geçersiz.",
    );
    db.cashSessions.push({
      id: uid(),
      openedAt: now.toISOString(),
      openingCents,
      actor,
      closedAt: null,
    });
  } else if (type === "closeCash") {
    const session = db.cashSessions?.find((item) => !item.closedAt),
      countedCents = cents(payload.amount);
    requireValue(
      session && Number.isFinite(countedCents) && countedCents >= 0,
      "Açık kasa veya sayım tutarı geçersiz.",
    );
    session.closedAt = now.toISOString();
    session.countedCents = countedCents;
    session.note = payload.note || "";
    session.expectedCents = cashBalance(db, session, now);
    session.closedBy = actor;
  } else throw new Error("İşlem tanınmıyor.");
  if (type !== "readNotice") {
    const table = {
      editMember: "members",
      freeze: "subscriptions",
      resume: "subscriptions",
      cancelSubscription: "subscriptions",
      savePlan: "plans",
      cardStatus: "cards",
      releaseCard: "cards",
      correctVisit: "visits",
      employeeStatus: "employees",
      correctShift: "shifts",
      deviceMode: "devices",
      stock: "products",
    }[type];
    const id =
      payload.id ||
      payload.memberId ||
      payload.invoiceId ||
      result?.memberId ||
      (type === "addMember" ? result : null);
    const clean = (value) =>
      value
        ? Object.fromEntries(
            Object.entries(value).filter(([key]) => key !== "photo"),
          )
        : null;
    db.audit.push({
      id: uid(),
      type,
      actor,
      role: user.role,
      at: now.toISOString(),
      entityId: id,
      detail: JSON.stringify({
        ...payload,
        photo: payload.photo ? "[fotoğraf]" : undefined,
      }),
      before: JSON.stringify(
        clean(source[table]?.find((item) => item.id === id)),
      ),
      after: JSON.stringify(clean(db[table]?.find((item) => item.id === id))),
    });
  }
  return { db, result };
}

export function automaticNotices(db, now = new Date()) {
  if (db.source === "server") return db.notificationItems || db.notices || [];
  const today = dateKey(now),
    notices = [...db.notices];
  for (const member of db.members) {
    const sub = currentSubscription(db, member.id, today);
    if (
      sub &&
      sub.end &&
      ["active", "ending"].includes(subscriptionStatus(sub, today)) &&
      dayDiff(sub.end, today) <= 7
    )
      notices.push({
        id: `expiry-${sub.id}-${sub.end}`,
        message: `${member.name}: üyelik ${dayDiff(sub.end, today)} gün içinde bitiyor.`,
        target: "members",
        memberId: member.id,
      });
    const overdue = db.invoices
      .filter((item) => item.memberId === member.id)
      .some((invoice) =>
        installmentRows(db, invoice).some(
          (item) => item.due < today && item.remaining > 0,
        ),
      );
    if (overdue)
      notices.push({
        id: `debt-${member.id}`,
        message: `${member.name}: gecikmiş taksit ödemesi var.`,
        target: "payments",
      });
  }
  db.products
    .filter((item) => item.active !== false && item.stock <= item.minimum)
    .forEach((item) =>
      notices.push({
        id: `stock-${item.id}`,
        message: `${item.name}: kritik stok (${item.stock}).`,
        target: "stock",
      }),
    );
  db.devices
    .filter((item) => item.status === "offline" && !item.simulated && item.enabled !== false && item.mode !== "maintenance" && item.lastSeen)
    .forEach((item) =>
      notices.push({
        id: `device-${item.id}`,
        message: `${item.name}: cihaz çevrimdışı.`,
        target: "devices",
      }),
    );
  return notices.map((item) => ({
    ...item,
    read: db.readNotices.includes(item.id),
  }));
}

export function cashBalance(db, session, now = new Date()) {
  const within = (at) =>
    new Date(at) >= new Date(session.openedAt) && new Date(at) <= now;
  const payments = db.payments
    .filter(
      (item) => item.method === "cash" && within(item.recordedAt || item.at),
    )
    .reduce((sum, item) => sum + item.amountCents, 0);
  const refunds = db.refunds
    .filter(
      (item) =>
        within(item.at) &&
        db.payments.some(
          (payment) =>
            payment.id === item.paymentId && payment.method === "cash",
        ),
    )
    .reduce((sum, item) => sum + item.amountCents, 0);
  const sales = db.sales
    .filter((item) => item.method === "cash" && within(item.at))
    .reduce((sum, item) => sum + item.totalCents, 0);
  const returns = db.stockMovements?.some((item) => item.refundCents != null)
    ? db.stockMovements
        .filter((item) => item.method === "cash" && within(item.at))
        .reduce((sum, item) => sum + (item.refundCents || 0), 0)
    : db.sales
        .filter(
          (item) =>
            item.method === "cash" && item.returned && within(item.returnedAt),
        )
        .reduce((sum, item) => sum + item.totalCents, 0);
  return session.openingCents + payments - refunds + sales - returns;
}
