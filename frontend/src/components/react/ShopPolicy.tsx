import { useEffect, useState } from 'react';
import { api, errorMessage } from '../../data/api';
import type { Shop } from '../../data/catalog';
import { ShopNote } from './booking/ShopNote';

export default function ShopPolicy() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api<Shop>('/shop', { signal: controller.signal }).then(setShop).catch((failure) => { if (!controller.signal.aborted) setError(errorMessage(failure)); });
    return () => controller.abort();
  }, []);
  return shop ? <><ShopNote shop={shop} /><p className="fineprint">Free cancellation until {shop.cancel_cutoff_hours} hours before your appointment.</p></> : <p role={error ? 'alert' : 'status'}>{error || 'Loading shop hours…'}</p>;
}
