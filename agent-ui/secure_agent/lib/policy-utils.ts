/**
 * Client-side helpers for role policy enforcement display.
 */

export interface TimeRestriction {
  start: string;
  end: string;
}

export function isWithinTimeWindow(
  start: string | null | undefined,
  end: string | null | undefined,
  now: Date = new Date(),
): boolean {
  if (!start || !end) return true;
  const nowHhmm = `${String(now.getUTCHours()).padStart(2, "0")}:${String(now.getUTCMinutes()).padStart(2, "0")}`;
  if (start <= end) {
    return start <= nowHhmm && nowHhmm <= end;
  }
  return nowHhmm >= start || nowHhmm <= end;
}

function utcHhmmToLocalLabel(hhmm: string): string {
  const [hours, minutes] = hhmm.split(":").map(Number);
  const date = new Date();
  date.setUTCHours(hours, minutes, 0, 0);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function formatTimeWindowLocal(start: string, end: string): string {
  const utcLabel = `${start}–${end} UTC`;
  const localStart = utcHhmmToLocalLabel(start);
  const localEnd = utcHhmmToLocalLabel(end);
  const tz =
    Intl.DateTimeFormat().resolvedOptions().timeZone ??
    "local";
  return `${utcLabel} (${localStart}–${localEnd} ${tz})`;
}

export function getTimeRestriction(
  start: string | null | undefined,
  end: string | null | undefined,
): TimeRestriction | null {
  if (!start || !end) return null;
  return { start, end };
}
