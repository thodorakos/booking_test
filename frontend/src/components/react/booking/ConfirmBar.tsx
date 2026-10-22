import { formatPrice, type AvailableSlot, type Service, type Shop } from '../../../data/catalog';
import { formatWall } from '../../../data/availability';

export function ConfirmBar({ service, slot, shop, busy, uncertain }: { service: Service | undefined; slot: AvailableSlot | null; shop: Shop; busy: boolean; uncertain: boolean }) {
  const ready = !!(service && slot);
  return <div className="confirm-bar">
    <div className="confirm-bar-info">
      <strong>{service ? formatPrice(service.price_cents, shop.currency) : '—'}</strong>
      <span>{slot ? formatWall(slot.starts_at_local) : 'No time selected'}</span>
    </div>
    <button className="btn" type="submit" disabled={!ready || busy}>{busy ? 'Confirming…' : uncertain ? 'Retry booking' : 'Confirm booking'}</button>
  </div>;
}
