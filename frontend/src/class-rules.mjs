export const classStates = {
  planned: "Planlandı",
  ongoing: "Devam ediyor",
  completed: "Tamamlandı",
  cancelled: "İptal edildi",
  notheld: "Yapılmadı",
};
export const attendanceStates = {
  booked: "Katılım bekleniyor",
  waiting: "Bekleme listesi",
  attended: "Katıldı",
  late: "Geç katıldı",
  absent: "Gelmedi",
  excused: "Mazeretli iptal",
  cancelled: "İptal edildi",
};
export function turkeyDay(value = new Date()) {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Istanbul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}
export function shiftDay(day, count) {
  const date = new Date(day + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}
export function shiftPeriod(day, mode, direction) {
  if (mode !== "month")
    return shiftDay(day, direction * (mode === "week" ? 7 : 1));
  const date = new Date(day.slice(0, 7) + "-01T12:00:00Z");
  date.setUTCMonth(date.getUTCMonth() + direction);
  return date.toISOString().slice(0, 10);
}
export function calendarDays(day, mode) {
  if (mode === "day") return [day];
  const start = mode === "month" ? day.slice(0, 7) + "-01" : day;
  const weekday = (new Date(start + "T12:00:00Z").getUTCDay() + 6) % 7;
  return Array.from({ length: mode === "month" ? 42 : 7 }, (_, i) =>
    shiftDay(start, i - weekday),
  );
}
export function classState(row, now = new Date()) {
  if (row.cancelled || row.state === "cancelled") return "cancelled";
  if (row.state === "notheld") return "notheld";
  const start = new Date(row.at),
    end = new Date(start.getTime() + Number(row.duration) * 60000);
  return now >= end ? "completed" : now >= start ? "ongoing" : "planned";
}
export function classOccupancy(id, bookings) {
  return bookings.filter(
    (b) =>
      b.classId === id &&
      ["booked", "attended", "late", "absent"].includes(b.status),
  ).length;
}
export function filteredClasses(
  classes,
  { trainer = "", kind = "", room = "" } = {},
) {
  return classes
    .filter(
      (c) =>
        (!trainer || c.trainerId === trainer) &&
        (!kind || c.kind === kind) &&
        (!room || c.room === room),
    )
    .sort((a, b) => new Date(a.at) - new Date(b.at));
}
export function localClassTime(value) {
  return new Date(value)
    .toLocaleString("sv-SE", { timeZone: "Europe/Istanbul" })
    .slice(0, 16)
    .replace(" ", "T");
}
