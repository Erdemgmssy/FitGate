export function dateKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function currentPeriodMonth(now = new Date()) {
  return dateKey(
    new Date(
      now.getFullYear(),
      now.getMonth() - (now.getDate() < 15 ? 1 : 0),
      15,
    ),
  ).slice(0, 7);
}

export function payrollPeriod(month) {
  const [year, index] = month.split("-").map(Number);
  return {
    start: new Date(year, index - 1, 15),
    end: new Date(year, index, 15),
  };
}

export function workedMilliseconds(
  shifts,
  employeeId,
  start,
  end,
  now = new Date(),
) {
  return shifts
    .filter((shift) => shift.employeeId === employeeId)
    .reduce((total, shift) => {
      // Clip shifts at both payroll boundaries, including overnight and open shifts.
      const from = Math.max(new Date(shift.entry).getTime(), start.getTime());
      const to = Math.min(
        shift.exit ? new Date(shift.exit).getTime() : now.getTime(),
        end.getTime(),
        now.getTime(),
      );
      return total + Math.max(0, to - from);
    }, 0);
}

export function durationLabel(ms) {
  const minutes = Math.floor(ms / 60000);
  return `${Math.floor(minutes / 60)} sa ${minutes % 60} dk`;
}

export const money = (value) =>
  new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(
    value,
  );
export const displayDate = (date) => new Date(date).toLocaleDateString("tr-TR");
export const displayTime = (date) =>
  new Date(date).toLocaleTimeString("tr-TR", {
    hour: "2-digit",
    minute: "2-digit",
  });

export function earnedAmount(
  shifts,
  employeeId,
  rates,
  start,
  end,
  now = new Date(),
) {
  const history = rates
    .filter((rate) => rate.employeeId === employeeId)
    .sort((a, b) => new Date(a.effectiveAt) - new Date(b.effectiveAt));
  return history.reduce((total, rate, index) => {
    const from = new Date(
      Math.max(start.getTime(), new Date(rate.effectiveAt).getTime()),
    );
    const to = new Date(
      Math.min(
        end.getTime(),
        history[index + 1]
          ? new Date(history[index + 1].effectiveAt).getTime()
          : end.getTime(),
      ),
    );
    return (
      total +
      (workedMilliseconds(shifts, employeeId, from, to, now) / 3600000) *
        rate.rate
    );
  }, 0);
}
