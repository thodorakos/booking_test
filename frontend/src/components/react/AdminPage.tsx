import { useCallback, useEffect, useRef, useState, type SubmitEvent } from 'react';
import { api, ApiError, errorMessage } from '../../data/api';
import { formatPrice, type AdminBarber, type AdminService, type Booking, type Shop } from '../../data/catalog';
import { formatWall, shopDate } from '../../data/availability';

type CatalogItem = AdminBarber | AdminService;

export default function AdminPage() {
  const [key, setKey] = useState('');
  const [session, setSession] = useState<{ key: string; barbers: AdminBarber[] } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const checking = useRef(false);
  const logout = useCallback((message = '') => { setSession(null); setError(message); }, []);
  async function login(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (checking.current) return;
    checking.current = true; setBusy(true); setError('');
    try {
      const barbers = await api<AdminBarber[]>('/admin/barbers', { headers: { 'X-Admin-Key': key.trim() } });
      setSession({ key: key.trim(), barbers }); setKey('');
    } catch (failure) { setError(errorMessage(failure)); }
    finally { checking.current = false; setBusy(false); }
  }
  if (session) return <AdminWorkspace adminKey={session.key} initialBarbers={session.barbers} onLogout={logout} />;
  return <div className="admin-login admin-card">
    <h2>Shop access</h2><p>Use the shop’s admin key to manage appointments and services.</p>
    <form onSubmit={login}>
      <div className="field"><label htmlFor="adminKey">Admin key</label><input id="adminKey" type="password" autoComplete="current-password" required value={key} onChange={(event) => setKey(event.target.value)} /></div>
      {error ? <p role="alert" className="form-message">{error}</p> : null}
      <button className="btn btn-block" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
    <p className="fineprint">Your key stays in this tab’s memory. Reloading signs you out.</p>
  </div>;
}

function CatalogForm({ kind, item, disabled, onSave, onDeactivate }: {
  kind: 'barbers' | 'services'; item?: CatalogItem; disabled: boolean;
  onSave: (form: HTMLFormElement, item?: CatalogItem) => void;
  onDeactivate: (item: CatalogItem) => void;
}) {
  const id = item?.id || `new-${kind}`;
  const service = item && 'duration_minutes' in item ? item : null;
  return <form className="catalog-row" onSubmit={(event) => { event.preventDefault(); onSave(event.currentTarget, item); }}>
    <fieldset className="catalog-fields" disabled={disabled}>
      <div className="field"><label htmlFor={`name-${id}`}>Name</label><input id={`name-${id}`} name="name" required maxLength={80} defaultValue={item?.name || ''} /></div>
      {kind === 'services' ? <>
        <div className="field"><label htmlFor={`duration-${id}`}>Minutes</label><input id={`duration-${id}`} name="duration" type="number" min={5} max={240} step={1} required defaultValue={service?.duration_minutes || 30} /></div>
        <div className="field"><label htmlFor={`price-${id}`}>Price (EUR cents)</label><input id={`price-${id}`} name="price" type="number" min={0} max={2147483647} step={1} placeholder="Not specified" defaultValue={service?.price_cents ?? ''} /></div>
      </> : null}
      <label className="check-label"><input name="active" type="checkbox" defaultChecked={item?.is_active ?? true} /> Active</label>
      <button className="btn btn-sm" type="submit">{item ? 'Save' : `Add ${kind === 'barbers' ? 'barber' : 'service'}`}</button>
      {item?.is_active ? <button className="text-button danger-text" type="button" onClick={() => onDeactivate(item)}>Deactivate</button> : null}
    </fieldset>
  </form>;
}

