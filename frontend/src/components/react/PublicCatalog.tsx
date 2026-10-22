import { useEffect, useState } from 'react';
import { api, errorMessage } from '../../data/api';
import { formatPrice, type Barber, type Service } from '../../data/catalog';
import { Icon } from './Icon';

export default function PublicCatalog({ kind }: { kind: 'services' | 'barbers' }) {
  const [items, setItems] = useState<(Barber | Service)[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api<(Barber | Service)[]>(`/${kind}`, { signal: controller.signal }).then(setItems).catch((failure) => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    return () => controller.abort();
  }, [kind]);
  if (!items) return <p role={error ? 'alert' : 'status'}>{error || `Loading ${kind}…`} {error ? <a href="/book" className="text-button">Try the booking page</a> : null}</p>;
  if (!items.length) return <p>No {kind} are available to book right now.</p>;
  if (kind === 'services') return <div className="price-group live-prices"><ul className="price-list">{items.map((item) => {
    const service = item as Service;
    return <li key={service.id}><a className="price-row" href={`/book?service=${service.id}`}><span className="pr-name">{service.name}</span><span className="pr-dur">{service.duration_minutes} min</span><span className="pr-price">{formatPrice(service.price_cents)}</span><span className="pr-go" aria-hidden="true"><Icon name="arrow" size={14} /></span></a></li>;
  })}</ul></div>;
  return <div className="barber-grid">{items.map((barber) => <a className="barber-card live-barber" key={barber.id} href={`/book?barber=${barber.id}`}>
    <div className="barber-initials" aria-hidden="true">{barber.name.split(' ').map((part) => part[0]).slice(0, 2).join('')}</div>
    <div className="barber-info"><h3 className="barber-name">{barber.name}</h3><span className="barber-book">Book a chair <Icon name="arrow" size={14} /></span></div>
  </a>)}</div>;
}
