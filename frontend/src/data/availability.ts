import type { Availability, AvailableSlot, Shop } from './catalog';

export function shopDate(timezone: string, now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const value = (type: string) => parts.find((p) => p.type === type)!.value;
  return `${value('year')}-${value('month')}-${value('day')}`;
}
export function addDays(date: string, count: number): string {
  const day = new Date(`${date}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() + count);
  return day.toISOString().slice(0, 10);
}
export function dateBounds(shop: Shop): { min: string; max: string } {
  const min = shopDate(shop.timezone);
  return { min, max: addDays(min, shop.booking_horizon_days) };
}
export function formatDay(date: string): string {
  return new Date(`${date}T12:00:00Z`).toLocaleDateString('en-GB', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric' });
}
export function formatWall(wall: string): string {
  return `${formatDay(wall.slice(0, 10))} · ${wall.slice(11, 16)}`;
}
export function mergeSlots(results: Availability[]): AvailableSlot[] {
  const slots = new Map<string, AvailableSlot>();
  for (const result of results) {
    for (const slot of result.available) {
      if (!slots.has(slot.starts_at)) slots.set(slot.starts_at, { ...slot, barber_id: result.barber_id, barber_name: result.barber_name });
    }
  }
  return [...slots.values()].sort((a, b) => a.starts_at.localeCompare(b.starts_at));
}
