export const roles = {
  admin: "Yönetici",
  staff: "Resepsiyon",
  trainer: "Antrenör",
};
export const leaveStatuses = {
  pending: "Bekliyor",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  withdrawn: "Geri çekildi",
};
export const scheduleStatuses = {
  planned: "Planlandı",
  attended: "Katıldı",
  absent: "Devamsız",
  late: "Geç kaldı",
  leave: "Onaylı izin",
  off: "İzin günü",
};
const zone = "Europe/Istanbul";
export function trDay(value = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}
export function trDate(value) {
  return value
    ? new Intl.DateTimeFormat("tr-TR", {
        timeZone: zone,
        dateStyle: "short",
      }).format(new Date(value))
    : "-";
}
export function trTime(value) {
  return value
    ? new Intl.DateTimeFormat("tr-TR", {
        timeZone: zone,
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "-";
}
export function inputTime(value) {
  if (!value) return "";
  const date = new Date(value);
  const clock = new Intl.DateTimeFormat("sv-SE", {timeZone:zone,hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date);
  return `${trDay(date)}T${clock}.${String(date.getUTCMilliseconds()).padStart(3,'0')}`;
}
export function isoTime(value) {
  return new Date(value + "+03:00").toISOString();
}
export function plusDay(value, count) {
  const date = new Date(value + "T12:00:00+03:00");
  date.setUTCDate(date.getUTCDate() + count);
  return trDay(date);
}
export function bounds(day, mode = "day") {
  let start = day,
    end = plusDay(day, 1);
  if (mode === "week") {
    const weekday = new Date(day + "T12:00:00+03:00").getUTCDay();
    start = plusDay(day, -((weekday + 6) % 7));
    end = plusDay(start, 7);
  }
  if (mode === "month") {
    start = day.slice(0, 7) + "-01";
    const date = new Date(start + "T12:00:00+03:00");
    date.setUTCMonth(date.getUTCMonth() + 1);
    end = trDay(date);
  }
  if (mode === "period15") {
    const date = new Date(day.slice(0, 7) + "-15T12:00:00+03:00");
    if (day.slice(-2) < "15") date.setUTCMonth(date.getUTCMonth() - 1);
    start = trDay(date);
    date.setUTCMonth(date.getUTCMonth() + 1);
    end = trDay(date);
  }
  return {
    start: new Date(start + "T00:00:00+03:00"),
    end: new Date(end + "T00:00:00+03:00"),
  };
}
export function worked(
  shifts,
  breaks,
  employeeId,
  range,
  now = new Date(),
  includeSimulation = false,
) {
  return shifts
    .filter(
      (row) =>
        row.employeeId === employeeId && (includeSimulation || !row.simulated),
    )
    .reduce((sum, row) => {
      const from = Math.max(+new Date(row.entry), +range.start),
        to = Math.min(+new Date(row.exit || now), +range.end, +now);
      let total = Math.max(0, to - from);
      for (const pause of breaks.filter((p) => p.shiftId === row.id && !p.paid))
        total -= Math.max(
          0,
          Math.min(to, +new Date(pause.end || now)) -
            Math.max(from, +new Date(pause.start)),
        );
      return sum + Math.max(0, total);
    }, 0);
}
export function scheduleWindow(day, start, end) {
  return {
    start: isoTime(`${day}T${start}`),
    end: isoTime(`${end <= start ? plusDay(day, 1) : day}T${end}`),
  };
}
export function calendarDays(day, mode) {
  const range = bounds(day, mode);
  const first = trDay(range.start),
    last = trDay(range.end);
  const days = [];
  for (let value = first; value < last; value = plusDay(value, 1))
    days.push(value);
  return days;
}
