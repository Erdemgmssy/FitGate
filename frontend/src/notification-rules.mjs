import { dateKey } from "./attendance.mjs";
export const noticeTypes = {
  manual: "Panel bildirimi",
  membership: "Üyelik",
  payment: "Gecikmiş ödeme",
  stock: "Stok",
  class: "Ders",
  shift: "Vardiya",
  device: "Cihaz",
};
export const noticeSeverities = {
  info: "Bilgi",
  warning: "Uyarı",
  critical: "Kritik",
};
export function filterNotices(notices, filters = {}) {
  return notices
    .filter(
      (n) =>
        (!filters.read || (filters.read === "read") === Boolean(n.read)) &&
        (!filters.type || n.type === filters.type) &&
        (!filters.severity || n.severity === filters.severity) &&
        (!filters.status || (n.status || "active") === filters.status) &&
        (!filters.from || (n.at && dateKey(new Date(n.at)) >= filters.from)) &&
        (!filters.to || (n.at && dateKey(new Date(n.at)) <= filters.to)),
    )
    .slice()
    .sort(
      (a, b) =>
        ({ critical: 0, warning: 1, info: 2 })[a.severity || "info"] -
          { critical: 0, warning: 1, info: 2 }[b.severity || "info"] ||
        new Date(b.at || 0) - new Date(a.at || 0) ||
        a.id.localeCompare(b.id),
    );
}
