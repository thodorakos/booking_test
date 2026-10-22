import { useEffect, useRef } from 'react';
import { formatPrice, type Booking, type Shop } from '../../../data/catalog';
import { formatWall } from '../../../data/availability';
import { Icon } from '../Icon';

export function ConfirmSheet({ booking, shop, onClose }: { booking: Booking | null; shop: Shop; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (booking) dialog.current?.showModal();
    else dialog.current?.close();
    document.body.classList.toggle('modal-open', !!booking);
    return () => document.body.classList.remove('modal-open');
  }, [booking]);
  return <dialog ref={dialog} className="sheet" aria-labelledby="sheetTitle" onClose={onClose}>
    {booking ? <>
      <button className="sheet-x" type="button" onClick={() => dialog.current?.close()} aria-label="Close confirmation"><Icon name="x" size={18} /></button>
      <div className="sheet-mark" aria-hidden="true"><Icon name="check" size={24} /></div>
      <h2 id="sheetTitle">You’re booked, {booking.customer_name.split(' ')[0]}.</h2>
      <p className="sheet-sub">Your appointment is confirmed. Save your booking reference.</p>
      <dl className="recap">
        <div><dt>Service</dt><dd>{booking.service_name} · {booking.duration_minutes} min</dd></div>
        <div><dt>Barber</dt><dd>{booking.barber_name}</dd></div>
        <div><dt>When</dt><dd>{formatWall(booking.starts_at_local)} ({shop.timezone})</dd></div>
        <div><dt>Total</dt><dd>{formatPrice(booking.price_cents, shop.currency)} · pay in shop</dd></div>
        <div><dt>Reference</dt><dd className="booking-reference">{booking.id}</dd></div>
      </dl>
      <p className="sheet-fine">Free cancellation until {shop.cancel_cutoff_hours} hours before your appointment.</p>
      <a className="btn btn-block" href={`/manage?id=${booking.id}`}>Manage this booking</a>
    </> : null}
  </dialog>;
}
