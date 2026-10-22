import type { Shop } from '../../../data/catalog';
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export function ShopNote({ shop }: { shop: Shop }) {
  return <div className="book-facts"><p>{DAYS.filter((_, index) => !shop.closed_weekdays.includes(index)).join(', ')} · {shop.open_time}–{shop.close_time}</p><p>{shop.timezone} · {shop.booking_horizon_days} days available to book</p></div>;
}
