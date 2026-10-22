import { useEffect, useRef, useState, type SubmitEvent } from 'react';
import { api, ApiError, errorMessage } from '../../data/api';
import type { Availability, AvailableSlot, Barber, Booking, BookingInput, Service, Shop } from '../../data/catalog';
import { dateBounds, mergeSlots, shopDate } from '../../data/availability';
import { BarberStep } from './booking/BarberStep';
import { ServiceStep } from './booking/ServiceStep';
import { WhenStep } from './booking/WhenStep';
import { DetailsStep } from './booking/DetailsStep';
import { SummaryPanel } from './booking/SummaryPanel';
import { ShopNote } from './booking/ShopNote';
import { ConfirmSheet } from './booking/ConfirmSheet';

export default function BookingFlow() {
  const [catalog, setCatalog] = useState<{ barbers: Barber[]; services: Service[]; shop: Shop } | null>(null);
  const [serviceId, setServiceId] = useState('');
  const [barberId, setBarberId] = useState('');
  const [date, setDate] = useState('');
  const [slot, setSlot] = useState<AvailableSlot | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [availability, setAvailability] = useState<{ query: string; slots: AvailableSlot[]; error: string } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [revision, setRevision] = useState(0);
  const pending = useRef<{ key: string; payload: BookingInput } | null>(null);
  const submitting = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const query = JSON.stringify([serviceId, barberId, date, revision]);
  const current = availability?.query === query ? availability : null;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api<Barber[]>('/barbers', { signal: controller.signal }), api<Service[]>('/services', { signal: controller.signal }), api<Shop>('/shop', { signal: controller.signal })])
      .then(([barbers, services, shop]) => {
        const params = new URLSearchParams(window.location.search);
        setCatalog({ barbers, services, shop });
        setServiceId(services.find((service) => service.id === params.get('service'))?.id || '');
        setBarberId(barbers.find((barber) => barber.id === params.get('barber'))?.id || '');
        setDate(shopDate(shop.timezone));
      }).catch((failure) => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!catalog || !serviceId || !date) return;
    const bounds = dateBounds(catalog.shop);
    if (date < bounds.min || date > bounds.max) return;
    const controller = new AbortController();
    const barbers = barberId ? catalog.barbers.filter((barber) => barber.id === barberId) : catalog.barbers;
    Promise.all(barbers.map((barber) => api<Availability>(`/availability?${new URLSearchParams({ barber_id: barber.id, service_id: serviceId, date })}`, { signal: controller.signal })))
      .then((results) => { if (!controller.signal.aborted) setAvailability({ query, slots: mergeSlots(results), error: '' }); })
      .catch((failure) => { if (!controller.signal.aborted) setAvailability({ query, slots: [], error: errorMessage(failure) }); });
    return () => controller.abort();
  }, [catalog, serviceId, barberId, date, query]);

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || !slot || !serviceId) return;
    const cleanedPhone = phone.replace(/[\s\-().]/g, '');
    if (!name.trim() || !/^\+?[0-9]{6,15}$/.test(cleanedPhone)) {
      setError('Enter your name and a phone number with 6–15 digits, optionally starting with +.');
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    const payload = { barber_id: slot.barber_id, service_id: serviceId, starts_at: slot.starts_at_local, customer_name: name.trim(), customer_phone: cleanedPhone };
    if (!pending.current || JSON.stringify(pending.current.payload) !== JSON.stringify(payload)) pending.current = { key: crypto.randomUUID(), payload };
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api<Booking>('/bookings', { method: 'POST', headers: { 'Idempotency-Key': pending.current.key }, body: JSON.stringify(pending.current.payload) });
      pending.current = null;
      setUncertain(false);
      setBooking(result);
    } catch (failure) {
      const ambiguous = !(failure instanceof ApiError) || failure.status === 0 || failure.status >= 500 || failure.code === 'INVALID_RESPONSE';
      setUncertain(ambiguous);
      if (!ambiguous) pending.current = null;
      if (failure instanceof ApiError && ['SLOT_TAKEN', 'TOO_SOON', 'IN_PAST'].includes(failure.code)) { setSlot(null); setRevision((value) => value + 1); }
      setError(ambiguous ? 'We could not verify whether your booking completed. Retry this same booking to recover its confirmation safely.' : errorMessage(failure));
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally { submitting.current = false; setBusy(false); }
  }

  if (!catalog) return <div className="wrap"><p role={error ? 'alert' : 'status'} className="form-message">{error || 'Loading services and barbers…'}</p>{error ? <button className="btn" onClick={() => window.location.reload()}>Retry</button> : null}</div>;
  if (!catalog.barbers.length || !catalog.services.length) return <p className="wrap form-message" role="status">Online booking is currently unavailable. Please contact the shop.</p>;
  const locked = busy || uncertain || !!booking;
  return <form className="wrap book-grid" ref={form} onSubmit={submit}>
    <fieldset className="steps booking-fields" disabled={locked}>
      <BarberStep barbers={catalog.barbers} selected={barberId} onSelect={(id) => { setBarberId(id); setSlot(null); }} />
      <ServiceStep services={catalog.services} selected={serviceId} onSelect={(id) => { setServiceId(id); setSlot(null); }} />
      <WhenStep shop={catalog.shop} date={date} slots={current?.slots || []} selected={slot} loading={!!serviceId && !!date && !current} error={current?.error || ''} hasService={!!serviceId} onDate={(value) => { setDate(value); setSlot(null); }} onSelect={setSlot} onRetry={() => { setSlot(null); setRevision((value) => value + 1); }} />
      <DetailsStep visible={!!slot} name={name} phone={phone} onNameChange={setName} onPhoneChange={setPhone} />
    </fieldset>
    <div className="book-rail">
      {error ? <p ref={errorRef} role="alert" tabIndex={-1} className="form-message">{error}</p> : null}
      <SummaryPanel service={catalog.services.find((service) => service.id === serviceId)} slot={slot} barberName={catalog.barbers.find((barber) => barber.id === barberId)?.name || 'First available'} shop={catalog.shop} busy={busy || !!booking} uncertain={uncertain} />
      <ShopNote shop={catalog.shop} />
    </div>
    <ConfirmSheet booking={booking} shop={catalog.shop} onClose={() => { setBooking(null); setSlot(null); setRevision((value) => value + 1); form.current?.querySelector<HTMLInputElement>('input[name="service"]:checked')?.focus(); }} />
  </form>;
}
