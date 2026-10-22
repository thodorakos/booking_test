import { formatPrice, type AvailableSlot, type Service, type Shop } from '../../../data/catalog';
import { formatWall } from '../../../data/availability';

export function SummaryPanel({ service, slot, barberName, shop, busy, uncertain }: { service: Service | undefined; slot: AvailableSlot | null; barberName: string; shop: Shop; busy: boolean; uncertain: boolean }) {
  return <aside className="summary" aria-labelledby="summaryTitle">
    <h2 id="summaryTitle">Your visit</h2>
    <dl>
      <div><dt>Service</dt><dd>{service?.name || '—'}</dd></div>
      <div><dt>Barber</dt><dd>{slot?.barber_name || barberName}</dd></div>
      <div><dt>When</dt><dd>{slot ? formatWall(slot.starts_at_local) : 'Choose a time'}</dd></div>
      <div><dt>Duration</dt><dd>{service ? `${service.duration_minutes} min` : '—'}</dd></div>
    </dl>
    <div className="sum-total"><span>Total</span><strong>{service ? formatPrice(service.price_cents, shop.currency) : '—'}</strong></div>
    <p className="pay-note">Pay in the shop by card or cash.</p>
    <button className="btn btn-block" type="submit" disabled={!service || !slot || busy}>{busy ? 'Confirming…' : uncertain ? 'Retry this booking' : 'Confirm booking'}</button>
    <p className="cancel-note">Free cancellation until {shop.cancel_cutoff_hours} hours before your appointment. All times in {shop.timezone}.</p>
  </aside>;
}
