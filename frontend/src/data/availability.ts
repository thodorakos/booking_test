export const DOWS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Minutes from midnight the shop is open, keyed by JS day number (0=Sun). */
export const SHOP_HOURS: Record<number, [number, number]> = {
  2: [600, 1200],
  3: [600, 1200],
  4: [600, 1200],
  5: [600, 1200],
  6: [540, 1080],
};

const BARBER_WORK: Record<string, number[]> = {
  marcus: [2, 3, 4, 5, 6],
  dario: [3, 4, 5, 6],
  june: [2, 3, 4, 5, 6],
  elias: [4, 5, 6],
};

export interface DayInfo {
  date: Date;
}

export function buildDays(count = 7): DayInfo[] {
  const base = new Date();
  base.setHours(0, 0, 0, 0);
  const days: DayInfo[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(base);
    d.setDate(base.getDate() + i);
    days.push({ date: d });
  }
  return days;
}

export function formatTime(mins: number): string {
  let h = Math.floor(mins / 60);
  const m = mins % 60;
  const ap = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, '0')} ${ap}`;
}

export function dateKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

export function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function dayLabel(i: number, days: DayInfo[]): string {
  if (i === 0) return 'Today';
  if (i === 1) return 'Tomorrow';
  const d = days[i].date;
  return `${DOWS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

export function fullDayLabel(i: number, days: DayInfo[]): string {
  return days[i].date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

export function dayEnabled(days: DayInfo[], i: number, barberId: string | null): boolean {
  const d = days[i].date;
  if (!SHOP_HOURS[d.getDay()]) return false;
  if (!barberId) return true;
  return BARBER_WORK[barberId]?.includes(d.getDay()) ?? false;
}

function hashSlot(key: string, minutes: number, barberId: string): number {
  let h = 2166136261;
  const s = `${key}-${minutes}-${barberId}`;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 100;
}

export function isSlotFree(days: DayInfo[], i: number, minutes: number, barberId: string | null): boolean {
  const d = days[i].date;
  const key = dateKey(d);
  if (barberId) {
    const work = BARBER_WORK[barberId];
    return !!work && work.includes(d.getDay()) && hashSlot(key, minutes, barberId) < 78;
  }
  return Object.entries(BARBER_WORK).some(([id, work]) => work.includes(d.getDay()) && hashSlot(key, minutes, id) < 78);
}

export interface Slot {
  minutes: number;
  label: string;
  free: boolean;
}

export function getSlots(days: DayInfo[], i: number, duration: number, barberId: string | null, now: Date): Slot[] {
  const d = days[i].date;
  const hours = SHOP_HOURS[d.getDay()];
  if (!hours || !dayEnabled(days, i, barberId)) return [];
  const today = isSameDay(d, now);
  const cutoff = today ? now.getHours() * 60 + now.getMinutes() + 60 : -1;
  const items: Slot[] = [];
  for (let m = hours[0]; m + duration <= hours[1]; m += 30) {
    if (today && m < cutoff) continue;
    items.push({ minutes: m, label: formatTime(m), free: isSlotFree(days, i, m, barberId) });
  }
  return items;
}

export function firstOpenDay(days: DayInfo[], duration: number, barberId: string | null, now: Date): number | null {
  for (let i = 0; i < days.length; i++) {
    if (dayEnabled(days, i, barberId) && getSlots(days, i, duration, barberId, now).some((x) => x.free)) return i;
  }
  for (let i = 0; i < days.length; i++) {
    if (dayEnabled(days, i, barberId)) return i;
  }
  return null;
}

export function findNextOpening(days: DayInfo[], now: Date): { date: Date; minutes: number; index: number } | null {
  for (let i = 0; i < days.length; i++) {
    const d = days[i].date;
    const hours = SHOP_HOURS[d.getDay()];
    if (!hours) continue;
    const today = isSameDay(d, now);
    const cutoff = today ? now.getHours() * 60 + now.getMinutes() + 60 : -1;
    for (let m = hours[0]; m + 45 <= hours[1]; m += 30) {
      if (today && m < cutoff) continue;
      if (isSlotFree(days, i, m, null)) return { date: d, minutes: m, index: i };
    }
  }
  return null;
}
