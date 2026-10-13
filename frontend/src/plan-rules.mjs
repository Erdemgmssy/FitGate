import { dateKey } from "./attendance.mjs";
export const planTypes = {
  timed: "Süreli",
  sessions: "Seanslı",
  hybrid: "Süre + seans",
};
export const durationUnits = {
  day: "gün",
  week: "hafta",
  month: "takvim ayı",
  year: "takvim yılı",
};
export const planKind = (plan) =>
  plan.kind || (plan.sessions == null ? "timed" : "hybrid");
export const planDuration = (plan) =>
  planKind(plan) === "sessions"
    ? "Bitiş tarihi yok"
    : `${plan.durationValue || plan.days} ${durationUnits[plan.durationUnit || "day"]}`;
export function saleAvailable(plan, today = dateKey()) {
  return (
    plan.active &&
    (!plan.saleStart || plan.saleStart <= today) &&
    (!plan.saleEnd || plan.saleEnd >= today)
  );
}
export function salePrice(plan) {
  return plan?.effectivePriceCents != null
    ? plan.effectivePriceCents / 100
    : Number(plan?.price || 0);
}
