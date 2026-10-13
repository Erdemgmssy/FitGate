import { dateKey } from "./attendance.mjs";
import { dayDiff, addDays, subscriptionStatus } from "./gym.mjs";

export function membershipEnd(plan, start) {
  if (!start) return "";
  if (plan.kind === "sessions") return "";
  if (!plan.durationUnit || plan.durationUnit === "day")
    return addDays(start, (plan.durationValue || plan.days) - 1);
  if (plan.durationUnit === "week")
    return addDays(start, Number(plan.durationValue) * 7 - 1);
  const [year, month, day] = start.split("-").map(Number);
  const offset =
    Number(plan.durationValue) * (plan.durationUnit === "year" ? 12 : 1);
  const target = new Date(year, month - 1 + offset, 1);
  target.setDate(
    Math.min(
      day,
      new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate(),
    ),
  );
  return addDays(dateKey(target), -1);
}

export function subscriptionDays(sub, today = dateKey()) {
  if (sub.status === "cancelled") return 0;
  if (!sub.end) return null;
  const periods = sub.freezePeriods || [];
  const legacy = periods.find(
    (period) => !period.end && !period.plannedEnd && period.start <= today,
  );
  const first = [
    sub.start,
    legacy?.start || (sub.legacyFrozen ? sub.frozenAt : today) || today,
  ]
    .sort()
    .at(-1);
  let days = Math.max(0, dayDiff(sub.end, first) + 1);
  for (const period of periods)
    if (period.end) {
      const start = [first, period.start].sort().at(-1);
      const end = [addDays(sub.end, 1), period.end].sort()[0];
      days -= Math.max(0, dayDiff(end, start));
    }
  return Math.max(0, days);
}
export function sessionCounts(sub) {
  if (sub.remaining == null)
    return { total: null, used: null, remaining: null };
  const total = sub.totalSessions ?? sub.rules?.sessions;
  return {
    total: total ?? null,
    used: total == null ? null : Math.max(0, total - sub.remaining),
    remaining: sub.remaining,
  };
}
export function subscriptionGroup(sub, today = dateKey()) {
  const value = subscriptionStatus(sub, today);
  return value === "ending" ? "active" : value;
}
export function orderSubscriptions(list) {
  return [...list].sort(
    (a, b) =>
      (a.end || "9999-12-31").localeCompare(b.end || "9999-12-31") ||
      a.start.localeCompare(b.start) ||
      (a.createdAt || "").localeCompare(b.createdAt || "") ||
      a.id.localeCompare(b.id),
  );
}
export function renewalStart(list, today = dateKey()) {
  const ends = list
    .filter((sub) => sub.status !== "cancelled" && sub.end >= today)
    .map((sub) => sub.end)
    .sort();
  return ends.length ? addDays(ends.at(-1), 1) : today;
}
