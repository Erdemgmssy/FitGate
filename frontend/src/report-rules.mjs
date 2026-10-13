export function turkeyDay(value = new Date()) {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Istanbul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(value);
}
export function shiftDay(day, count) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}
export function period(id, today = turkeyDay()) {
  const first = `${today.slice(0, 7)}-01`;
  if (id === "today") return { from: today, to: today };
  if (id === "yesterday")
    return { from: shiftDay(today, -1), to: shiftDay(today, -1) };
  if (id === "week") return { from: shiftDay(today, -6), to: today };
  if (id === "previousMonth") {
    const last = shiftDay(first, -1);
    return { from: `${last.slice(0, 7)}-01`, to: last };
  }
  return { from: first, to: today };
}
export const reportTypes = {
  overview: [],
  finance: [
    ["membership", "Üyelik"],
    ["lesson", "Ders"],
    ["product", "Ürün"],
    ["debt", "Açık alacak"],
    ["overdue", "Gecikmiş taksit"],
  ],
  members: [
    ["active", "Aktif"],
    ["expired", "Süresi dolmuş"],
    ["frozen", "Dondurulmuş"],
    ["cancelled", "İptal"],
    ["pending", "Gelecek üyelik"],
    ["renewal", "Yenileme"],
  ],
  visits: [
    ["manual", "Manuel işlemler / admin düzeltmeleri"],
    ["entry", "Fiziksel giriş"],
    ["exit", "Fiziksel çıkış"],
    ["approved", "Kart izni"],
    ["rejected", "Reddedilen kart"],
    ["duplicates", "Tekrarlı okutma"],
    ["timeout", "Doğrulanmamış süre dolumu"],
  ],
  classes: [
    ["group", "Grup dersi"],
    ["private", "Özel ders"],
    ["booked", "Rezervasyon"],
    ["waiting", "Bekleme"],
    ["attended", "Katıldı"],
    ["late", "Geç katıldı"],
    ["absent", "Gelmedi"],
    ["cancelled", "İptal"],
    ["excused", "Mazeret"],
  ],
  personnel: [
    ["late", "Geç kalma"],
    ["overtime", "Fazla mesai"],
    ["absent", "Devamsızlık"],
    ["leave", "İzin"],
  ],
  stock: [
    ["sale", "Satış"],
    ["return", "İade"],
    ["critical", "Kritik stok"],
    ["empty", "Tükenen stok"],
    ["movements", "Stok hareketleri"],
  ],
  devices: [],
  audit: [],
};
export const reportLabels = {
  entry: "Giriş",
  exit: "Çıkış",
  membership: "Üyelik",
  lesson: "Ders",
  product: "Ürün",
  collection: "Tahsilat",
  refund: "İade",
  timed: "Süreli",
  sessions: "Seanslı",
  hybrid: "Süre + seans",
  private: "Özel",
  group: "Grup",
  late: "Geç katıldı",
  absent: "Gelmedi",
  excused: "Mazeret",
  consumed: "Kullanıldı",
  reserved: "Rezerve",
  released: "Geri verildi",
  sale: "Satış",
  return: "İade",
  receipt: "Stok girişi",
  loss: "Kayıp",
  count: "Sayım",
  cost_change: "Alış fiyatı değişimi",
};
export function cleanFilters(tab, values, admin = true) {
  const result = { ...values, tab, page: 1, type: "", hour: "", weekday: "" };
  if (!["overview", "finance", "members", "visits", "classes"].includes(tab))
    result.planId = "";
  if (!["overview", "finance", "stock"].includes(tab)) result.category = "";
  if (!["overview", "finance", "stock"].includes(tab)) result.method = "";
  if (tab === "visits" || !admin) result.person = "";
  return result;
}
export function query(values) {
  return new URLSearchParams(
    Object.entries(values).filter(([, v]) => v !== "" && v != null),
  ).toString();
}
export function chartFilter(current, selected) {
  if (!selected) return current;
  if (selected.date) {
    const start = selected.date;
    const end = current.granularity === "week" ? shiftDay(start, 6) : start;
    // Month rollover is calendar arithmetic, not a fixed number of days.
    if (current.granularity === "month") {
      const next = new Date(`${start}T12:00:00Z`);
      next.setUTCMonth(next.getUTCMonth() + 1, 1);
      return {
        ...current,
        from: start < current.from ? current.from : start,
        to:
          shiftDay(next.toISOString().slice(0, 10), -1) > current.to
            ? current.to
            : shiftDay(next.toISOString().slice(0, 10), -1),
        page: 1,
      };
    }
    return {
      ...current,
      from: start < current.from ? current.from : start,
      to: end > current.to ? current.to : end,
      page: 1,
    };
  }
  return { ...current, ...selected, page: 1 };
}