function AdminWorkspace({ adminKey, initialBarbers, onLogout }: { adminKey: string; initialBarbers: AdminBarber[]; onLogout: (message?: string) => void }) {
  const [barbers, setBarbers] = useState(initialBarbers);
  const [services, setServices] = useState<AdminService[]>([]);
  const [shop, setShop] = useState<Shop | null>(null);
  const [filters, setFilters] = useState<{ from: string; to: string; barber: string; cancelled: boolean } | null>(null);
  const [revision, setRevision] = useState(0);
  const [calendar, setCalendar] = useState<{ query: string; bookings: Booking[]; error: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const mutating = useRef(false);
  const mounted = useRef(true);
  const query = JSON.stringify([filters, revision]);
  const current = calendar?.query === query ? calendar : null;

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    Promise.all([api<AdminService[]>('/admin/services', { headers: { 'X-Admin-Key': adminKey }, signal: controller.signal }), api<Shop>('/shop', { signal: controller.signal })])
      .then(([items, policy]) => { setServices(items); setShop(policy); const today = shopDate(policy.timezone); setFilters({ from: today, to: today, barber: '', cancelled: true }); })
      .catch((failure) => { if (!controller.signal.aborted) { if (failure instanceof ApiError && failure.status === 401) onLogout('Your admin key is no longer valid.'); else setError(errorMessage(failure)); } });
    return () => { mounted.current = false; controller.abort(); };
  }, [adminKey, onLogout]);

  useEffect(() => {
    if (!filters) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ from: filters.from, to: filters.to, include_cancelled: String(filters.cancelled) });
    if (filters.barber) params.set('barber_id', filters.barber);
    api<{ bookings: Booking[] }>(`/admin/bookings?${params}`, { headers: { 'X-Admin-Key': adminKey }, signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setCalendar({ query, bookings: result.bookings, error: '' }); })
      .catch((failure) => { if (!controller.signal.aborted) { if (failure instanceof ApiError && failure.status === 401) onLogout('Your admin key is no longer valid.'); else setCalendar({ query, bookings: [], error: errorMessage(failure) }); } });
    return () => controller.abort();
  }, [adminKey, filters, query, onLogout]);

  async function run(action: () => Promise<void>) {
    if (mutating.current) return;
    mutating.current = true; setBusy(true); setError(''); setNotice('');
    try { await action(); }
    catch (failure) {
      if (mounted.current) {
        if (failure instanceof ApiError && failure.status === 401) onLogout('Your admin key is no longer valid.');
        else setError(errorMessage(failure));
      }
    } finally { mutating.current = false; if (mounted.current) setBusy(false); }
  }
  async function saveCatalog(kind: 'barbers' | 'services', form: HTMLFormElement, item?: CatalogItem) {
    const data = new FormData(form);
    const payload = { name: String(data.get('name')).trim(), is_active: data.has('active'), ...(kind === 'services' ? { duration_minutes: Number(data.get('duration')), price_cents: data.get('price') === '' ? null : Number(data.get('price')) } : {}) };
    if (!payload.name) { setError('Enter a name.'); return; }
    await run(async () => {
      const result = await api<CatalogItem>(`/admin/${kind}${item ? `/${item.id}` : ''}`, { method: item ? 'PUT' : 'POST', headers: { 'X-Admin-Key': adminKey }, body: JSON.stringify(payload) });
      if (!mounted.current) return;
      if (kind === 'barbers') setBarbers((items) => [...items.filter((entry) => entry.id !== result.id), result as AdminBarber]);
      else setServices((items) => [...items.filter((entry) => entry.id !== result.id), result as AdminService]);
      if (!item) form.reset();
      setNotice(`${result.name} saved.`); setRevision((value) => value + 1);
    });
  }
  async function deactivate(kind: 'barbers' | 'services', item: CatalogItem) {
    if (!window.confirm(`Deactivate ${item.name}? Existing appointments will be kept.`)) return;
    await run(async () => {
      const result = await api<CatalogItem>(`/admin/${kind}/${item.id}`, { method: 'DELETE', headers: { 'X-Admin-Key': adminKey } });
      if (!mounted.current) return;
      if (kind === 'barbers') setBarbers((items) => items.map((entry) => entry.id === result.id ? result as AdminBarber : entry));
      else setServices((items) => items.map((entry) => entry.id === result.id ? result as AdminService : entry));
      setNotice(`${item.name} deactivated. Existing appointments are preserved.`);
    });
  }
  async function cancelBooking(event: SubmitEvent<HTMLFormElement>, booking: Booking) {
    event.preventDefault();
    const form = event.currentTarget;
    const reason = String(new FormData(form).get('reason') || '').trim();
    if (!window.confirm(`Cancel ${booking.customer_name}’s appointment on ${formatWall(booking.starts_at_local)}?`)) return;
    await run(async () => {
      await api<Booking>(`/admin/bookings/${booking.id}/cancel`, { method: 'POST', headers: { 'X-Admin-Key': adminKey }, body: JSON.stringify({ reason: reason || null }) });
      if (!mounted.current) return;
      setNotice('Appointment cancelled.'); setRevision((value) => value + 1);
    });
  }
  return <div className="admin-workspace">
    <div className="admin-toolbar"><p>{shop ? `Shop time · ${shop.timezone}` : 'Loading shop settings…'}</p><button className="btn btn-sm" type="button" onClick={() => onLogout()}>Sign out</button></div>
    {error ? <p role="alert" className="form-message">{error}</p> : null}
    {notice ? <p role="status" className="form-message">{notice}</p> : null}
    <section className="admin-card" aria-labelledby="appointmentsTitle">
      <div className="admin-section-head"><h2 id="appointmentsTitle">Appointments</h2><button className="text-button" disabled={busy || !filters} type="button" onClick={() => setRevision((value) => value + 1)}>Refresh</button></div>
      {filters ? <form className="admin-filters" onSubmit={(event) => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        setFilters({ from: String(data.get('from')), to: String(data.get('to')), barber: String(data.get('barber')), cancelled: data.has('cancelled') });
      }}>
        <div className="field"><label htmlFor="fromDate">From</label><input id="fromDate" type="date" name="from" required defaultValue={filters.from} /></div>
        <div className="field"><label htmlFor="toDate">To</label><input id="toDate" type="date" name="to" required defaultValue={filters.to} /></div>
        <div className="field"><label htmlFor="barberFilter">Barber</label><select id="barberFilter" name="barber"><option value="">All barbers</option>{barbers.map((barber) => <option key={barber.id} value={barber.id}>{barber.name}{barber.is_active ? '' : ' (inactive)'}</option>)}</select></div>
        <label className="check-label"><input type="checkbox" name="cancelled" defaultChecked /> Include cancelled</label>
        <button className="btn btn-sm" disabled={busy}>Apply filters</button>
      </form> : null}
      <p className="fineprint">Date ranges can span up to 31 days. Inactive barbers remain in historical appointments.</p>
      {!current ? <p role="status">Loading appointments…</p> : current.error ? <p role="alert" className="form-message">{current.error} Use Refresh to retry.</p> : <>
        <p className="admin-count" role="status">{current.bookings.length} appointment{current.bookings.length === 1 ? '' : 's'}</p>
        {!current.bookings.length ? <p>No appointments in this range.</p> : <div className="appointment-list">{current.bookings.map((booking) => <article className="appointment" key={booking.id}>
          <div className="appointment-main"><span className="status-badge">{booking.status}</span><h3>{booking.customer_name}</h3><p>{formatWall(booking.starts_at_local)}–{booking.ends_at_local.slice(11, 16)}</p><p>{booking.service_name} · {booking.barber_name} · {formatPrice(booking.price_cents)}</p><a className="text-button" href={`tel:${booking.customer_phone}`}>{booking.customer_phone}</a><p className="booking-reference">{booking.id}</p>{booking.notes ? <p>{booking.notes}</p> : null}{booking.cancellation_reason ? <p>Cancellation: {booking.cancellation_reason}</p> : null}</div>
          {booking.status === 'confirmed' ? <form className="cancel-form" onSubmit={(event) => cancelBooking(event, booking)}><div className="field"><label htmlFor={`reason-${booking.id}`}>Cancellation reason (optional)</label><input id={`reason-${booking.id}`} name="reason" maxLength={200} /></div><button className="text-button danger-text" disabled={busy}>Cancel appointment</button></form> : null}
        </article>)}</div>}
      </>}
    </section>
    <div className="admin-catalog">
      <section className="admin-card" aria-labelledby="barbersTitle"><h2 id="barbersTitle">Barbers</h2><p className="fineprint">Deactivate a barber to stop new bookings. Save with Active checked to restore them.</p>
        {barbers.map((item) => <CatalogForm key={JSON.stringify(item)} kind="barbers" item={item} disabled={busy} onSave={(form, entry) => saveCatalog('barbers', form, entry)} onDeactivate={(entry) => deactivate('barbers', entry)} />)}
        <h3 className="catalog-add-title">New barber</h3><CatalogForm kind="barbers" disabled={busy || !shop} onSave={(form) => saveCatalog('barbers', form)} onDeactivate={() => {}} />
      </section>
      <section className="admin-card" aria-labelledby="servicesTitle"><h2 id="servicesTitle">Services</h2><p className="fineprint">Prices are in EUR cents (1500 = €15). Leave blank for no listed price. Existing bookings keep their agreed price and duration.</p>
        {services.map((item) => <CatalogForm key={JSON.stringify(item)} kind="services" item={item} disabled={busy} onSave={(form, entry) => saveCatalog('services', form, entry)} onDeactivate={(entry) => deactivate('services', entry)} />)}
        <h3 className="catalog-add-title">New service</h3><CatalogForm kind="services" disabled={busy || !shop} onSave={(form) => saveCatalog('services', form)} onDeactivate={() => {}} />
      </section>
    </div>
  </div>;
}
