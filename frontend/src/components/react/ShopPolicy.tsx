import { useEffect, useState } from 'react';
import { api, errorMessage } from '../../data/api';
import type { Shop } from '../../data/catalog';
import { ShopNote } from './booking/ShopNote';

export default function ShopPolicy() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<Shop>('/shop', { signal: controller.signal }).then(setShop).catch((failure) => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    return () => controller.abort();
  }, [attempt]);
  if (shop) return <><ShopNote shop={shop} /><p className="fineprint">Free cancellation until {shop.cancel_cutoff_hours} hours before your appointment.</p></>;
  if (error) return <p role="alert" className="status-note">{error} <span className="state-actions"><button type="button" className="text-button" onClick={() => { setShop(null); setError(''); setAttempt((value) => value + 1); }}>Retry</button></span></p>;
  return <div className="status-note" role="status" aria-label="Loading shop hours"><span className="sk sk-line" style={{ width: 168 }} /><span className="sk sk-line" style={{ width: 118, marginTop: 6 }} /></div>;
}
