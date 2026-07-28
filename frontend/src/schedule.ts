/** Convert stored cron (min hour * * dow) ↔ friendly time for the UI. */

export type ScheduleDays = "mon-fri" | "mon-sat" | "*";

export function cronToTime(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return "08:15";
  const [minute, hour] = parts;
  const h = String(parseInt(hour, 10)).padStart(2, "0");
  const m = String(parseInt(minute, 10)).padStart(2, "0");
  if (Number.isNaN(parseInt(hour, 10)) || Number.isNaN(parseInt(minute, 10))) return "08:15";
  return `${h}:${m}`;
}

export function cronToDays(cron: string): ScheduleDays {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return "mon-fri";
  const dow = parts[4].toLowerCase();
  if (dow === "*" || dow === "mon-sun") return "*";
  if (dow === "mon-sat" || dow === "0-5" || dow === "1-6") return "mon-sat";
  // legacy numeric 1-5 was Tue–Sat in APScheduler — treat as weekdays
  return "mon-fri";
}

export function buildScheduleCron(time: string, days: ScheduleDays): string {
  const [hour, minute] = time.split(":");
  const h = parseInt(hour, 10);
  const m = parseInt(minute, 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return "15 8 * * mon-fri";
  return `${m} ${h} * * ${days}`;
}

/** @deprecated use buildScheduleCron */
export function timeToWeekdayCron(time: string): string {
  return buildScheduleCron(time, "mon-fri");
}

function formatTime12h(hour: number, minute: number): string {
  const ampm = hour >= 12 ? "PM" : "AM";
  const h12 = hour % 12 || 12;
  return `${h12}:${String(minute).padStart(2, "0")} ${ampm}`;
}

function describeDays(dow: string): string {
  const d = dow.toLowerCase();
  if (d === "*" || d === "mon-sun") return "every day";
  if (d === "mon-fri" || d === "0-4" || d === "1-5") return "Monday–Friday";
  if (d === "mon-sat" || d === "0-5" || d === "1-6") return "Monday–Saturday";
  return `days: ${dow}`;
}

export function describeSchedule(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return "Runs Monday–Friday at 8:15 AM IST";
  const [minute, hour, , , dow] = parts;
  const h = parseInt(hour, 10);
  const m = parseInt(minute, 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return "Invalid time";
  return `Runs ${describeDays(dow)} at ${formatTime12h(h, m)} IST`;
}

export function formatNextRun(iso: string | null | undefined): string {
  if (!iso) return "No upcoming run (schedule off)";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}
