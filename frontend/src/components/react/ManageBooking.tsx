import { useEffect, useRef, useState, type SubmitEvent } from 'react';
import { api, errorMessage } from '../../data/api';
import { formatPrice, type Booking } from '../../data/catalog';
import { formatWall } from '../../data/availability';

export default function ManageBooking() {
  const [id, setId] = useState('');
  const [phone, setPhone] = useState('');
  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  useEffect(() => {
    // The reference comes from the confirmation link; customer phone stays out of the URL.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setId(new URLSearchParams(window.location.search).get('id') || '');
  }, []);
  async function lookup(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); setBooking(null);
    try { setBooking(await api<Booking>(`/bookings/${encodeURIComponent(id.trim())}?${new URLSearchParams({ phone: phone.trim() })}`)); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function cancel() {
    if (!booking || inFlight.current || !window.confirm('Cancel this appointment? This will release your chair.')) return;
    inFlight.current = true; setBusy(true); setError('');
    try { setBooking(await api<Booking>(`/bookings/${booking.id}/cancel`, { method: 'POST', body: JSON.stringify({ phone: booking.customer_phone }) })); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <div className="manage-panel">
    <form className="admin-card" onSubmit={lookup}>
      <div className="field"><label htmlFor="bookingRef">Booking reference</label><input id="bookingRef" required value={id} maxLength={36} pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" onChange={(event) => { setId(event.target.value); setBooking(null); }} /></div>
      <div className="field"><label htmlFor="ownerPhone">Phone used to book</label><input id="ownerPhone" type="tel" autoComplete="tel" required maxLength={24} value={phone} onChange={(event) => { setPhone(event.target.value); setBooking(null); }} /></div>
      <button className="btn" disabled={busy}>{busy ? 'Please wait…' : 'Find booking'}</button>
    </form>
    {error ? <p role="alert" className="form-message">{error}</p> : null}
    {booking ? <section className="admin-card" aria-labelledby="visitHeading">
      <h2 id="visitHeading">Your appointment</h2>
      <p className="status-badge" role="status">{booking.status === 'confirmed' ? 'Confirmed' : 'Cancelled'}</p>
      <p>{booking.service_name} with {booking.barber_name}</p>
      <p>{formatWall(booking.starts_at_local)} (shop time)</p>
      <p>{booking.duration_minutes} min · {formatPrice(booking.price_cents)}</p>
      {booking.cancellation_reason ? <p>{booking.cancellation_reason}</p> : null}
      {booking.status === 'confirmed' ? <button className="btn danger-button" disabled={busy} type="button" onClick={cancel}>Cancel booking</button> : null}
    </section> : null}
  </div>;
}
