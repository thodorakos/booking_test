import type { AvailableSlot, Shop } from '../../../data/catalog';
import { dateBounds, formatDay } from '../../../data/availability';
import { DatePicker } from './DatePicker';

interface Props {
  shop: Shop; date: string; slots: AvailableSlot[]; selected: AvailableSlot | null;
  loading: boolean; error: string; hasService: boolean;
  onDate: (date: string) => void; onSelect: (slot: AvailableSlot) => void; onRetry: () => void;
}
export function WhenStep({ shop, date, slots, selected, loading, error, hasService, onDate, onSelect, onRetry }: Props) {
  const { min, max } = dateBounds(shop);
  return <section className="step" aria-labelledby="stepWhenTitle">
    <div className="step-head"><h2 id="stepWhenTitle"><span className="step-num">3</span>Day &amp; time</h2></div>
    <div className="field">
      <label htmlFor="dateToggle">Appointment date</label>
      <DatePicker shop={shop} id="dateToggle" value={date} min={min} max={max} onSelect={onDate} />
    </div>
    <p className="step-note">All times are in {shop.timezone}. Book at least {shop.booking_lead_minutes} minutes ahead.</p>
    {error ? <p role="alert" className="form-message">{error} <button type="button" className="text-button" onClick={onRetry}>Retry availability</button></p> : null}
    <div className="slot-grid" role="radiogroup" aria-label={`Choose a time${date ? ` on ${formatDay(date)}` : ''}`} aria-busy={loading}>
      {loading ? <p className="slots-empty" role="status">Checking availability…</p> : !hasService ? <p className="slots-empty">Choose a service to see available times.</p> : !date ? <p className="slots-empty">Choose a date.</p> : !slots.length && !error ? <p className="slots-empty">No times available. Try another date or barber.</p> : slots.map((slot) => <label className="slot-opt" key={slot.starts_at}>
        <input className="control-input" type="radio" name="time" value={slot.starts_at} checked={selected?.starts_at === slot.starts_at && selected.barber_id === slot.barber_id} onChange={() => onSelect(slot)} />
        <span className="slot-in">{slot.starts_at_local.slice(11, 16)}</span>
      </label>)}
    </div>
  </section>;
}
