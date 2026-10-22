import { useEffect, useState } from 'react';
import { api, errorMessage } from '../../data/api';
import { formatPrice, type Barber, type Service } from '../../data/catalog';
import { Icon } from './Icon';

export default function PublicCatalog({ kind }: { kind: 'services' | 'barbers' }) {
  const [items, setItems] = useState<(Barber | Service)[] | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<(Barber | Service)[]>(`/${kind}`, { signal: controller.signal }).then(setItems).catch((failure) => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    return () => controller.abort();
  }, [kind, attempt]);
  if (error) return (
    <p role="alert" className="status-note">
      {error}
      <span className="state-actions">
        <button type="button" className="text-button" onClick={() => { setItems(null); setError(''); setAttempt((value) => value + 1); }}>Retry</button>
        <a className="text-button" href="/book">Try the booking page</a>
      </span>
    </p>
  );
  if (!items) return kind === 'services'
    ? <ul className="price-list" aria-hidden="true">{[0, 1, 2, 3, 4].map((row) => <li key={row}><span className="sk sk-row" /></li>)}</ul>
    : <div className="barber-grid" aria-hidden="true">{[0, 1, 2, 3].map((row) => <div className="barber-card" key={row}><span className="sk sk-tile" /><span className="sk sk-line" style={{ width: '58%', marginTop: 14 }} /><span className="sk sk-line" style={{ width: '36%', marginTop: 8 }} /></div>)}</div>;
  if (!items.length) return <p className="status-note" role="status">No {kind} are available to book right now.</p>;
  if (kind === 'services') return <div className="price-group live-prices"><ul className="price-list">{items.map((item) => {
    const service = item as Service;
    return <li key={service.id}><a className="price-row" href={`/book?service=${service.id}`}><span className="pr-name">{service.name}</span><span className="pr-dur">{service.duration_minutes} min</span><span className="pr-price">{formatPrice(service.price_cents)}</span><span className="pr-go" aria-hidden="true"><Icon name="arrow" size={14} /></span></a></li>;
  })}</ul></div>;
  return <div className="barber-grid">{items.map((barber) => <a className="barber-card live-barber" key={barber.id} href={`/book?barber=${barber.id}`}>
    <div className="barber-initials" aria-hidden="true">{barber.name.split(' ').map((part) => part[0]).slice(0, 2).join('')}</div>
    <div className="barber-info"><h3 className="barber-name">{barber.name}</h3><span className="barber-book">Book a chair <Icon name="arrow" size={14} /></span></div>
  </a>)}</div>;
}
